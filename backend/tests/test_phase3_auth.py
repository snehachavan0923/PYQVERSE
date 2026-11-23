from fastapi import HTTPException
import pytest

from app.core.security import (
    create_supabase_anon_client,
    log_supabase_auth_error,
    normalize_admin_email,
    registration_error_response,
    password_login_error_response,
    validate_student_email,
)
from app.models.user import UserRole
from app.schemas.auth import RegisterRequest
from supabase_auth.errors import AuthApiError
from app.core.config import settings


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


def test_student_role_cannot_be_assigned_in_registration_payload():
    request = RegisterRequest(
        email="student@rvce.edu.in",
        password="strong-password",
        full_name="Student",
    )
    assert not hasattr(request, "role")


def test_admin_email_is_separate_from_student_email():
    admin = normalize_admin_email("faculty@gmail.com")
    assert admin == "faculty@gmail.com"
    with pytest.raises(HTTPException):
        validate_student_email(admin)


def test_public_role_is_fixed():
    assert UserRole.STUDENT.value == "STUDENT"
    assert set(role.value for role in UserRole) == {"STUDENT", "ADMIN_FACULTY"}
    request = RegisterRequest(email="student@rvce.edu.in", password="strong-password", full_name="Student")
    assert not hasattr(request, "role")
    with pytest.raises(Exception):
        RegisterRequest(
            email="student@rvce.edu.in",
            password="strong-password",
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


def test_invalid_password_maps_to_safe_401():
    error = AuthApiError("Invalid login credentials", 400, "invalid_credentials")
    response = password_login_error_response(error)
    assert response.status_code == 401
    assert "Invalid email or password" in response.detail


def test_supabase_unavailable_maps_to_503():
    error = AuthApiError("Auth service unavailable", 503, "service_unavailable")
    response = password_login_error_response(error)
    assert response.status_code == 503


def test_login_rate_limit_maps_to_429():
    error = AuthApiError("Email rate limit exceeded", 429, "over_request_rate_limit")
    response = password_login_error_response(error)
    assert response.status_code == 429
