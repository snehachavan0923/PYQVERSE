import uuid

from pydantic import BaseModel, ConfigDict


class BranchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    code: str
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
    semester_id: uuid.UUID
    academic_scheme_id: uuid.UUID
    active: bool


class UnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    order_index: int
    active: bool


class TopicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    order_index: int
    active: bool
