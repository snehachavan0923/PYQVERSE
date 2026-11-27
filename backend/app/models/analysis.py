import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AnalysisJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    CLASSIFYING = "CLASSIFYING"
    MAPPING = "MAPPING"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    FLAGGED_REVIEW = "FLAGGED_REVIEW"


class RepeatCategory(str, enum.Enum):
    EXACT_REPEAT = "EXACT_REPEAT"
    REWORDED_REPEAT = "REWORDED_REPEAT"
    SAME_TOPIC_DIFFERENT_QUESTION = "SAME_TOPIC_DIFFERENT_QUESTION"
    RELATED_CONCEPT = "RELATED_CONCEPT"


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("ix_analysis_jobs_paper_status", "question_paper_id", "status"),
        Index("ix_analysis_jobs_doc", "uploaded_document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question_papers.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("uploaded_documents.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[AnalysisJobStatus] = mapped_column(
        Enum(AnalysisJobStatus, name="analysis_job_status"),
        nullable=False,
        default=AnalysisJobStatus.PENDING,
    )
    stage: Mapped[str | None] = mapped_column(String(200))
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mapped_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flagged_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_confidence: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(String(200))
    model_provider: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class QuestionClassification(Base):
    __tablename__ = "question_classifications"
    __table_args__ = (
        Index("ix_question_classifications_question", "question_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    main_topic: Mapped[str | None] = mapped_column(String(300))
    subtopic: Mapped[str | None] = mapped_column(String(300))
    related_concepts: Mapped[list | None] = mapped_column(JSONB)
    question_type: Mapped[str | None] = mapped_column(String(50))
    difficulty: Mapped[str | None] = mapped_column(String(20))
    bloom_taxonomy: Mapped[str | None] = mapped_column(String(50))
    unit_number: Mapped[int | None] = mapped_column(Integer)
    suggested_unit_title: Mapped[str | None] = mapped_column(String(300))
    suggested_topic_title: Mapped[str | None] = mapped_column(String(300))
    confidence: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[str | None] = mapped_column(Text)
    provisional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_name: Mapped[str | None] = mapped_column(String(200))
    model_provider: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class QuestionSimilarity(Base):
    __tablename__ = "question_similarities"
    __table_args__ = (
        UniqueConstraint("source_question_id", "target_question_id", name="uq_question_pair_similarity"),
        Index("ix_question_similarities_source", "source_question_id"),
        Index("ix_question_similarities_target", "target_question_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    target_question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    repeat_category: Mapped[RepeatCategory] = mapped_column(
        Enum(RepeatCategory, name="repeat_category"),
        nullable=False,
        default=RepeatCategory.RELATED_CONCEPT,
    )
    explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class SubjectAnalysisSummary(Base):
    __tablename__ = "subject_analysis_summaries"
    __table_args__ = (
        Index("ix_subject_analysis_summaries_subject", "subject_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    total_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit_stats: Mapped[list | None] = mapped_column(JSONB)
    topic_insights: Mapped[list | None] = mapped_column(JSONB)
    repeated_question_clusters: Mapped[list | None] = mapped_column(JSONB)
    recommendations: Mapped[dict | None] = mapped_column(JSONB)
    calculated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
