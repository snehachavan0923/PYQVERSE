import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)


class SendOtpRequest(BaseModel):
    email: EmailStr
    purpose: str = Field(pattern="^(login|signup)$", default="signup")


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    token: str = Field(min_length=6, max_length=10)
    purpose: str = Field(pattern="^(login|signup)$", default="signup")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class BootstrapAdminRequest(BaseModel):
    email: EmailStr
    bootstrap_token: str = Field(min_length=8)


class OnboardingRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    usn: str | None = Field(default=None, max_length=30)
    branch_id: uuid.UUID
    academic_scheme_id: uuid.UUID
    semester_id: uuid.UUID
    selected_elective_id: uuid.UUID | None = None
    enrollment_year: int = Field(ge=2020, le=2100)
