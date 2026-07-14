"""add priority to races

Revision ID: 4e7b2a1c9d30
Revises: c3f86b2dd4a1
Create Date: 2026-07-14 14:20:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4e7b2a1c9d30"
down_revision: Union[str, None] = "c3f86b2dd4a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The column may already exist in databases initialized from the ORM
    # schema before this migration was added. Keep the upgrade safe there.
    op.execute(
        "ALTER TABLE races "
        "ADD COLUMN IF NOT EXISTS priority TEXT"
    )
    op.execute(
        "UPDATE races SET priority = 'B' WHERE priority IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE races DROP COLUMN IF EXISTS priority")
