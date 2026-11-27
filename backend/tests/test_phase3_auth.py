import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import HTTPException
import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from supabase_auth.errors import AuthApiError, UserDoesntExist

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
from app.services.admin_provisioning import (
    ProvisioningError,
    provision_admin,
    recover_staging_admin_identity,
    reset_staging_admin_password,
    reset_staging_user_password,
)
from app.services.auth import require_role, supabase_user, synchronized_user


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


_DEFAULT_STAGING_BIND = SimpleNamespace(
    url=make_url(
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"
    )
)


class FakeDB:
    def __init__(self, scalar_values=None, bind=..., bind_error=None):
        self.added = []
        self.committed = 0
        self.rolled_back = 0
        self._scalar_values = list(scalar_values or [])
        self._bind = _DEFAULT_STAGING_BIND if bind is ... else bind
        self._bind_error = bind_error

    def get_bind(self):
        if self._bind_error is not None:
            raise self._bind_error
        return self._bind

    def rollback(self):
        self.rolled_back += 1

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


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (RuntimeError("network unavailable"), 503),
        (AuthApiError("temporarily unavailable", 503, "unexpected_failure"), 503),
        (AuthApiError("rate limited", 429, "over_request_rate_limit"), 429),
    ],
)
def test_password_login_reports_auth_service_failures_without_mislabeling_credentials(
    monkeypatch,
    failure,
    expected_status,
):
    class FakeAuth:
        def sign_in_with_password(self, _credentials):
            raise failure

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

    assert exc.value.status_code == expected_status
    assert exc.value.status_code != 401


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


def test_existing_verified_account_allowed_during_identity_sync(monkeypatch):
    user_id = uuid.uuid4()
    local_user = SimpleNamespace(
        id=user_id,
        supabase_auth_id=user_id,
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
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
    db = FakeDB([[local_user]])
    user, _ = synchronized_user(db, "token")
    assert user.id == user_id
    assert user.email_verified is True


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


def test_supabase_token_validation_service_failure_is_not_reported_as_expired(monkeypatch):
    class FakeAuth:
        def get_user(self, _token):
            raise RuntimeError("network unavailable")

    monkeypatch.setattr(
        "app.services.auth.create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    with pytest.raises(HTTPException) as exc:
        supabase_user("valid-token")

    assert exc.value.status_code == 503
    assert exc.value.detail == "Authentication service is temporarily unavailable"


def test_authenticated_supabase_user_without_application_account_is_forbidden(monkeypatch):
    auth_id = uuid.uuid4()

    class FakeAuth:
        def get_user(self, token):
            assert token == "valid-supabase-token"
            return SimpleNamespace(
                user=SimpleNamespace(
                    id=str(auth_id),
                    email="unregistered@rvce.edu.in",
                    email_confirmed_at="confirmed",
                )
            )

    monkeypatch.setattr(
        "app.services.auth.create_supabase_anon_client",
        lambda: SimpleNamespace(auth=FakeAuth()),
    )

    with pytest.raises(HTTPException) as exc:
        synchronized_user(FakeDB([[], []]), "valid-supabase-token")

    assert exc.value.status_code == 403
    assert exc.value.detail == "Profile not found. Complete registration first."


def test_student_dashboard_requires_an_application_profile(monkeypatch):
    student = SimpleNamespace(id=uuid.uuid4(), role=UserRole.STUDENT)
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda db, token: (student, None))

    with pytest.raises(HTTPException) as exc:
        auth_routes.student_dashboard("valid-token", FakeDB([[]]))

    assert exc.value.status_code == 409
    assert exc.value.detail == "Student onboarding is required"


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
    db.scalar = MagicMock(side_effect=[8, 1, 1, 1, 5, 1, 2, 3, 4, 6, 0])
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
        "syllabus_documents": 4,
        "learning_resources": 6,
        "pending_reviews": 0,
    }
    assert result["recent_activity"] == []


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
            self.execute_queue = [
                [(subject.id, 2)],
                [(subject.id, 3)],
            ]

        def scalars(self, _query):
            return ScalarResult(self.scalars_queue.pop(0))

        def execute(self, _query):
            rows = self.execute_queue.pop(0)
            return SimpleNamespace(all=lambda: rows)

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
        "learning_resources_available": True,
        "learning_resource_count": 3,
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
        user_id=user.id,
        usn="1RV22CS001",
        profile_completed=True,
        branch_id=None,
        current_semester_id=None,
    )
    db = MagicMock()
    db.scalar.return_value = 1
    db.scalars.side_effect = [ScalarResult([user]), ScalarResult([profile])]
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda db, token: (admin, None))

    result = auth_routes.admin_users(
        "token",
        db,
        page=1,
        page_size=20,
        role=None,
        status=None,
        branch_id=None,
        semester_id=None,
        search=None,
    )

    assert result["total"] == 1
    assert result["pages"] == 1
    assert result["items"][0]["email"] == "student@rvce.edu.in"
    assert "password" not in result["items"][0]


def _provisioning_db(existing_admins, local_user=None, bootstrap_record=None):
    db = FakeDB([existing_admins, [local_user] if local_user else [], [bootstrap_record] if bootstrap_record else []])
    return db


def test_admin_provisioning_creates_linked_admin():
    auth_id = uuid.uuid4()

    class FakeAdmin:
        def list_users(self):
            return []

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
    auth_id = uuid.uuid4()
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        email="admin@example.com",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=auth_id,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    bootstrap_record = SimpleNamespace(email="admin@example.com", supabase_auth_id=auth_id, completed_at=None)
    db = _provisioning_db([existing], bootstrap_record=bootstrap_record)

    class FakeAdmin:
        def list_users(self, page=None, per_page=None):
            return [SimpleNamespace(id=str(auth_id), email="admin@example.com")]

        def update_user_by_id(self, target_id, payload):
            raise AssertionError("update_user_by_id must not be called when admin is already correctly linked")

    client = SimpleNamespace(auth=SimpleNamespace(admin=FakeAdmin()))

    result = provision_admin(
        db,
        client,
        email="admin@example.com",
        full_name="Admin Person",
        password="StrongPass1",
    )

    assert result["status"] == "already_provisioned"
    assert result["role"] == "ADMIN_FACULTY"
    assert db.added == []


