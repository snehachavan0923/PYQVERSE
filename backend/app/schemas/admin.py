import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BranchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=1, max_length=30)
    college_id: uuid.UUID | None = None
    active: bool = True


class BranchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=2, max_length=200)
    code: str | None = Field(default=None, min_length=1, max_length=30)
    active: bool | None = None


class SchemeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=1, max_length=30)
    college_id: uuid.UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    active: bool = True

    @model_validator(mode="after")
    def validate_validity(self):
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        return self


class SchemeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=2, max_length=100)
    code: str | None = Field(default=None, min_length=1, max_length=30)
    valid_from: date | None = None
    valid_to: date | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def validate_validity(self):
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        return self


class SemesterCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    academic_scheme_id: uuid.UUID
    number: int = Field(ge=1, le=8)
    name: str = Field(min_length=2, max_length=50)
    active: bool = True


class SemesterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: int | None = Field(default=None, ge=1, le=8)
    name: str | None = Field(default=None, min_length=2, max_length=50)
    active: bool | None = None


class SubjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    academic_scheme_id: uuid.UUID
    semester_id: uuid.UUID
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=2, max_length=300)
    subject_type: Literal["CORE", "ELECTIVE"] = "CORE"
    credits: int | None = Field(default=None, ge=0, le=30)
    description: str | None = Field(default=None, max_length=4000)
    course_category: str | None = Field(default=None, max_length=100)
    course_delivery: Literal["THEORY", "PRACTICAL", "THEORY_AND_PRACTICAL"] | None = None
    lecture_credits: int | None = Field(default=None, ge=0, le=30)
    tutorial_credits: int | None = Field(default=None, ge=0, le=30)
    practical_credits: int | None = Field(default=None, ge=0, le=30)
    lecture_hours: int | None = Field(default=None, ge=0, le=1000)
    tutorial_hours: int | None = Field(default=None, ge=0, le=1000)
    practical_hours: int | None = Field(default=None, ge=0, le=1000)
    self_study_hours: int | None = Field(default=None, ge=0, le=1000)
    practical_component_summary: str | None = Field(default=None, max_length=4000)
    source_document_reference: str | None = Field(default=None, max_length=2000)
    source_page_start: int | None = Field(default=None, ge=1)
    source_page_end: int | None = Field(default=None, ge=1)
    source_verification_status: Literal["VERIFIED", "NEEDS_REVIEW", "NOT_AVAILABLE"] | None = None
    source_notes: str | None = Field(default=None, max_length=4000)
    active: bool = True

    @model_validator(mode="after")
    def normalize(self):
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        if (
            self.source_page_start is not None
            and self.source_page_end is not None
            and self.source_page_end < self.source_page_start
        ):
            raise ValueError("source_page_end must be on or after source_page_start")
        return self


class SubjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semester_id: uuid.UUID | None = None
    code: str | None = Field(default=None, min_length=1, max_length=30)
    name: str | None = Field(default=None, min_length=2, max_length=300)
    subject_type: Literal["CORE", "ELECTIVE"] | None = None
    credits: int | None = Field(default=None, ge=0, le=30)
    description: str | None = Field(default=None, max_length=4000)
    course_category: str | None = Field(default=None, max_length=100)
    course_delivery: Literal["THEORY", "PRACTICAL", "THEORY_AND_PRACTICAL"] | None = None
    lecture_credits: int | None = Field(default=None, ge=0, le=30)
    tutorial_credits: int | None = Field(default=None, ge=0, le=30)
    practical_credits: int | None = Field(default=None, ge=0, le=30)
    lecture_hours: int | None = Field(default=None, ge=0, le=1000)
    tutorial_hours: int | None = Field(default=None, ge=0, le=1000)
    practical_hours: int | None = Field(default=None, ge=0, le=1000)
    self_study_hours: int | None = Field(default=None, ge=0, le=1000)
    practical_component_summary: str | None = Field(default=None, max_length=4000)
    source_document_reference: str | None = Field(default=None, max_length=2000)
    source_page_start: int | None = Field(default=None, ge=1)
    source_page_end: int | None = Field(default=None, ge=1)
    source_verification_status: Literal["VERIFIED", "NEEDS_REVIEW", "NOT_AVAILABLE"] | None = None
    source_notes: str | None = Field(default=None, max_length=4000)
    active: bool | None = None


class ElectiveBasketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    academic_scheme_id: uuid.UUID
    semester_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    name: str = Field(min_length=2, max_length=200)


class BranchSubjectOfferingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: uuid.UUID
    subject_id: uuid.UUID


class ElectiveOptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    basket_id: uuid.UUID
    subject_id: uuid.UUID


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_new_password(self):
        from app.schemas.auth import PASSWORD_POLICY_MESSAGE, password_is_strong

        if not password_is_strong(self.new_password):
            raise ValueError(PASSWORD_POLICY_MESSAGE)
        if self.new_password == self.current_password:
            raise ValueError("New password must differ from the current password")
        return self


class AdminProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(min_length=2, max_length=200)

    @model_validator(mode="after")
    def normalize_name(self):
        self.full_name = " ".join(self.full_name.split())
        if len(self.full_name) < 2:
            raise ValueError("Full name is required")
        return self


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    usn: str | None = Field(default=None, max_length=30)
    branch_id: uuid.UUID | None = None
    academic_scheme_id: uuid.UUID | None = None
    current_semester_id: uuid.UUID | None = None
    selected_elective_id: uuid.UUID | None = None
    enrollment_year: int | None = Field(default=None, ge=2020, le=2100)
