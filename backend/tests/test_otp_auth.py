import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import HTTPException
import pytest
from pydantic import ValidationError
from supabase_auth.errors import AuthApiError

from app.api import auth_routes
from app.models.user import AccountStatus, UserRole
from app.schemas.auth import OtpRequest, OtpVerifyRequest, ResendConfirmationRequest


def _request():
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))


class ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values

    def unique(self):
        return self

    def first(self):
        return self.values[0] if self.values else None


class FakeDB:
    def __init__(self, scalar_values=None):
        self.added = []
        self.committed = 0
        self._scalar_values = list(scalar_values or [])

    def scalars(self, _query):
        if self._scalar_values:
            return ScalarResult(self._scalar_values.pop(0))
        return ScalarResult([])

    def scalar(self, _query):
        if self._scalar_values:
            return self._scalar_values.pop(0)
        return None

    def add(self, value):
        self.added.append(value)

    def flush(self):
        pass

    def commit(self):
        self.committed += 1

    def refresh(self, _value):
        pass

    def get(self, _model, _key):
        return None


def test_otp_token_schema_validation():
    # Valid 6-digit code
    req = OtpVerifyRequest(email="student@rvce.edu.in", token="123456")
    assert req.token == "123456"

    # Whitespace stripped
    req_trimmed = OtpVerifyRequest(email="student@rvce.edu.in", token=" 654321 ")
    assert req_trimmed.token == "654321"

    # Too short
    with pytest.raises(ValidationError):
        OtpVerifyRequest(email="student@rvce.edu.in", token="12345")

    # Alpha characters
    with pytest.raises(ValidationError):
        OtpVerifyRequest(email="student@rvce.edu.in", token="12345a")

    # Too long
    with pytest.raises(ValidationError):
        OtpVerifyRequest(email="student@rvce.edu.in", token="1234567")


def test_mask_email_utility():
    assert auth_routes.mask_email("student@rvce.edu.in") == "s*****@rvce.edu.in"
    assert auth_routes.mask_email("ab@rvce.edu.in") == "a*@rvce.edu.in"
    assert auth_routes.mask_email("a@rvce.edu.in") == "*@rvce.edu.in"
    assert auth_routes.mask_email("professor.name@rvce.edu.in") == "p*****@rvce.edu.in"


def test_valid_otp_request_for_registered_student(monkeypatch):
    calls = []

    class FakeAuth:
        def sign_in_with_otp(self, credentials):
            calls.append(credentials)
            return SimpleNamespace(message_id="msg-123")

    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
    )
    db = FakeDB([[user]])

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    response = auth_routes.request_otp(
        OtpRequest(email="student@rvce.edu.in"),
        _request(),
        db,
    )

    assert len(calls) == 1
    assert calls[0]["email"] == "student@rvce.edu.in"
    assert calls[0]["options"]["should_create_user"] is False
    assert response["message"] == "Verification code sent"
    assert response["email"] == "s*****@rvce.edu.in"


def test_valid_otp_request_for_registered_admin(monkeypatch):
    calls = []

    class FakeAuth:
        def sign_in_with_otp(self, credentials):
            calls.append(credentials)
            return SimpleNamespace(message_id="msg-admin-123")

    admin_user = SimpleNamespace(
        id=uuid.uuid4(),
        email="admin@gmail.com",
        role=UserRole.ADMIN_FACULTY,
        account_status=AccountStatus.ACTIVE,
    )
    # First query for admin check in domain validation, second query for user lookup
    db = FakeDB([[admin_user], [admin_user]])

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    response = auth_routes.request_otp(
        OtpRequest(email="admin@gmail.com"),
        _request(),
        db,
    )

    assert len(calls) == 1
    assert calls[0]["email"] == "admin@gmail.com"
    assert calls[0]["options"]["should_create_user"] is False
    assert response["message"] == "Verification code sent"
    assert response["email"] == "a*****@gmail.com"


def test_non_college_email_rejected_for_student_otp_request(monkeypatch):
    # Non-rvce email that is not an existing admin
    db = FakeDB([[]])
    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc:
        auth_routes.request_otp(
            OtpRequest(email="stranger@gmail.com"),
            _request(),
            db,
        )

    assert exc.value.status_code == 400
    assert "Student email must end with @rvce.edu.in" in exc.value.detail


def test_unregistered_student_account_does_not_call_supabase_otp(monkeypatch):
    calls = []

    class FakeAuth:
        def sign_in_with_otp(self, credentials):
            calls.append(credentials)

    db = FakeDB([[]])  # No user found
    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    response = auth_routes.request_otp(
        OtpRequest(email="unknown@rvce.edu.in"),
        _request(),
        db,
    )

    # Must NOT call Supabase to create an account
    assert len(calls) == 0
    # Must prevent account enumeration by returning generic message
    assert "If an eligible account exists" in response["message"]
    assert response["email"] == "u*****@rvce.edu.in"


