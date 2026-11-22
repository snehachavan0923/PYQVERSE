import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import HTTPException
import pytest
from pydantic import ValidationError
from supabase_auth.errors import AuthApiError

from app.api import auth_routes
from app.core.config import settings
from app.core.security import (
    bearer_token,
    create_supabase_anon_client,
    create_supabase_service_client,
    log_supabase_auth_error,
    normalize_admin_email,
    registration_error_response,
    validate_password_strength,
    validate_student_email,
)
from app.models.user import AccountStatus, UserRole
from app.schemas.auth import LoginRequest, PasswordResetRequest, RegisterRequest
from app.services.admin_provisioning import ProvisioningError, provision_admin
from app.services.auth import require_role, supabase_user, synchronized_user


def _request():
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))


class ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values

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

    def execute(self, _query, _params=None):
        pass

    def commit(self):
        self.committed += 1

    def refresh(self, _value):
        pass

    def get(self, _model, _key):
        return None


def test_valid_rvce_email():
    assert validate_student_email("Student.Name@rvce.edu.in") == "student.name@rvce.edu.in"


@pytest.mark.parametrize("email", [
    "student@gmail.com",
    "student@rvce.edu.in.example.com",
    "student@rvce.edu.ind",
    "student@RVCE.EDU.INX",
])
def test_non_rvce_email_rejected(email):
    with pytest.raises(HTTPException) as exc:
        validate_student_email(email)
    assert exc.value.status_code == 400


def test_personal_admin_email_allowed():
    assert normalize_admin_email(" Admin.Person@gmail.com ") == "admin.person@gmail.com"


def test_admin_bootstrap_accepts_valid_non_rvce_domains():
    assert normalize_admin_email("admin@yahoo.com") == "admin@yahoo.com"
    assert normalize_admin_email("admin@alumni.example.edu") == "admin@alumni.example.edu"


def test_admin_bootstrap_rejects_malformed_email():
    with pytest.raises(HTTPException) as exc:
        normalize_admin_email("not-an-email")
    assert exc.value.status_code == 400


def test_supabase_placeholder_configuration_returns_service_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://YOUR_PROJECT_REF.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", "YOUR_SUPABASE_ANON_KEY")
    with pytest.raises(HTTPException) as exc:
        create_supabase_anon_client()
    assert exc.value.status_code == 503


def test_service_role_placeholder_configuration_returns_service_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://YOUR_PROJECT_REF.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "YOUR_SUPABASE_SERVICE_ROLE_KEY")

    with pytest.raises(HTTPException) as exc:
        create_supabase_service_client()

    assert exc.value.status_code == 503


def test_password_strength_policy():
    assert validate_password_strength("StrongPass1") == "StrongPass1"
    for weak in ("short1A", "alllowercase1", "ALLUPPERCASE1", "NoNumbersHere"):
        with pytest.raises(HTTPException):
            validate_password_strength(weak)


def test_public_registration_validates_password_and_confirmation():
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="student@rvce.edu.in",
            password="weakpassword",
            confirm_password="weakpassword",
            full_name="Student",
        )
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="student@rvce.edu.in",
            password="StrongPass1",
            confirm_password="DifferentPass1",
            full_name="Student",
        )


def test_public_registration_rejects_role_escalation():
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="student@rvce.edu.in",
            password="StrongPass1",
            confirm_password="StrongPass1",
            full_name="Student",
            role="ADMIN_FACULTY",
        )


def test_supabase_signup_error_is_logged_safely(caplog):
    error = AuthApiError(
        "User already registered for admin.person@gmail.com with password: hidden and token: eyJabc.def.ghi",
        422,
        "user_already_exists",
    )
    response = registration_error_response(error)
    assert response.status_code == 409
    log_supabase_auth_error("signup-test", error)
    assert "user_already_exists" in caplog.text
    assert "422" in caplog.text
    assert "[redacted-email]" in caplog.text
    assert "hidden" not in caplog.text
    assert "eyJabc.def.ghi" not in caplog.text
    assert "admin.person@gmail.com" not in caplog.text


def test_public_registration_creates_only_student_role(monkeypatch):
    user_id = uuid.uuid4()

    class FakeAuth:
        def sign_up(self, credentials):
            assert credentials["email"] == "student@rvce.edu.in"
            assert credentials["password"] == "StrongPass1"
            return SimpleNamespace(
                user=SimpleNamespace(id=str(user_id), email_confirmed_at=None),
                session=None,
            )

    db = FakeDB()
    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    result = auth_routes.register(
        RegisterRequest(
            email="student@rvce.edu.in",
            password="StrongPass1",
            confirm_password="StrongPass1",
            full_name="Student",
        ),
        _request(),
        db,
    )

    assert len(db.added) == 1
    assert db.added[0].role == UserRole.STUDENT
    assert result["email_verification_pending"] is True
    assert result["profile"]["role"] == "STUDENT"