def test_admin_provisioning_repairs_unlinked_existing_admin_when_auth_user_missing():
    auth_id = uuid.uuid4()
    db_user_id = uuid.uuid4()
    existing = SimpleNamespace(
        id=db_user_id,
        email="admin@example.com",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=None,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    bootstrap_record = SimpleNamespace(email="admin@example.com", supabase_auth_id=None, completed_at=None)
    db = _provisioning_db([existing], bootstrap_record=bootstrap_record)

    created_payloads = []

    class FakeAdmin:
        def list_users(self, page=None, per_page=None):
            return []

        def create_user(self, payload):
            created_payloads.append(payload)
            return SimpleNamespace(user=SimpleNamespace(id=str(auth_id)))

    client = SimpleNamespace(auth=SimpleNamespace(admin=FakeAdmin()))

    result = provision_admin(
        db,
        client,
        email="admin@example.com",
        full_name="Admin Person",
        password="StrongPass1",
    )

    assert result["status"] == "updated"
    assert result["user_id"] == str(db_user_id)
    assert existing.id == db_user_id  # UUID preserved
    assert existing.supabase_auth_id == auth_id  # Linked
    assert existing.role == UserRole.ADMIN_FACULTY
    assert existing.account_status == AccountStatus.ACTIVE
    assert existing.email_verified is True
    assert db.added == []  # No duplicate user row added
    assert bootstrap_record.supabase_auth_id == auth_id
    assert len(created_payloads) == 1
    assert created_payloads[0]["email"] == "admin@example.com"
    assert created_payloads[0]["email_confirm"] is True


def test_admin_provisioning_repairs_unlinked_existing_admin_when_auth_user_exists():
    auth_id = uuid.uuid4()
    db_user_id = uuid.uuid4()
    existing = SimpleNamespace(
        id=db_user_id,
        email="admin@example.com",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=None,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    bootstrap_record = SimpleNamespace(email="admin@example.com", supabase_auth_id=None, completed_at=None)
    db = _provisioning_db([existing], bootstrap_record=bootstrap_record)

    class FakeAdmin:
        def list_users(self, page=None, per_page=None):
            return [SimpleNamespace(id=str(auth_id), email="admin@example.com")]

        def update_user_by_id(self, target_id, payload):
            raise AssertionError("update_user_by_id must not be called when reset_password=False")

    client = SimpleNamespace(auth=SimpleNamespace(admin=FakeAdmin()))

    result = provision_admin(
        db,
        client,
        email="admin@example.com",
        full_name="Admin Person",
        password="StrongPass1",
        reset_password=False,
    )

    assert result["status"] == "updated"
    assert result["user_id"] == str(db_user_id)
    assert existing.id == db_user_id
    assert existing.supabase_auth_id == auth_id
    assert existing.role == UserRole.ADMIN_FACULTY
    assert existing.account_status == AccountStatus.ACTIVE
    assert existing.email_verified is True
    assert db.added == []
    assert bootstrap_record.supabase_auth_id == auth_id


def test_admin_provisioning_repairs_unlinked_existing_admin_with_explicit_password_reset():
    auth_id = uuid.uuid4()
    db_user_id = uuid.uuid4()
    existing = SimpleNamespace(
        id=db_user_id,
        email="admin@example.com",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=None,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    bootstrap_record = SimpleNamespace(email="admin@example.com", supabase_auth_id=None, completed_at=None)
    db = _provisioning_db([existing], bootstrap_record=bootstrap_record)

    updated_payloads = []

    class FakeAdmin:
        def list_users(self, page=None, per_page=None):
            return [SimpleNamespace(id=str(auth_id), email="admin@example.com")]

        def update_user_by_id(self, target_id, payload):
            assert target_id == str(auth_id)
            updated_payloads.append(payload)
            return SimpleNamespace(id=str(auth_id))

    client = SimpleNamespace(auth=SimpleNamespace(admin=FakeAdmin()))

    result = provision_admin(
        db,
        client,
        email="admin@example.com",
        full_name="Admin Person",
        password="StrongPass1",
        reset_password=True,
    )

    assert result["status"] == "updated"
    assert result["user_id"] == str(db_user_id)
    assert existing.id == db_user_id
    assert existing.supabase_auth_id == auth_id
    assert len(updated_payloads) == 1
    assert updated_payloads[0]["password"] == "StrongPass1"
    assert updated_payloads[0]["email_confirm"] is True


def test_admin_provisioning_fails_safely_when_supabase_query_fails():
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        email="admin@example.com",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=None,
    )
    db = _provisioning_db([existing])

    class FailingAdmin:
        def list_users(self, page=None, per_page=None):
            raise Exception("Supabase 503 Service Unavailable")

        def create_user(self, payload):
            raise AssertionError("create_user must never be called on list_users failure")

    client = SimpleNamespace(auth=SimpleNamespace(admin=FailingAdmin()))

    with pytest.raises(ProvisioningError) as exc_info:
        provision_admin(
            db,
            client,
            email="admin@example.com",
            full_name="Admin Person",
            password="StrongPass1",
        )

    assert "Supabase Auth query failed" in str(exc_info.value)
    assert existing.supabase_auth_id is None
    assert db.added == []


def test_find_auth_user_handles_pagination_correctly():
    auth_id = uuid.uuid4()
    page1_users = [
        SimpleNamespace(id=str(uuid.uuid4()), email=f"user{i}@example.com")
        for i in range(50)
    ]
    page2_users = [
        SimpleNamespace(id=str(uuid.uuid4()), email="other@example.com"),
        SimpleNamespace(id=str(auth_id), email="Admin@example.com"),
    ]

    pages_queried = []

    class PagedAdmin:
        def list_users(self, page=None, per_page=None):
            pages_queried.append(page)
            if page == 1:
                return page1_users
            elif page == 2:
                return page2_users
            return []

    client = SimpleNamespace(auth=SimpleNamespace(admin=PagedAdmin()))
    from app.services.admin_provisioning import _find_auth_user

    found = _find_auth_user(client, "admin@example.com")
    assert found is not None
    assert str(found.id) == str(auth_id)
    assert pages_queried == [1, 2]


def test_admin_provisioning_refuses_to_create_identity_if_admin_already_has_non_null_auth_id():
    existing_auth_id = uuid.uuid4()
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        email="admin@example.com",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=existing_auth_id,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    bootstrap_record = SimpleNamespace(email="admin@example.com", supabase_auth_id=existing_auth_id, completed_at=None)
    db = _provisioning_db([existing], bootstrap_record=bootstrap_record)

    class FakeAdmin:
        def list_users(self, page=None, per_page=None):
            return []  # Auth user cannot be found by email

        def create_user(self, payload):
            raise AssertionError("create_user must not be called when admin already has a non-null supabase_auth_id")

    client = SimpleNamespace(auth=SimpleNamespace(admin=FakeAdmin()))

    with pytest.raises(ProvisioningError) as exc_info:
        provision_admin(
            db,
            client,
            email="admin@example.com",
            full_name="Admin Person",
            password="StrongPass1",
        )

    assert "already has a linked Supabase Auth identity" in str(exc_info.value)
    assert existing.supabase_auth_id == existing_auth_id
    assert db.added == []


def test_admin_provisioning_handles_integrity_conflict_safely():
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        email="admin@example.com",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=None,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )

    class ConflictingDB(FakeDB):
        def commit(self):
            raise IntegrityError("statement", params=None, orig=Exception("unique violation"))

    db = ConflictingDB([[existing], [], []])
    admin_mock = SimpleNamespace(
        list_users=lambda: [],
        create_user=lambda payload: SimpleNamespace(user=SimpleNamespace(id=str(uuid.uuid4()))),
    )
    client = SimpleNamespace(auth=SimpleNamespace(admin=admin_mock))

    with pytest.raises(ProvisioningError) as exc_info:
        provision_admin(
            db,
            client,
            email="admin@example.com",
            full_name="Admin Person",
            password="StrongPass1",
        )

    assert "Database integrity conflict" in str(exc_info.value)


def test_admin_provisioning_refuses_to_promote_existing_student():
    student = SimpleNamespace(
        id=uuid.uuid4(),
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
    )
    # No existing admins, but student user exists with same email
    db = FakeDB([[], [student], []])

    admin_mock = SimpleNamespace(
        list_users=lambda: [],
        create_user=lambda payload: SimpleNamespace(user=SimpleNamespace(id=str(uuid.uuid4()))),
    )
    client = SimpleNamespace(auth=SimpleNamespace(admin=admin_mock))

    with pytest.raises(ProvisioningError) as exc_info:
        provision_admin(
            db,
            client,
            email="student@rvce.edu.in",
            full_name="Student Person",
            password="StrongPass1",
        )

    assert "Refusing to promote" in str(exc_info.value)
    assert student.role == UserRole.STUDENT


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


# ==============================================================================
# Staging Administrator Identity Recovery Tests
# ==============================================================================

def test_staging_recovery_succeeds_and_updates_only_auth_uuid(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")
    new_auth_id = uuid.uuid4()
    db_user_id = uuid.uuid4()

    existing = SimpleNamespace(
        id=db_user_id,
        email="snehachavan0923@gmail.com",
        full_name="Sneha Chavan",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=stale_uuid,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    bootstrap_record = SimpleNamespace(
        email="snehachavan0923@gmail.com",
        supabase_auth_id=stale_uuid,
        completed_at=None,
    )
    db = FakeDB([[existing], [bootstrap_record]])

    created_payloads = []

    class FakeStagingAdmin:
        def list_users(self, page=None, per_page=None):
            return []

        def get_user_by_id(self, uid):
            raise AuthApiError("User not found", 404, "user_not_found")

        def create_user(self, payload):
            created_payloads.append(payload)
            return SimpleNamespace(user=SimpleNamespace(id=str(new_auth_id)))

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=FakeStagingAdmin()),
    )

    result = recover_staging_admin_identity(
        db,
        client,
        email="snehachavan0923@gmail.com",
        password="NewAdminPassword1!",
        expected_stale_auth_id=str(stale_uuid),
    )

    assert result["status"] == "recovered"
    assert result["new_auth_id"] == str(new_auth_id)
    assert result["previous_auth_id"] == str(stale_uuid)
    # Check that ONLY supabase_auth_id was changed on the existing PostgreSQL record
    assert existing.supabase_auth_id == new_auth_id
    assert existing.id == db_user_id  # UUID preserved
    assert existing.email == "snehachavan0923@gmail.com"
    assert existing.full_name == "Sneha Chavan"  # full_name preserved
    assert existing.role == UserRole.ADMIN_FACULTY
    assert existing.account_status == AccountStatus.ACTIVE
    assert existing.email_verified is True
    assert bootstrap_record.supabase_auth_id == new_auth_id
    assert len(created_payloads) == 1
    assert created_payloads[0]["email"] == "snehachavan0923@gmail.com"
    assert created_payloads[0]["email_confirm"] is True


def test_staging_recovery_rejects_wrong_project_url(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://production-project-ref.supabase.co")

    stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")
    client = SimpleNamespace(
        supabase_url="https://production-project-ref.supabase.co",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )
    db = FakeDB([])

    with pytest.raises(ProvisioningError) as exc_info:
        recover_staging_admin_identity(
            db,
            client,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(stale_uuid),
        )

    assert "host does not match the expected staging Supabase host" in str(exc_info.value)


def test_staging_recovery_rejects_production_database_url(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres:pass@db.inuqzeciawzeyripvbze.supabase.co:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")
    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )
    db = FakeDB([])

    with pytest.raises(ProvisioningError) as exc_info:
        recover_staging_admin_identity(
            db,
            client,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(stale_uuid),
        )

    assert "does not belong to the expected staging project" in str(exc_info.value)


def test_staging_recovery_accepts_staging_direct_db_url(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres:pass@db.fauzmbfcvivzpkmisrrj.supabase.co:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")
    new_auth_id = uuid.uuid4()
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        email="snehachavan0923@gmail.com",
        full_name="Admin",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=stale_uuid,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    db = FakeDB([[existing], []])

    class FakeAdmin:
        def list_users(self, page=None, per_page=None):
            return []

        def get_user_by_id(self, uid):
            raise AuthApiError("User not found", 404, "user_not_found")

        def create_user(self, payload):
            return SimpleNamespace(user=SimpleNamespace(id=str(new_auth_id)))

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=FakeAdmin()),
    )

    result = recover_staging_admin_identity(
        db,
        client,
        email="snehachavan0923@gmail.com",
        password="NewAdminPassword1!",
        expected_stale_auth_id=str(stale_uuid),
    )
    assert result["status"] == "recovered"
    assert existing.supabase_auth_id == new_auth_id


def test_staging_recovery_accepts_staging_pooler_identity(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")
    new_auth_id = uuid.uuid4()
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        email="snehachavan0923@gmail.com",
        full_name="Admin",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=stale_uuid,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    db = FakeDB([[existing], []])

    class FakeAdmin:
        def list_users(self, page=None, per_page=None):
            return []

        def get_user_by_id(self, uid):
            raise AuthApiError("User not found", 404, "user_not_found")

        def create_user(self, payload):
            return SimpleNamespace(user=SimpleNamespace(id=str(new_auth_id)))

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=FakeAdmin()),
    )

    result = recover_staging_admin_identity(
        db,
        client,
        email="snehachavan0923@gmail.com",
        password="NewAdminPassword1!",
        expected_stale_auth_id=str(stale_uuid),
    )
    assert result["status"] == "recovered"


