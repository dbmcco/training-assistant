"""Long-term coach memory storage and retrieval using Postgres vectors."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings

TOKEN_RE = re.compile(r"[a-z0-9']+")


async def memory_table_available(db: AsyncSession) -> bool:
    if not settings.coach_memory_enabled:
        return False
    result = await db.execute(text("SELECT to_regclass('public.coach_memories')"))
    return result.scalar_one_or_none() is not None


def embed_text(text_value: str, *, dim: int | None = None) -> list[float]:
    """Create a compact deterministic embedding for vector retrieval."""
    size = dim or settings.coach_memory_embedding_dim
    if size <= 0:
        return []

    tokens = TOKEN_RE.findall(text_value.lower())
    if not tokens:
        return [0.0] * size

    vec = [0.0] * size
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest, byteorder="big")
        idx = bucket % size
        sign = -1.0 if ((bucket >> 1) & 1) else 1.0
        weight = 1.0 + min(len(token), 16) * 0.03
        vec[idx] += sign * weight

    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return [0.0] * size
    return [v / norm for v in vec]


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


def _normalize_memory_text(content: str, max_chars: int = 1800) -> str:
    cleaned = " ".join(content.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars].rstrip()}..."


async def search_relevant_memories(
    db: AsyncSession,
    query_text: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if not query_text.strip() or not await memory_table_available(db):
        return []

    top_k = max(1, min(limit or settings.coach_memory_retrieval_limit, 12))
    query_embedding = _vector_literal(embed_text(query_text))
    total_count = (
        await db.execute(text("SELECT count(*) FROM coach_memories"))
    ).scalar_one()

    if int(total_count or 0) < 2000:
        # For small datasets, force exact scan. IVF approximate index can return
        # sparse/empty results with tiny tables.
        await db.execute(text("SET LOCAL enable_indexscan = off"))
        await db.execute(text("SET LOCAL enable_bitmapscan = off"))

    result = await db.execute(
        text(
            """
            SELECT
                id::text AS id,
                role,
                content,
                metadata,
                created_at,
                (embedding <=> CAST(:embedding AS vector)) AS distance
            FROM coach_memories
            ORDER BY embedding <=> CAST(:embedding AS vector) ASC, created_at DESC
            LIMIT :limit
            """
        ),
        {
            "embedding": query_embedding,
            "limit": top_k,
        },
    )

    rows = result.mappings().all()
    memories: list[dict[str, Any]] = []
    for row in rows:
        memories.append(
            {
                "id": row.get("id"),
                "role": row.get("role"),
                "content": row.get("content"),
                "metadata": row.get("metadata"),
                "created_at": row.get("created_at"),
                "distance": float(row.get("distance") or 0.0),
            }
        )
    return memories


async def sync_missing_conversation_memories(
    db: AsyncSession,
    *,
    conversation_id: str,
    limit_messages: int | None = None,
) -> int:
    """Backfill missing message memories for a conversation."""
    if not conversation_id or not await memory_table_available(db):
        return 0

    limit_count = max(
        1,
        min(limit_messages or settings.coach_memory_backfill_limit_messages, 5000),
    )
    missing_result = await db.execute(
        text(
            """
            SELECT
                m.id::text AS message_id,
                m.role AS role,
                m.content AS content,
                m.created_at AS created_at
            FROM messages m
            LEFT JOIN coach_memories cm
              ON cm.source_message_id = m.id
            WHERE m.conversation_id = CAST(:conversation_id AS uuid)
              AND cm.source_message_id IS NULL
            ORDER BY m.created_at ASC
            LIMIT :limit_messages
            """
        ),
        {
            "conversation_id": conversation_id,
            "limit_messages": limit_count,
        },
    )
    missing_rows = missing_result.mappings().all()
    if not missing_rows:
        return 0

    inserted = 0
    for row in missing_rows:
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        normalized = _normalize_memory_text(content)
        embedding = _vector_literal(embed_text(normalized))
        metadata = {
            "source": "chat_message",
            "conversation_id": conversation_id,
            "source_message_id": row.get("message_id"),
        }
        created_at = row.get("created_at") or datetime.now(timezone.utc)

        await db.execute(
            text(
                """
                INSERT INTO coach_memories (
                    id,
                    conversation_id,
                    source_message_id,
                    role,
                    content,
                    embedding,
                    metadata,
                    created_at
                ) VALUES (
                    CAST(:id AS uuid),
                    CAST(:conversation_id AS uuid),
                    CAST(:source_message_id AS uuid),
                    :role,
                    :content,
                    CAST(:embedding AS vector),
                    CAST(:metadata AS jsonb),
                    :created_at
                )
                ON CONFLICT (source_message_id) DO NOTHING
                """
            ),
            {
                "id": str(uuid4()),
                "conversation_id": conversation_id,
                "source_message_id": row.get("message_id"),
                "role": row.get("role") or "assistant",
                "content": normalized,
                "embedding": embedding,
                "metadata": json.dumps(metadata),
                "created_at": created_at,
            },
        )
        inserted += 1

    return inserted
