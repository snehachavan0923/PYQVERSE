from fastapi import HTTPException
import pytest

from app.core.security import normalize_admin_email, validate_student_email
from app.models.user import UserRole


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


def test_public_role_is_fixed():
    assert UserRole.STUDENT.value == "STUDENT"
    assert set(role.value for role in UserRole) == {"STUDENT", "ADMIN_FACULTY"}
