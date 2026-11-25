"""merge the Phase 6 academic and learning migration branches

Revision ID: d9e7a5c1f3b2
Revises: b6d2f8a1c947, 6f8a2c9d1b40
"""

from typing import Sequence, Union

revision: str = "d9e7a5c1f3b2"
down_revision: Union[str, Sequence[str], None] = (
    "b6d2f8a1c947",
    "6f8a2c9d1b40",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
