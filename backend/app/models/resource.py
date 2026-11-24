import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.syllabus import VerificationStatus


class ResourceType(str, enum.Enum):
    NOTES = "NOTES"
    STUDY_MATERIAL = "STUDY_MATERIAL"
    REFERENCE = "REFERENCE"
    IMPORTANT_QUESTIONS = "IMPORTANT_QUESTIONS"
    OTHER = "OTHER"


class LearningResource(Base):
    __tablename__ = "learning_resources"
    __table_args__ = (
        CheckConstraint(
            "resource_type IN ('NOTES','STUDY_MATERIAL','REFERENCE','IMPORTANT_QUESTIONS','OTHER')",
            name="ck_learning_resource_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    academic_scheme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_schemes.id", ondelete="CASCADE"), nullable=False
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semesters.id", ondelete="CASCADE"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False, default=ResourceType.NOTES.value)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"),
        nullable=False,
        default=VerificationStatus.DRAFT,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
