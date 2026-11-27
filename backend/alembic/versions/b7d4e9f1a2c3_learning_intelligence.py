"""Question sequencing, PYQ bookmarks and student topic learning

Revision ID: b7d4e9f1a2c3
Revises: f9c2d5e8a1b4
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "b7d4e9f1a2c3"
down_revision: Union[str, Sequence[str], None] = "f9c2d5e8a1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Questions can legitimately repeat a printed question number across pages or
    # combined papers. Use an extraction sequence as the stable identity instead.
    op.drop_constraint("uq_question_document_number", "questions", type_="unique")
    op.add_column(
        "questions",
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_unique_constraint(
        "uq_question_document_sequence", "questions", ["document_id", "sequence"]
    )

    op.create_table(
        "pyq_question_bookmarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "student_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("student_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "student_profile_id", "question_id", name="uq_student_pyq_question_bookmark"
        ),
    )
    op.create_index(
        "ix_pyq_question_bookmarks_student",
        "pyq_question_bookmarks",
        ["student_profile_id"],
    )

    op.create_table(
        "student_topic_learning",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "student_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("student_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("topic_key", sa.String(length=300), nullable=False),
        sa.Column("topic_title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="NOT_STARTED"),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "student_profile_id",
            "subject_id",
            "topic_key",
            name="uq_student_subject_topic_learning",
        ),
        sa.CheckConstraint(
            "status IN ('NOT_STARTED','LEARNING','LEARNED','NEEDS_REVISION')",
            name="ck_student_topic_learning_status",
        ),
    )
    op.create_index(
        "ix_student_topic_learning_student_subject",
        "student_topic_learning",
        ["student_profile_id", "subject_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_student_topic_learning_student_subject", table_name="student_topic_learning"
    )
    op.drop_table("student_topic_learning")
    op.drop_index("ix_pyq_question_bookmarks_student", table_name="pyq_question_bookmarks")
    op.drop_table("pyq_question_bookmarks")
    op.drop_constraint("uq_question_document_sequence", "questions", type_="unique")
    op.drop_column("questions", "sequence")
    op.create_unique_constraint(
        "uq_question_document_number", "questions", ["document_id", "question_number"]
    )
