# ABOUTME: AI-driven weekly training plan generation using Claude.
# ABOUTME: Gathers athlete context, sends to Claude for reasoning, parses structured plan output.

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

import anthropic
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import (
    AthleteBiometrics,
    Conversation,
    GarminActivity,
    GarminDailySummary,
    Message,
    PlannedWorkout,
    Race,
)
from src.services.analytics import (
    _classify_discipline,
    weekly_volume_by_discipline,
)
from src.services.assistant_plan import (
    AssistantPlanEntry,
    _phase_label,
    _upcoming_race,
    _ensure_assistant_training_plan,
    _delete_existing_assistant_window,
    _existing_garmin_ids_by_slot,
    _slot_key_for_workout,
    _to_garmin_steps,
    ensure_assistant_plan_table,
    is_assistant_owned_mode,
)
from src.services.garmin_writeback import (
    fallback_writeback_payload,
    write_recommendation_change,
)
from src.services.plan_engine import get_plan_adherence

logger = logging.getLogger(__name__)


def _next_planning_window(today: date) -> tuple[date, date]:
    """Return the Monday-Sunday window used by both prompt and writer."""
    days_to_monday = (7 - today.weekday()) % 7
    if days_to_monday == 0 and today.weekday() == 0:
        window_start = today
    else:
        window_start = today + timedelta(days=days_to_monday)
    return window_start, window_start + timedelta(days=6)


