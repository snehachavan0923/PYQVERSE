import re
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


PASSWORD_POLICY_MESSAGE = (
    "Password must be at least 8 characters and include an uppercase letter, "
    "a lowercase letter and a number"
)


def password_is_strong(value: str) -> bool:
    return bool(
        len(value) >= 8
        and re.search(r"[A-Z]", value)
        and re.search(r"[a-z]", value)
        and re.search(r"[0-9]", value)
    )


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)

    @model_validator(mode="after")
    def validate_passwords(self):
        if not password_is_strong(self.password):
            raise ValueError(PASSWORD_POLICY_MESSAGE)
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class OtpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class ResendConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class OtpVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    token: str = Field(min_length=6, max_length=10)

    @model_validator(mode="after")
    def validate_token(self):
        stripped = self.token.strip()
        if not re.fullmatch(r"^\d{6}$", stripped):
            raise ValueError("Verification code must be a 6-digit number")
        self.token = stripped
        return self


class OnboardingRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    usn: str | None = Field(default=None, max_length=30)
    branch_id: uuid.UUID
    academic_scheme_id: uuid.UUID
    semester_id: uuid.UUID
    selected_elective_id: uuid.UUID | None = None
    enrollment_year: int = Field(ge=2020, le=2100)


class AdminProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_password(self):
        if not password_is_strong(self.password):
            raise ValueError(PASSWORD_POLICY_MESSAGE)
        return self
