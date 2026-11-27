"""AI analysis engine models and tables

Revision ID: e8b1c4d7f2a3
Revises: c734a9e25f61
"""

from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "e8b1c4d7f2a3"
down_revision: Union[str, Sequence[str], None] = "c734a9e25f61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enums
    analysis_job_status_enum = postgresql.ENUM(
        "PENDING",
        "EXTRACTING",
        "CLASSIFYING",
        "MAPPING",
        "ANALYZING",
        "COMPLETED",
        "FAILED",
        "FLAGGED_REVIEW",
        name="analysis_job_status",
        create_type=False,
    )
    analysis_job_status_enum.create(op.get_bind(), checkfirst=True)

    repeat_category_enum = postgresql.ENUM(
        "EXACT_REPEAT",
        "REWORDED_REPEAT",
        "SAME_TOPIC_DIFFERENT_QUESTION",
        "RELATED_CONCEPT",
        name="repeat_category",
        create_type=False,
    )
    repeat_category_enum.create(op.get_bind(), checkfirst=True)

    # 2. analysis_jobs table
    op.create_table(
        "analysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_paper_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("question_papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("uploaded_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", analysis_job_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("stage", sa.String(length=200), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mapped_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flagged_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("average_confidence", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("model_provider", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_analysis_jobs_paper_status", "analysis_jobs", ["question_paper_id", "status"])
    op.create_index("ix_analysis_jobs_doc", "analysis_jobs", ["uploaded_document_id"])

    # 3. question_classifications table
    op.create_table(
        "question_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questions.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("main_topic", sa.String(length=300), nullable=True),
        sa.Column("subtopic", sa.String(length=300), nullable=True),
        sa.Column("related_concepts", postgresql.JSONB(), nullable=True),
        sa.Column("question_type", sa.String(length=50), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=True),
        sa.Column("bloom_taxonomy", sa.String(length=50), nullable=True),
        sa.Column("unit_number", sa.Integer(), nullable=True),
        sa.Column("suggested_unit_title", sa.String(length=300), nullable=True),
        sa.Column("suggested_topic_title", sa.String(length=300), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("provisional", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("model_provider", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_question_classifications_question", "question_classifications", ["question_id"])

    # 4. question_similarities table
    op.create_table(
        "question_similarities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("repeat_category", repeat_category_enum, nullable=False, server_default="RELATED_CONCEPT"),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("source_question_id", "target_question_id", name="uq_question_pair_similarity"),
    )
    op.create_index("ix_question_similarities_source", "question_similarities", ["source_question_id"])
    op.create_index("ix_question_similarities_target", "question_similarities", ["target_question_id"])

    # 5. subject_analysis_summaries table
    op.create_table(
        "subject_analysis_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("total_papers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("unit_stats", postgresql.JSONB(), nullable=True),
        sa.Column("topic_insights", postgresql.JSONB(), nullable=True),
        sa.Column("repeated_question_clusters", postgresql.JSONB(), nullable=True),
        sa.Column("recommendations", postgresql.JSONB(), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_subject_analysis_summaries_subject", "subject_analysis_summaries", ["subject_id"])


def downgrade() -> None:
    op.drop_table("subject_analysis_summaries")
    op.drop_table("question_similarities")
    op.drop_table("question_classifications")
    op.drop_table("analysis_jobs")
    op.execute("DROP TYPE IF EXISTS repeat_category")
    op.execute("DROP TYPE IF EXISTS analysis_job_status")
