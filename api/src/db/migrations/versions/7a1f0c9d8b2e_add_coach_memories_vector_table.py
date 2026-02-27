"""add coach memories vector table

Revision ID: 7a1f0c9d8b2e
Revises: 3b2f0f4f2c71
Create Date: 2026-02-27 11:20:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a1f0c9d8b2e"
down_revision: Union[str, None] = "3b2f0f4f2c71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS coach_memories (
            id UUID PRIMARY KEY,
            conversation_id UUID NULL REFERENCES conversations(id) ON DELETE SET NULL,
            source_message_id UUID UNIQUE NULL REFERENCES messages(id) ON DELETE SET NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding vector(256) NOT NULL,
            metadata JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_coach_memories_created_at
            ON coach_memories (created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_coach_memories_conversation_id
            ON coach_memories (conversation_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_coach_memories_embedding_cosine
            ON coach_memories
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_coach_memories_embedding_cosine")
    op.execute("DROP INDEX IF EXISTS ix_coach_memories_conversation_id")
    op.execute("DROP INDEX IF EXISTS ix_coach_memories_created_at")
    op.execute("DROP TABLE IF EXISTS coach_memories")
