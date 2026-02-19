"""Daily briefing generator.

Gathers readiness, metrics, training plan, and race data, then asks
Claude to produce a structured morning briefing with coaching guidance.
"""

import json
from datetime import date, datetime, timedelta, timezone

import anthropic
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import (
    DailyBriefing,
    GarminActivity,
    GarminDailySummary,
    PlannedWorkout,
    Race,
)
from src.services.readiness import compute_readiness

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

BRIEFING_PROMPT = """You are a training coach writing a short daily briefing. Today is {today}.

DATA:
Readiness: {readiness}
Metrics (3d): {metrics}
Today's workout: {today_workout}
Upcoming (5d): {upcoming}
Load: {load}
Races: {races}
Recent activities: {recent}

Respond in exactly this JSON. No markdown fences, no extra text outside the JSON.

RULES:
- NO markdown anywhere. No **bold**, no *italic*, no headers, no bullet syntax. Plain text only.
- Each field has a different job. Do NOT repeat information across fields.
- "content" is the headline — what matters most today in 1-2 short sentences. Not a recap of everything.
- "readiness_summary" is recovery state only — score, key signal, one-word call (push/moderate/easy/rest).
- "workout_recommendation" is about today's workout only — confirm it, adjust it, or swap it. One sentence.
- "alerts" are only for genuine concerns. Not restatements of the briefing. Empty array if nothing is wrong.
- Reference numbers, not vibes. Keep it tight enough to scan on a phone.

{{
  "content": "1-2 sentences. The one thing to know today.",
  "readiness_summary": "Score and call. e.g. Readiness 78 — HRV up, sleep weak. Moderate.",
  "workout_recommendation": "Confirm, adjust, or swap today's session. One sentence.",
  "alerts": ["short, specific concern if any"]
}}
"""


async def gather_context(db: AsyncSession) -> dict:
    """Collect all data needed for briefing generation."""
    today = date.today()

    # Readiness
    summary_result = await db.execute(
        select(GarminDailySummary)
        .order_by(GarminDailySummary.calendar_date.desc())
        .limit(1)
    )
    summary = summary_result.scalar_one_or_none()

    readiness_text = "No readiness data available."
    if summary:
        r = compute_readiness(
            hrv_last_night=summary.hrv_last_night,
            hrv_7d_avg=summary.hrv_7d_avg,
            sleep_score=summary.sleep_score,
            body_battery_wake=summary.body_battery_at_wake,
            recovery_time_hours=summary.recovery_time_hours,
            training_load_7d=summary.training_load_7d,
            training_load_28d=summary.training_load_28d,
        )
        parts = [f"Score: {r.score}/100 ({r.label})"]
        for c in r.components:
            parts.append(f"  {c.name}: {c.detail} (norm {c.normalized:.0f}/100)")
        readiness_text = "\n".join(parts)

    # Recent metrics (last 3 days)
    metrics_result = await db.execute(
        select(GarminDailySummary)
        .where(GarminDailySummary.calendar_date >= today - timedelta(days=3))
        .order_by(GarminDailySummary.calendar_date.desc())
    )
    metrics_rows = metrics_result.scalars().all()
    metrics_lines = []
    for s in metrics_rows:
        parts = [f"{s.calendar_date}:"]
        if s.hrv_last_night is not None:
            parts.append(f"HRV {s.hrv_last_night}ms")
        if s.sleep_score is not None:
            parts.append(f"Sleep {s.sleep_score}")
        if s.body_battery_at_wake is not None:
            parts.append(f"BB wake {s.body_battery_at_wake}")
        if s.resting_heart_rate is not None:
            parts.append(f"RHR {s.resting_heart_rate}")
        if s.training_status:
            parts.append(f"({s.training_status})")
        metrics_lines.append(" ".join(parts))
    metrics_text = "\n".join(metrics_lines) or "No recent metrics."

    # Today's workout
    workout_result = await db.execute(
        select(PlannedWorkout).where(PlannedWorkout.date == today)
    )
    workouts_today = workout_result.scalars().all()
    if workouts_today:
        wo_lines = []
        for w in workouts_today:
            line = f"{w.discipline}: {w.workout_type or w.description or 'Scheduled'}"
            if w.target_duration:
                line += f" ({w.target_duration}min)"
            wo_lines.append(line)
        today_workout_text = "\n".join(wo_lines)
    else:
        today_workout_text = "No workout planned for today."

    # Upcoming schedule (next 5 days)
    upcoming_result = await db.execute(
        select(PlannedWorkout)
        .where(
            and_(
                PlannedWorkout.date > today,
                PlannedWorkout.date <= today + timedelta(days=5),
            )
        )
        .order_by(PlannedWorkout.date)
    )
    upcoming_workouts = upcoming_result.scalars().all()
    if upcoming_workouts:
        up_lines = []
        for w in upcoming_workouts:
            up_lines.append(
                f"{w.date}: {w.discipline} — {w.workout_type or w.description or 'Scheduled'}"
            )
        upcoming_text = "\n".join(up_lines)
    else:
        upcoming_text = "No workouts scheduled for the next 5 days."

    # Training load
    load_text = "No load data."
    if summary and summary.training_load_7d is not None:
        load_parts = [f"7-day load: {summary.training_load_7d:.0f}"]
        if summary.training_load_28d is not None and summary.training_load_28d > 0:
            acr = summary.training_load_7d / summary.training_load_28d
            load_parts.append(f"28-day load: {summary.training_load_28d:.0f}")
            load_parts.append(f"Acute:Chronic ratio: {acr:.2f}")
        load_text = ", ".join(load_parts)

    # Races
    race_result = await db.execute(
        select(Race).where(Race.date >= today).order_by(Race.date)
    )
    races = race_result.scalars().all()
    if races:
        race_lines = []
        for r in races:
            days = (r.date - today).days
            weeks = days // 7
            race_lines.append(f"{r.name} ({r.distance_type}): {r.date} — {weeks}w {days % 7}d out")
        races_text = "\n".join(race_lines)
    else:
        races_text = "No upcoming races."

    # Recent activities
    recent_result = await db.execute(
        select(GarminActivity)
        .order_by(GarminActivity.start_time.desc())
        .limit(5)
    )
    recent = recent_result.scalars().all()
    if recent:
        act_lines = []
        for a in recent:
            line = f"{a.start_time:%Y-%m-%d} {a.activity_type}: {a.name}"
            if a.duration_seconds:
                line += f" ({a.duration_seconds / 60:.0f}min)"
            if a.distance_meters:
                line += f" {a.distance_meters / 1000:.1f}km"
            if a.average_hr:
                line += f" HR {a.average_hr}"
            act_lines.append(line)
        recent_text = "\n".join(act_lines)
    else:
        recent_text = "No recent activities."

    return {
        "readiness": readiness_text,
        "metrics": metrics_text,
        "today_workout": today_workout_text,
        "upcoming": upcoming_text,
        "load": load_text,
        "races": races_text,
        "recent": recent_text,
    }


