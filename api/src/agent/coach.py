"""Async streaming coach agent using the Anthropic SDK.

Runs a tool-use loop: streams tokens to the caller via SSE events,
handles tool calls by invoking execute_tool(), and persists the
conversation when complete.

Now includes dynamic athlete context injection (phase detection, load ratio,
discipline balance, recovery state, active alerts) informed by Matt Wilpers'
coaching methodology.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import anthropic
from sqlalchemy import select, text
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
    PlannedWorkout,
    Race,
    RecommendationChange,
)
from src.services.memory_store import (
    search_relevant_memories,
    sync_missing_conversation_memories,
)
from src.services.recommendations import recommendation_table_available

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
logger = logging.getLogger(__name__)
RECENT_DECISION_CONTEXT_LIMIT = 5


async def _uses_legacy_conversation_schema(db: AsyncSession) -> bool:
    """Detect legacy conversations schema from shared PAIA tables."""
    result = await db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'conversations'
              AND column_name IN ('channel_id', 'assistant_id', 'date')
            """
        )
    )
    cols = {row[0] for row in result.all()}
    return {"channel_id", "assistant_id", "date"}.issubset(cols)


async def _legacy_conversation_defaults(
    db: AsyncSession,
) -> tuple[str, str] | None:
    """Find channel/assistant defaults for legacy conversation inserts."""
    latest = await db.execute(
        text(
            """
            SELECT channel_id, assistant_id
            FROM conversations
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
    )
    row = latest.first()
    if row and row[0] and row[1]:
        return str(row[0]), str(row[1])

    channel_id = await db.execute(
        text(
            """
            SELECT id
            FROM channels
            WHERE key = 'dm:paia'
            LIMIT 1
            """
        )
    )
    channel_value = channel_id.scalar_one_or_none()
    if channel_value is None:
        fallback_channel = await db.execute(
            text("SELECT id FROM channels ORDER BY created_at ASC LIMIT 1")
        )
        channel_value = fallback_channel.scalar_one_or_none()

    assistant_id = await db.execute(text("SELECT system_default_assistant_id()"))
    assistant_value = assistant_id.scalar_one_or_none()

    if channel_value is None or assistant_value is None:
        return None
    return str(channel_value), str(assistant_value)


async def _build_dynamic_context(db: AsyncSession) -> dict:
    """Query DB to build dynamic athlete context for system prompt injection."""

    # Races — find A-race by priority, not just first by date
    race_result = await db.execute(
        select(Race).where(Race.date >= date.today()).order_by(Race.date)
    )
    races = race_result.scalars().all()
    a_race = None
    race_list = []
    for r in races:
        rd = {
            "name": r.name,
            "date": r.date,
            "distance_type": r.distance_type,
            "priority": getattr(r, "priority", "B") or "B",
        }
        race_list.append(rd)
        if rd["priority"].upper() == "A" and a_race is None:
            a_race = rd
    # Fallback: if no A-race flagged, use the last race (biggest)
    if a_race is None and race_list:
        a_race = race_list[-1]

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
        select(AthleteBiometrics).order_by(AthleteBiometrics.date.desc()).limit(1)
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


async def _resolve_conversation_id(
    db: AsyncSession, requested_conversation_id: str | None
) -> str | None:
    """Use only an explicit conversation_id; missing means start fresh."""
    _ = db
    return requested_conversation_id


async def _load_conversation_history(
    db: AsyncSession,
    conversation_id: str | None,
    max_messages: int,
) -> list[dict]:
    if not conversation_id:
        return []

    bounded_limit = max(2, min(max_messages, 24))
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(bounded_limit)
    )
    recent = list(result.scalars().all())
    recent.reverse()
    return [
        {"role": msg.role, "content": msg.content}
        for msg in recent
        if msg.role in {"user", "assistant"} and (msg.content or "").strip()
    ]


async def _build_recent_decisions_context(db: AsyncSession) -> str:
    if not await recommendation_table_available(db):
        return ""

    result = await db.execute(
        select(RecommendationChange)
        .where(RecommendationChange.status != "pending")
        .order_by(
            RecommendationChange.decided_at.desc().nullslast(),
            RecommendationChange.created_at.desc(),
        )
        .limit(RECENT_DECISION_CONTEXT_LIMIT)
    )
    rows = result.scalars().all()
    if not rows:
        return ""

    lines = ["## Recent Recommendation Decisions"]
    for row in rows:
        when = row.decided_at.date().isoformat() if row.decided_at else "unknown-date"
        proposed = row.proposed_workout or {}
        workout_type = proposed.get("workout_type") or "session change"
        discipline = proposed.get("discipline") or "unknown"
        date_text = row.workout_date.isoformat() if row.workout_date else "unknown-date"
        notes = row.decision_notes or row.requested_changes or ""
        note_suffix = f" — notes: {notes}" if notes else ""
        lines.append(
            f"- {when}: {row.status} {discipline} {workout_type} on {date_text}{note_suffix}"
        )
    return "\n".join(lines)


def _format_memory_context(memories: list[dict]) -> str:
    if not memories:
        return ""

    lines = ["## Long-Term Memory (retrieved)"]
    for memory in memories:
        created_at = memory.get("created_at")
        when = (
            created_at.date().isoformat()
            if hasattr(created_at, "date")
            else "unknown-date"
        )
        role = str(memory.get("role") or "note")
        content = str(memory.get("content") or "").strip()
        if not content:
            continue
        if len(content) > 260:
            content = f"{content[:260].rstrip()}..."
        lines.append(f"- {when} [{role}] {content}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _classify_activity_discipline_lite(activity: GarminActivity) -> str:
    text = f"{activity.sport_type or ''} {activity.activity_type or ''}".lower()
    if "run" in text or "trail" in text:
        return "run"
    if "bike" in text or "cycl" in text or "peloton" in text or "spin" in text:
        return "bike"
    if "swim" in text or "pool" in text or "open_water" in text:
        return "swim"
    if "strength" in text or "lift" in text:
        return "strength"
    return "other"


def _normalize_planned_discipline(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw.startswith("run") or "trail" in raw:
        return "run"
    if raw.startswith("bike") or "cycl" in raw or "peloton" in raw or "spin" in raw:
        return "bike"
    if raw.startswith("swim") or "pool" in raw or "open_water" in raw:
        return "swim"
    if raw.startswith("strength") or "yoga" in raw or "pilates" in raw:
        return "strength"
    return raw if raw else "other"


def _format_training_summary(
    activities: list[GarminActivity],
    planned: list[PlannedWorkout],
    adherence: dict | None,
) -> str:
    today = date.today()
    seven_days_ago = today - timedelta(days=7)

    disc_order = ["run", "bike", "swim", "strength"]

    actual_by_disc: dict[str, list[GarminActivity]] = {d: [] for d in disc_order}
    for a in activities:
        disc = _classify_activity_discipline_lite(a)
        if disc in actual_by_disc:
            actual_by_disc[disc].append(a)

    planned_by_disc: dict[str, list[PlannedWorkout]] = {d: [] for d in disc_order}
    for w in planned:
        if w.date and seven_days_ago <= w.date <= today:
            disc = _normalize_planned_discipline(w.discipline)
            if disc in planned_by_disc:
                planned_by_disc[disc].append(w)

    lines = ["## Recent Training (Last 7 Days)"]

    has_data = False
    for disc in disc_order:
        acts = actual_by_disc[disc]
        count = len(acts)
        total_dur_s = sum(a.duration_seconds or 0.0 for a in acts)
        total_dist_m = sum(a.distance_meters or 0.0 for a in acts)
        planned_count = len(planned_by_disc[disc])

        if count == 0 and planned_count == 0:
            continue

        has_data = True
        parts = [
            f"- {disc.capitalize()}: {count} session{'s' if count != 1 else ''} completed"
        ]
        if total_dur_s > 0:
            dur_min = total_dur_s / 60.0
            if dur_min >= 60:
                parts.append(f"{dur_min / 60:.1f} hrs total")
            else:
                parts.append(f"{dur_min:.0f}min total")
        if total_dist_m > 0:
            if disc == "run":
                parts.append(f"{total_dist_m / 1609.34:.1f} mi")
            elif disc == "swim":
                parts.append(f"{total_dist_m / 0.9144:.0f} yd")
            else:
                parts.append(f"{total_dist_m / 1000:.1f} km")
        if count == 0 and planned_count > 0:
            parts.append(f"({planned_count} planned, {planned_count} missed)")
        elif planned_count > count:
            missed = planned_count - count
            parts.append(f"({planned_count} planned, {missed} missed)")
        lines.append(" ".join(parts))

    if adherence:
        completed = adherence.get("completed", 0)
        due = adherence.get("due_planned", 0)
        pct = adherence.get("completion_pct", 0.0)
        missed = adherence.get("missed", 0)
        if due > 0:
            has_data = True
            suffix = ""
            if missed > 0:
                suffix = f", {missed} missed"
            lines.append(
                f"- Plan adherence: {pct:.0f}% ({completed}/{due} planned workouts completed{suffix})"
            )

    if not has_data:
        return ""

    return "\n".join(lines)


async def build_training_context(db: AsyncSession) -> str:
    today = date.today()
    seven_days_ago = today - timedelta(days=7)

    activity_result = await db.execute(
        select(GarminActivity)
        .where(
            GarminActivity.start_time
            >= datetime.combine(seven_days_ago, datetime.min.time()).replace(
                tzinfo=timezone.utc
            )
        )
        .order_by(GarminActivity.start_time.desc())
    )
    activities = list(activity_result.scalars().all())

    planned_result = await db.execute(
        select(PlannedWorkout).where(
            PlannedWorkout.date >= seven_days_ago,
            PlannedWorkout.date <= today,
        )
    )
    planned = list(planned_result.scalars().all())

    adherence = None
    try:
        from src.services.plan_engine import get_plan_adherence

        adherence = await get_plan_adherence(db, seven_days_ago, today)
    except Exception:
        logger.exception("Failed to get plan adherence for training context")

    return _format_training_summary(activities, planned, adherence)


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
    conversation_id = await _resolve_conversation_id(db, conversation_id)
    if conversation_id:
        try:
            await sync_missing_conversation_memories(
                db,
                conversation_id=conversation_id,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Failed to sync missing conversation memories")

    recent_decisions_context = await _build_recent_decisions_context(db)
    memory_context = ""
    daily_comparison_context = ""
    training_context = ""
    try:
        memories = await search_relevant_memories(
            db,
            user_message,
            limit=settings.coach_memory_retrieval_limit,
        )
        memory_context = _format_memory_context(memories)
    except Exception:
        logger.exception("Failed to retrieve long-term memory context")
    try:
        comparison = await execute_tool(
            "compare_planned_vs_actual",
            {"days_back": 7},
            db,
        )
        if comparison and not comparison.lower().startswith("error"):
            if len(comparison) > 2200:
                comparison = f"{comparison[:2200].rstrip()}..."
            daily_comparison_context = (
                f"## Planned vs Actual Snapshot (last 7 days)\n{comparison}"
            )
    except Exception:
        logger.exception("Failed to build planned-vs-actual comparison context")
    try:
        training_context = await build_training_context(db)
    except Exception:
        logger.exception("Failed to build training context")

    system_prompt = build_system_prompt(
        athlete_profile={"notes": profile.notes} if profile else None,
        view_context=view_context,
        races=ctx["races"],
        athlete_context=athlete_context_str,
    )
    if recent_decisions_context:
        system_prompt = f"{system_prompt}\n\n{recent_decisions_context}"
    if memory_context:
        system_prompt = f"{system_prompt}\n\n{memory_context}"
    if daily_comparison_context:
        system_prompt = f"{system_prompt}\n\n{daily_comparison_context}"
    if training_context:
        system_prompt = f"{system_prompt}\n\n{training_context}"

    # ------------------------------------------------------------------
    # 4. Load conversation history
    # ------------------------------------------------------------------
    history = await _load_conversation_history(
        db,
        conversation_id,
        max_messages=max(2, min(settings.coach_prompt_history_messages, 24)),
    )

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
    # 6. Persist conversation (best-effort) and always terminate stream
    # ------------------------------------------------------------------
    now = datetime.now(timezone.utc)
    if not conversation_id:
        conversation_id = str(uuid4())

    persistence_error = False
    try:
        uses_legacy_schema = await _uses_legacy_conversation_schema(db)
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.updated_at = now
        else:
            title = user_message[:50]
            if uses_legacy_schema:
                defaults = await _legacy_conversation_defaults(db)
                if defaults is None:
                    raise RuntimeError(
                        "Cannot resolve legacy conversation defaults (channel_id/assistant_id)"
                    )
                channel_id, assistant_id = defaults
                await db.execute(
                    text(
                        """
                        INSERT INTO conversations (
                            id, channel_id, assistant_id, date, title, created_at, updated_at
                        ) VALUES (
                            :id, :channel_id, :assistant_id, :date, :title, :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "id": conversation_id,
                        "channel_id": channel_id,
                        "assistant_id": assistant_id,
                        "date": now.date(),
                        "title": title,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
            else:
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
    except Exception:
        persistence_error = True
        await db.rollback()
        logger.exception("Failed to persist chat conversation/message")
    else:
        if conversation_id:
            try:
                await sync_missing_conversation_memories(
                    db,
                    conversation_id=conversation_id,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("Failed to store long-term memory embeddings")

    yield {
        "event": "done",
        "data": {
            "conversation_id": conversation_id,
            "content": full_response,
            "persisted": not persistence_error,
        },
    }
