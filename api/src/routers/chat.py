"""SSE chat endpoint and conversation CRUD routes."""

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from src.agent.coach import run_coach
from src.db.connection import get_db
from src.db.models import Conversation, Message

router = APIRouter(prefix="/api/v1", tags=["chat"])
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    view_context: dict | None = None


# ---------------------------------------------------------------------------
# POST /chat — SSE streaming
# ---------------------------------------------------------------------------


@router.post("/chat")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    async def event_generator():
        try:
            async for event in run_coach(
                user_message=req.message,
                conversation_id=req.conversation_id,
                view_context=req.view_context,
                db=db,
            ):
                yield {"event": event["event"], "data": json.dumps(event["data"])}
        except Exception:
            logger.exception("Unhandled error while streaming chat response")
            yield {
                "event": "done",
                "data": json.dumps({"conversation_id": req.conversation_id, "error": True}),
            }

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# GET /conversations — list
# ---------------------------------------------------------------------------


@router.get("/conversations")
async def list_conversations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation).order_by(Conversation.updated_at.desc())
    )
    conversations = result.scalars().all()
    return [_conversation_to_dict(c) for c in conversations]


# ---------------------------------------------------------------------------
# GET /conversations/{id} — get single with messages
# ---------------------------------------------------------------------------


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    limit: int = Query(default=120, ge=20, le=500),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(msg_result.scalars().all())
    messages.reverse()

    data = _conversation_to_dict(conv)
    data["messages"] = [_message_to_dict(m) for m in messages]
    return data


# ---------------------------------------------------------------------------
# DELETE /conversations/{id}
# ---------------------------------------------------------------------------


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Delete messages first (FK constraint)
    msg_result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
    )
    for msg in msg_result.scalars().all():
        await db.delete(msg)

    await db.delete(conv)
    await db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _conversation_to_dict(conv: Conversation) -> dict:
    return {
        "id": str(conv.id),
        "title": conv.title,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }


def _message_to_dict(msg: Message) -> dict:
    return {
        "id": str(msg.id),
        "conversation_id": str(msg.conversation_id),
        "role": msg.role,
        "content": msg.content,
        "tool_calls": msg.tool_calls,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }
