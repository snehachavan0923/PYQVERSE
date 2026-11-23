"""phase 4 content and resources

Revision ID: 8c3f1d2a7b60
Revises: 1a7d8c2f4e91
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8c3f1d2a7b60"
down_revision: Union[str, Sequence[str], None] = "1a7d8c2f4e91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("uploaded_documents", sa.Column("title", sa.String(length=300), nullable=True))
    op.add_column("uploaded_documents", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("uploaded_documents", sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("question_papers", sa.Column("title", sa.String(length=300), nullable=True))
    op.add_column("question_papers", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("question_papers", sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("question_papers", sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_question_papers_uploaded_by", "question_papers", "users", ["uploaded_by"], ["id"], ondelete="SET NULL")
    op.add_column("syllabus_documents", sa.Column("title", sa.String(length=300), nullable=True))
    op.add_column("syllabus_documents", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("syllabus_documents", sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("syllabus_documents", sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_syllabus_documents_uploaded_by", "syllabus_documents", "users", ["uploaded_by"], ["id"], ondelete="SET NULL")
    op.create_table(
        "learning_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=30), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["semester_id"], ["semesters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_resources_subject_published", "learning_resources", ["subject_id", "published"])


def downgrade() -> None:
    op.drop_index("ix_learning_resources_subject_published", table_name="learning_resources")
    op.drop_table("learning_resources")
    op.drop_constraint("fk_syllabus_documents_uploaded_by", "syllabus_documents", type="foreignkey")
    op.drop_column("syllabus_documents", "uploaded_by")
    op.drop_column("syllabus_documents", "published")
    op.drop_column("syllabus_documents", "description")
    op.drop_column("syllabus_documents", "title")
    op.drop_constraint("fk_question_papers_uploaded_by", "question_papers", type="foreignkey")
    op.drop_column("question_papers", "uploaded_by")
    op.drop_column("question_papers", "published")
    op.drop_column("question_papers", "description")
    op.drop_column("question_papers", "title")
    op.drop_column("uploaded_documents", "published")
    op.drop_column("uploaded_documents", "description")
    op.drop_column("uploaded_documents", "title")