async def generate_briefing(db: AsyncSession) -> dict:
    """Generate today's daily briefing via Claude and persist it."""
    today = date.today()

    # Check if one already exists for today
    existing = await db.execute(
        select(DailyBriefing).where(DailyBriefing.date == today)
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row:
        return {
            "id": str(existing_row.id),
            "date": existing_row.date.isoformat(),
            "content": existing_row.content,
            "readiness_summary": existing_row.readiness_summary,
            "workout_recommendation": existing_row.workout_recommendation,
            "alerts": existing_row.alerts,
            "created_at": existing_row.created_at.isoformat() if existing_row.created_at else None,
        }

    ctx = await gather_context(db)
    prompt = BRIEFING_PROMPT.format(today=today.isoformat(), **ctx)

    response = await client.messages.create(
        model=settings.coach_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text.strip()

    # Parse JSON response
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown fences
        if "```" in raw_text:
            start = raw_text.index("{")
            end = raw_text.rindex("}") + 1
            parsed = json.loads(raw_text[start:end])
        else:
            parsed = {
                "content": raw_text,
                "readiness_summary": None,
                "workout_recommendation": None,
                "alerts": [],
            }

    briefing = DailyBriefing(
        date=today,
        content=parsed.get("content", ""),
        readiness_summary=parsed.get("readiness_summary"),
        workout_recommendation=parsed.get("workout_recommendation"),
        alerts=parsed.get("alerts", []),
        raw_agent_response={"model": settings.coach_model, "response": raw_text},
        created_at=datetime.now(timezone.utc),
    )
    db.add(briefing)
    await db.commit()
    await db.refresh(briefing)

    return {
        "id": str(briefing.id),
        "date": briefing.date.isoformat(),
        "content": briefing.content,
        "readiness_summary": briefing.readiness_summary,
        "workout_recommendation": briefing.workout_recommendation,
        "alerts": briefing.alerts,
        "created_at": briefing.created_at.isoformat() if briefing.created_at else None,
    }