def test_inactive_account_rejected_on_otp_request(monkeypatch):
    inactive_user = SimpleNamespace(
        id=uuid.uuid4(),
        email="inactive@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.INACTIVE,
    )
    db = FakeDB([[inactive_user]])
    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc:
        auth_routes.request_otp(
            OtpRequest(email="inactive@rvce.edu.in"),
            _request(),
            db,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Account is inactive"


def test_otp_request_handles_rate_limits(monkeypatch):
    def fake_rate_limit(key, limit=3, window_seconds=300):
        if "otp-request:" in key:
            raise HTTPException(status_code=429, detail="Too many requests; try again later")

    monkeypatch.setattr(auth_routes, "rate_limit", fake_rate_limit)

    with pytest.raises(HTTPException) as exc:
        auth_routes.request_otp(
            OtpRequest(email="student@rvce.edu.in"),
            _request(),
            FakeDB(),
        )

    assert exc.value.status_code == 429


def test_otp_request_handles_supabase_email_rate_limit(monkeypatch):
    class FakeAuth:
        def sign_in_with_otp(self, _credentials):
            raise AuthApiError("email rate limit exceeded", 429, "over_email_send_rate_limit")

    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
    )
    db = FakeDB([[user]])
    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    with pytest.raises(HTTPException) as exc:
        auth_routes.request_otp(
            OtpRequest(email="student@rvce.edu.in"),
            _request(),
            db,
        )

    assert exc.value.status_code == 429
    assert "rate limited" in exc.value.detail.lower()


def test_otp_request_handles_supabase_outage(monkeypatch):
    class FakeAuth:
        def sign_in_with_otp(self, _credentials):
            raise RuntimeError("Supabase connection failed")

    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
    )
    db = FakeDB([[user]])
    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    with pytest.raises(HTTPException) as exc:
        auth_routes.request_otp(
            OtpRequest(email="student@rvce.edu.in"),
            _request(),
            db,
        )

    assert exc.value.status_code == 503
    assert "temporarily unavailable" in exc.value.detail


def test_valid_otp_verification_creates_session_and_syncs_user(monkeypatch):
    calls = []
    user_id = uuid.uuid4()

    class FakeAuth:
        def verify_otp(self, params):
            calls.append(params)
            return SimpleNamespace(
                session=SimpleNamespace(access_token="otp-access-token", refresh_token="otp-refresh-token"),
                user=SimpleNamespace(id=str(user_id), email="student@rvce.edu.in", email_confirmed_at="yes"),
            )

    user = SimpleNamespace(
        id=user_id,
        email="student@rvce.edu.in",
        full_name="Student",
        role=UserRole.STUDENT,
        email_verified=False,
        last_login_at=None,
    )
    db = FakeDB([[]])

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda db, token: (user, None))

    result = auth_routes.verify_otp(
        OtpVerifyRequest(email="student@rvce.edu.in", token="123456"),
        _request(),
        db,
    )

    assert len(calls) == 1
    assert calls[0]["email"] == "student@rvce.edu.in"
    assert calls[0]["token"] == "123456"
    assert calls[0]["type"] == "email"
    assert result["access_token"] == "otp-access-token"
    assert result["profile"]["role"] == "STUDENT"
    assert user.email_verified is True
    assert user.last_login_at is not None


