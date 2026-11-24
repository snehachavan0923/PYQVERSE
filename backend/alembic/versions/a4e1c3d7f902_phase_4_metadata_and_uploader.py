"""phase 4 syllabus metadata and uploader nullability

Revision ID: a4e1c3d7f902
Revises: 7c3f9a2b5d10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4e1c3d7f902"
down_revision: Union[str, Sequence[str], None] = "7c3f9a2b5d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("syllabus_documents", sa.Column("title", sa.String(length=300), nullable=True))
    op.add_column("syllabus_documents", sa.Column("description", sa.Text(), nullable=True))
    op.alter_column("learning_resources", "uploaded_by", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM learning_resources WHERE uploaded_by IS NULL")
    op.alter_column("learning_resources", "uploaded_by", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("syllabus_documents", "description")
    op.drop_column("syllabus_documents", "title")
