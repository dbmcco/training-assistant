"""Async streaming coach agent using the Anthropic SDK.

Runs a tool-use loop: streams tokens to the caller via SSE events,
handles tool calls by invoking execute_tool(), and persists the
conversation when complete.

Now includes dynamic athlete context injection (phase detection, load ratio,
discipline balance, recovery state, active alerts) informed by Matt Wilpers'
coaching methodology.
"""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import anthropic
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.personality import (
    assess_discipline_balance,
    build_athlete_context_string,
    build_system_prompt,
    compute_load_ratio,
    determine_phase,
)
from src.agent.tools import TOOL_DEFINITIONS, execute_tool
from src.config import settings
from src.db.models import (
    AlertLog,
    AthleteBiometrics,
    AthleteProfile,
    Conversation,
    GarminActivity,
    GarminDailySummary,
    Message,
    Race,
)

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def _build_dynamic_context(db: AsyncSession) -> dict:
    """Query DB to build dynamic athlete context for system prompt injection."""

    # A-race
    race_result = await db.execute(
        select(Race).where(Race.date >= date.today()).order_by(Race.date)
    )
    races = race_result.scalars().all()
    a_race = None
    race_list = []
    for r in races:
        rd = {"name": r.name, "date": r.date, "distance_type": r.distance_type}
        race_list.append(rd)
        if a_race is None:
            a_race = rd

    # Phase detection
    phase = None
    if a_race and a_race["date"]:
        phase = determine_phase(a_race["date"])

    # Recovery state (latest daily summary)
    recovery_result = await db.execute(
        select(GarminDailySummary)
        .order_by(GarminDailySummary.calendar_date.desc())
        .limit(1)
    )
    summary = recovery_result.scalar_one_or_none()

    recovery = {}
    load_ratio = None
    acute_load = None
    chronic_load = None
    if summary:
        recovery = {
            "hrv_7d_avg": summary.hrv_7d_avg,
            "hrv_last_night": summary.hrv_last_night,
            "hrv_status": summary.hrv_status,
            "body_battery_at_wake": summary.body_battery_at_wake,
            "sleep_score": summary.sleep_score,
            "training_readiness_score": summary.training_readiness_score,
        }
        acute_load = summary.training_load_7d
        chronic_load = summary.training_load_28d
        load_ratio = compute_load_ratio(acute_load, chronic_load)

    # Discipline distribution (28 days)
    from src.services.analytics import weekly_volume_by_discipline

    cutoff_28d = date.today() - timedelta(days=28)
    volumes = await weekly_volume_by_discipline(db, cutoff_28d, date.today())

    total_hours = sum(v["hours"] for v in volumes.values()) or 1.0
    distribution = {}
    for disc, v in volumes.items():
        distribution[disc] = {
            "hours": v["hours"],
            "pct": round(v["hours"] / total_hours * 100, 1),
        }

    race_type = "70.3"
    if a_race and "marathon" in (a_race.get("distance_type") or "").lower():
        race_type = "marathon"
    elif a_race and "olympic" in (a_race.get("distance_type") or "").lower():
        race_type = "olympic"

    discipline_balance = assess_discipline_balance(distribution, race_type)

    # Biometrics
    bio_result = await db.execute(
        select(AthleteBiometrics)
        .order_by(AthleteBiometrics.date.desc())
        .limit(1)
    )
    bio = bio_result.scalar_one_or_none()
    biometrics = {}
    if bio:
        biometrics = {
            "cycling_ftp": bio.cycling_ftp,
            "lactate_threshold_hr": bio.lactate_threshold_hr,
            "weight_kg": bio.weight_kg,
            "date": bio.date.isoformat() if bio.date else None,
        }

    # Active alerts
    alerts_result = await db.execute(
        select(AlertLog)
        .where(AlertLog.acknowledged == False)  # noqa: E712
        .order_by(AlertLog.created_at.desc())
        .limit(5)
    )
    alerts = [
        {"severity": a.severity, "title": a.title}
        for a in alerts_result.scalars().all()
    ]

    return {
        "a_race": a_race,
        "races": race_list,
        "phase": phase,
        "load_ratio": load_ratio,
        "acute_load": acute_load,
        "chronic_load": chronic_load,
        "discipline_balance": discipline_balance,
        "recovery": recovery,
        "biometrics": biometrics,
        "alerts": alerts,
    }


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
    # 2. Build dynamic athlete context
    # ------------------------------------------------------------------
    ctx = await _build_dynamic_context(db)

    athlete_context_str = build_athlete_context_string(
        a_race=ctx["a_race"],
        phase=ctx["phase"],
        load_ratio=ctx["load_ratio"],
        acute_load=ctx["acute_load"],
        chronic_load=ctx["chronic_load"],
        discipline_balance=ctx["discipline_balance"],
        recovery=ctx["recovery"],
        biometrics=ctx["biometrics"],
        alerts=ctx["alerts"],
    )

    # ------------------------------------------------------------------
    # 3. Build system prompt
    # ------------------------------------------------------------------
    system_prompt = build_system_prompt(
        athlete_profile={"notes": profile.notes} if profile else None,
        view_context=view_context,
        races=ctx["races"],
        athlete_context=athlete_context_str,
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
