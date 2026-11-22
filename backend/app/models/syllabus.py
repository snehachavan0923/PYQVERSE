import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class VerificationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class SyllabusVersion(Base):
    __tablename__ = "syllabus_versions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    academic_scheme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_schemes.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus, name="verification_status"), nullable=False, default=VerificationStatus.DRAFT)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_document_reference: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    __table_args__ = (UniqueConstraint("subject_id", "version", name="uq_syllabus_subject_version"),)


class SyllabusDocument(Base):
    __tablename__ = "syllabus_documents"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("syllabus_versions.id", ondelete="CASCADE"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(30), nullable=False)
    file_size: Mapped[int | None] = mapped_column()
    verification_status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus, name="verification_status"), nullable=False, default=VerificationStatus.DRAFT)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Unit(Base):
    __tablename__ = "units"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    syllabus_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("syllabus_versions.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus, name="verification_status"), nullable=False, default=VerificationStatus.DRAFT)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("subject_id", "order_index", name="uq_units_subject_order"),)


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus, name="verification_status"), nullable=False, default=VerificationStatus.DRAFT)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("unit_id", "order_index", name="uq_topics_unit_order"),)


class Subtopic(Base):
    __tablename__ = "subtopics"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus, name="verification_status"), nullable=False, default=VerificationStatus.DRAFT)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
