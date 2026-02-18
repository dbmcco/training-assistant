"""Agent tool definitions and handlers for the training assistant coach.

Each tool allows the Claude Agent SDK coach to query the database and return
formatted text for the agent to reason about.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    AthleteProfile,
    GarminActivity,
    GarminDailySummary,
    PlannedWorkout,
    Race,
)

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "query_activities",
        "description": (
            "Query recent training activities. Can filter by discipline "
            "(e.g. running, cycling, swimming) and look back a specified number of days."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "discipline": {
                    "type": "string",
                    "description": "Sport type filter (e.g. 'running', 'cycling', 'swimming'). Use 'all' for everything.",
                    "default": "all",
                },
                "days_back": {
                    "type": "integer",
                    "description": "Number of days to look back.",
                    "default": 7,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of activities to return.",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_daily_metrics",
        "description": (
            "Get daily health and recovery metrics including HRV, body battery, "
            "sleep score, stress, resting heart rate, and training status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {
                    "type": "integer",
                    "description": "Number of days of metrics to retrieve.",
                    "default": 7,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_readiness_score",
        "description": (
            "Compute today's composite readiness score from HRV, sleep, body battery, "
            "recovery time, and training load balance. Returns score (0-100), label, "
            "and component breakdown."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_plan_adherence",
        "description": (
            "Get training plan completion statistics showing planned vs completed "
            "vs missed workouts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Time period: 'this_week', 'last_week', or 'this_month'.",
                    "default": "this_week",
                    "enum": ["this_week", "last_week", "this_month"],
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_upcoming_workouts",
        "description": (
            "Get the next N planned workouts from today onwards, including discipline, "
            "workout type, target duration, and description."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of upcoming workouts to return.",
                    "default": 5,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_race_countdown",
        "description": (
            "Get days and weeks remaining until each upcoming race, "
            "including race name, date, and distance type."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_training_load",
        "description": (
            "Get weekly training load trends showing 7-day and 28-day load "
            "values over the specified number of weeks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "weeks": {
                    "type": "integer",
                    "description": "Number of weeks of load data to return.",
                    "default": 4,
                },
            },
            "required": [],
        },
    },
    {
        "name": "modify_workout",
        "description": (
            "Suggest a modification to a planned workout. Returns the current workout "
            "details and frames the modification suggestion. Does NOT apply changes — "
            "the athlete must confirm."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workout_id": {
                    "type": "string",
                    "description": "UUID of the planned workout to modify.",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for the suggested modification.",
                },
            },
            "required": ["workout_id", "reason"],
        },
    },
    {
        "name": "update_athlete_profile",
        "description": (
            "Store a learned observation about the athlete in their profile. "
            "Use this to remember preferences, injury notes, or patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Category key for the observation (e.g. 'injury', 'preference', 'pattern').",
                },
                "note": {
                    "type": "string",
                    "description": "The observation to store.",
                },
            },
            "required": ["key", "note"],
        },
    },
]


async def execute_tool(name: str, args: dict, db: AsyncSession) -> str:
    """Route a tool call to the appropriate handler.

    Args:
        name: Tool name from TOOL_DEFINITIONS.
        args: Arguments dict from the agent.
        db: Async SQLAlchemy session.

    Returns:
        Formatted string result for the agent to reason about.
    """
    handlers = {
        "query_activities": _query_activities,
        "get_daily_metrics": _get_daily_metrics,
        "get_readiness_score": _get_readiness_score,
        "get_plan_adherence": _get_plan_adherence,
        "get_upcoming_workouts": _get_upcoming_workouts,
        "get_race_countdown": _get_race_countdown,
        "get_training_load": _get_training_load,
        "modify_workout": _modify_workout,
        "update_athlete_profile": _update_athlete_profile,
    }

    handler = handlers.get(name)
    if not handler:
        return f"Error: Unknown tool '{name}'."

    try:
        return await handler(db, **args)
    except Exception as e:
        return f"Error executing {name}: {e}"


# ---------------------------------------------------------------------------
# Handler implementations
# ---------------------------------------------------------------------------


async def _query_activities(
    db: AsyncSession,
    discipline: str = "all",
    days_back: int = 7,
    limit: int = 10,
) -> str:
    q = (
        select(GarminActivity)
        .where(
            GarminActivity.start_time
            >= datetime.now(timezone.utc) - timedelta(days=days_back)
        )
        .order_by(GarminActivity.start_time.desc())
        .limit(limit)
    )

    if discipline != "all":
        q = q.where(GarminActivity.sport_type.ilike(f"%{discipline}%"))

    result = await db.execute(q)
    activities = result.scalars().all()

    if not activities:
        return "No activities found for the given criteria."

    lines = []
    for a in activities:
        line = f"- {a.start_time:%Y-%m-%d} {a.activity_type}: {a.name}"
        if a.duration_seconds:
            mins = a.duration_seconds / 60
            line += f" ({mins:.0f}min)"
        if a.distance_meters:
            km = a.distance_meters / 1000
            line += f" {km:.1f}km"
        if a.average_hr:
            line += f" avg HR {a.average_hr}"
        lines.append(line)
    return "\n".join(lines)


async def _get_daily_metrics(db: AsyncSession, days_back: int = 7) -> str:
    cutoff = date.today() - timedelta(days=days_back)
    result = await db.execute(
        select(GarminDailySummary)
        .where(GarminDailySummary.calendar_date >= cutoff)
        .order_by(GarminDailySummary.calendar_date.desc())
    )
    summaries = result.scalars().all()

    if not summaries:
        return "No daily metrics found for the given period."

    lines = []
    for s in summaries:
        parts = [f"- {s.calendar_date}:"]
        if s.hrv_last_night is not None:
            parts.append(f"HRV {s.hrv_last_night}ms")
        if s.hrv_status:
            parts.append(f"({s.hrv_status})")
        if s.sleep_score is not None:
            parts.append(f"Sleep {s.sleep_score}")
        if s.body_battery_at_wake is not None:
            parts.append(f"BB wake {s.body_battery_at_wake}")
        if s.average_stress is not None:
            parts.append(f"Stress {s.average_stress}")
        if s.resting_heart_rate is not None:
            parts.append(f"RHR {s.resting_heart_rate}")
        if s.training_status:
            parts.append(f"Status: {s.training_status}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


async def _get_readiness_score(db: AsyncSession) -> str:
    from src.services.readiness import compute_readiness

    result = await db.execute(
        select(GarminDailySummary)
        .order_by(GarminDailySummary.calendar_date.desc())
        .limit(1)
    )
    summary = result.scalar_one_or_none()

    if not summary:
        return "No daily summary data available to compute readiness score."

    score = compute_readiness(
        hrv_last_night=summary.hrv_last_night,
        hrv_7d_avg=summary.hrv_7d_avg,
        sleep_score=summary.sleep_score,
        body_battery_wake=summary.body_battery_at_wake,
        recovery_time_hours=summary.recovery_time_hours,
        training_load_7d=summary.training_load_7d,
        training_load_28d=summary.training_load_28d,
    )

    lines = [
        f"Readiness Score: {score.score}/100 ({score.label})",
        f"Based on data from: {summary.calendar_date}",
        "",
        "Components:",
    ]
    for c in score.components:
        lines.append(f"  - {c.name}: {c.detail} (normalized: {c.normalized:.0f}/100)")

    return "\n".join(lines)


async def _get_plan_adherence(db: AsyncSession, period: str = "this_week") -> str:
    from src.services.plan_engine import get_plan_adherence

    today = date.today()

    if period == "this_week":
        start = today - timedelta(days=today.weekday())
        end = today
    elif period == "last_week":
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
    elif period == "this_month":
        start = today.replace(day=1)
        end = today
    else:
        start = today - timedelta(days=7)
        end = today

    stats = await get_plan_adherence(db, start, end)

    lines = [
        f"Plan Adherence ({period.replace('_', ' ')}: {start} to {end}):",
        f"  Total planned: {stats['total_planned']}",
        f"  Completed: {stats['completed']}",
        f"  Missed: {stats['missed']}",
        f"  Skipped: {stats['skipped']}",
        f"  Completion rate: {stats['completion_pct']}%",
    ]
    return "\n".join(lines)


async def _get_upcoming_workouts(db: AsyncSession, count: int = 5) -> str:
    from src.services.plan_engine import get_upcoming_workouts

    workouts = await get_upcoming_workouts(db, count=count)

    if not workouts:
        return "No upcoming workouts planned."

    lines = []
    for w in workouts:
        line = f"- {w['date']} {w['discipline']}"
        if w.get("workout_type"):
            line += f" ({w['workout_type']})"
        if w.get("target_duration"):
            line += f" {w['target_duration']}min"
        if w.get("description"):
            line += f": {w['description']}"
        lines.append(line)
    return "\n".join(lines)


async def _get_race_countdown(db: AsyncSession) -> str:
    today = date.today()
    result = await db.execute(
        select(Race)
        .where(Race.date >= today)
        .order_by(Race.date)
    )
    races = result.scalars().all()

    if not races:
        return "No upcoming races on the calendar."

    lines = []
    for r in races:
        days = (r.date - today).days
        weeks = days // 7
        line = f"- {r.name} ({r.distance_type}): {r.date} — {days} days ({weeks} weeks) out"
        if r.goal_time:
            hours = r.goal_time // 3600
            mins = (r.goal_time % 3600) // 60
            line += f" | Goal: {hours}:{mins:02d}"
        lines.append(line)
    return "\n".join(lines)


async def _get_training_load(db: AsyncSession, weeks: int = 4) -> str:
    from src.services.analytics import training_load_trend

    trend = await training_load_trend(db, weeks=weeks)

    if not trend:
        return "No training load data available for the requested period."

    lines = [f"Training Load Trend ({weeks} weeks):"]
    for entry in trend:
        load_7d = entry.get("load_7d")
        load_28d = entry.get("load_28d")
        load_7d_str = f"{load_7d:.0f}" if load_7d is not None else "N/A"
        load_28d_str = f"{load_28d:.0f}" if load_28d is not None else "N/A"
        ratio = ""
        if load_7d is not None and load_28d is not None and load_28d > 0:
            acr = load_7d / load_28d
            ratio = f" (A:C ratio {acr:.2f})"
        lines.append(
            f"  - Week of {entry['week_start']}: "
            f"7d load {load_7d_str}, 28d load {load_28d_str}{ratio}"
        )
    return "\n".join(lines)


async def _modify_workout(db: AsyncSession, workout_id: str, reason: str) -> str:
    try:
        from uuid import UUID

        uuid = UUID(workout_id)
    except ValueError:
        return f"Error: Invalid workout ID format: {workout_id}"

    result = await db.execute(
        select(PlannedWorkout).where(PlannedWorkout.id == uuid)
    )
    workout = result.scalar_one_or_none()

    if not workout:
        return f"No planned workout found with ID {workout_id}."

    lines = [
        "Current workout:",
        f"  Date: {workout.date}",
        f"  Discipline: {workout.discipline}",
        f"  Type: {workout.workout_type or 'Not specified'}",
        f"  Target duration: {workout.target_duration or 'Not specified'}min",
        f"  Description: {workout.description or 'None'}",
        f"  Status: {workout.status}",
        "",
        f"Modification reason: {reason}",
        "",
        "Suggest the modified workout to the athlete. "
        "Changes will not be applied until the athlete confirms.",
    ]
    return "\n".join(lines)


async def _update_athlete_profile(db: AsyncSession, key: str, note: str) -> str:
    result = await db.execute(select(AthleteProfile).limit(1))
    profile = result.scalar_one_or_none()

    if profile is None:
        profile = AthleteProfile(notes={key: note})
        db.add(profile)
    else:
        current_notes = profile.notes or {}
        current_notes[key] = note
        profile.notes = current_notes

    await db.commit()
    return f"Saved observation — {key}: {note}"
