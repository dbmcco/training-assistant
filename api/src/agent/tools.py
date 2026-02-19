"""Agent tool definitions and handlers for the training assistant coach.

Each tool allows the Claude Agent SDK coach to query the database and return
formatted text for the agent to reason about.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    AlertLog,
    AthleteBiometrics,
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
    {
        "name": "get_discipline_distribution",
        "description": (
            "Get swim/bike/run training time distribution over a period. "
            "Shows hours and percentage per discipline, useful for checking "
            "if training balance matches race demands (e.g. 70.3 targets: "
            "~25% swim, 40% bike, 30% run)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {
                    "type": "integer",
                    "description": "Number of days to analyze.",
                    "default": 28,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_fitness_trends",
        "description": (
            "Get fitness trend data over time including VO2 max (run and cycling), "
            "training load, HRV averages, body battery, sleep scores, endurance score, "
            "and race predictions. Useful for assessing fitness trajectory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {
                    "type": "integer",
                    "description": "Number of days of trend data.",
                    "default": 60,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_biometrics",
        "description": (
            "Get the athlete's latest biometric data including weight, body fat, "
            "FTP, lactate threshold HR and pace, fitness age, and VO2 max details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_active_alerts",
        "description": (
            "Get unacknowledged proactive alerts including recovery warnings, "
            "coaching insights, and race countdown milestones."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of alerts to return.",
                    "default": 10,
                },
            },
            "required": [],
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
        "get_discipline_distribution": _get_discipline_distribution,
        "get_fitness_trends": _get_fitness_trends,
        "get_biometrics": _get_biometrics,
        "get_active_alerts": _get_active_alerts,
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


async def _get_discipline_distribution(
    db: AsyncSession, days_back: int = 28
) -> str:
    from src.services.analytics import weekly_volume_by_discipline

    cutoff = date.today() - timedelta(days=days_back)
    volumes = await weekly_volume_by_discipline(db, cutoff, date.today())

    if not volumes:
        return "No activity data found for the given period."

    # Compute totals and percentages
    total_hours = sum(v["hours"] for v in volumes.values()) or 1.0
    lines = [f"Discipline Distribution (last {days_back} days):"]
    for disc in ["swim", "run", "bike", "strength", "cross_training", "other"]:
        if disc in volumes:
            v = volumes[disc]
            pct = round(v["hours"] / total_hours * 100, 1)
            lines.append(
                f"  - {disc}: {v['hours']:.1f}h ({pct}%) — "
                f"{v['distance_km']:.1f}km, {v['count']} sessions"
            )

    lines.append(f"  Total: {total_hours:.1f} hours")

    # Add 70.3 target comparison
    target = {"swim": 25, "bike": 40, "run": 30}
    lines.append("\n70.3 Target vs Actual:")
    for disc, target_pct in target.items():
        actual_pct = round(
            volumes.get(disc, {}).get("hours", 0) / total_hours * 100, 1
        )
        delta = actual_pct - target_pct
        indicator = "✓" if abs(delta) < 10 else ("↑" if delta > 0 else "↓")
        lines.append(
            f"  - {disc}: {actual_pct:.0f}% actual vs {target_pct}% target {indicator}"
        )

    return "\n".join(lines)


async def _get_fitness_trends(db: AsyncSession, days_back: int = 60) -> str:
    cutoff = date.today() - timedelta(days=days_back)
    result = await db.execute(
        select(GarminDailySummary)
        .where(GarminDailySummary.calendar_date >= cutoff)
        .order_by(GarminDailySummary.calendar_date.asc())
    )
    summaries = result.scalars().all()

    if not summaries:
        return "No daily summary data found for the given period."

    # Get first and last for deltas
    first = summaries[0]
    last = summaries[-1]

    lines = [f"Fitness Trends ({days_back} days, {first.calendar_date} to {last.calendar_date}):"]

    # VO2 max
    if last.vo2_max_run is not None:
        delta = ""
        if first.vo2_max_run is not None:
            d = last.vo2_max_run - first.vo2_max_run
            delta = f" ({d:+.1f})" if d != 0 else " (stable)"
        lines.append(f"  VO2 max (run): {last.vo2_max_run}{delta}")

    if last.vo2_max_cycling is not None:
        delta = ""
        if first.vo2_max_cycling is not None:
            d = last.vo2_max_cycling - first.vo2_max_cycling
            delta = f" ({d:+.1f})" if d != 0 else " (stable)"
        lines.append(f"  VO2 max (cycling): {last.vo2_max_cycling}{delta}")

    # Endurance score
    if last.endurance_score is not None:
        lines.append(f"  Endurance score: {last.endurance_score}")

    # Training load
    if last.training_load_7d is not None:
        lines.append(f"  Training load 7d: {last.training_load_7d:.0f}")
    if last.training_load_28d is not None:
        lines.append(f"  Training load 28d: {last.training_load_28d:.0f}")

    # HRV trend
    if last.hrv_7d_avg is not None:
        delta = ""
        if first.hrv_7d_avg is not None:
            d = last.hrv_7d_avg - first.hrv_7d_avg
            delta = f" ({d:+d}ms)" if d != 0 else " (stable)"
        lines.append(f"  HRV 7d avg: {last.hrv_7d_avg}ms{delta}")

    # RHR trend
    if last.resting_heart_rate is not None:
        delta = ""
        if first.resting_heart_rate is not None:
            d = last.resting_heart_rate - first.resting_heart_rate
            delta = f" ({d:+d}bpm)" if d != 0 else " (stable)"
        lines.append(f"  Resting HR: {last.resting_heart_rate}bpm{delta}")

    # Race predictions
    preds = []
    if last.race_prediction_5k_seconds:
        m, s = divmod(last.race_prediction_5k_seconds, 60)
        preds.append(f"5K: {m}:{s:02d}")
    if last.race_prediction_10k_seconds:
        m, s = divmod(last.race_prediction_10k_seconds, 60)
        preds.append(f"10K: {m}:{s:02d}")
    if last.race_prediction_half_seconds:
        h = last.race_prediction_half_seconds // 3600
        m = (last.race_prediction_half_seconds % 3600) // 60
        preds.append(f"HM: {h}:{m:02d}")
    if last.race_prediction_marathon_seconds:
        h = last.race_prediction_marathon_seconds // 3600
        m = (last.race_prediction_marathon_seconds % 3600) // 60
        preds.append(f"Marathon: {h}:{m:02d}")
    if preds:
        lines.append(f"  Race predictions: {', '.join(preds)}")

    # Training status
    if last.training_status:
        lines.append(f"  Training status: {last.training_status}")

    return "\n".join(lines)


async def _get_biometrics(db: AsyncSession) -> str:
    result = await db.execute(
        select(AthleteBiometrics)
        .order_by(AthleteBiometrics.date.desc())
        .limit(1)
    )
    bio = result.scalar_one_or_none()

    if not bio:
        return "No biometric data available."

    lines = [f"Latest Biometrics (as of {bio.date}):"]
    if bio.weight_kg is not None:
        lines.append(f"  Weight: {bio.weight_kg:.1f} kg")
    if bio.body_fat_pct is not None:
        lines.append(f"  Body fat: {bio.body_fat_pct:.1f}%")
    if bio.muscle_mass_kg is not None:
        lines.append(f"  Muscle mass: {bio.muscle_mass_kg:.1f} kg")
    if bio.bmi is not None:
        lines.append(f"  BMI: {bio.bmi:.1f}")
    if bio.fitness_age is not None:
        lines.append(f"  Fitness age: {bio.fitness_age}")
    if bio.cycling_ftp is not None:
        lines.append(f"  Cycling FTP: {bio.cycling_ftp}W")
    if bio.lactate_threshold_hr is not None:
        lines.append(f"  Lactate threshold HR: {bio.lactate_threshold_hr} bpm")
    if bio.lactate_threshold_pace is not None:
        # pace is stored as seconds per km
        m, s = divmod(int(bio.lactate_threshold_pace), 60)
        lines.append(f"  Lactate threshold pace: {m}:{s:02d}/km")

    return "\n".join(lines)


async def _get_active_alerts(db: AsyncSession, limit: int = 10) -> str:
    result = await db.execute(
        select(AlertLog)
        .where(AlertLog.acknowledged == False)  # noqa: E712
        .order_by(AlertLog.created_at.desc())
        .limit(limit)
    )
    alerts = result.scalars().all()

    if not alerts:
        return "No active alerts."

    lines = [f"Active Alerts ({len(alerts)}):"]
    for a in alerts:
        lines.append(f"  - [{a.severity}] {a.title}: {a.message or ''}")

    return "\n".join(lines)