async def gather_planning_context(session: AsyncSession) -> dict[str, Any]:
    """Pull all data the planning model needs in one pass."""
    today = date.today()
    lookback_start = today - timedelta(days=14)
    planning_window_start, planning_window_end = _next_planning_window(today)

    # Races
    race_result = await session.execute(
        select(Race).where(Race.date >= today).order_by(Race.date.asc())
    )
    races = []
    for race in race_result.scalars().all():
        weeks_out = (race.date - today).days / 7
        races.append({
            "name": race.name,
            "date": race.date.isoformat(),
            "distance_type": race.distance_type,
            "goal_time": race.goal_time,
            "weeks_out": round(weeks_out, 1),
        })

    # Phase from nearest A-race
    from src.services.assistant_plan import _phase_label
    if races:
        days_to_race = (date.fromisoformat(races[0]["date"]) - today).days
        phase = _phase_label(days_to_race)
    else:
        phase = "base"

    # Recent activities (14 days)
    start_dt = datetime(lookback_start.year, lookback_start.month, lookback_start.day, tzinfo=timezone.utc)
    activity_result = await session.execute(
        select(
            GarminActivity.start_time,
            GarminActivity.activity_type,
            GarminActivity.duration_seconds,
            GarminActivity.distance_meters,
            GarminActivity.average_hr,
            GarminActivity.aerobic_training_effect,
            GarminActivity.anaerobic_training_effect,
            GarminActivity.name,
        )
        .where(GarminActivity.start_time >= start_dt)
        .order_by(GarminActivity.start_time.asc())
    )
    recent_activities = []
    for row in activity_result:
        discipline = _classify_discipline(row.activity_type)
        recent_activities.append({
            "date": row.start_time.date().isoformat() if row.start_time else None,
            "name": row.name,
            "discipline": discipline,
            "type": row.activity_type,
            "duration_min": round((row.duration_seconds or 0) / 60),
            "distance_km": round((row.distance_meters or 0) / 1000, 1),
            "avg_hr": row.average_hr,
            "training_effect": round(
                (row.aerobic_training_effect or 0) + (row.anaerobic_training_effect or 0), 1
            ),
        })

    # Adherence (last 14 days)
    adherence_raw = await get_plan_adherence(session, lookback_start, today)
    adherence = {
        "completed": int(adherence_raw.get("completed", 0)),
        "planned": int(adherence_raw.get("total_planned", adherence_raw.get("total", 0))),
        "rate_pct": round(float(adherence_raw.get("completion_pct", 0)), 1),
        "missed": int(adherence_raw.get("missed", 0)),
    }

    # Recovery trend (14 days of daily summaries)
    summary_result = await session.execute(
        select(
            GarminDailySummary.calendar_date,
            GarminDailySummary.training_readiness_score,
            GarminDailySummary.sleep_score,
            GarminDailySummary.body_battery_at_wake,
            GarminDailySummary.hrv_7d_avg,
            GarminDailySummary.hrv_last_night,
            GarminDailySummary.resting_heart_rate,
        )
        .where(GarminDailySummary.calendar_date >= lookback_start)
        .order_by(GarminDailySummary.calendar_date.asc())
    )
    recovery_trend = []
    for row in summary_result:
        recovery_trend.append({
            "date": row.calendar_date.isoformat(),
            "readiness": row.training_readiness_score,
            "sleep": row.sleep_score,
            "body_battery_wake": row.body_battery_at_wake,
            "hrv_7d": row.hrv_7d_avg,
            "hrv_night": row.hrv_last_night,
            "rhr": row.resting_heart_rate,
        })

    # Training load (latest values)
    load_result = await session.execute(
        select(
            GarminDailySummary.training_load_7d,
            GarminDailySummary.training_load_28d,
        )
        .where(GarminDailySummary.training_load_7d.is_not(None))
        .order_by(GarminDailySummary.calendar_date.desc())
        .limit(1)
    )
    load_row = load_result.one_or_none()
    if load_row and load_row.training_load_28d and load_row.training_load_28d > 0:
        acwr = round(load_row.training_load_7d / load_row.training_load_28d, 2)
        if acwr < 0.8:
            band = "underloaded"
        elif acwr <= 1.3:
            band = "balanced"
        else:
            band = "overreaching"
        load = {
            "acute": round(float(load_row.training_load_7d), 1),
            "chronic": round(float(load_row.training_load_28d), 1),
            "acwr": acwr,
            "band": band,
        }
    else:
        load = {"acute": None, "chronic": None, "acwr": None, "band": "unknown"}

    # Discipline balance (28 days)
    volume = await weekly_volume_by_discipline(session, today - timedelta(days=28), today)
    total_hours = sum(v.get("hours", 0) for v in volume.values())
    discipline_balance = {}
    if total_hours > 0:
        for disc, data in volume.items():
            discipline_balance[disc] = round((data.get("hours", 0) / total_hours) * 100, 1)

    # Biometrics
    bio_result = await session.execute(
        select(AthleteBiometrics).order_by(AthleteBiometrics.date.desc()).limit(1)
    )
    bio_row = bio_result.scalar_one_or_none()
    biometrics = {}
    if bio_row:
        if bio_row.cycling_ftp:
            biometrics["ftp"] = bio_row.cycling_ftp
        if bio_row.lactate_threshold_hr:
            biometrics["lthr"] = bio_row.lactate_threshold_hr
        if bio_row.weight_kg:
            biometrics["weight_kg"] = bio_row.weight_kg

    return {
        "today": today.isoformat(),
        "races": races,
        "phase": phase,
        "recent_activities": recent_activities,
        "adherence": adherence,
        "recovery_trend": recovery_trend,
        "load": load,
        "discipline_balance": discipline_balance,
        "biometrics": biometrics,
        "planning_window_start": planning_window_start.isoformat(),
        "planning_window_end": planning_window_end.isoformat(),
    }


PLANNING_SYSTEM_PROMPT = """You are Coach — a personal triathlon training coach informed by Matt Wilpers' methodology. You are generating a weekly training plan for your athlete.

Your planning principles:
- Periodization drives structure: base → build → peak → taper → race week
- Quality and consistency beat volume. Every session has a purpose
- Recovery data is real data. If readiness/HRV/body battery say back off, back off
- Discipline balance should match race demands (roughly swim 25% / bike 40% / run 30% for 70.3)
- Progressive overload: increase volume/intensity no more than 10% per week
- Hard days hard, easy days easy. Polarize intentionally
- If the athlete missed workouts last week, don't stack them — restructure
- Account for life: rest days matter, don't schedule 7 days straight

For each workout, provide concrete session structure:
- Run: miles and pace ranges (per mile)
- Swim: yards and pace targets (per 100yd)
- Bike: power/zone targets, cadence, and duration
- Strength: specific exercises, sets, reps with cues

Respond with ONLY valid JSON matching this schema:
{
  "reasoning": "2-3 paragraphs explaining your assessment of last week, recovery status, and this week's strategy",
  "workouts": [
    {
      "day": "monday|tuesday|wednesday|thursday|friday|saturday|sunday",
      "discipline": "run|bike|swim|strength|rest",
      "workout_type": "endurance_run|long_run|tempo_run|intervals|easy_spin|quality_intervals|long_ride|endurance_builder|speed_set|mobility_strength|rest",
      "duration_minutes": 45,
      "summary": "One-line description of the session",
      "session_plan": [
        {"label": "Step description with distance/duration", "target": "Pace/power/zone target", "cue": "Optional coaching cue or null"}
      ],
      "coaching_cues": ["Bullet point coaching notes for the session"]
    }
  ]
}

Include rest days explicitly with discipline "rest". Plan exactly 7 days starting from Monday."""