def test_staging_recovery_rejects_unknown_or_ambiguous_database_target(monkeypatch):
    stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")
    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )

    # 1. Localhost
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://postgres:pass@localhost:5432/postgres")
    with pytest.raises(ProvisioningError):
        recover_staging_admin_identity(
            FakeDB([]),
            client,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(stale_uuid),
        )

    # 2. Pooler with missing staging project ref in username
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://postgres:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres")
    with pytest.raises(ProvisioningError):
        recover_staging_admin_identity(
            FakeDB([]),
            client,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(stale_uuid),
        )

    # 3. Malformed database URL
    monkeypatch.setattr(settings, "DATABASE_URL", "not-a-valid-url://")
    with pytest.raises(ProvisioningError) as exc_info:
        recover_staging_admin_identity(
            FakeDB([]),
            client,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(stale_uuid),
        )
    assert "Malformed DATABASE_URL" in str(exc_info.value)


def test_staging_recovery_rejects_supabase_hostname_substring_spoof(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")

    # Spoof A: attacker subdomain after staging ref
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co.attacker.com")
    client_a = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co.attacker.com",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )
    with pytest.raises(ProvisioningError) as exc_a:
        recover_staging_admin_identity(
            FakeDB([]),
            client_a,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(stale_uuid),
        )
    assert "host does not match the expected staging Supabase host" in str(exc_a.value)

    # Spoof B: prefix spoof
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://attacker-fauzmbfcvivzpkmisrrj.supabase.co")
    client_b = SimpleNamespace(
        supabase_url="https://attacker-fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )
    with pytest.raises(ProvisioningError) as exc_b:
        recover_staging_admin_identity(
            FakeDB([]),
            client_b,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(stale_uuid),
        )
    assert "host does not match the expected staging Supabase host" in str(exc_b.value)


def test_caller_cannot_override_expected_staging_project():
    import inspect
    sig = inspect.signature(recover_staging_admin_identity)
    assert "expected_project_ref" not in sig.parameters

    with pytest.raises(TypeError):
        recover_staging_admin_identity(
            FakeDB([]),
            SimpleNamespace(),
            email="admin@example.com",
            password="Pass",
            expected_stale_auth_id=str(uuid.uuid4()),
            expected_project_ref="evil",  # type: ignore[call-arg]
        )


def test_staging_recovery_rejects_client_config_url_mismatch(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    client = SimpleNamespace(
        supabase_url="https://other-instance.supabase.co",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )
    with pytest.raises(ProvisioningError) as exc_info:
        recover_staging_admin_identity(
            FakeDB([]),
            client,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(uuid.uuid4()),
        )
    assert "Supabase service client host does not match" in str(exc_info.value)


def test_find_auth_user_by_id_searches_multiple_pages_on_fallback():
    target_uuid = uuid.uuid4()
    page1_users = [
        SimpleNamespace(id=str(uuid.uuid4()), email=f"user{i}@example.com")
        for i in range(50)
    ]
    page2_users = [
        SimpleNamespace(id=str(uuid.uuid4()), email="other@example.com"),
        SimpleNamespace(id=str(target_uuid), email="target@example.com"),
    ]

    pages_queried = []

    class PagedAdminNoGetById:
        def list_users(self, page=None, per_page=None):
            pages_queried.append(page)
            if page == 1:
                return page1_users
            elif page == 2:
                return page2_users
            return []

    client = SimpleNamespace(auth=SimpleNamespace(admin=PagedAdminNoGetById()))
    from app.services.admin_provisioning import _find_auth_user_by_id

    found = _find_auth_user_by_id(client, str(target_uuid))
    assert found is not None
    assert str(found.id) == str(target_uuid)
    assert pages_queried == [1, 2]


def test_find_auth_user_by_id_does_not_interpret_network_error_as_missing():
    class FailingAdmin:
        def get_user_by_id(self, uid):
            raise Exception("500 Internal Server Error: Database timeout")

    client = SimpleNamespace(auth=SimpleNamespace(admin=FailingAdmin()))
    from app.services.admin_provisioning import _find_auth_user_by_id

    with pytest.raises(ProvisioningError) as exc_info:
        _find_auth_user_by_id(client, str(uuid.uuid4()))

    assert "lookup by ID failed due to API/network error" in str(exc_info.value)


def test_staging_recovery_preserves_every_postgresql_field_except_auth_id(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")
    new_auth_id = uuid.uuid4()
    db_user_id = uuid.uuid4()

    existing = SimpleNamespace(
        id=db_user_id,
        email="snehachavan0923@gmail.com",
        full_name="Original Name Exactly",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=stale_uuid,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    # No existing bootstrap record
    db = FakeDB([[existing], []])

    class FakeAdmin:
        def list_users(self, page=None, per_page=None):
            return []

        def get_user_by_id(self, uid):
            raise AuthApiError("User not found", 404, "user_not_found")

        def create_user(self, payload):
            return SimpleNamespace(user=SimpleNamespace(id=str(new_auth_id)))

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=FakeAdmin()),
    )

    result = recover_staging_admin_identity(
        db,
        client,
        email="snehachavan0923@gmail.com",
        password="NewAdminPassword1!",
        expected_stale_auth_id=str(stale_uuid),
    )

    assert result["status"] == "recovered"
    assert existing.id == db_user_id
    assert existing.email == "snehachavan0923@gmail.com"
    assert existing.full_name == "Original Name Exactly"
    assert existing.role == UserRole.ADMIN_FACULTY
    assert existing.account_status == AccountStatus.ACTIVE
    assert existing.email_verified is True
    assert existing.supabase_auth_id == new_auth_id
    # Confirms no new bootstrap record was created when none existed
    assert db.added == []


def test_staging_recovery_reports_commit_failure_and_refresh_failure_distinctly(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")
    new_auth_id = uuid.uuid4()

    # Case A: Commit failure
    class FailingCommitDB(FakeDB):
        def commit(self):
            raise Exception("disk failure")

    existing_a = SimpleNamespace(
        id=uuid.uuid4(),
        email="snehachavan0923@gmail.com",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=stale_uuid,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    db_a = FailingCommitDB([[existing_a], []])

    class FakeAdmin:
        def get_user_by_id(self, uid):
            raise AuthApiError("User not found", 404, "user_not_found")

        def list_users(self, page=None, per_page=None):
            return []

        def create_user(self, payload):
            return SimpleNamespace(user=SimpleNamespace(id=str(new_auth_id)))

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=FakeAdmin()),
    )

    with pytest.raises(ProvisioningError) as exc_a:
        recover_staging_admin_identity(
            db_a,
            client,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(stale_uuid),
        )

    msg_a = str(exc_a.value)
    assert "database transaction commit failed. The database transaction was rolled back." in msg_a
    assert str(new_auth_id) in msg_a
    assert "Manual reconciliation is required" in msg_a

    # Case B: Commit succeeded, refresh/verification failure
    class FailingRefreshDB(FakeDB):
        def refresh(self, obj):
            raise Exception("session invalid after commit")

    existing_b = SimpleNamespace(
        id=uuid.uuid4(),
        email="snehachavan0923@gmail.com",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=stale_uuid,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    db_b = FailingRefreshDB([[existing_b], []])

    with pytest.raises(ProvisioningError) as exc_b:
        recover_staging_admin_identity(
            db_b,
            client,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(stale_uuid),
        )

    msg_b = str(exc_b.value)
    assert "Database commit succeeded and linked Auth ID" in msg_b
    assert "post-commit verification failed" in msg_b
    assert "Do not rerun recovery; inspect database state manually." in msg_b


def test_staging_recovery_rejects_unexpected_stale_uuid(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    real_stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")
    different_uuid = uuid.uuid4()

    existing = SimpleNamespace(
        id=uuid.uuid4(),
        email="snehachavan0923@gmail.com",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=real_stale_uuid,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    db = FakeDB([[existing]])
    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )

    with pytest.raises(ProvisioningError) as exc_info:
        recover_staging_admin_identity(
            db,
            client,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(different_uuid),
        )

    assert "does not match the expected stale UUID" in str(exc_info.value)
    assert existing.supabase_auth_id == real_stale_uuid


def test_staging_recovery_rejects_existing_auth_user_with_email(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        email="snehachavan0923@gmail.com",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=stale_uuid,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    db = FakeDB([[existing]])

    already_present_auth_id = str(uuid.uuid4())

    class FakeAdminWithEmail:
        def get_user_by_id(self, uid):
            raise AuthApiError("User not found", 404, "user_not_found")

        def list_users(self, page=None, per_page=None):
            return [SimpleNamespace(id=already_present_auth_id, email="snehachavan0923@gmail.com")]

        def create_user(self, payload):
            raise AssertionError("create_user must not be called when user with email already exists")

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=FakeAdminWithEmail()),
    )

    with pytest.raises(ProvisioningError) as exc_info:
        recover_staging_admin_identity(
            db,
            client,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(stale_uuid),
        )

    assert "already exists in staging Supabase Auth" in str(exc_info.value)
    assert "manual reconciliation is required" in str(exc_info.value)
    assert already_present_auth_id in str(exc_info.value)


def test_staging_recovery_rejects_stale_uuid_found_in_staging(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        email="snehachavan0923@gmail.com",
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=stale_uuid,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    db = FakeDB([[existing]])

    class FakeAdminWithStaleUser:
        def get_user_by_id(self, uid):
            if str(uid) == str(stale_uuid):
                return SimpleNamespace(id=str(stale_uuid), email="some_other@rvce.edu.in")
            raise Exception("not found (404)")

        def list_users(self, page=None, per_page=None):
            return []

        def create_user(self, payload):
            raise AssertionError("create_user must not be called when stale UUID exists in staging")

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=FakeAdminWithStaleUser()),
    )

    with pytest.raises(ProvisioningError) as exc_info:
        recover_staging_admin_identity(
            db,
            client,
            email="snehachavan0923@gmail.com",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(stale_uuid),
        )

    assert "unexpectedly found in staging Supabase Auth" in str(exc_info.value)


def test_staging_recovery_rejects_student_or_non_admin(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    stale_uuid = uuid.UUID("1c057070-2158-42f6-b44a-e3e216b5f6d5")
    student = SimpleNamespace(
        id=uuid.uuid4(),
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        supabase_auth_id=stale_uuid,
    )
    db = FakeDB([[student]])
    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )

    with pytest.raises(ProvisioningError) as exc_info:
        recover_staging_admin_identity(
            db,
            client,
            email="student@rvce.edu.in",
            password="NewAdminPassword1!",
            expected_stale_auth_id=str(stale_uuid),
        )

    assert "Refusing to perform recovery on a non-administrator account" in str(exc_info.value)
    assert student.role == UserRole.STUDENT


# ---------------------------------------------------------------------------
# Strict Auth UUID Absence Tests
# ---------------------------------------------------------------------------

def test_find_auth_user_by_id_returns_none_for_genuine_404():
    from app.services.admin_provisioning import _find_auth_user_by_id

    class Admin404:
        def get_user_by_id(self, uid):
            raise AuthApiError("User not found", 404, None)

    client = SimpleNamespace(auth=SimpleNamespace(admin=Admin404()))
    assert _find_auth_user_by_id(client, str(uuid.uuid4())) is None


def test_find_auth_user_by_id_returns_none_for_exact_user_not_found_code():
    from app.services.admin_provisioning import _find_auth_user_by_id

    class AdminUserNotFoundCode:
        def get_user_by_id(self, uid):
            raise AuthApiError("Not found", 400, "user_not_found")

    client = SimpleNamespace(auth=SimpleNamespace(admin=AdminUserNotFoundCode()))
    assert _find_auth_user_by_id(client, str(uuid.uuid4())) is None


def test_find_auth_user_by_id_returns_none_for_user_doesnt_exist_exception():
    from app.services.admin_provisioning import _find_auth_user_by_id

    class AdminUserDoesntExist:
        def get_user_by_id(self, uid):
            raise UserDoesntExist()

    client = SimpleNamespace(auth=SimpleNamespace(admin=AdminUserDoesntExist()))
    assert _find_auth_user_by_id(client, str(uuid.uuid4())) is None


def test_find_auth_user_by_id_raises_for_403_forbidden():
    from app.services.admin_provisioning import _find_auth_user_by_id

    class Admin403:
        def get_user_by_id(self, uid):
            raise AuthApiError("Forbidden access to auth admin", 403, "forbidden")

    client = SimpleNamespace(auth=SimpleNamespace(admin=Admin403()))
    with pytest.raises(ProvisioningError) as exc_info:
        _find_auth_user_by_id(client, str(uuid.uuid4()))
    assert "lookup by ID failed due to API/network error" in str(exc_info.value)


def test_find_auth_user_by_id_raises_for_500_server_error():
    from app.services.admin_provisioning import _find_auth_user_by_id

    class Admin500:
        def get_user_by_id(self, uid):
            raise AuthApiError("Internal Server Error", 500, "unexpected_failure")

    client = SimpleNamespace(auth=SimpleNamespace(admin=Admin500()))
    with pytest.raises(ProvisioningError) as exc_info:
        _find_auth_user_by_id(client, str(uuid.uuid4()))
    assert "lookup by ID failed due to API/network error" in str(exc_info.value)


def test_find_auth_user_by_id_raises_for_timeout():
    from app.services.admin_provisioning import _find_auth_user_by_id

    class AdminTimeout:
        def get_user_by_id(self, uid):
            raise TimeoutError("Connection to Supabase Auth timed out")

    client = SimpleNamespace(auth=SimpleNamespace(admin=AdminTimeout()))
    with pytest.raises(ProvisioningError) as exc_info:
        _find_auth_user_by_id(client, str(uuid.uuid4()))
    assert "lookup by ID failed due to API/network error" in str(exc_info.value)


def test_find_auth_user_by_id_raises_for_ambiguous_error_message():
    from app.services.admin_provisioning import _find_auth_user_by_id

    # 1. Plain exception with "user not found" in text, but no HTTP 404 or user_not_found code
    class AdminAmbiguousString:
        def get_user_by_id(self, uid):
            raise RuntimeError("Database cache: user not found in local memory buffer")

    client1 = SimpleNamespace(auth=SimpleNamespace(admin=AdminAmbiguousString()))
    with pytest.raises(ProvisioningError) as exc_info1:
        _find_auth_user_by_id(client1, str(uuid.uuid4()))
    assert "lookup by ID failed due to API/network error" in str(exc_info1.value)

    # 2. AuthApiError with status 400 and different code, despite "not found" in message
    class AdminAmbiguousAuthApiError:
        def get_user_by_id(self, uid):
            raise AuthApiError("Requested entity not found in organization", 400, "bad_request")

    client2 = SimpleNamespace(auth=SimpleNamespace(admin=AdminAmbiguousAuthApiError()))
    with pytest.raises(ProvisioningError) as exc_info2:
        _find_auth_user_by_id(client2, str(uuid.uuid4()))
    assert "lookup by ID failed due to API/network error" in str(exc_info2.value)


# ---------------------------------------------------------------------------
# Fail-closed Supabase Client Destination Verification Tests
# ---------------------------------------------------------------------------

def test_verify_staging_supabase_url_missing_client_url(monkeypatch):
    from app.services.admin_provisioning import _verify_staging_supabase_url

    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    # Client without supabase_url attribute
    client_no_attr = SimpleNamespace(auth=SimpleNamespace())
    with pytest.raises(ProvisioningError) as exc1:
        _verify_staging_supabase_url(client_no_attr)
    assert "Unable to inspect Supabase service client destination URL" in str(exc1.value)

    # Client with supabase_url=None
    client_none_url = SimpleNamespace(supabase_url=None, auth=SimpleNamespace())
    with pytest.raises(ProvisioningError) as exc2:
        _verify_staging_supabase_url(client_none_url)
    assert "Unable to inspect Supabase service client destination URL" in str(exc2.value)


def test_verify_staging_supabase_url_mismatched_client_url(monkeypatch):
    from app.services.admin_provisioning import _verify_staging_supabase_url

    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    client = SimpleNamespace(
        supabase_url="https://otherproject.supabase.co",
        auth=SimpleNamespace(),
    )
    with pytest.raises(ProvisioningError) as exc:
        _verify_staging_supabase_url(client)
    assert "Supabase service client host does not match" in str(exc.value)


def test_verify_staging_supabase_url_wrong_project(monkeypatch):
    from app.services.admin_provisioning import _verify_staging_supabase_url

    # Both client and config point to a non-staging / production project
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://prodproject12345.supabase.co")
    client = SimpleNamespace(
        supabase_url="https://prodproject12345.supabase.co",
        auth=SimpleNamespace(),
    )
    with pytest.raises(ProvisioningError) as exc:
        _verify_staging_supabase_url(client)
    assert "Configured SUPABASE_URL host does not match the expected staging" in str(exc.value)


def test_verify_staging_supabase_url_valid_staging_client(monkeypatch):
    from app.services.admin_provisioning import _verify_staging_supabase_url

    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    # Valid staging client URL with trailing slash
    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co/",
        auth=SimpleNamespace(),
    )
    # Should not raise
    _verify_staging_supabase_url(client)


# ---------------------------------------------------------------------------
# Fail-closed Active Database Bind Verification Tests
# ---------------------------------------------------------------------------

def test_verify_staging_database_session_get_bind_raises_exception(monkeypatch):
    from app.services.admin_provisioning import _verify_staging_database

    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    db = FakeDB([], bind_error=RuntimeError("connection pool exhausted"))

    with pytest.raises(ProvisioningError) as exc:
        _verify_staging_database(db)
    assert "Failed to inspect active database session bind: RuntimeError" in str(exc.value)


def test_verify_staging_database_missing_bind_or_missing_url(monkeypatch):
    from app.services.admin_provisioning import _verify_staging_database

    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )

    # 1. db has no get_bind attribute
    class NoGetBindSession:
        pass

    with pytest.raises(ProvisioningError) as exc1:
        _verify_staging_database(NoGetBindSession())
    assert "Database session has no get_bind() method" in str(exc1.value)

    # 2. get_bind() returns None
    db_none = FakeDB([], bind=None)
    with pytest.raises(ProvisioningError) as exc2:
        _verify_staging_database(db_none)
    assert "Active database session bind is None" in str(exc2.value)

    # 3. get_bind() returns object with url=None
    db_no_url = FakeDB([], bind=SimpleNamespace(url=None))
    with pytest.raises(ProvisioningError) as exc3:
        _verify_staging_database(db_no_url)
    assert "Active database session bind has no URL" in str(exc3.value)


def test_verify_staging_database_production_bind_with_staging_config(monkeypatch):
    from app.services.admin_provisioning import _verify_staging_database

    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )

    # Production pooler bind with staging settings
    prod_bind = SimpleNamespace(
        url=make_url(
            "postgresql+psycopg://postgres.prodprojectref:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"
        )
    )
    db = FakeDB([], bind=prod_bind)

    with pytest.raises(ProvisioningError) as exc:
        _verify_staging_database(db)
    assert "Active database session bind does not belong to the expected staging project" in str(exc.value)


