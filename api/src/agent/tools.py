"""Agent tool definitions and handlers for the training assistant coach.

Each tool allows the Claude Agent SDK coach to query the database and return
formatted text for the agent to reason about.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings

from src.db.models import (
    AlertLog,
    AssistantPlanEntry,
    AthleteBiometrics,
    AthleteProfile,
    GarminActivity,
    GarminDailySummary,
    PlannedWorkout,
    Race,
    RecommendationChange,
)
from src.services.assistant_plan import (
    acquire_workout_lock,
    assistant_plan_table_available,
    generate_assistant_plan,
    is_assistant_owned_mode,
    release_workout_lock,
)
from src.services.recommendations import (
    create_coach_recommendation_intent,
    decide_recommendation,
    recommendation_table_available,
)
from src.services.units import (
    format_distance_from_kilometers,
    format_distance_from_meters,
    format_pace_per_mile,
)
from src.services.plan_changes import (
    list_recent_plan_changes,
    refresh_with_plan_change_tracking,
)
from src.services.recovery_time import normalize_recovery_time_hours
from src.services.workout_duration import format_planned_duration

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
        "name": "compare_planned_vs_actual",
        "description": (
            "Compare recent planned workouts against completed activities with day-by-day "
            "planned + actual data and current recovery inputs. Returns raw comparison data "
            "for model reasoning (no hardcoded coaching recommendation)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {
                    "type": "integer",
                    "description": "How many recent days to compare (up to 21).",
                    "default": 7,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_plan_mode",
        "description": "Get current plan ownership mode (assistant-owned vs Garmin-owned).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "build_assistant_plan",
        "description": (
            "Generate or refresh an assistant-owned rolling training plan and optionally "
            "sync near-term workouts to Garmin. Use this for bulk rebuilds, not single-session swaps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days_ahead": {
                    "type": "integer",
                    "description": "How many days to generate ahead.",
                    "default": 14,
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Replace existing assistant-owned future workouts.",
                    "default": True,
                },
                "sync_to_garmin": {
                    "type": "boolean",
                    "description": "Push generated workouts to Garmin calendar.",
                    "default": True,
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
        "name": "get_plan_changes",
        "description": (
            "Get recent Garmin-driven plan changes (added, moved, updated, removed workouts) "
            "so coaching advice reflects adaptive schedule shifts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {
                    "type": "integer",
                    "description": "How many days of change history to inspect.",
                    "default": 7,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of changes to return.",
                    "default": 10,
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
                "workout_date": {
                    "type": "string",
                    "description": "Workout date in YYYY-MM-DD when workout_id is unavailable.",
                },
                "discipline": {
                    "type": "string",
                    "description": "Optional discipline filter when resolving by date (run/bike/swim/strength).",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for the suggested modification.",
                },
            },
            "required": ["reason"],
        },
    },
    {
        "name": "apply_workout_change",
        "description": (
            "Atomically apply a workout change: update the planned workout in the DB, "
            "write back to Garmin (with verification), and return the final status. "
            "This is the preferred single-step tool — use it instead of the old "
            "create/apply two-step flow."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workout_date": {
                    "type": "string",
                    "description": "Target workout date in YYYY-MM-DD (required).",
                },
                "discipline": {
                    "type": "string",
                    "description": "Target discipline (run/bike/swim/strength).",
                },
                "workout_type": {
                    "type": "string",
                    "description": "Workout type label (e.g. endurance_run, quality_intervals).",
                },
                "target_duration": {
                    "type": "integer",
                    "description": "Planned duration in minutes.",
                },
                "target_distance": {
                    "type": "number",
                    "description": "Target distance in meters.",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed workout description and coaching cues.",
                },
                "workout_steps": {
                    "type": "array",
                    "description": "Structured workout steps with durations and cues.",
                    "items": {
                        "type": "object",
                    },
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for making this change.",
                },
            },
            "required": ["workout_date"],
        },
    },
    {
        "name": "create_plan_change_intent",
        "description": (
            "[Legacy] Create a detailed, approval-gated plan-change intent. "
            "Prefer apply_workout_change for atomic one-step changes. "
            "This records the coach's proposed change but does NOT apply it yet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "recommendation_text": {
                    "type": "string",
                    "description": "Human-readable recommendation summary.",
                },
                "workout_id": {
                    "type": "string",
                    "description": "UUID of target planned workout when available.",
                },
                "workout_date": {
                    "type": "string",
                    "description": "Target workout date in YYYY-MM-DD.",
                },
                "discipline": {
                    "type": "string",
                    "description": "Target discipline (run/bike/swim/strength).",
                },
                "workout_type": {
                    "type": "string",
                    "description": "Workout type label for the proposed session.",
                },
                "target_duration": {
                    "type": "integer",
                    "description": "Planned duration in minutes.",
                },
                "target_distance": {
                    "type": "number",
                    "description": "Target distance in meters for the structured workout.",
                },
                "target_hr_zone": {
                    "type": "integer",
                    "description": "Optional heart-rate zone target.",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed workout description and coaching cues.",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for making this change.",
                },
                "workout_steps": {
                    "type": "array",
                    "description": "Structured workout steps with durations and cues.",
                    "items": {
                        "type": "object",
                    },
                },
            },
            "required": ["recommendation_text"],
        },
    },
    {
        "name": "apply_plan_change_intent",
        "description": (
            "Apply or reject a previously created plan-change intent through the execution "
            "pipeline. Use only after the athlete explicitly approves."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intent_id": {
                    "type": "string",
                    "description": "Recommendation/intent UUID.",
                },
                "decision": {
                    "type": "string",
                    "enum": ["approved", "rejected", "changes_requested"],
                    "default": "approved",
                    "description": "Decision on the intent.",
                },
                "note": {
                    "type": "string",
                    "description": "Optional decision note.",
                },
                "requested_changes": {
                    "type": "string",
                    "description": "Requested edits when decision is changes_requested.",
                },
            },
            "required": ["intent_id", "decision"],
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
    {
        "name": "refresh_garmin_data",
        "description": (
            "Run an on-demand Garmin refresh so plan/calendar and daily recovery metrics "
            "are re-synced before answering freshness or mismatch questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_calendar": {
                    "type": "boolean",
                    "description": "Also refresh Garmin calendar/planned workouts.",
                    "default": True,
                },
                "force": {
                    "type": "boolean",
                    "description": "Bypass short cooldown and trigger refresh now.",
                    "default": True,
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
        "compare_planned_vs_actual": _compare_planned_vs_actual,
        "get_plan_mode": _get_plan_mode,
        "build_assistant_plan": _build_assistant_plan,
        "get_upcoming_workouts": _get_upcoming_workouts,
        "get_plan_changes": _get_plan_changes,
        "get_race_countdown": _get_race_countdown,
        "get_training_load": _get_training_load,
        "modify_workout": _modify_workout,
        "apply_workout_change": _apply_workout_change,
        "create_plan_change_intent": _create_plan_change_intent,
        "apply_plan_change_intent": _apply_plan_change_intent,
        "update_athlete_profile": _update_athlete_profile,
        "get_discipline_distribution": _get_discipline_distribution,
        "get_fitness_trends": _get_fitness_trends,
        "get_biometrics": _get_biometrics,
        "get_active_alerts": _get_active_alerts,
        "refresh_garmin_data": _refresh_garmin_data,
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


def _normalize_discipline_filter(value: str | None) -> str:
    raw = (value or "all").strip().lower()
    aliases = {
        "all": "all",
        "running": "run",
        "run": "run",
        "trail_running": "run",
        "cycling": "bike",
        "cycle": "bike",
        "bike": "bike",
        "biking": "bike",
        "peloton": "bike",
        "spinning": "bike",
        "spin": "bike",
        "swim": "swim",
        "swimming": "swim",
        "pool_swim": "swim",
        "open_water_swim": "swim",
        "strength": "strength",
        "strength_training": "strength",
        "walk": "walk",
        "walking": "walk",
        "hike": "walk",
        "hiking": "walk",
    }
    return aliases.get(raw, raw)


def _classify_activity_discipline(activity: GarminActivity) -> str:
    text = f"{activity.sport_type or ''} {activity.activity_type or ''}".lower()
    if "run" in text or "trail" in text:
        return "run"
    if "bike" in text or "cycl" in text or "peloton" in text or "spin" in text:
        return "bike"
    if "swim" in text or "pool" in text or "open_water" in text:
        return "swim"
    if "strength" in text or "lift" in text:
        return "strength"
    if "walk" in text or "hike" in text:
        return "walk"
    return "other"


def _matches_discipline_filter(discipline: str, activity: GarminActivity) -> bool:
    normalized_filter = _normalize_discipline_filter(discipline)
    if normalized_filter == "all":
        return True
    classified = _classify_activity_discipline(activity)
    if classified == normalized_filter:
        return True
    raw_text = f"{activity.sport_type or ''} {activity.activity_type or ''}".lower()
    return normalized_filter in raw_text


async def _query_activities(
    db: AsyncSession,
    discipline: str = "all",
    days_back: int = 7,
    limit: int = 10,
) -> str:
    clamped_days_back = max(1, min(days_back, 60))
    clamped_limit = max(1, min(limit, 50))

    q = (
        select(GarminActivity)
        .where(
            GarminActivity.start_time
            >= datetime.now(timezone.utc) - timedelta(days=clamped_days_back)
        )
        .order_by(GarminActivity.start_time.desc())
    )

    result = await db.execute(q)
    recent_activities = list(result.scalars().all())
    filtered_activities = [
        activity
        for activity in recent_activities
        if _matches_discipline_filter(discipline, activity)
    ]
    activities = filtered_activities[:clamped_limit]

    if not activities:
        normalized = _normalize_discipline_filter(discipline)
        if normalized != "all" and recent_activities:
            return (
                f"No {normalized} activities found in the last {clamped_days_back} days. "
                "I can still review your full recent activity list if you want."
            )
        return "No activities found for the given criteria."

    lines = []
    for a in activities:
        line = f"- {a.start_time:%Y-%m-%d} {a.activity_type}: {a.name}"
        if a.duration_seconds:
            mins = a.duration_seconds / 60
            line += f" ({mins:.0f}min)"
        if a.distance_meters:
            line += f" {format_distance_from_meters(a.distance_meters, a.sport_type or a.activity_type)}"
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

    recovery_time_hours = normalize_recovery_time_hours(
        summary.recovery_time_hours,
        summary.raw_data,
    )
    score = compute_readiness(
        hrv_last_night=summary.hrv_last_night,
        hrv_7d_avg=summary.hrv_7d_avg,
        sleep_score=summary.sleep_score,
        body_battery_wake=summary.body_battery_at_wake,
        recovery_time_hours=recovery_time_hours,
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
    strict_completed = stats.get("strict_completed", stats.get("completed", 0))
    aligned_substitutions = stats.get("aligned_substitutions", 0)
    same_day_substitutions = stats.get("same_day_substitutions", aligned_substitutions)
    shifted_substitutions = stats.get("shifted_substitutions", 0)
    due_planned = stats.get("due_planned", stats.get("total_planned", 0))
    pending_future = stats.get("pending_future", 0)
    strict_pct = stats.get("strict_completion_pct")
    detail_pct = stats.get("detail_compliance_pct")
    completed_detail_pct = stats.get("completed_detail_compliance_pct")
    duration_match_pct = stats.get("duration_match_pct")
    distance_match_pct = stats.get("distance_match_pct")
    on_schedule_pct = stats.get("on_schedule_pct")
    high_fidelity_completed = stats.get("high_fidelity_completed", 0)
    low_fidelity_completed = stats.get("low_fidelity_completed", 0)

    lines = [
        f"Plan Adherence ({period.replace('_', ' ')}: {start} to {end}):",
        f"  Total planned: {stats['total_planned']}",
        f"  Due so far: {due_planned}",
        f"  On-plan completed: {stats['completed']}",
        f"  Strict completed: {strict_completed}",
        f"  Aligned substitutions: {aligned_substitutions} (same-day: {same_day_substitutions}, shifted ±1d: {shifted_substitutions})",
        f"  Missed: {stats['missed']}",
        f"  Skipped: {stats['skipped']}",
        f"  Completion rate: {stats['completion_pct']}%",
        (
            "  Detail compliance (due): "
            f"{detail_pct}% | completed-only: {completed_detail_pct}%"
        ),
        (
            "  Detail components: "
            f"duration={duration_match_pct}% "
            f"distance={'-' if distance_match_pct is None else f'{distance_match_pct}%'} "
            f"on-schedule={on_schedule_pct}%"
        ),
        (
            "  Fidelity breakdown: "
            f"high={high_fidelity_completed} low={low_fidelity_completed}"
        ),
    ]
    if strict_pct is not None:
        lines.append(f"  Strict completion rate: {strict_pct}%")
    if pending_future:
        lines.append(f"  Pending future workouts: {pending_future}")
    return "\n".join(lines)


def _planned_discipline(value: str | None) -> str:
    normalized = _normalize_discipline_filter(value or "other")
    return normalized if normalized != "all" else "other"


def _dedupe_planned_workouts_for_compare(
    workouts: list[PlannedWorkout],
) -> list[PlannedWorkout]:
    deduped: dict[tuple, PlannedWorkout] = {}
    for workout in workouts:
        key = (
            workout.date,
            _planned_discipline(workout.discipline),
            (workout.workout_type or "").strip().lower(),
            int(workout.target_duration or 0),
            (workout.description or "").strip().lower(),
        )
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = workout
            continue
        existing_created = existing.created_at or datetime.min.replace(
            tzinfo=timezone.utc
        )
        current_created = workout.created_at or datetime.min.replace(
            tzinfo=timezone.utc
        )
        if current_created >= existing_created:
            deduped[key] = workout
    return sorted(
        deduped.values(),
        key=lambda item: (
            item.date or date.min,
            item.created_at or datetime.min.replace(tzinfo=timezone.utc),
        ),
    )


async def _compare_planned_vs_actual(db: AsyncSession, days_back: int = 7) -> str:
    from src.services.plan_engine import (
        _index_activities_by_day_and_discipline,
        _reconcile_due_workouts_detailed,
    )

    clamped_days = max(1, min(int(days_back or 7), 21))
    today = date.today()
    start = today - timedelta(days=clamped_days - 1)

    workouts_query = select(PlannedWorkout).where(
        and_(
            PlannedWorkout.date >= start,
            PlannedWorkout.date <= today,
        )
    )
    if is_assistant_owned_mode():
        if not await assistant_plan_table_available(db):
            return "Assistant plan comparison unavailable: assistant_plan_entries table not ready."
        workouts_query = workouts_query.join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )
    workouts_query = workouts_query.order_by(
        PlannedWorkout.date.asc(), PlannedWorkout.created_at.asc()
    )

    workout_result = await db.execute(workouts_query)
    planned_workouts = _dedupe_planned_workouts_for_compare(
        list(workout_result.scalars().all())
    )
    if not planned_workouts:
        return f"No planned workouts found between {start} and {today}."

    activity_result = await db.execute(
        select(GarminActivity).where(
            and_(
                GarminActivity.start_time
                >= datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
                GarminActivity.start_time
                < datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
                + timedelta(days=1),
            )
        )
    )
    activities = list(activity_result.scalars().all())
    activities_by_day_and_discipline = _index_activities_by_day_and_discipline(
        activities
    )
    reconciliation = _reconcile_due_workouts_detailed(
        planned_workouts,
        activities_by_day_and_discipline,
    )
    match_rows = reconciliation.get("matches", [])
    done_rows = [
        row
        for row in match_rows
        if row.get("match_type")
        in {"strict", "aligned_same_day", "aligned_shifted_day"}
    ]
    fidelity_values = [
        float(row.get("fidelity_score"))
        for row in done_rows
        if isinstance(row.get("fidelity_score"), (int, float))
    ]
    avg_fidelity = (
        round(sum(fidelity_values) / len(fidelity_values) * 100, 1)
        if fidelity_values
        else 0.0
    )
    match_by_workout_id = {
        row.get("planned_workout_id"): row
        for row in match_rows
        if row.get("planned_workout_id")
    }

    planned_by_day: dict[date, list[PlannedWorkout]] = {}
    for workout in planned_workouts:
        if workout.date is None:
            continue
        planned_by_day.setdefault(workout.date, []).append(workout)

    activities_by_day: dict[date, list[GarminActivity]] = {}
    for activity in activities:
        if activity.start_time is None:
            continue
        day = activity.start_time.date()
        activities_by_day.setdefault(day, []).append(activity)

    for bucket in activities_by_day.values():
        bucket.sort(
            key=lambda item: (
                float(item.duration_seconds or 0.0),
                item.start_time or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )

    lines: list[str] = [
        f"Planned vs Actual Data ({start} to {today}):",
        "(Raw comparison feed — no rule-based interpretation.)",
        (
            "Alignment summary: "
            f"strict={reconciliation.get('strict_completed', 0)}, "
            f"aligned_same_day={reconciliation.get('same_day_substitutions', 0)}, "
            f"aligned_shifted_±1d={reconciliation.get('shifted_substitutions', 0)}, "
            f"missed={reconciliation.get('missed', 0)}, "
            f"skipped={reconciliation.get('skipped', 0)}, "
            f"avg_fidelity={avg_fidelity}%"
        ),
    ]

    day_count = (today - start).days + 1
    for offset in range(day_count):
        day = start + timedelta(days=offset)
        day_planned = planned_by_day.get(day, [])
        day_actual = activities_by_day.get(day, [])
        lines.append(f"\nDate: {day}")

        if day_planned:
            lines.append("  Planned:")
            for workout in day_planned:
                discipline = _planned_discipline(workout.discipline)
                duration_text = format_planned_duration(workout.target_duration)
                distance_text = format_distance_from_meters(
                    workout.target_distance,
                    discipline,
                )
                hr_zone = (
                    f"Z{int(workout.target_hr_zone)}"
                    if workout.target_hr_zone is not None
                    else "-"
                )
                description = (workout.description or "").strip()
                if len(description) > 180:
                    description = f"{description[:180].rstrip()}..."
                lines.append(
                    (
                        f"  - {discipline} {workout.workout_type or 'session'} | "
                        f"duration={duration_text} distance={distance_text} hr_zone={hr_zone}"
                    )
                )
                match = match_by_workout_id.get(str(workout.id))
                if match:
                    match_type = str(match.get("match_type") or "")
                    day_offset = match.get("day_offset")
                    activity_date = match.get("activity_date") or "-"
                    activity_id = match.get("activity_id") or "-"
                    fidelity_score = match.get("fidelity_score")
                    fidelity_components = match.get("fidelity_components")
                    fidelity_label = (
                        f"{round(float(fidelity_score) * 100, 1)}%"
                        if isinstance(fidelity_score, (int, float))
                        else "-"
                    )
                    if match_type == "strict":
                        lines.append(
                            f"    alignment: strict_completed_status | fidelity={fidelity_label}"
                        )
                    elif match_type == "aligned_same_day":
                        lines.append(
                            f"    alignment: aligned_same_day (activity_id={activity_id}) | fidelity={fidelity_label}"
                        )
                    elif match_type == "aligned_shifted_day":
                        offset_value = (
                            int(day_offset)
                            if isinstance(day_offset, (int, float))
                            else 0
                        )
                        lines.append(
                            (
                                "    alignment: aligned_shifted_±1d "
                                f"(offset={offset_value:+d}, activity_date={activity_date}, activity_id={activity_id}) "
                                f"| fidelity={fidelity_label}"
                            )
                        )
                    elif match_type == "skipped":
                        lines.append("    alignment: skipped")
                    elif match_type == "missed":
                        lines.append("    alignment: unmatched")
                    if isinstance(fidelity_components, dict):
                        duration_component = fidelity_components.get("duration")
                        distance_component = fidelity_components.get("distance")
                        timing_component = fidelity_components.get("timing")
                        lines.append(
                            (
                                "    fidelity components: "
                                f"duration={'-' if duration_component is None else f'{round(float(duration_component) * 100, 1)}%'} "
                                f"distance={'-' if distance_component is None else f'{round(float(distance_component) * 100, 1)}%'} "
                                f"timing={'-' if timing_component is None else f'{round(float(timing_component) * 100, 1)}%'}"
                            )
                        )
                if description:
                    lines.append(f"    notes: {description}")
        else:
            lines.append("  Planned: none")

        if day_actual:
            lines.append("  Actual:")
            for activity in day_actual:
                actual_disc = _classify_activity_discipline(activity)
                duration_text = format_planned_duration(
                    float(activity.duration_seconds or 0.0) / 60.0
                )
                distance_text = format_distance_from_meters(
                    activity.distance_meters,
                    activity.sport_type or activity.activity_type,
                )
                avg_hr = (
                    str(int(activity.average_hr))
                    if activity.average_hr is not None
                    else "-"
                )
                lines.append(
                    (
                        f"  - {actual_disc} {activity.activity_type or 'activity'} "
                        f'"{activity.name or "Unnamed"}" | duration={duration_text} '
                        f"distance={distance_text} avg_hr={avg_hr}"
                    )
                )
        else:
            lines.append("  Actual: none")

    latest_result = await db.execute(
        select(GarminDailySummary)
        .order_by(GarminDailySummary.calendar_date.desc())
        .limit(1)
    )
    summary = latest_result.scalar_one_or_none()
    readiness = (
        int(summary.training_readiness_score)
        if summary and summary.training_readiness_score is not None
        else None
    )
    sleep_score = (
        int(summary.sleep_score)
        if summary and summary.sleep_score is not None
        else None
    )
    hrv_last = (
        int(summary.hrv_last_night)
        if summary and summary.hrv_last_night is not None
        else None
    )
    body_battery = (
        int(summary.body_battery_at_wake)
        if summary and summary.body_battery_at_wake is not None
        else None
    )

    next_workout_query = (
        select(PlannedWorkout)
        .where(
            and_(
                PlannedWorkout.date >= today,
                PlannedWorkout.status.in_(["upcoming", "modified"]),
            )
        )
        .order_by(PlannedWorkout.date.asc(), PlannedWorkout.created_at.asc())
        .limit(1)
    )
    if is_assistant_owned_mode():
        next_workout_query = next_workout_query.join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )
    next_workout_result = await db.execute(next_workout_query)
    next_workout = next_workout_result.scalar_one_or_none()

    next_label = "none scheduled"
    if next_workout and next_workout.date:
        next_label = (
            f"{next_workout.date} {_planned_discipline(next_workout.discipline)} "
            f"{next_workout.workout_type or 'session'} "
            f"{format_planned_duration(next_workout.target_duration)}"
        )
    lines.extend(
        [
            "",
            "Context Inputs:",
            f"  Latest readiness: {readiness if readiness is not None else '-'}",
            f"  Latest sleep score: {sleep_score if sleep_score is not None else '-'}",
            f"  Latest HRV last night: {hrv_last if hrv_last is not None else '-'}",
            f"  Latest body battery at wake: {body_battery if body_battery is not None else '-'}",
            f"  Next up: {next_label}",
        ]
    )

    return "\n".join(lines)


async def _get_plan_mode(db: AsyncSession) -> str:
    _ = db
    mode = "assistant" if is_assistant_owned_mode() else "garmin"
    return f"Plan ownership mode: {mode}"


async def _build_assistant_plan(
    db: AsyncSession,
    days_ahead: int = 14,
    overwrite: bool = True,
    sync_to_garmin: bool = True,
) -> str:
    if not is_assistant_owned_mode():
        return (
            "Cannot build assistant plan: plan ownership mode is not assistant. "
            "Set plan_ownership_mode=assistant first."
        )

    result = await generate_assistant_plan(
        db,
        days_ahead=days_ahead,
        overwrite=overwrite,
        sync_to_garmin=sync_to_garmin,
    )
    await db.commit()
    lines = [
        "Assistant plan generated.",
        f"  Phase: {result.get('phase')}",
        f"  Window: {result.get('window_start')} -> {result.get('window_end')}",
        f"  Created workouts: {result.get('created_workouts')}",
        f"  Preserved locked days: {result.get('preserved_locked', 0)}",
        f"  Preserved modified days: {result.get('preserved_modified', 0)}",
        f"  Preserved approved-intent days: {result.get('preserved_approved_recommendations', 0)}",
        (
            "  Garmin sync: "
            f"{result.get('synced_success', 0)} success / "
            f"{result.get('synced_failed', 0)} failed / "
            f"{result.get('synced_skipped', 0)} skipped"
        ),
    ]
    return "\n".join(lines)


async def _get_upcoming_workouts(db: AsyncSession, count: int = 5) -> str:
    from src.services.plan_engine import get_upcoming_workouts

    workouts = await get_upcoming_workouts(db, count=count)

    if not workouts:
        return "No upcoming workouts planned."

    lines = []
    for w in workouts:
        line = f"- id={w['id']} | {w['date']} {w['discipline']}"
        if w.get("workout_type"):
            line += f" ({w['workout_type']})"
        if w.get("target_duration"):
            line += f" {format_planned_duration(w['target_duration'])}"
        if w.get("description"):
            line += f": {w['description']}"
        lines.append(line)
    return "\n".join(lines)


async def _get_plan_changes(
    db: AsyncSession,
    days_back: int = 7,
    limit: int = 10,
) -> str:
    events = await list_recent_plan_changes(
        db,
        days_back=days_back,
        limit=limit,
    )
    if not events:
        return f"No Garmin plan changes detected in the last {days_back} days."

    lines = [f"Recent Garmin Plan Changes (last {days_back} days):"]
    for event in events:
        when = event.get("detected_at", "")
        summary = event.get("summary", "Plan changed.")
        lines.append(f"- {summary} [{when}]")
    return "\n".join(lines)


async def _get_race_countdown(db: AsyncSession) -> str:
    today = date.today()
    result = await db.execute(
        select(Race).where(Race.date >= today).order_by(Race.date)
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


async def _modify_workout(
    db: AsyncSession,
    reason: str,
    workout_id: str | None = None,
    workout_date: str | None = None,
    discipline: str | None = None,
) -> str:
    workout = None
    if workout_id:
        try:
            from uuid import UUID

            uuid = UUID(workout_id)
        except ValueError:
            return f"Error: Invalid workout ID format: {workout_id}"
        result = await db.execute(
            select(PlannedWorkout).where(PlannedWorkout.id == uuid)
        )
        workout = result.scalar_one_or_none()

    if workout is None and workout_date:
        try:
            parsed_date = date.fromisoformat(workout_date)
        except ValueError:
            return (
                f"Error: Invalid workout_date format: {workout_date}. Use YYYY-MM-DD."
            )

        query = (
            select(PlannedWorkout)
            .where(
                and_(
                    PlannedWorkout.date == parsed_date,
                    PlannedWorkout.status.in_(["upcoming", "modified"]),
                )
            )
            .order_by(PlannedWorkout.created_at.desc())
            .limit(1)
        )
        if discipline:
            query = query.where(
                PlannedWorkout.discipline.ilike(f"%{discipline.strip()}%")
            )
        if is_assistant_owned_mode():
            query = query.join(
                AssistantPlanEntry,
                AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
            )
        result = await db.execute(query)
        workout = result.scalar_one_or_none()

    if not workout:
        if workout_id:
            return f"No planned workout found with ID {workout_id}."
        if workout_date:
            return (
                "No planned workout found for "
                f"{workout_date}" + (f" ({discipline})" if discipline else "") + "."
            )
        return "No workout target provided. Pass workout_id or workout_date."

    lines = [
        "Current workout:",
        f"  ID: {workout.id}",
        f"  Date: {workout.date}",
        f"  Discipline: {workout.discipline}",
        f"  Type: {workout.workout_type or 'Not specified'}",
        f"  Target duration: {format_planned_duration(workout.target_duration)}",
        f"  Description: {workout.description or 'None'}",
        f"  Status: {workout.status}",
        "",
        f"Modification reason: {reason}",
        "",
        "Suggest the modified workout to the athlete. "
        "Changes will not be applied until the athlete confirms.",
    ]
    return "\n".join(lines)


async def _apply_workout_change(
    db: AsyncSession,
    workout_date: str,
    discipline: str | None = None,
    workout_type: str | None = None,
    target_duration: int | None = None,
    target_distance: float | None = None,
    description: str | None = None,
    workout_steps: list[dict] | None = None,
    reason: str | None = None,
) -> str:
    import json as _json
    from uuid import uuid4 as _uuid4

    from src.services.garmin_writeback import (
        fallback_writeback_payload,
        write_recommendation_change,
    )
    from src.services.recommendations import (
        _coerce_float,
        _coerce_int,
        _hydrate_proposed_workout_details,
        _normalise_discipline,
        _sanitize_workout_steps,
    )

    try:
        parsed_date = date.fromisoformat(workout_date)
    except (ValueError, TypeError):
        return _json.dumps(
            {
                "status": "failed",
                "error": f"Invalid workout_date: {workout_date}. Use YYYY-MM-DD.",
            }
        )

    proposed: dict = {
        "workout_date": parsed_date.isoformat(),
        "discipline": _normalise_discipline(discipline),
        "workout_type": (workout_type or "").strip() or None,
        "target_duration": _coerce_int(target_duration),
        "target_distance": _coerce_float(target_distance),
        "description": (description or "").strip() or None,
        "reason": (reason or "").strip() or None,
    }
    sanitized_steps = _sanitize_workout_steps(workout_steps)
    if sanitized_steps:
        proposed["workout_steps"] = sanitized_steps
    proposed = _hydrate_proposed_workout_details(proposed)

    query = (
        select(PlannedWorkout)
        .where(
            and_(
                PlannedWorkout.date == parsed_date,
                PlannedWorkout.status.in_(["upcoming", "modified"]),
            )
        )
        .order_by(PlannedWorkout.created_at.desc())
        .limit(1)
    )
    if proposed.get("discipline"):
        query = query.where(
            PlannedWorkout.discipline.ilike(f"%{proposed['discipline']}%")
        )
    if is_assistant_owned_mode():
        query = query.join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )
    result = await db.execute(query)
    workout = result.scalar_one_or_none()

    created_new = False
    if workout is None:
        workout = PlannedWorkout(
            id=_uuid4(),
            plan_id=None,
            date=parsed_date,
            discipline=proposed.get("discipline") or "run",
            workout_type=proposed.get("workout_type") or "session",
            target_duration=proposed.get("target_duration"),
            target_distance=proposed.get("target_distance"),
            description=proposed.get("description"),
            status="modified",
            created_at=datetime.now(timezone.utc),
        )
        db.add(workout)
        await db.flush()
        created_new = True

    locked = False
    try:
        locked = await acquire_workout_lock(db, workout.id)

        if proposed.get("discipline"):
            workout.discipline = proposed["discipline"]
        if proposed.get("workout_type"):
            workout.workout_type = proposed["workout_type"]
        new_dur = _coerce_int(proposed.get("target_duration"))
        if new_dur is not None and new_dur > 0:
            workout.target_duration = new_dur
        new_dist = _coerce_float(proposed.get("target_distance"))
        if new_dist is not None and new_dist > 0:
            workout.target_distance = new_dist
        if proposed.get("description"):
            workout.description = proposed["description"]
        workout.status = "modified"

        await db.flush()

        changes_applied = {
            k: v for k, v in proposed.items() if v is not None and k != "reason"
        }

        garmin_sync: dict = {}
        final_status = "saved_local"

        if not settings.garmin_writeback_enabled:
            garmin_sync = {"status": "skipped", "reason": "garmin_writeback_disabled"}
            final_status = "saved_local"
        else:
            replace_workout_id = None
            if is_assistant_owned_mode():
                ape_result = await db.execute(
                    select(AssistantPlanEntry).where(
                        AssistantPlanEntry.planned_workout_id == workout.id
                    )
                )
                ape = ape_result.scalar_one_or_none()
                if ape and ape.garmin_workout_id:
                    candidate = str(ape.garmin_workout_id).strip()
                    if candidate:
                        replace_workout_id = candidate

            payload = fallback_writeback_payload(
                workout_date=workout.date.isoformat(),
                discipline=workout.discipline,
                workout_type=workout.workout_type,
                target_duration=workout.target_duration,
                description=workout.description,
                workout_steps=proposed.get("workout_steps")
                if isinstance(proposed.get("workout_steps"), list)
                else None,
                replace_workout_id=replace_workout_id,
                recommendation_text=reason,
            )
            garmin_sync = await write_recommendation_change(payload)

            if is_assistant_owned_mode():
                ape_result2 = await db.execute(
                    select(AssistantPlanEntry).where(
                        AssistantPlanEntry.planned_workout_id == workout.id
                    )
                )
                ape2 = ape_result2.scalar_one_or_none()
                if ape2 is not None:
                    ape2.garmin_sync_status = str(garmin_sync.get("status", "failed"))
                    ape2.garmin_sync_result = garmin_sync
                    ape2.updated_at = datetime.now(timezone.utc)
                    if garmin_sync.get("status") == "success":
                        new_gwid = str(garmin_sync.get("workout_id") or "").strip()
                        if new_gwid:
                            ape2.garmin_workout_id = new_gwid

            verify_status = garmin_sync.get("verification_status", "")
            raw_status = str(garmin_sync.get("status", "failed"))
            if verify_status == "success":
                final_status = "success"
            elif raw_status == "success":
                final_status = "synced_unverified"
            else:
                final_status = "failed"

        await db.commit()
        await db.refresh(workout)

        response = {
            "status": final_status,
            "workout_id": str(workout.id),
            "workout_date": workout.date.isoformat(),
            "changes_applied": changes_applied,
            "garmin_sync": garmin_sync,
        }
        if created_new:
            response["created_new"] = True
        return _json.dumps(response)
    except Exception as exc:
        await db.rollback()
        return _json.dumps({"status": "failed", "error": str(exc)})
    finally:
        if locked:
            try:
                await release_workout_lock(db, workout.id)
            except Exception:
                pass


async def _create_plan_change_intent(
    db: AsyncSession,
    recommendation_text: str,
    workout_id: str | None = None,
    workout_date: str | None = None,
    discipline: str | None = None,
    workout_type: str | None = None,
    target_duration: int | None = None,
    target_distance: float | None = None,
    target_hr_zone: int | None = None,
    description: str | None = None,
    reason: str | None = None,
    workout_steps: list[dict] | None = None,
) -> str:
    effective_date = workout_date
    if not effective_date and workout_id:
        try:
            from uuid import UUID

            uuid = UUID(workout_id)
        except ValueError:
            pass
        else:
            pw_result = await db.execute(
                select(PlannedWorkout).where(PlannedWorkout.id == uuid)
            )
            pw = pw_result.scalar_one_or_none()
            if pw and pw.date:
                effective_date = pw.date.isoformat()

    if not effective_date:
        proposed_workout: dict = {
            "workout_id": workout_id,
            "workout_date": workout_date,
            "discipline": discipline,
            "workout_type": workout_type,
            "target_duration": target_duration,
            "target_distance": target_distance,
            "target_hr_zone": target_hr_zone,
            "description": description,
            "reason": reason,
        }
        if workout_steps:
            proposed_workout["workout_steps"] = workout_steps

        try:
            rec = await create_coach_recommendation_intent(
                db,
                recommendation_text=recommendation_text,
                proposed_workout=proposed_workout,
                source="coach_intent",
            )
            await db.commit()
        except ValueError as exc:
            await db.rollback()
            return f"Could not create plan intent: {exc}"

        return (
            "Plan change intent created (legacy two-step; prefer apply_workout_change).\n"
            f"  Intent ID: {rec.id}\n"
            f"  Status: {rec.status}\n"
            f"  Target date: {rec.workout_date}\n"
            "Await athlete approval, then call apply_plan_change_intent with decision=approved."
        )

    merged_result = await _apply_workout_change(
        db,
        workout_date=effective_date,
        discipline=discipline,
        workout_type=workout_type,
        target_duration=target_duration,
        target_distance=target_distance,
        description=description,
        workout_steps=workout_steps,
        reason=reason or recommendation_text,
    )
    return (
        f"Plan change intent created and auto-applied via apply_workout_change.\n"
        f"  {merged_result}"
    )


async def _apply_plan_change_intent(
    db: AsyncSession,
    intent_id: str,
    decision: str = "approved",
    note: str | None = None,
    requested_changes: str | None = None,
) -> str:
    return (
        "apply_plan_change_intent is now a no-op alias. "
        "Use apply_workout_change for atomic one-step workout changes. "
        f"Intent {intent_id} was not processed through the legacy pipeline."
    )


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


async def _get_discipline_distribution(db: AsyncSession, days_back: int = 28) -> str:
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
                f"{format_distance_from_kilometers(v['distance_km'], disc)}, {v['count']} sessions"
            )

    lines.append(f"  Total: {total_hours:.1f} hours")

    # Add 70.3 target comparison
    target = {"swim": 25, "bike": 40, "run": 30}
    lines.append("\n70.3 Target vs Actual:")
    for disc, target_pct in target.items():
        actual_pct = round(volumes.get(disc, {}).get("hours", 0) / total_hours * 100, 1)
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

    lines = [
        f"Fitness Trends ({days_back} days, {first.calendar_date} to {last.calendar_date}):"
    ]

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
        select(AthleteBiometrics).order_by(AthleteBiometrics.date.desc()).limit(1)
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
        lines.append(
            f"  Lactate threshold pace: {format_pace_per_mile(bio.lactate_threshold_pace)}"
        )

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


async def _refresh_garmin_data(
    db: AsyncSession, include_calendar: bool = True, force: bool = True
) -> str:
    result, events = await refresh_with_plan_change_tracking(
        db,
        include_calendar=include_calendar,
        force=force,
        source="coach_refresh",
    )

    status = result.get("status")
    if status == "success":
        lines = [
            "Garmin refresh: success",
            f"  include_calendar: {bool(result.get('include_calendar', include_calendar))}",
        ]
        if include_calendar:
            lines.append(f"  plan_changes_detected: {len(events)}")
            for event in events[:5]:
                summary = event.get("summary")
                if summary:
                    lines.append(f"  - {summary}")
        if "days_back" in result:
            lines.append(f"  days_back: {result.get('days_back')}")
        for idx, cmd_result in enumerate(result.get("results", [])[:3], start=1):
            cmd = cmd_result.get("command", [])
            cmd_text = " ".join(str(part) for part in cmd[-4:]) if cmd else "(unknown)"
            lines.append(
                f"  command {idx}: {cmd_result.get('status', 'unknown')} [{cmd_text}]"
            )
            stdout_tail = (cmd_result.get("stdout") or "").strip()
            if stdout_tail:
                lines.append(f"    stdout: {stdout_tail.splitlines()[-1]}")
        return "\n".join(lines)

    reason = result.get("reason", "unknown")
    lines = [f"Garmin refresh: {status or 'unknown'} ({reason})"]
    if "lock_age_seconds" in result:
        lines.append(f"  lock_age_seconds: {result.get('lock_age_seconds')}")
    if "seconds_since_last_success" in result:
        lines.append(
            "  seconds_since_last_success: "
            f"{result.get('seconds_since_last_success')} "
            f"(min_interval={result.get('min_interval_seconds')})"
        )
    return "\n".join(lines)
