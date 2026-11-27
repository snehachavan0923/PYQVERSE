"""Support file, link, and both sources for learning resources

Revision ID: f9c2d5e8a1b4
Revises: e8b1c4d7f2a3
"""

from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "f9c2d5e8a1b4"
down_revision: Union[str, Sequence[str], None] = "e8b1c4d7f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Make file columns nullable
    op.alter_column("learning_resources", "storage_path", nullable=True)
    op.alter_column("learning_resources", "original_filename", nullable=True)
    op.alter_column("learning_resources", "file_type", nullable=True)
    op.alter_column("learning_resources", "file_size", nullable=True)

    # 2. Add new columns
    op.add_column(
        "learning_resources",
        sa.Column("resource_source", sa.String(length=20), nullable=False, server_default="FILE"),
    )
    op.add_column(
        "learning_resources",
        sa.Column("external_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "learning_resources",
        sa.Column("link_title", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "learning_resources",
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 3. Create index & constraint
    op.create_index("ix_learning_resources_unit", "learning_resources", ["unit_id"])
    op.create_check_constraint(
        "ck_learning_resource_source",
        "learning_resources",
        "resource_source IN ('FILE','LINK','BOTH')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_learning_resource_source", "learning_resources", type_="check")
    op.drop_index("ix_learning_resources_unit", table_name="learning_resources")
    op.drop_column("learning_resources", "unit_id")
    op.drop_column("learning_resources", "link_title")
    op.drop_column("learning_resources", "external_url")
    op.drop_column("learning_resources", "resource_source")
    op.alter_column("learning_resources", "file_size", nullable=False)
    op.alter_column("learning_resources", "file_type", nullable=False)
    op.alter_column("learning_resources", "original_filename", nullable=False)
    op.alter_column("learning_resources", "storage_path", nullable=False)
