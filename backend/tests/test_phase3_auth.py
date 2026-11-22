from fastapi import HTTPException
import pytest

from app.core.security import (
    create_supabase_anon_client,
    log_supabase_auth_error,
    normalize_admin_email,
    registration_error_response,
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