def test_verify_staging_database_staging_bind_with_production_config(monkeypatch):
    from app.services.admin_provisioning import _verify_staging_database

    # Staging bind with production config
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.prodprojectref:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    db = FakeDB([])  # Default bind is staging

    with pytest.raises(ProvisioningError) as exc:
        _verify_staging_database(db)
    assert "Configured DATABASE_URL does not belong to the expected staging project" in str(exc.value)


# ---------------------------------------------------------------------------
# Staging Admin Password Reset Tests
# ---------------------------------------------------------------------------

def test_reset_staging_admin_password_succeeds(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    admin_auth_id = uuid.UUID("8bf32e67-851c-41e0-898e-edaf58874bfb")
    admin_pg_id = uuid.uuid4()
    admin_email = "snehachavan0923@gmail.com"

    admin_record = SimpleNamespace(
        id=admin_pg_id,
        email=admin_email,
        full_name="Sneha Chavan",
        role=UserRole.ADMIN_FACULTY,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
        supabase_auth_id=admin_auth_id,
    )
    db = FakeDB([[admin_record]])

    updated_payloads = []

    class FakeAdminApi:
        def get_user_by_id(self, uid):
            if str(uid) == str(admin_auth_id):
                return SimpleNamespace(id=str(admin_auth_id), email=admin_email)
            raise AuthApiError("User not found", 404, "user_not_found")

        def update_user_by_id(self, uid, attributes):
            updated_payloads.append((uid, attributes))
            return SimpleNamespace(id=str(uid), email=admin_email)

    signed_in_calls = []

    class FakeAuth:
        admin = FakeAdminApi()

        def sign_in_with_password(self, credentials):
            signed_in_calls.append(credentials)
            return SimpleNamespace(user=SimpleNamespace(id=str(admin_auth_id), email=admin_email))

        def sign_out(self, options=None):
            pass

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=FakeAuth(),
    )

    result = reset_staging_admin_password(
        db,
        client,
        email=admin_email,
        password="NewStrongPassword123!",
        expected_auth_id=str(admin_auth_id),
    )

    assert result["status"] == "PASSWORD_RESET_AND_AUTH_TEST_SUCCESS"
    assert result["email"] == admin_email
    assert result["auth_id"] == str(admin_auth_id)
    assert result["user_id"] == str(admin_pg_id)
    # Verify update_user_by_id was called with exact UUID and password only
    assert len(updated_payloads) == 1
    assert updated_payloads[0][0] == str(admin_auth_id)
    assert updated_payloads[0][1] == {"password": "NewStrongPassword123!"}
    # Verify direct authentication test was called immediately
    assert len(signed_in_calls) == 1
    assert signed_in_calls[0] == {"email": admin_email, "password": "NewStrongPassword123!"}
    # Verify zero PostgreSQL mutations occurred
    assert db.added == []
    assert db.committed == 0
    assert admin_record.role == UserRole.ADMIN_FACULTY
    assert admin_record.account_status == AccountStatus.ACTIVE


