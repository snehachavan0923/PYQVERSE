"""phase 3 auth onboarding

Revision ID: 1a7d8c2f4e91
Revises: 99d74ee0742c
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "1a7d8c2f4e91"
down_revision: Union[str, Sequence[str], None] = "99d74ee0742c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_users_rvce_email", "users", type_="check")
    op.add_column("users", sa.Column("supabase_auth_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_unique_constraint("uq_users_supabase_auth_id", "users", ["supabase_auth_id"])
    op.create_check_constraint(
        "ck_users_role_email",
        "users",
        "(role = 'ADMIN_FACULTY') OR (email ~ '@rvce\\.edu\\.in$')",
    )
    op.add_column("student_profiles", sa.Column("usn", sa.String(length=30), nullable=True))
    op.create_unique_constraint("uq_student_profiles_usn", "student_profiles", ["usn"])

    op.create_table(
        "administrator_bootstrap_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("supabase_auth_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("supabase_auth_id"),
    )


def downgrade() -> None:
    op.drop_table("administrator_bootstrap_records")
    op.drop_constraint("uq_student_profiles_usn", "student_profiles", type_="unique")
    op.drop_column("student_profiles", "usn")
    op.drop_constraint("ck_users_role_email", "users", type_="check")
    op.drop_constraint("uq_users_supabase_auth_id", "users", type_="unique")
    op.drop_column("users", "supabase_auth_id")
    op.create_check_constraint(
        "ck_users_rvce_email",
        "users",
        "email ~ '@rvce\\.edu\\.in$'",
    )
