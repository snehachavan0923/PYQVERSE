import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class StudentProfile(Base):
    __tablename__ = "student_profiles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    student_name: Mapped[str] = mapped_column(String(200), nullable=False)
    usn: Mapped[str | None] = mapped_column(String(30), unique=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"))
    academic_scheme_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("academic_schemes.id", ondelete="SET NULL"))
    current_semester_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("semesters.id", ondelete="SET NULL"))
    selected_elective_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"))
    enrollment_year: Mapped[int | None] = mapped_column(Integer)
    profile_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    user: Mapped["User"] = relationship(back_populates="student_profile")


class College(Base):
    __tablename__ = "colleges"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("college_id", "code", name="uq_branches_college_code"),)


class AcademicScheme(Base):
    __tablename__ = "academic_schemes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("college_id", "code", name="uq_schemes_college_code"),)


class Semester(Base):
    __tablename__ = "semesters"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    academic_scheme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_schemes.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (
        UniqueConstraint("academic_scheme_id", "number", name="uq_semesters_scheme_number"),
        CheckConstraint("number BETWEEN 1 AND 8", name="ck_semesters_number"),
    )


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    academic_scheme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_schemes.id", ondelete="CASCADE"), nullable=False)
    semester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False, default="CORE")
    credits: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    __table_args__ = (
        UniqueConstraint("academic_scheme_id", "code", name="uq_subjects_scheme_code"),
        CheckConstraint("subject_type IN ('CORE','ELECTIVE')", name="ck_subject_type"),
    )


class ElectiveBasket(Base):
    __tablename__ = "elective_baskets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    academic_scheme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_schemes.id", ondelete="CASCADE"), nullable=False)
    semester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("academic_scheme_id", "semester_id", "name", name="uq_elective_basket"),)


class ElectiveOption(Base):
    __tablename__ = "elective_options"
    basket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("elective_baskets.id", ondelete="CASCADE"), primary_key=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True)


class StudentSubjectEnrollment(Base):
    __tablename__ = "student_subject_enrollments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    semester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), nullable=False)
    academic_scheme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_schemes.id", ondelete="CASCADE"), nullable=False)
    is_elective: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    __table_args__ = (
        UniqueConstraint("student_profile_id", "subject_id", "semester_id", name="uq_student_subject_semester"),
    )
