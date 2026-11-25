import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class BranchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    code: str
    active: bool


class AcademicSchemeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    code: str
    valid_from: date | None = None
    valid_to: date | None = None
    active: bool


class SemesterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    academic_scheme_id: uuid.UUID
    number: int
    name: str
    active: bool


class SubjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    subject_type: str
    credits: int | None = None
    description: str | None = None
    course_category: str | None = None
    course_delivery: str | None = None
    lecture_credits: int | None = None
    tutorial_credits: int | None = None
    practical_credits: int | None = None
    lecture_hours: int | None = None
    tutorial_hours: int | None = None
    practical_hours: int | None = None
    self_study_hours: int | None = None
    practical_component_summary: str | None = None
    source_document_reference: str | None = None
    source_page_start: int | None = None
    source_page_end: int | None = None
    source_verification_status: str | None = None
    source_notes: str | None = None
    semester_id: uuid.UUID
    academic_scheme_id: uuid.UUID
    active: bool


class UnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    order_index: int
    duration_hours: int | None = None
    description: str | None = None
    source_page_number: int | None = None
    source_verification_status: str | None = None
    active: bool


class TopicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    kind: str
    order_index: int
    source_page_number: int | None = None
    source_verification_status: str | None = None
    active: bool


class SubtopicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    order_index: int
    source_page_number: int | None = None
    source_verification_status: str | None = None
    active: bool