def test_password_login_uses_sign_in_with_password(monkeypatch):
    calls = []
    user_id = uuid.uuid4()

    class FakeAuth:
        def sign_in_with_password(self, credentials):
            calls.append(credentials)
            return SimpleNamespace(
                session=SimpleNamespace(access_token="access-token", refresh_token="refresh-token"),
                user=SimpleNamespace(id=str(user_id), email="student@rvce.edu.in", email_confirmed_at="yes"),
            )

    user = SimpleNamespace(
        id=user_id,
        email="student@rvce.edu.in",
        full_name="Student",
        role=UserRole.STUDENT,
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

    result = auth_routes.login(
        LoginRequest(email="student@rvce.edu.in", password="StrongPass1"),
        _request(),
        db,
    )

    assert calls == [{"email": "student@rvce.edu.in", "password": "StrongPass1"}]
    assert result["access_token"] == "access-token"
    assert result["profile"]["role"] == "STUDENT"
    assert user.last_login_at is not None


def test_invalid_password_is_rejected(monkeypatch):
    class FakeAuth:
        def sign_in_with_password(self, credentials):
            raise AuthApiError("Invalid login credentials", 400, "invalid_credentials")

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    with pytest.raises(HTTPException) as exc:
        auth_routes.login(
            LoginRequest(email="student@rvce.edu.in", password="WrongPass1"),
            _request(),
            FakeDB(),
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid email or password"


def test_unverified_password_login_is_rejected_with_confirmation_message(monkeypatch):
    class FakeAuth:
        def sign_in_with_password(self, credentials):
            raise AuthApiError("Email not confirmed", 400, "email_not_confirmed")

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    with pytest.raises(HTTPException) as exc:
        auth_routes.login(
            LoginRequest(email="student@rvce.edu.in", password="StrongPass1"),
            _request(),
            FakeDB(),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Please confirm your email before signing in."


def test_unverified_email_is_rejected_during_identity_sync(monkeypatch):
    user_id = uuid.uuid4()
    local_user = SimpleNamespace(
        id=user_id,
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
    )

    class FakeAuth:
        def get_user(self, _token):
            return SimpleNamespace(user=SimpleNamespace(
                id=str(user_id),
                email="student@rvce.edu.in",
                email_confirmed_at=None,
            ))

    monkeypatch.setattr(
        "app.services.auth.create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )
    with pytest.raises(HTTPException) as exc:
        synchronized_user(FakeDB([[local_user]]), "token")
    assert exc.value.status_code == 403
    assert "Email verification" in exc.value.detail


def test_password_reset_request_uses_supabase_recovery(monkeypatch):
    calls = []

    class FakeAuth:
        def reset_password_for_email(self, email, options):
            calls.append((email, options))

    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    result = auth_routes.request_password_reset(
        PasswordResetRequest(email="Admin.Person@example.com"),
        _request(),
    )

    assert calls == [("admin.person@example.com", {"redirect_to": f"{settings.FRONTEND_URL.rstrip('/')}/reset-password"})]
    assert "If an account exists" in result["message"]


def test_logout_calls_supabase_admin_sign_out(monkeypatch):
    calls = []

    class FakeAdmin:
        def sign_out(self, token):
            calls.append(token)

    class FakeAuth:
        admin = FakeAdmin()

    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    assert auth_routes.logout("access-token") == {"message": "Logged out"}
    assert calls == ["access-token"]


def test_bearer_token_validation():
    assert bearer_token("Bearer token-value") == "token-value"
    with pytest.raises(HTTPException) as missing:
        bearer_token(None)
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException):
        bearer_token("Token token-value")
    with pytest.raises(HTTPException):
        bearer_token("Bearer")


def test_student_cannot_access_admin_role():
    student = SimpleNamespace(role=UserRole.STUDENT)
    with pytest.raises(HTTPException) as exc:
        require_role(student, UserRole.ADMIN_FACULTY)
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    ("message", "code"),
    [("Invalid JWT", "bad_jwt"), ("JWT expired", "token_expired")],
)
def test_invalid_or_expired_supabase_jwt_is_rejected(monkeypatch, message, code):
    class FakeAuth:
        def get_user(self, token):
            assert token == "untrusted-token"
            raise AuthApiError(message, 401, code)

    monkeypatch.setattr(
        "app.services.auth.create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    with pytest.raises(HTTPException) as exc:
        supabase_user("untrusted-token")

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid or expired session"


def test_service_role_key_is_not_in_frontend_source():
    frontend_source = Path(__file__).resolve().parents[2] / "frontend" / "src"
    source_text = "\n".join(path.read_text() for path in frontend_source.rglob("*") if path.is_file())
    assert "SUPABASE_SERVICE_ROLE_KEY" not in source_text
    assert "VITE_SUPABASE_SERVICE_ROLE_KEY" not in source_text


def test_admin_dashboard_uses_real_count_queries(monkeypatch):
    admin = SimpleNamespace(
        id=uuid.uuid4(),
        email="admin@example.com",
        full_name="Admin",
        role=UserRole.ADMIN_FACULTY,
    )
    db = FakeDB()
    db.scalar = MagicMock(side_effect=[8, 1, 1, 1, 5, 1, 2, 3, 0])
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda db, token: (admin, None))

    result = auth_routes.admin_dashboard("token", db)

    assert result["catalog_overview"] == {
        "subjects": 8,
        "semesters": 1,
        "branches": 1,
        "academic_schemes": 1,
    }
    assert result["user_overview"] == {"students": 5, "administrators": 1}
    assert result["document_overview"] == {
        "uploaded_documents": 2,
        "pyqs": 3,
        "pending_reviews": 0,
    }


def test_student_dashboard_empty_state(monkeypatch):
    student = SimpleNamespace(id=uuid.uuid4(), role=UserRole.STUDENT)
    profile = SimpleNamespace(
        id=uuid.uuid4(),
        student_name="Student",
        usn=None,
        branch_id=None,
        academic_scheme_id=None,
        current_semester_id=None,
        selected_elective_id=None,
        enrollment_year=None,
        profile_completed=True,
    )
    db = MagicMock()
    db.scalars.side_effect = [ScalarResult([profile]), ScalarResult([])]
    db.get.return_value = None
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda db, token: (student, None))

    result = auth_routes.student_dashboard("token", db)

    assert result["subjects"] == []
    assert result["academic_overview"]["enrolled_subjects"] == 0
    assert result["academic_overview"]["learning_resources_available"] is False


def test_subject_summary_uses_actual_syllabus_and_pyq_rows():
    profile = SimpleNamespace(id=uuid.uuid4())
    semester = SimpleNamespace(id=uuid.uuid4(), name="Semester III", number=3)
    subject = SimpleNamespace(
        id=uuid.uuid4(),
        code="CS101",
        name="Data Structures",
        subject_type="CORE",
        credits=4,
        semester_id=semester.id,
        active=True,
    )
    enrollment = SimpleNamespace(subject_id=subject.id)

    class SummaryDB:
        def __init__(self):
            self.scalars_queue = [
                [enrollment],
                [subject],
                [subject.id],
                [semester],
            ]

        def scalars(self, _query):
            return ScalarResult(self.scalars_queue.pop(0))

        def execute(self, _query):
            return SimpleNamespace(all=lambda: [(subject.id, 2)])

    summaries = auth_routes._subject_summaries(SummaryDB(), profile)

    assert summaries == [{
        "id": str(subject.id),
        "code": "CS101",
        "name": "Data Structures",
        "subject_type": "CORE",
        "credits": 4,
        "semester": "Semester III",
        "semester_number": 3,
        "syllabus_available": True,
        "pyq_count": 2,
        "pyq_available": True,
        "learning_resources_available": False,
        "learning_resource_count": 0,
    }]


def test_admin_user_list_is_paginated_and_has_no_secrets(monkeypatch):
    admin = SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN_FACULTY)
    created = datetime(2026, 1, 1, 12, 0, 0)
    user = SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Student One",
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
        created_at=created,
        last_login_at=None,
    )
    profile = SimpleNamespace(
        usn="1RV22CS001",
        profile_completed=True,
        branch_id=None,
        current_semester_id=None,
    )
    db = MagicMock()
    db.scalar.return_value = 1
    db.scalars.side_effect = [ScalarResult([user]), ScalarResult([profile])]
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda db, token: (admin, None))

    result = auth_routes.admin_users("token", db, page=1, page_size=20, role=None, search=None)

    assert result["total"] == 1
    assert result["pages"] == 1
    assert result["items"][0]["email"] == "student@rvce.edu.in"
    assert "password" not in result["items"][0]


