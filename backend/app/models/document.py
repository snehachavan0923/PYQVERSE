import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.syllabus import VerificationStatus


class ExamType(str, enum.Enum):
    CIE = "CIE"
    SEE = "SEE"


class PermissionStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(String(30), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"))
    academic_scheme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_schemes.id", ondelete="SET NULL"))
    semester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("semesters.id", ondelete="SET NULL"))
    exam_type: Mapped[ExamType] = mapped_column(Enum(ExamType, name="exam_type"), nullable=False)
    cie_number: Mapped[int | None] = mapped_column(Integer)
    examination_year: Mapped[int | None] = mapped_column(Integer)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    source: Mapped[str | None] = mapped_column(Text)
    permission_status: Mapped[PermissionStatus] = mapped_column(Enum(PermissionStatus, name="permission_status"), nullable=False, default=PermissionStatus.PENDING)
    verification_status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus, name="verification_status"), nullable=False, default=VerificationStatus.DRAFT)


class QuestionPaper(Base):
    __tablename__ = "question_papers"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uploaded_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploaded_documents.id", ondelete="CASCADE"), unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    academic_scheme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_schemes.id", ondelete="CASCADE"), nullable=False)
    semester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), nullable=False)
    exam_type: Mapped[ExamType] = mapped_column(Enum(ExamType, name="exam_type"), nullable=False)
    cie_number: Mapped[int | None] = mapped_column(Integer)
    examination_year: Mapped[int | None] = mapped_column(Integer)