def test_invalid_otp_verification_rejected(monkeypatch):
    class FakeAuth:
        def verify_otp(self, _params):
            raise AuthApiError("Token has expired or is invalid", 400, "otp_expired")

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    with pytest.raises(HTTPException) as exc:
        auth_routes.verify_otp(
            OtpVerifyRequest(email="student@rvce.edu.in", token="000000"),
            _request(),
            FakeDB(),
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid or expired verification code"


def test_expired_or_reused_otp_rejected(monkeypatch):
    class FakeAuth:
        def verify_otp(self, _params):
            raise AuthApiError("Token has expired or is invalid", 401, "bad_jwt")

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    with pytest.raises(HTTPException) as exc:
        auth_routes.verify_otp(
            OtpVerifyRequest(email="student@rvce.edu.in", token="999999"),
            _request(),
            FakeDB(),
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid or expired verification code"


def test_otp_verify_supabase_outage(monkeypatch):
    class FakeAuth:
        def verify_otp(self, _params):
            raise RuntimeError("Database unavailable")

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    with pytest.raises(HTTPException) as exc:
        auth_routes.verify_otp(
            OtpVerifyRequest(email="student@rvce.edu.in", token="123456"),
            _request(),
            FakeDB(),
        )

    assert exc.value.status_code == 503
    assert "temporarily unavailable" in exc.value.detail


def test_authenticated_user_without_pyqverse_record_rejected_with_403(monkeypatch):
    class FakeAuth:
        def verify_otp(self, _params):
            return SimpleNamespace(
                session=SimpleNamespace(access_token="valid-token", refresh_token="valid-refresh"),
                user=SimpleNamespace(id=str(uuid.uuid4()), email="orphan@rvce.edu.in", email_confirmed_at="yes"),
            )

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )
    def fail_sync(db, token):
        raise HTTPException(status_code=403, detail="Profile not found. Complete registration first.")
    monkeypatch.setattr(auth_routes, "synchronized_user", fail_sync)

    with pytest.raises(HTTPException) as exc:
        auth_routes.verify_otp(
            OtpVerifyRequest(email="orphan@rvce.edu.in", token="123456"),
            _request(),
            FakeDB(),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Profile not found. Complete registration first."


def test_admin_faculty_otp_verification_routes_to_admin(monkeypatch):
    user_id = uuid.uuid4()

    class FakeAuth:
        def verify_otp(self, _params):
            return SimpleNamespace(
                session=SimpleNamespace(access_token="admin-token", refresh_token="admin-refresh"),
                user=SimpleNamespace(id=str(user_id), email="admin@rvce.edu.in", email_confirmed_at="yes"),
            )

    admin_user = SimpleNamespace(
        id=user_id,
        email="admin@rvce.edu.in",
        full_name="Admin Faculty",
        role=UserRole.ADMIN_FACULTY,
        email_verified=True,
        last_login_at=None,
    )
    db = FakeDB([[]])

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda db, token: (admin_user, None))

    result = auth_routes.verify_otp(
        OtpVerifyRequest(email="admin@rvce.edu.in", token="123456"),
        _request(),
        db,
    )

    assert result["profile"]["role"] == "ADMIN_FACULTY"


def test_otp_verify_supports_signup_token_type(monkeypatch):
    """Verifies that an OTP code delivered during registration (type: signup) can be verified."""
    calls = []
    user_id = uuid.uuid4()

    class FakeAuth:
        def verify_otp(self, params):
            calls.append(params["type"])
            # type 'email' fails, type 'signup' succeeds
            if params["type"] == "email":
                raise AuthApiError("Token has expired or is invalid", 400, "otp_expired")
            return SimpleNamespace(
                session=SimpleNamespace(access_token="signup-session-token", refresh_token="signup-refresh"),
                user=SimpleNamespace(id=str(user_id), email="student@rvce.edu.in", email_confirmed_at="yes"),
            )

    student_user = SimpleNamespace(
        id=user_id,
        email="student@rvce.edu.in",
        full_name="Student User",
        role=UserRole.STUDENT,
        email_verified=False,
        last_login_at=None,
    )
    db = FakeDB([[]])

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda db, token: (student_user, None))

    result = auth_routes.verify_otp(
        OtpVerifyRequest(email="student@rvce.edu.in", token="123456"),
        _request(),
        db,
    )

    assert calls == ["email", "signup"]
    assert result["access_token"] == "signup-session-token"
    assert student_user.email_verified is True


def test_resend_confirmation_for_unverified_student(monkeypatch):
    calls = []

    class FakeAuth:
        def resend(self, params):
            calls.append(params)
            return SimpleNamespace(message_id="resend-123")

    student_user = SimpleNamespace(
        id=uuid.uuid4(),
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        email_verified=False,
        account_status=AccountStatus.ACTIVE,
    )
    db = FakeDB([[student_user]])

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    result = auth_routes.resend_confirmation(
        ResendConfirmationRequest(email="student@rvce.edu.in"),
        _request(),
        db,
    )

    assert len(calls) == 1
    assert calls[0]["email"] == "student@rvce.edu.in"
    assert calls[0]["type"] == "signup"
    assert "sent" in result["message"].lower()


def test_resend_confirmation_for_already_verified_student(monkeypatch):
    student_user = SimpleNamespace(
        id=uuid.uuid4(),
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        email_verified=True,
        account_status=AccountStatus.ACTIVE,
    )
    db = FakeDB([[student_user]])
    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)

    result = auth_routes.resend_confirmation(
        ResendConfirmationRequest(email="student@rvce.edu.in"),
        _request(),
        db,
    )

    assert "already verified" in result["message"].lower()


def test_resend_confirmation_rejects_non_rvce_email():
    with pytest.raises(HTTPException) as exc:
        auth_routes.resend_confirmation(
            ResendConfirmationRequest(email="outsider@gmail.com"),
            _request(),
            FakeDB(),
        )
    assert exc.value.status_code == 400
    assert "Student email must end with @rvce.edu.in" in exc.value.detail


def test_resend_confirmation_handles_rate_limits(monkeypatch):
    class FakeAuth:
        def resend(self, _params):
            raise AuthApiError("email rate limit exceeded", 429, "over_email_send_rate_limit")

    student_user = SimpleNamespace(
        id=uuid.uuid4(),
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        email_verified=False,
        account_status=AccountStatus.ACTIVE,
    )
    db = FakeDB([[student_user]])
    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    with pytest.raises(HTTPException) as exc:
        auth_routes.resend_confirmation(
            ResendConfirmationRequest(email="student@rvce.edu.in"),
            _request(),
            db,
        )

    assert exc.value.status_code == 429
    assert "rate limited" in exc.value.detail.lower()