def _provisioning_db(existing_admins, local_user=None):
    db = FakeDB([existing_admins, [local_user] if local_user else [], []])
    return db


def test_admin_provisioning_creates_linked_admin():
    auth_id = uuid.uuid4()

    class FakeAdmin:
        def create_user(self, payload):
            assert payload["email"] == "admin@example.com"
            assert payload["email_confirm"] is True
            return SimpleNamespace(user=SimpleNamespace(id=str(auth_id)))

    client = SimpleNamespace(auth=SimpleNamespace(admin=FakeAdmin()))
    db = _provisioning_db([])

    result = provision_admin(
        db,
        client,
        email="Admin@Example.com",
        full_name="Admin Person",
        password="StrongPass1",
    )

    assert result["status"] == "created"
    assert result["role"] == "ADMIN_FACULTY"
    assert result["email"] == "admin@example.com"
    created = next(item for item in db.added if getattr(item, "email", None) == "admin@example.com")
    assert created.role == UserRole.ADMIN_FACULTY
    assert created.supabase_auth_id == auth_id
    assert "StrongPass1" not in str(result)


def test_duplicate_admin_provisioning_is_rejected():
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        email="existing@example.com",
        role=UserRole.ADMIN_FACULTY,
    )
    db = _provisioning_db([existing])

    with pytest.raises(ProvisioningError):
        provision_admin(
            db,
            SimpleNamespace(),
            email="admin@example.com",
            full_name="Admin Person",
            password="StrongPass1",
        )


