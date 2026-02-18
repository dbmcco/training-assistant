"""Async streaming coach agent using the Anthropic SDK.

Runs a tool-use loop: streams tokens to the caller via SSE events,
handles tool calls by invoking execute_tool(), and persists the
conversation when complete.
"""

from datetime import date, datetime, timezone
from uuid import uuid4

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.personality import build_system_prompt
from src.agent.tools import TOOL_DEFINITIONS, execute_tool
from src.config import settings
from src.db.models import AthleteProfile, Conversation, Message, Race

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def run_coach(
    user_message: str,
    conversation_id: str | None,
    view_context: dict | None,
    db: AsyncSession,
):
    """Run the coaching agent. Yields SSE event dicts.

    Each yielded dict has ``event`` (str) and ``data`` (dict) keys suitable
    for serialisation into an SSE stream.
    """

    # ------------------------------------------------------------------
    # 1. Load athlete profile
    # ------------------------------------------------------------------
    profile_result = await db.execute(select(AthleteProfile).limit(1))
    profile = profile_result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # 2. Load upcoming races
    # ------------------------------------------------------------------
    race_result = await db.execute(
        select(Race).where(Race.date >= date.today()).order_by(Race.date)
    )
    races = [
        {"name": r.name, "date": r.date, "distance_type": r.distance_type}
        for r in race_result.scalars().all()
    ]

    # ------------------------------------------------------------------
    # 3. Build system prompt
    # ------------------------------------------------------------------
    system_prompt = build_system_prompt(
        athlete_profile={"notes": profile.notes} if profile else None,
        view_context=view_context,
        races=races,
    )

    # ------------------------------------------------------------------
    # 4. Load conversation history
    # ------------------------------------------------------------------
    history: list[dict] = []
    if conversation_id:
        msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        for msg in msg_result.scalars().all():
            history.append({"role": msg.role, "content": msg.content})

    messages: list[dict] = history + [{"role": "user", "content": user_message}]

    # ------------------------------------------------------------------
    # 5. Agent loop — stream with tool use
    # ------------------------------------------------------------------
    full_response = ""

    while True:
        async with client.messages.stream(
            model=settings.coach_model,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
            tools=TOOL_DEFINITIONS,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "tool_use":
                        yield {
                            "event": "tool_call",
                            "data": {
                                "tool": event.content_block.name,
                                "status": "calling",
                            },
                        }
                elif event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        full_response += event.delta.text
                        yield {
                            "event": "token",
                            "data": {"content": event.delta.text},
                        }

            response = await stream.get_final_message()

        # Check if we need to handle tool calls
        if response.stop_reason == "tool_use":
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            tool_results = []
            for block in tool_use_blocks:
                result = await execute_tool(block.name, block.input, db)
                yield {
                    "event": "tool_result",
                    "data": {"tool": block.name, "summary": result[:200]},
                }
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            # Done — no more tool calls
            break

    # ------------------------------------------------------------------
    # 6. Persist conversation
    # ------------------------------------------------------------------
    now = datetime.now(timezone.utc)

    if conversation_id:
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.updated_at = now
        else:
            # Conversation ID was provided but doesn't exist — create it
            title = user_message[:50]
            conv = Conversation(
                id=conversation_id, title=title, created_at=now, updated_at=now
            )
            db.add(conv)
    else:
        conversation_id = str(uuid4())
        title = user_message[:50]
        conv = Conversation(
            id=conversation_id, title=title, created_at=now, updated_at=now
        )
        db.add(conv)

    # Save user message
    db.add(
        Message(
            conversation_id=conversation_id,
            role="user",
            content=user_message,
            created_at=now,
        )
    )

    # Save assistant response
    db.add(
        Message(
            conversation_id=conversation_id,
            role="assistant",
            content=full_response,
            created_at=now,
        )
    )

    await db.commit()

    yield {
        "event": "done",
        "data": {"conversation_id": conversation_id, "content": full_response},
    }
