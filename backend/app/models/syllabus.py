import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
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
    source_page_start: Mapped[int | None] = mapped_column(Integer)
    source_page_end: Mapped[int | None] = mapped_column(Integer)
    source_verification_status: Mapped[str | None] = mapped_column(String(20))
    source_text_imported: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    __table_args__ = (
        UniqueConstraint("subject_id", "version", name="uq_syllabus_subject_version"),
        Index("ix_syllabus_versions_subject", "subject_id"),
        CheckConstraint(
            "source_verification_status IS NULL OR source_verification_status IN "
            "('VERIFIED','NEEDS_REVIEW','NOT_AVAILABLE')",
            name="ck_syllabus_version_source_status",
        ),
        CheckConstraint(
            "source_page_start IS NULL OR source_page_end IS NULL OR source_page_end >= source_page_start",
            name="ck_syllabus_version_source_page_range",
        ),
    )


class SyllabusDocument(Base):
    __tablename__ = "syllabus_documents"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("syllabus_versions.id", ondelete="CASCADE"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
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
    description: Mapped[str | None] = mapped_column(Text)
    duration_hours: Mapped[int | None] = mapped_column(Integer)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_page_number: Mapped[int | None] = mapped_column(Integer)
    source_verification_status: Mapped[str | None] = mapped_column(String(20))
    verification_status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus, name="verification_status"), nullable=False, default=VerificationStatus.DRAFT)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (
        Index(
            "uq_units_version_order",
            "syllabus_version_id",
            "order_index",
            unique=True,
            postgresql_where=text("syllabus_version_id IS NOT NULL"),
            sqlite_where=text("syllabus_version_id IS NOT NULL"),
        ),
        Index(
            "uq_units_legacy_subject_order",
            "subject_id",
            "order_index",
            unique=True,
            postgresql_where=text("syllabus_version_id IS NULL"),
            sqlite_where=text("syllabus_version_id IS NULL"),
        ),
        CheckConstraint("duration_hours IS NULL OR duration_hours >= 0", name="ck_unit_duration_nonnegative"),
        CheckConstraint(
            "source_verification_status IS NULL OR source_verification_status IN "
            "('VERIFIED','NEEDS_REVIEW','NOT_AVAILABLE')",
            name="ck_unit_source_status",
        ),
    )


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="SYLLABUS")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_page_number: Mapped[int | None] = mapped_column(Integer)
    source_verification_status: Mapped[str | None] = mapped_column(String(20))
    verification_status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus, name="verification_status"), nullable=False, default=VerificationStatus.DRAFT)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (
        UniqueConstraint("unit_id", "order_index", name="uq_topics_unit_order"),
        CheckConstraint("kind IN ('SYLLABUS','SELF_LEARNING','PRACTICAL')", name="ck_topic_kind"),
        CheckConstraint(
            "source_verification_status IS NULL OR source_verification_status IN "
            "('VERIFIED','NEEDS_REVIEW','NOT_AVAILABLE')",
            name="ck_topic_source_status",
        ),
    )


class Subtopic(Base):
    __tablename__ = "subtopics"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_page_number: Mapped[int | None] = mapped_column(Integer)
    source_verification_status: Mapped[str | None] = mapped_column(String(20))
    verification_status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus, name="verification_status"), nullable=False, default=VerificationStatus.DRAFT)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (
        UniqueConstraint("topic_id", "order_index", name="uq_subtopics_topic_order"),
        CheckConstraint(
            "source_verification_status IS NULL OR source_verification_status IN "
            "('VERIFIED','NEEDS_REVIEW','NOT_AVAILABLE')",
            name="ck_subtopic_source_status",
        ),
    )
