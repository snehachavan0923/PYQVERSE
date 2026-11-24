"""phase 4 content management and learning resources

Revision ID: 7c3f9a2b5d10
Revises: 1a7d8c2f4e91

Additive only: existing catalog, user and authentication data is preserved.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "7c3f9a2b5d10"
down_revision: Union[str, Sequence[str], None] = "1a7d8c2f4e91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "uploaded_documents",
        sa.Column("title", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "uploaded_documents",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "uploaded_documents",
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "question_papers",
        sa.Column("title", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "question_papers",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "subjects",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "subjects",
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.add_column(
        "subjects",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.create_table(
        "learning_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("academic_scheme_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(length=30), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column(
            "verification_status",
            postgresql.ENUM(
                "DRAFT", "PENDING", "VERIFIED", "REJECTED",
                name="verification_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint(
            "resource_type IN ('NOTES','STUDY_MATERIAL','REFERENCE','IMPORTANT_QUESTIONS','OTHER')",
            name="ck_learning_resource_type",
        ),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["academic_scheme_id"], ["academic_schemes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["semester_id"], ["semesters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_learning_resources_subject", "learning_resources", ["subject_id"])
    op.create_index(
        "ix_learning_resources_subject_status",
        "learning_resources",
        ["subject_id", "verification_status"],
    )
    op.create_index(
        "ix_question_papers_subject_year",
        "question_papers",
        ["subject_id", "examination_year"],
    )
    op.create_index(
        "ix_uploaded_documents_subject_status",
        "uploaded_documents",
        ["subject_id", "verification_status"],
    )
    op.create_index("ix_syllabus_versions_subject", "syllabus_versions", ["subject_id"])


def downgrade() -> None:
    op.drop_index("ix_syllabus_versions_subject", table_name="syllabus_versions")
    op.drop_index("ix_uploaded_documents_subject_status", table_name="uploaded_documents")
    op.drop_index("ix_question_papers_subject_year", table_name="question_papers")
    op.drop_index("ix_learning_resources_subject_status", table_name="learning_resources")
    op.drop_index("ix_learning_resources_subject", table_name="learning_resources")
    op.drop_table("learning_resources")

    op.drop_column("subjects", "updated_at")
    op.drop_column("subjects", "created_at")
    op.drop_column("subjects", "description")
    op.drop_column("question_papers", "description")
    op.drop_column("question_papers", "title")
    op.drop_column("uploaded_documents", "active")
    op.drop_column("uploaded_documents", "description")
    op.drop_column("uploaded_documents", "title")