def build_planning_prompt(ctx: dict[str, Any]) -> tuple[str, str]:
    """Build system and user prompts for the planning call."""
    window_start = date.fromisoformat(ctx["planning_window_start"])
    window_end = date.fromisoformat(ctx["planning_window_end"])
    day_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    date_mapping = ", ".join(
        f"{day}={(window_start + timedelta(days=idx)).isoformat()}"
        for idx, day in enumerate(day_names)
    )
    user_parts = [
        (
            f"Today is {ctx['today']}. Generate the training plan for Monday "
            f"{window_start.isoformat()} through Sunday {window_end.isoformat()}.\n"
        ),
        f"Day/date mapping for your JSON day names: {date_mapping}.\n",
        (
            "Only schedule a race as a workout if the race date is inside this exact "
            "planning window. If a race is before the window, account for recovery "
            "from it; do not move it into this window.\n"
        ),
    ]

    # Races
    if ctx["races"]:
        user_parts.append("## Upcoming Races")
        for r in ctx["races"]:
            gt = f" (goal: {r['goal_time']})" if r.get("goal_time") else ""
            race_date = date.fromisoformat(r["date"])
            if race_date < window_start:
                relation = "before this planning window"
            elif race_date > window_end:
                relation = "after this planning window"
            else:
                relation = "inside this planning window"
            user_parts.append(
                f"- {r['name']} — {r['distance_type']} — {r['date']} "
                f"({r['weeks_out']} weeks out; {relation}){gt}"
            )
        user_parts.append("")

    user_parts.append(f"## Training Phase: {ctx['phase'].upper()}\n")

    # Recent activities
    if ctx["recent_activities"]:
        user_parts.append("## Last 14 Days of Training")
        for a in ctx["recent_activities"]:
            user_parts.append(
                f"- {a['date']}: {a['discipline']} ({a['type']}) — "
                f"{a['duration_min']} min, {a['distance_km']} km, "
                f"avg HR {a.get('avg_hr') or '?'}, TE {a['training_effect']}"
            )
        user_parts.append("")

    # Adherence
    adh = ctx["adherence"]
    user_parts.append(
        f"## Plan Adherence (14d): {adh['completed']}/{adh['planned']} completed "
        f"({adh['rate_pct']}%), {adh['missed']} missed\n"
    )

    # Recovery
    if ctx["recovery_trend"]:
        user_parts.append("## Recovery Trend (last 14 days)")
        for r in ctx["recovery_trend"][-7:]:  # Last 7 days for brevity
            user_parts.append(
                f"- {r['date']}: readiness {r.get('readiness') or '?'}, "
                f"sleep {r.get('sleep') or '?'}, "
                f"BB wake {r.get('body_battery_wake') or '?'}, "
                f"HRV 7d {r.get('hrv_7d') or '?'}"
            )
        user_parts.append("")

    # Load
    ld = ctx["load"]
    if ld.get("acwr") is not None:
        user_parts.append(
            f"## Training Load: acute {ld['acute']}, chronic {ld['chronic']}, "
            f"ACWR {ld['acwr']} ({ld['band']})\n"
        )

    # Discipline balance
    if ctx["discipline_balance"]:
        parts = [f"{d}: {pct}%" for d, pct in ctx["discipline_balance"].items()]
        user_parts.append(f"## Discipline Balance (28d): {', '.join(parts)}\n")

    # Biometrics
    bio = ctx.get("biometrics", {})
    if bio:
        bio_parts = []
        if bio.get("ftp"):
            bio_parts.append(f"FTP {bio['ftp']}W")
        if bio.get("lthr"):
            bio_parts.append(f"LTHR {bio['lthr']} bpm")
        if bio.get("weight_kg"):
            bio_parts.append(f"Weight {bio['weight_kg']} kg")
        if bio_parts:
            user_parts.append(f"## Biometrics: {', '.join(bio_parts)}\n")

    return PLANNING_SYSTEM_PROMPT, "\n".join(user_parts)