def test_reset_staging_admin_password_rejects_wrong_project(monkeypatch):
    # Production database URL configured
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.prodprojectref:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )
    db = FakeDB([])

    with pytest.raises(ProvisioningError) as exc_info:
        reset_staging_admin_password(
            db,
            client,
            email="snehachavan0923@gmail.com",
            password="NewStrongPassword123!",
            expected_auth_id=str(uuid.uuid4()),
        )
    assert "does not belong to the expected staging project" in str(exc_info.value)


def test_reset_staging_admin_password_rejects_wrong_uuid_or_email_mismatch(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    admin_auth_id = uuid.UUID("8bf32e67-851c-41e0-898e-edaf58874bfb")
    different_uuid = uuid.uuid4()
    admin_email = "snehachavan0923@gmail.com"

    admin_record = SimpleNamespace(
        id=uuid.uuid4(),
        email=admin_email,
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=admin_auth_id,
    )
    db = FakeDB([[admin_record]])

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )

    # 1. UUID passed does not match PostgreSQL admin record's supabase_auth_id
    with pytest.raises(ProvisioningError) as exc1:
        reset_staging_admin_password(
            db,
            client,
            email=admin_email,
            password="NewStrongPassword123!",
            expected_auth_id=str(different_uuid),
        )
    assert "does not match expected UUID" in str(exc1.value)

    # 2. Auth user email does not match administrator email
    class EmailMismatchAdmin:
        def get_user_by_id(self, uid):
            return SimpleNamespace(id=str(admin_auth_id), email="other_person@example.com")

        def update_user_by_id(self, uid, attributes):
            pass

    client_mismatch = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=EmailMismatchAdmin()),
    )
    db_mismatch = FakeDB([[admin_record]])
    with pytest.raises(ProvisioningError) as exc2:
        reset_staging_admin_password(
            db_mismatch,
            client_mismatch,
            email=admin_email,
            password="NewStrongPassword123!",
            expected_auth_id=str(admin_auth_id),
        )
    assert "does not match expected administrator email" in str(exc2.value)