def test_rerunning_same_admin_is_safe_and_does_not_create_duplicate():
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        email="admin@example.com",
        role=UserRole.ADMIN_FACULTY,
    )
    db = _provisioning_db([existing])

    class ExplodingClient:
        @property
        def auth(self):
            raise AssertionError("Supabase must not be called for an existing administrator")

    result = provision_admin(
        db,
        ExplodingClient(),
        email="admin@example.com",
        full_name="Admin Person",
        password="StrongPass1",
    )

    assert result["status"] == "already_provisioned"
    assert result["role"] == "ADMIN_FACULTY"
    assert db.added == []


def test_provisioning_rejects_weak_password():
    db = _provisioning_db([])
    with pytest.raises(ProvisioningError):
        provision_admin(
            db,
            SimpleNamespace(),
            email="admin@example.com",
            full_name="Admin Person",
            password="weak",
        )


def test_supabase_auth_log_redacts_all_sensitive_values(monkeypatch, caplog):
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", "test-anon-api-key")
    error = AuthApiError(
        'Failure for person@example.com OTP: 123456 api_key=test-anon-api-key '
        '"access_token":"eyJabc.def.ghi", "refresh_token":"refresh-secret" '
        'Authorization: Bearer bearer-secret password: hidden-password',
        400,
        "invalid_credentials",
    )

    log_supabase_auth_error("test", error)

    assert "AuthApiError" in caplog.text
    for sensitive in (
        "person@example.com",
        "123456",
        "test-anon-api-key",
        "eyJabc.def.ghi",
        "refresh-secret",
        "bearer-secret",
        "hidden-password",
    ):
        assert sensitive not in caplog.text


def test_admin_password_login_returns_admin_profile(monkeypatch):
    user_id = uuid.uuid4()

    class FakeAuth:
        def sign_in_with_password(self, credentials):
            assert credentials == {"email": "admin@example.com", "password": "StrongPass1"}
            return SimpleNamespace(
                session=SimpleNamespace(access_token="admin-access", refresh_token="admin-refresh"),
                user=SimpleNamespace(id=str(user_id), email="admin@example.com", email_confirmed_at="yes"),
            )

    admin = SimpleNamespace(
        id=user_id,
        email="admin@example.com",
        full_name="Admin",
        role=UserRole.ADMIN_FACULTY,
        last_login_at=None,
    )
    db = FakeDB([[]])
    monkeypatch.setattr(auth_routes, "rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        auth_routes,
        "create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda db, token: (admin, None))

    result = auth_routes.login(
        LoginRequest(email="admin@example.com", password="StrongPass1"),
        _request(),
        db,
    )

    assert result["profile"]["role"] == "ADMIN_FACULTY"
    assert result["access_token"] == "admin-access"


def test_student_is_denied_admin_dashboard_endpoint(monkeypatch):
    student = SimpleNamespace(id=uuid.uuid4(), role=UserRole.STUDENT)
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda db, token: (student, None))

    with pytest.raises(HTTPException) as exc:
        auth_routes.admin_dashboard("token", FakeDB())
    assert exc.value.status_code == 403
