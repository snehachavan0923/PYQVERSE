"""phase 6 academic foundation

Revision ID: 6f8a2c9d1b40
Revises: a4e1c3d7f902
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "6f8a2c9d1b40"
down_revision: Union[str, Sequence[str], None] = "a4e1c3d7f902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("academic_schemes", sa.Column("valid_from", sa.Date(), nullable=True))
    op.add_column("academic_schemes", sa.Column("valid_to", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_scheme_validity_range",
        "academic_schemes",
        "valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from",
    )

    subject_columns = (
        ("course_category", sa.String(length=100)),
        ("course_delivery", sa.String(length=30)),
        ("lecture_credits", sa.Integer()),
        ("tutorial_credits", sa.Integer()),
        ("practical_credits", sa.Integer()),
        ("lecture_hours", sa.Integer()),
        ("tutorial_hours", sa.Integer()),
        ("practical_hours", sa.Integer()),
        ("self_study_hours", sa.Integer()),
        ("practical_component_summary", sa.Text()),
        ("source_document_reference", sa.Text()),
        ("source_page_start", sa.Integer()),
        ("source_page_end", sa.Integer()),
        ("source_verification_status", sa.String(length=20)),
        ("source_notes", sa.Text()),
    )
    for column_name, column_type in subject_columns:
        op.add_column("subjects", sa.Column(column_name, column_type, nullable=True))
    op.create_check_constraint(
        "ck_subject_source_status",
        "subjects",
        "source_verification_status IS NULL OR source_verification_status IN "
        "('VERIFIED','NEEDS_REVIEW','NOT_AVAILABLE')",
    )
    op.create_check_constraint(
        "ck_subject_source_page_range",
        "subjects",
        "source_page_start IS NULL OR source_page_end IS NULL OR source_page_end >= source_page_start",
    )
    op.create_check_constraint(
        "ck_subject_credit_hours_nonnegative",
        "subjects",
        "(lecture_credits IS NULL OR lecture_credits >= 0) AND "
        "(tutorial_credits IS NULL OR tutorial_credits >= 0) AND "
        "(practical_credits IS NULL OR practical_credits >= 0) AND "
        "(lecture_hours IS NULL OR lecture_hours >= 0) AND "
        "(tutorial_hours IS NULL OR tutorial_hours >= 0) AND "
        "(practical_hours IS NULL OR practical_hours >= 0) AND "
        "(self_study_hours IS NULL OR self_study_hours >= 0)",
    )
    op.create_check_constraint(
        "ck_subject_course_delivery",
        "subjects",
        "course_delivery IS NULL OR course_delivery IN "
        "('THEORY','PRACTICAL','THEORY_AND_PRACTICAL')",
    )

    op.create_table(
        "branch_subject_offerings",
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("branch_id", "subject_id"),
    )
    op.create_index(
        "ix_branch_subject_offerings_subject",
        "branch_subject_offerings",
        ["subject_id"],
    )

    op.add_column(
        "elective_baskets",
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_elective_baskets_branch",
        "elective_baskets",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("uq_elective_basket", "elective_baskets", type_="unique")
    op.create_index(
        "uq_elective_basket_shared",
        "elective_baskets",
        ["academic_scheme_id", "semester_id", "name"],
        unique=True,
        postgresql_where=sa.text("branch_id IS NULL"),
    )
    op.create_index(
        "uq_elective_basket_branch",
        "elective_baskets",
        ["academic_scheme_id", "semester_id", "branch_id", "name"],
        unique=True,
        postgresql_where=sa.text("branch_id IS NOT NULL"),
    )

    version_columns = (
        ("source_page_start", sa.Integer()),
        ("source_page_end", sa.Integer()),
        ("source_verification_status", sa.String(length=20)),
        ("source_text_imported", sa.Boolean()),
    )
    for column_name, column_type in version_columns:
        op.add_column(
            "syllabus_versions",
            sa.Column(
                column_name,
                column_type,
                server_default=sa.text("false") if column_name == "source_text_imported" else None,
                nullable=False if column_name == "source_text_imported" else True,
            ),
        )
    op.create_check_constraint(
        "ck_syllabus_version_source_status",
        "syllabus_versions",
        "source_verification_status IS NULL OR source_verification_status IN "
        "('VERIFIED','NEEDS_REVIEW','NOT_AVAILABLE')",
    )
    op.create_check_constraint(
        "ck_syllabus_version_source_page_range",
        "syllabus_versions",
        "source_page_start IS NULL OR source_page_end IS NULL OR source_page_end >= source_page_start",
    )

    op.add_column("units", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("units", sa.Column("duration_hours", sa.Integer(), nullable=True))
    op.add_column("units", sa.Column("source_page_number", sa.Integer(), nullable=True))
    op.add_column("units", sa.Column("source_verification_status", sa.String(length=20), nullable=True))
    op.drop_constraint("uq_units_subject_order", "units", type_="unique")
    op.create_index(
        "uq_units_version_order",
        "units",
        ["syllabus_version_id", "order_index"],
        unique=True,
        postgresql_where=sa.text("syllabus_version_id IS NOT NULL"),
    )
    op.create_index(
        "uq_units_legacy_subject_order",
        "units",
        ["subject_id", "order_index"],
        unique=True,
        postgresql_where=sa.text("syllabus_version_id IS NULL"),
    )
    op.create_check_constraint(
        "ck_unit_duration_nonnegative",
        "units",
        "duration_hours IS NULL OR duration_hours >= 0",
    )
    op.create_check_constraint(
        "ck_unit_source_status",
        "units",
        "source_verification_status IS NULL OR source_verification_status IN "
        "('VERIFIED','NEEDS_REVIEW','NOT_AVAILABLE')",
    )

    op.add_column(
        "topics",
        sa.Column("kind", sa.String(length=20), server_default=sa.text("'SYLLABUS'"), nullable=False),
    )
    op.add_column("topics", sa.Column("source_page_number", sa.Integer(), nullable=True))
    op.add_column("topics", sa.Column("source_verification_status", sa.String(length=20), nullable=True))
    op.create_check_constraint(
        "ck_topic_kind",
        "topics",
        "kind IN ('SYLLABUS','SELF_LEARNING','PRACTICAL')",
    )
    op.create_check_constraint(
        "ck_topic_source_status",
        "topics",
        "source_verification_status IS NULL OR source_verification_status IN "
        "('VERIFIED','NEEDS_REVIEW','NOT_AVAILABLE')",
    )

    op.add_column("subtopics", sa.Column("source_page_number", sa.Integer(), nullable=True))
    op.add_column("subtopics", sa.Column("source_verification_status", sa.String(length=20), nullable=True))
    op.create_unique_constraint("uq_subtopics_topic_order", "subtopics", ["topic_id", "order_index"])
    op.create_check_constraint(
        "ck_subtopic_source_status",
        "subtopics",
        "source_verification_status IS NULL OR source_verification_status IN "
        "('VERIFIED','NEEDS_REVIEW','NOT_AVAILABLE')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_subtopic_source_status", "subtopics", type_="check")
    op.drop_constraint("uq_subtopics_topic_order", "subtopics", type_="unique")
    op.drop_column("subtopics", "source_verification_status")
    op.drop_column("subtopics", "source_page_number")

    op.drop_constraint("ck_topic_source_status", "topics", type_="check")
    op.drop_constraint("ck_topic_kind", "topics", type_="check")
    op.drop_column("topics", "source_verification_status")
    op.drop_column("topics", "source_page_number")
    op.drop_column("topics", "kind")

    op.drop_constraint("ck_unit_source_status", "units", type_="check")
    op.drop_constraint("ck_unit_duration_nonnegative", "units", type_="check")
    op.drop_index("uq_units_legacy_subject_order", table_name="units")
    op.drop_index("uq_units_version_order", table_name="units")
    op.create_unique_constraint(
        "uq_units_subject_order", "units", ["subject_id", "order_index"]
    )
    op.drop_column("units", "source_verification_status")
    op.drop_column("units", "source_page_number")
    op.drop_column("units", "duration_hours")
    op.drop_column("units", "description")

    op.drop_constraint(
        "ck_syllabus_version_source_page_range", "syllabus_versions", type_="check"
    )
    op.drop_constraint(
        "ck_syllabus_version_source_status", "syllabus_versions", type_="check"
    )
    op.drop_column("syllabus_versions", "source_text_imported")
    op.drop_column("syllabus_versions", "source_verification_status")
    op.drop_column("syllabus_versions", "source_page_end")
    op.drop_column("syllabus_versions", "source_page_start")

    op.drop_index("uq_elective_basket_branch", table_name="elective_baskets")
    op.drop_index("uq_elective_basket_shared", table_name="elective_baskets")
    op.create_unique_constraint(
        "uq_elective_basket",
        "elective_baskets",
        ["academic_scheme_id", "semester_id", "name"],
    )
    op.drop_constraint("fk_elective_baskets_branch", "elective_baskets", type_="foreignkey")
    op.drop_column("elective_baskets", "branch_id")

    op.drop_index("ix_branch_subject_offerings_subject", table_name="branch_subject_offerings")
    op.drop_table("branch_subject_offerings")

    op.drop_constraint("ck_subject_course_delivery", "subjects", type_="check")
    op.drop_constraint("ck_subject_credit_hours_nonnegative", "subjects", type_="check")
    op.drop_constraint("ck_subject_source_page_range", "subjects", type_="check")
    op.drop_constraint("ck_subject_source_status", "subjects", type_="check")
    for column_name in (
        "source_verification_status",
        "source_notes",
        "source_page_end",
        "source_page_start",
        "source_document_reference",
        "practical_component_summary",
        "self_study_hours",
        "practical_hours",
        "tutorial_hours",
        "lecture_hours",
        "practical_credits",
        "tutorial_credits",
        "lecture_credits",
        "course_delivery",
        "course_category",
    ):
        op.drop_column("subjects", column_name)

    op.drop_constraint("ck_scheme_validity_range", "academic_schemes", type_="check")
    op.drop_column("academic_schemes", "valid_to")
    op.drop_column("academic_schemes", "valid_from")