def test_reset_staging_admin_password_rejects_missing_user(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    admin_auth_id = uuid.UUID("8bf32e67-851c-41e0-898e-edaf58874bfb")
    admin_email = "snehachavan0923@gmail.com"

    # Case A: User missing from PostgreSQL
    db_no_user = FakeDB([[]])
    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )
    with pytest.raises(ProvisioningError) as exc_a:
        reset_staging_admin_password(
            db_no_user,
            client,
            email=admin_email,
            password="NewStrongPassword123!",
            expected_auth_id=str(admin_auth_id),
        )
    assert "No database user found" in str(exc_a.value)

    # Case B: User found in PostgreSQL, but missing from Supabase Auth
    admin_record = SimpleNamespace(
        id=uuid.uuid4(),
        email=admin_email,
        role=UserRole.ADMIN_FACULTY,
        supabase_auth_id=admin_auth_id,
    )
    db_pg = FakeDB([[admin_record]])

    class MissingAuthUserAdmin:
        def get_user_by_id(self, uid):
            raise AuthApiError("User not found", 404, "user_not_found")

        def update_user_by_id(self, uid, attributes):
            pass

    client_missing = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=MissingAuthUserAdmin()),
    )
    with pytest.raises(ProvisioningError) as exc_b:
        reset_staging_admin_password(
            db_pg,
            client_missing,
            email=admin_email,
            password="NewStrongPassword123!",
            expected_auth_id=str(admin_auth_id),
        )
    assert "not found" in str(exc_b.value).lower()