def parse_plan_response(raw: str) -> dict[str, Any] | None:
    """Extract and validate plan JSON from Claude's response."""
    # Try direct parse
    text = raw.strip()

    # Strip markdown code fences if present
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse plan response as JSON")
        return None

    if not isinstance(data, dict) or "workouts" not in data:
        logger.error("Plan response missing 'workouts' key")
        return None

    return data


def render_workout_description(workout: dict[str, Any]) -> str:
    """Render a workout dict into the Session Plan format the dashboard parses."""
    lines = [workout.get("summary", "Training session").strip(), "", "Session Plan:"]

    for i, step in enumerate(workout.get("session_plan", []), start=1):
        segment = step.get("label", "Step")
        if step.get("target"):
            segment += f" @ {step['target']}"
        if step.get("cue"):
            segment += f" ({step['cue']})"
        lines.append(f"{i}. {segment}")

    cues = workout.get("coaching_cues", [])
    if cues:
        lines.extend(["", "Coaching Cues:"])
        lines.extend(f"- {c.strip()}" for c in cues if isinstance(c, str) and c.strip())

    return "\n".join(lines).strip()


async def generate_intelligent_plan(
    session: AsyncSession,
    *,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call Claude to generate a thoughtful weekly training plan.

    Returns the parsed plan dict with 'reasoning' and 'workouts'.
    """
    if ctx is None:
        ctx = await gather_planning_context(session)

    system_prompt, user_prompt = build_planning_prompt(ctx)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    model = getattr(settings, "coach_model", None) or "claude-sonnet-4-6"

    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text if response.content else ""
    plan = parse_plan_response(raw_text)

    if plan is None:
        raise ValueError(f"Failed to parse plan from model response: {raw_text[:200]}")

    return plan


DAY_TO_WEEKDAY = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


async def write_intelligent_plan(
    db: AsyncSession,
    plan: dict[str, Any],
    *,
    sync_to_garmin: bool = True,
) -> dict[str, Any]:
    """Write Claude's plan output to DB and optionally sync to Garmin.

    Uses the existing assistant_plan infrastructure for DB writes and Garmin sync.
    Falls back to generate_assistant_plan() from assistant_plan.py on failure.
    """
    await ensure_assistant_plan_table(db)

    today = date.today()
    next_monday, end = _next_planning_window(today)
    race = await _upcoming_race(db)
    days_to_race = (race.date - today).days if race else None
    phase = _phase_label(days_to_race)

    training_plan = await _ensure_assistant_training_plan(
        db, start=next_monday, end=end, race=race,
    )

    # Get existing Garmin IDs for slot replacement
    previous_slot_ids = await _existing_garmin_ids_by_slot(db, start=next_monday)

    # Delete existing plan entries for the week
    await _delete_existing_assistant_window(db, start=next_monday)

    now = datetime.now(timezone.utc)
    sync_cutoff = next_monday + timedelta(days=6)
    created_rows = []
    synced_success = 0
    synced_failed = 0
    synced_skipped = 0

    for workout_data in plan.get("workouts", []):
        day_name = workout_data.get("day", "").lower()
        if day_name not in DAY_TO_WEEKDAY:
            continue
        if workout_data.get("discipline") == "rest":
            continue

        workout_date = next_monday + timedelta(days=DAY_TO_WEEKDAY[day_name])
        description = render_workout_description(workout_data)
        duration = workout_data.get("duration_minutes", 45)

        workout = PlannedWorkout(
            plan_id=training_plan.id,
            date=workout_date,
            discipline=workout_data.get("discipline", "other"),
            workout_type=workout_data.get("workout_type", "session"),
            target_duration=duration,
            description=description,
            status="upcoming",
            created_at=now,
        )
        db.add(workout)
        await db.flush()

        entry = AssistantPlanEntry(
            planned_workout_id=workout.id,
            is_locked=False,
            garmin_sync_status="pending" if sync_to_garmin else "skipped",
            created_at=now,
            updated_at=now,
        )
        db.add(entry)

        # Garmin sync
        if sync_to_garmin and workout_date <= sync_cutoff:
            steps = [
                {"type": s.get("type", "interval"), "duration_minutes": 1, "label": s.get("label", "Step")}
                for s in workout_data.get("session_plan", [])
            ]
            garmin_steps = _to_garmin_steps(steps)
            replace_id = previous_slot_ids.get(
                _slot_key_for_workout(
                    workout_date=workout_date,
                    discipline=workout.discipline,
                    workout_type=workout.workout_type,
                )
            )
            payload = fallback_writeback_payload(
                workout_date=workout_date.isoformat(),
                discipline=workout.discipline,
                workout_type=workout.workout_type,
                target_duration=duration,
                description=description,
                workout_steps=garmin_steps,
                replace_workout_id=replace_id,
                dedupe_by_title=True,
                recommendation_text=f"AI plan ({phase})",
            )
            result = await write_recommendation_change(payload)
            status = str(result.get("status", "failed")).lower()
            entry.garmin_sync_result = result
            entry.updated_at = datetime.now(timezone.utc)
            if status == "success":
                entry.garmin_workout_id = str(result.get("workout_id", ""))
                entry.garmin_sync_status = "success"
                synced_success += 1
            else:
                entry.garmin_sync_status = "failed"
                synced_failed += 1
        elif sync_to_garmin:
            entry.garmin_sync_status = "skipped_out_of_window"
            synced_skipped += 1

        created_rows.append(workout)

    await db.flush()

    return {
        "phase": phase,
        "reasoning": plan.get("reasoning", ""),
        "window_start": next_monday.isoformat(),
        "window_end": end.isoformat(),
        "created_workouts": len(created_rows),
        "synced_success": synced_success,
        "synced_failed": synced_failed,
        "synced_skipped": synced_skipped,
    }


async def post_plan_summary(
    db: AsyncSession,
    result: dict[str, Any],
    plan: dict[str, Any],
) -> None:
    """Post a summary of the generated plan to the coach chat."""
    # Find or create the coach conversation
    conv_result = await db.execute(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(1)
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        conversation = Conversation(
            title="Coach",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(conversation)
        await db.flush()

    # Build summary message
    reasoning = plan.get("reasoning", "Plan generated.")
    workouts = plan.get("workouts", [])
    lines = [
        f"**Weekly Plan Generated** ({result.get('window_start')} → {result.get('window_end')})",
        "",
        reasoning,
        "",
        "**This week's schedule:**",
    ]
    for w in workouts:
        day = w.get("day", "?").capitalize()
        disc = w.get("discipline", "?")
        if disc == "rest":
            lines.append(f"- {day}: Rest")
        else:
            dur = w.get("duration_minutes", "?")
            summary = w.get("summary", w.get("workout_type", "session"))
            lines.append(f"- {day}: {disc} — {summary} ({dur} min)")

    synced = result.get("synced_success", 0)
    if synced > 0:
        lines.append(f"\n{synced} workouts synced to Garmin.")

    content = "\n".join(lines)

    msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=content,
        created_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    conversation.updated_at = datetime.now(timezone.utc)


async def run_intelligent_plan_generation(
    db: AsyncSession,
    *,
    sync_to_garmin: bool = True,
) -> dict[str, Any]:
    """Full orchestration: gather context → call Claude → write plan → return summary."""
    ctx = await gather_planning_context(db)
    plan = await generate_intelligent_plan(db, ctx=ctx)
    result = await write_intelligent_plan(db, plan, sync_to_garmin=sync_to_garmin)
    await post_plan_summary(db, result, plan)
    await db.commit()
    return result
