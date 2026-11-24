import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SyllabusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["DRAFT", "PENDING", "VERIFIED", "REJECTED"] | None = None
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    active: bool | None = None


class PyqUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["DRAFT", "PENDING", "VERIFIED", "REJECTED"] | None = None
    active: bool | None = None


class ResourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    resource_type: Literal["NOTES", "STUDY_MATERIAL", "REFERENCE", "IMPORTANT_QUESTIONS", "OTHER"] | None = None
    status: Literal["DRAFT", "PENDING", "VERIFIED", "REJECTED"] | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def normalize_title(self):
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title:
                raise ValueError("Title is required")
        return self