def test_reset_staging_admin_password_rejects_weak_password(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )
    db = FakeDB([])

    with pytest.raises(ProvisioningError) as exc:
        reset_staging_admin_password(
            db,
            client,
            email="snehachavan0923@gmail.com",
            password="weak",
            expected_auth_id=str(uuid.uuid4()),
        )
    assert "Password must be between 8 and 128 characters" in str(exc.value)


def test_cli_read_password_rejects_mismatched_confirmation(monkeypatch):
    import scripts.provision_admin as pa

    # Simulate getpass entering two mismatched passwords
    inputs = iter(["Password123!", "MismatchPass456!"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(inputs))
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    with pytest.raises(ProvisioningError) as exc:
        pa._read_password()
    assert "Passwords do not match" in str(exc.value)


def test_reset_staging_admin_password_direct_auth_failure(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    admin_auth_id = uuid.UUID("8bf32e67-851c-41e0-898e-edaf58874bfb")
    admin_pg_id = uuid.uuid4()
    admin_email = "snehachavan0923@gmail.com"

    admin_record = SimpleNamespace(
        id=admin_pg_id,
        email=admin_email,
        full_name="Sneha Chavan",
        role=UserRole.ADMIN_FACULTY,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
        supabase_auth_id=admin_auth_id,
    )
    db = FakeDB([[admin_record]])

    class FakeAdminApi:
        def get_user_by_id(self, uid):
            return SimpleNamespace(id=str(admin_auth_id), email=admin_email)

        def update_user_by_id(self, uid, attributes):
            return SimpleNamespace(id=str(uid), email=admin_email)

    class FailingAuth:
        admin = FakeAdminApi()

        def sign_in_with_password(self, credentials):
            raise AuthApiError("Invalid login credentials", 400, "invalid_credentials")

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=FailingAuth(),
    )

    with pytest.raises(ProvisioningError) as exc:
        reset_staging_admin_password(
            db,
            client,
            email=admin_email,
            password="NewStrongPassword123!",
            expected_auth_id=str(admin_auth_id),
        )
    assert "Direct password authentication test failed immediately after reset" in str(exc.value)
    assert "code=invalid_credentials" in str(exc.value)
    assert "status=400" in str(exc.value)


def test_reset_staging_admin_password_direct_auth_mismatched_id(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    admin_auth_id = uuid.UUID("8bf32e67-851c-41e0-898e-edaf58874bfb")
    different_auth_id = uuid.uuid4()
    admin_pg_id = uuid.uuid4()
    admin_email = "snehachavan0923@gmail.com"

    admin_record = SimpleNamespace(
        id=admin_pg_id,
        email=admin_email,
        full_name="Sneha Chavan",
        role=UserRole.ADMIN_FACULTY,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
        supabase_auth_id=admin_auth_id,
    )
    db = FakeDB([[admin_record]])

    class FakeAdminApi:
        def get_user_by_id(self, uid):
            return SimpleNamespace(id=str(admin_auth_id), email=admin_email)

        def update_user_by_id(self, uid, attributes):
            return SimpleNamespace(id=str(uid), email=admin_email)

    class MismatchedAuth:
        admin = FakeAdminApi()

        def sign_in_with_password(self, credentials):
            return SimpleNamespace(user=SimpleNamespace(id=str(different_auth_id), email=admin_email))

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=MismatchedAuth(),
    )

    with pytest.raises(ProvisioningError) as exc:
        reset_staging_admin_password(
            db,
            client,
            email=admin_email,
            password="NewStrongPassword123!",
            expected_auth_id=str(admin_auth_id),
        )
    assert "Direct auth test returned mismatched user ID" in str(exc.value)


def test_reset_staging_password_supports_student(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    student_auth_id = uuid.UUID("722128a1-2390-498e-858d-c0f5bb70f122")
    student_pg_id = uuid.uuid4()
    student_email = "neha.cd26@rvce.edu.in"

    student_record = SimpleNamespace(
        id=student_pg_id,
        email=student_email,
        full_name="Neha",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
        email_verified=False,
        supabase_auth_id=student_auth_id,
    )
    db = FakeDB([[student_record]])

    updated_payloads = []

    class FakeAdminApi:
        def get_user_by_id(self, uid):
            if str(uid) == str(student_auth_id):
                return SimpleNamespace(id=str(student_auth_id), email=student_email)
            raise AuthApiError("User not found", 404, "user_not_found")

        def update_user_by_id(self, uid, attributes):
            updated_payloads.append((uid, attributes))
            return SimpleNamespace(id=str(uid), email=student_email)

    signed_in_calls = []

    class FakeAuth:
        admin = FakeAdminApi()

        def sign_in_with_password(self, credentials):
            signed_in_calls.append(credentials)
            return SimpleNamespace(user=SimpleNamespace(id=str(student_auth_id), email=student_email))

        def sign_out(self, options=None):
            pass

    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=FakeAuth(),
    )

    result = reset_staging_user_password(
        db,
        client,
        email=student_email,
        password="StudentNewPassword123!",
        expected_auth_id=str(student_auth_id),
    )

    assert result["status"] == "PASSWORD_RESET_AND_AUTH_TEST_SUCCESS"
    assert result["email"] == student_email
    assert result["auth_id"] == str(student_auth_id)
    assert result["user_id"] == str(student_pg_id)
    assert result["role"] == "STUDENT"

    # Verify update_user_by_id was called with exact UUID, password, and email_confirm (auto confirmed)
    assert len(updated_payloads) == 1
    assert updated_payloads[0][0] == str(student_auth_id)
    assert updated_payloads[0][1] == {"password": "StudentNewPassword123!", "email_confirm": True}

    # Verify direct authentication test was called immediately
    assert len(signed_in_calls) == 1
    assert signed_in_calls[0] == {"email": student_email, "password": "StudentNewPassword123!"}

    # Verify zero PostgreSQL mutations occurred
    assert db.added == []
    assert db.committed == 0
    assert student_record.role == UserRole.STUDENT
    assert student_record.account_status == AccountStatus.ACTIVE


def test_reset_staging_student_password_rejects_mismatched_uuid(monkeypatch):
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        "postgresql+psycopg://postgres.fauzmbfcvivzpkmisrrj:pass@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://fauzmbfcvivzpkmisrrj.supabase.co")

    student_auth_id = uuid.UUID("722128a1-2390-498e-858d-c0f5bb70f122")
    different_uuid = uuid.uuid4()
    student_email = "neha.cd26@rvce.edu.in"

    student_record = SimpleNamespace(
        id=uuid.uuid4(),
        email=student_email,
        role=UserRole.STUDENT,
        supabase_auth_id=student_auth_id,
    )
    db = FakeDB([[student_record]])
    client = SimpleNamespace(
        supabase_url="https://fauzmbfcvivzpkmisrrj.supabase.co",
        auth=SimpleNamespace(admin=SimpleNamespace()),
    )

    with pytest.raises(ProvisioningError) as exc:
        reset_staging_admin_password(
            db,
            client,
            email=student_email,
            password="StudentNewPassword123!",
            expected_auth_id=str(different_uuid),
        )
    assert "PostgreSQL student record's supabase_auth_id" in str(exc.value)
    assert "does not match expected UUID" in str(exc.value)

