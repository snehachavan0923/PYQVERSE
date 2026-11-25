"""add content hashes for question papers

Revision ID: c734a9e25f61
Revises: d9e7a5c1f3b2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c734a9e25f61"
down_revision: Union[str, Sequence[str], None] = "d9e7a5c1f3b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "uploaded_documents",
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_uploaded_documents_active_content_sha256",
        "uploaded_documents",
        ["content_sha256"],
        unique=True,
        postgresql_where=sa.text("active IS TRUE AND content_sha256 IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_uploaded_documents_active_content_sha256",
        table_name="uploaded_documents",
    )
    op.drop_column("uploaded_documents", "content_sha256")
