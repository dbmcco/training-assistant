"""Plan engine service for training plan management."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import AssistantPlanEntry
from src.db.models import GarminActivity, PlannedWorkout, TrainingPlan
from src.services.assistant_plan import assistant_plan_table_available
from src.services.workout_duration import (
    normalize_planned_duration_minutes,
    planned_duration_seconds,
)


def _normalize_discipline(value: str | None) -> str:
    if not value:
        return "other"
    raw = value.strip().lower()
    if raw.startswith("run") or "trail" in raw:
        return "run"
    if raw.startswith("bike") or "cycl" in raw or "peloton" in raw or "spin" in raw:
        return "bike"
    if raw.startswith("swim") or "pool" in raw or "open_water" in raw:
        return "swim"
    if raw.startswith("strength") or "yoga" in raw or "pilates" in raw:
        return "strength"
    if raw.startswith("walk") or "hike" in raw:
        return "walk"
    if raw in {"cross_training", "cross-training"}:
        return "other"
    return raw or "other"


def _classify_activity_discipline(activity: GarminActivity) -> str:
    text = f"{activity.sport_type or ''} {activity.activity_type or ''}".lower()
    if "run" in text or "trail" in text:
        return "run"
    if "bike" in text or "cycl" in text or "peloton" in text or "spin" in text:
        return "bike"
    if "swim" in text or "pool" in text or "open_water" in text:
        return "swim"
    if "strength" in text or "yoga" in text or "pilates" in text:
        return "strength"
    if "walk" in text or "hike" in text:
        return "walk"
    return "other"


def _activity_date(activity: GarminActivity) -> date | None:
    if activity.start_time is None:
        return None
    return activity.start_time.date()


def _workout_dedupe_key(workout: PlannedWorkout) -> tuple:
    return (
        workout.date,
        _normalize_discipline(workout.discipline),
        (workout.workout_type or "").strip().lower(),
        (workout.description or "").strip().lower(),
        int(normalize_planned_duration_minutes(workout.target_duration) or 0),
        round(float(workout.target_distance or 0.0), 3),
    )


def _status_priority(status: str | None) -> int:
    order = {
        "completed": 6,
        "modified": 5,
        "upcoming": 4,
        "missed": 3,
        "skipped": 2,
    }
    return order.get((status or "").strip().lower(), 1)


def _coerce_created_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _assistant_mode() -> bool:
    return settings.plan_ownership_mode.strip().lower() == "assistant"


def _dedupe_workouts(workouts: list[PlannedWorkout]) -> list[PlannedWorkout]:
    deduped: dict[tuple, PlannedWorkout] = {}
    for workout in workouts:
        key = _workout_dedupe_key(workout)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = workout
            continue

        existing_rank = (
            _coerce_created_at(existing.created_at),
            _status_priority(existing.status),
        )
        current_rank = (
            _coerce_created_at(workout.created_at),
            _status_priority(workout.status),
        )
        if current_rank >= existing_rank:
            deduped[key] = workout
    return list(deduped.values())


def _minimum_expected_seconds(workout: PlannedWorkout) -> float:
    # 60% keeps substitutions realistic while allowing imperfect matches (e.g., 120m plan vs 90m bike).
    duration_seconds = planned_duration_seconds(workout.target_duration)
    if duration_seconds and duration_seconds > 0:
        return max(duration_seconds * 0.6, 10.0 * 60.0)

    defaults_minutes = {
        "run": 20,
        "bike": 30,
        "swim": 20,
        "strength": 15,
        "walk": 20,
        "other": 20,
    }
    discipline = _normalize_discipline(workout.discipline)
    return float(defaults_minutes.get(discipline, 20) * 60)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _duration_match_score(expected_seconds: float, actual_seconds: float) -> float:
    if expected_seconds <= 0:
        return 1.0
    return _clamp01(actual_seconds / expected_seconds)


def _distance_match_score(
    expected_meters: float | None, actual_meters: float | None
) -> float | None:
    if expected_meters is None or expected_meters <= 0:
        return None
    if actual_meters is None or actual_meters <= 0:
        return 0.0
    return _clamp01(actual_meters / expected_meters)


def _timing_match_score(day_offset: int | None) -> float:
    if day_offset == 0:
        return 1.0
    if day_offset in (-1, 1):
        return 0.85
    return 0.7


def _fidelity_for_match(
    *,
    match_type: str,
    day_offset: int | None,
    expected_seconds: float,
    actual_seconds: float | None,
    expected_distance_meters: float | None,
    actual_distance_meters: float | None,
) -> tuple[float, dict[str, float | None]]:
    if match_type == "strict":
        return (
            1.0,
            {
                "duration": 1.0,
                "distance": None,
                "timing": 1.0,
            },
        )
    if match_type in {"missed", "skipped"}:
        return (
            0.0,
            {
                "duration": 0.0,
                "distance": None,
                "timing": 0.0,
            },
        )

    duration_score = _duration_match_score(expected_seconds, float(actual_seconds or 0.0))
    timing_score = _timing_match_score(day_offset)
    distance_score = _distance_match_score(
        expected_distance_meters,
        actual_distance_meters,
    )

    weighted_sum = 0.0
    total_weight = 0.0
    for score, weight in (
        (duration_score, 0.65),
        (timing_score, 0.20),
        (distance_score, 0.15),
    ):
        if score is None:
            continue
        weighted_sum += float(score) * weight
        total_weight += weight

    fidelity = (weighted_sum / total_weight) if total_weight > 0 else 0.0
    return (
        _clamp01(fidelity),
        {
            "duration": round(duration_score, 3),
            "distance": (
                round(float(distance_score), 3) if distance_score is not None else None
            ),
            "timing": round(timing_score, 3),
        },
    )


def _index_activities_by_day_and_discipline(
    activities: list[GarminActivity],
) -> dict[tuple[date, str], list[dict]]:
    buckets: dict[tuple[date, str], list[dict]] = {}
    for activity in activities:
        day = _activity_date(activity)
        if day is None:
            continue
        discipline = _classify_activity_discipline(activity)
        key = (day, discipline)
        bucket = buckets.setdefault(key, [])
        activity_id = str(activity.id) if activity.id is not None else (
            f"{day.isoformat()}:{discipline}:{len(bucket)}"
        )
        bucket.append(
            {
                "id": activity_id,
                "activity_date": day,
                "duration_seconds": float(activity.duration_seconds or 0.0),
                "distance_meters": (
                    float(activity.distance_meters)
                    if activity.distance_meters is not None
                    else None
                ),
            }
        )

    for bucket in buckets.values():
        bucket.sort(key=lambda item: item["duration_seconds"], reverse=True)
    return buckets


def _find_matching_activity(
    workout: PlannedWorkout,
    activities_by_day_and_discipline: dict[tuple[date, str], list[dict]],
    used_activity_ids: set[str],
    offsets: tuple[int, ...] = (0, -1, 1),
) -> dict | None:
    if workout.date is None:
        return None

    discipline = _normalize_discipline(workout.discipline)
    expected_seconds = _minimum_expected_seconds(workout)
    expected_distance_meters = (
        float(workout.target_distance)
        if workout.target_distance is not None and float(workout.target_distance) > 0
        else None
    )

    for offset in offsets:
        candidate_day = workout.date + timedelta(days=offset)
        bucket = activities_by_day_and_discipline.get((candidate_day, discipline), [])
        best_candidate: dict | None = None
        best_surplus: float | None = None
        for candidate in bucket:
            candidate_id = candidate["id"]
            if candidate_id in used_activity_ids:
                continue
            candidate_seconds = float(candidate.get("duration_seconds") or 0.0)
            if candidate_seconds < expected_seconds:
                continue
            surplus = candidate_seconds - expected_seconds
            if best_surplus is None or surplus < best_surplus:
                best_surplus = surplus
                best_candidate = candidate
        if best_candidate is not None:
            return {
                "id": str(best_candidate["id"]),
                "planned_date": workout.date,
                "activity_date": best_candidate.get("activity_date", candidate_day),
                "day_offset": offset,
                "discipline": discipline,
                "expected_seconds": expected_seconds,
                "expected_distance_meters": expected_distance_meters,
                "duration_seconds": float(best_candidate.get("duration_seconds") or 0.0),
                "distance_meters": best_candidate.get("distance_meters"),
            }
    return None


def _reconcile_due_workouts_detailed(
    due_workouts: list[PlannedWorkout],
    activities_by_day_and_discipline: dict[tuple[date, str], list[dict]],
) -> dict[str, int | list[dict]]:
    used_activity_ids: set[str] = set()
    strict_completed = 0
    aligned_substitutions = 0
    same_day_substitutions = 0
    shifted_substitutions = 0
    missed = 0
    skipped = 0
    matches: list[dict] = []

    sorted_workouts = sorted(
        due_workouts,
        key=lambda workout: (
            workout.date or date.min,
            _coerce_created_at(workout.created_at),
            _status_priority(workout.status),
        ),
    )

    pending_workouts: list[PlannedWorkout] = []
    for workout in sorted_workouts:
        status = (workout.status or "").strip().lower()
        workout_id = str(workout.id) if workout.id is not None else None
        workout_day = workout.date.isoformat() if workout.date else None
        discipline = _normalize_discipline(workout.discipline)
        expected_seconds = _minimum_expected_seconds(workout)
        expected_distance_meters = (
            float(workout.target_distance)
            if workout.target_distance is not None and float(workout.target_distance) > 0
            else None
        )

        if status == "completed":
            strict_completed += 1
            fidelity_score, components = _fidelity_for_match(
                match_type="strict",
                day_offset=0,
                expected_seconds=expected_seconds,
                actual_seconds=expected_seconds,
                expected_distance_meters=expected_distance_meters,
                actual_distance_meters=expected_distance_meters,
            )
            matches.append(
                {
                    "planned_workout_id": workout_id,
                    "planned_date": workout_day,
                    "discipline": discipline,
                    "match_type": "strict",
                    "day_offset": 0,
                    "activity_id": None,
                    "activity_date": workout_day,
                    "expected_seconds": expected_seconds,
                    "actual_seconds": None,
                    "expected_distance_meters": expected_distance_meters,
                    "actual_distance_meters": None,
                    "fidelity_score": fidelity_score,
                    "fidelity_components": components,
                }
            )
            continue

        pending_workouts.append(workout)

    unresolved_workouts: list[PlannedWorkout] = []
    for workout in pending_workouts:
        candidate_match = _find_matching_activity(
            workout,
            activities_by_day_and_discipline,
            used_activity_ids,
            offsets=(0,),
        )
        workout_id = str(workout.id) if workout.id is not None else None
        workout_day = workout.date.isoformat() if workout.date else None
        discipline = _normalize_discipline(workout.discipline)
        expected_seconds = _minimum_expected_seconds(workout)
        if candidate_match is not None:
            used_activity_ids.add(candidate_match["id"])
            aligned_substitutions += 1
            same_day_substitutions += 1
            activity_date = candidate_match.get("activity_date")
            fidelity_score, components = _fidelity_for_match(
                match_type="aligned_same_day",
                day_offset=0,
                expected_seconds=float(candidate_match["expected_seconds"]),
                actual_seconds=float(candidate_match["duration_seconds"]),
                expected_distance_meters=candidate_match.get("expected_distance_meters"),
                actual_distance_meters=candidate_match.get("distance_meters"),
            )
            matches.append(
                {
                    "planned_workout_id": workout_id,
                    "planned_date": workout_day,
                    "discipline": discipline,
                    "match_type": "aligned_same_day",
                    "day_offset": 0,
                    "activity_id": candidate_match["id"],
                    "activity_date": (
                        activity_date.isoformat()
                        if isinstance(activity_date, date)
                        else str(activity_date or "")
                    ),
                    "expected_seconds": float(candidate_match["expected_seconds"]),
                    "actual_seconds": float(candidate_match["duration_seconds"]),
                    "expected_distance_meters": candidate_match.get(
                        "expected_distance_meters"
                    ),
                    "actual_distance_meters": candidate_match.get("distance_meters"),
                    "fidelity_score": fidelity_score,
                    "fidelity_components": components,
                }
            )
        else:
            unresolved_workouts.append(workout)

    for workout in unresolved_workouts:
        candidate_match = _find_matching_activity(
            workout,
            activities_by_day_and_discipline,
            used_activity_ids,
            offsets=(-1, 1),
        )
        workout_id = str(workout.id) if workout.id is not None else None
        workout_day = workout.date.isoformat() if workout.date else None
        discipline = _normalize_discipline(workout.discipline)
        expected_seconds = _minimum_expected_seconds(workout)
        expected_distance_meters = (
            float(workout.target_distance)
            if workout.target_distance is not None and float(workout.target_distance) > 0
            else None
        )
        status = (workout.status or "").strip().lower()
        if candidate_match is not None:
            used_activity_ids.add(candidate_match["id"])
            aligned_substitutions += 1
            shifted_substitutions += 1
            activity_date = candidate_match.get("activity_date")
            day_offset = int(candidate_match.get("day_offset") or 0)
            fidelity_score, components = _fidelity_for_match(
                match_type="aligned_shifted_day",
                day_offset=day_offset,
                expected_seconds=float(candidate_match["expected_seconds"]),
                actual_seconds=float(candidate_match["duration_seconds"]),
                expected_distance_meters=candidate_match.get("expected_distance_meters"),
                actual_distance_meters=candidate_match.get("distance_meters"),
            )
            matches.append(
                {
                    "planned_workout_id": workout_id,
                    "planned_date": workout_day,
                    "discipline": discipline,
                    "match_type": "aligned_shifted_day",
                    "day_offset": day_offset,
                    "activity_id": candidate_match["id"],
                    "activity_date": (
                        activity_date.isoformat()
                        if isinstance(activity_date, date)
                        else str(activity_date or "")
                    ),
                    "expected_seconds": float(candidate_match["expected_seconds"]),
                    "actual_seconds": float(candidate_match["duration_seconds"]),
                    "expected_distance_meters": candidate_match.get(
                        "expected_distance_meters"
                    ),
                    "actual_distance_meters": candidate_match.get("distance_meters"),
                    "fidelity_score": fidelity_score,
                    "fidelity_components": components,
                }
            )
            continue

        if status == "skipped":
            skipped += 1
            match_type = "skipped"
        else:
            missed += 1
            match_type = "missed"
        fidelity_score, components = _fidelity_for_match(
            match_type=match_type,
            day_offset=None,
            expected_seconds=expected_seconds,
            actual_seconds=None,
            expected_distance_meters=expected_distance_meters,
            actual_distance_meters=None,
        )
        matches.append(
            {
                "planned_workout_id": workout_id,
                "planned_date": workout_day,
                "discipline": discipline,
                "match_type": match_type,
                "day_offset": None,
                "activity_id": None,
                "activity_date": None,
                "expected_seconds": expected_seconds,
                "actual_seconds": None,
                "expected_distance_meters": expected_distance_meters,
                "actual_distance_meters": None,
                "fidelity_score": fidelity_score,
                "fidelity_components": components,
            }
        )

    return {
        "strict_completed": strict_completed,
        "aligned_substitutions": aligned_substitutions,
        "same_day_substitutions": same_day_substitutions,
        "shifted_substitutions": shifted_substitutions,
        "missed": missed,
        "skipped": skipped,
        "matches": matches,
    }


def _reconcile_due_workouts(
    due_workouts: list[PlannedWorkout],
    activities_by_day_and_discipline: dict[tuple[date, str], list[dict]],
) -> dict[str, int]:
    reconciliation = _reconcile_due_workouts_detailed(
        due_workouts, activities_by_day_and_discipline
    )
    return {
        "strict_completed": int(reconciliation["strict_completed"]),
        "aligned_substitutions": int(reconciliation["aligned_substitutions"]),
        "same_day_substitutions": int(reconciliation["same_day_substitutions"]),
        "shifted_substitutions": int(reconciliation["shifted_substitutions"]),
        "missed": int(reconciliation["missed"]),
        "skipped": int(reconciliation["skipped"]),
    }


async def get_today_workout(session: AsyncSession) -> dict | None:
    """Get today's planned workout, if any."""
    query = (
        select(PlannedWorkout)
        .where(PlannedWorkout.date == date.today())
        .order_by(PlannedWorkout.created_at.desc())
        .limit(1)
    )
    if _assistant_mode():
        if not await assistant_plan_table_available(session):
            return None
        query = query.join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )

    result = await session.execute(query)
    workout = result.scalar_one_or_none()
    if not workout:
        return None
    return {
        "id": str(workout.id),
        "date": workout.date.isoformat(),
        "discipline": workout.discipline,
        "workout_type": workout.workout_type,
        "target_duration": normalize_planned_duration_minutes(workout.target_duration),
        "target_distance": workout.target_distance,
        "description": workout.description,
        "status": workout.status,
    }


async def get_upcoming_workouts(
    session: AsyncSession,
    count: int = 5,
) -> list[dict]:
    """Get next N planned workouts from today onwards."""
    query = (
        select(PlannedWorkout)
        .where(
            and_(
                PlannedWorkout.date >= date.today(),
                PlannedWorkout.status.in_(["upcoming", "modified"]),
            )
        )
        .order_by(PlannedWorkout.date)
        .limit(count)
    )
    if _assistant_mode():
        if not await assistant_plan_table_available(session):
            return []
        query = query.join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )

    result = await session.execute(query)
    workouts = result.scalars().all()
    return [
        {
            "id": str(w.id),
            "date": w.date.isoformat(),
            "discipline": w.discipline,
            "workout_type": w.workout_type,
            "target_duration": normalize_planned_duration_minutes(w.target_duration),
            "description": w.description,
            "status": w.status,
        }
        for w in workouts
    ]


async def get_plan_adherence(
    session: AsyncSession,
    start: date,
    end: date,
) -> dict:
    """Calculate substitution-aware plan adherence for a date range.

    A planned workout is counted as "on plan" when either:
    - it is explicitly marked completed, or
    - a same-discipline activity exists with enough duration (same day preferred,
      then +/-1 day).
    """
    query = select(PlannedWorkout).where(
        and_(
            PlannedWorkout.date >= start,
            PlannedWorkout.date <= end,
        )
    )
    if _assistant_mode():
        if not await assistant_plan_table_available(session):
            return {
                "total_planned": 0,
                "due_planned": 0,
                "pending_future": 0,
                "completed": 0,
                "strict_completed": 0,
                "aligned_substitutions": 0,
                "same_day_substitutions": 0,
                "shifted_substitutions": 0,
                "missed": 0,
                "skipped": 0,
                "completion_pct": 0.0,
                "strict_completion_pct": 0.0,
                "detail_compliance_pct": 0.0,
                "completed_detail_compliance_pct": 0.0,
                "high_fidelity_completed": 0,
                "low_fidelity_completed": 0,
                "duration_match_pct": 0.0,
                "distance_match_pct": None,
                "on_schedule_pct": 0.0,
            }
        query = query.join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )

    workouts_result = await session.execute(query)
    workouts = _dedupe_workouts(list(workouts_result.scalars().all()))
    total_planned = len(workouts)
    if total_planned == 0:
        return {
            "total_planned": 0,
            "due_planned": 0,
            "pending_future": 0,
            "completed": 0,
            "strict_completed": 0,
            "aligned_substitutions": 0,
            "same_day_substitutions": 0,
            "shifted_substitutions": 0,
            "missed": 0,
            "skipped": 0,
            "completion_pct": 0.0,
            "strict_completion_pct": 0.0,
            "detail_compliance_pct": 0.0,
            "completed_detail_compliance_pct": 0.0,
            "high_fidelity_completed": 0,
            "low_fidelity_completed": 0,
            "duration_match_pct": 0.0,
            "distance_match_pct": None,
            "on_schedule_pct": 0.0,
        }

    today = date.today()
    due_cutoff = min(end, today)
    due_workouts = [w for w in workouts if w.date and w.date <= due_cutoff]
    due_planned = len(due_workouts)
    pending_future = max(0, total_planned - due_planned)

    if due_planned == 0:
        return {
            "total_planned": total_planned,
            "due_planned": 0,
            "pending_future": pending_future,
            "completed": 0,
            "strict_completed": 0,
            "aligned_substitutions": 0,
            "same_day_substitutions": 0,
            "shifted_substitutions": 0,
            "missed": 0,
            "skipped": 0,
            "completion_pct": 0.0,
            "strict_completion_pct": 0.0,
            "detail_compliance_pct": 0.0,
            "completed_detail_compliance_pct": 0.0,
            "high_fidelity_completed": 0,
            "low_fidelity_completed": 0,
            "duration_match_pct": 0.0,
            "distance_match_pct": None,
            "on_schedule_pct": 0.0,
        }

    activity_start = datetime(
        start.year, start.month, start.day, tzinfo=timezone.utc
    )
    activity_end = (
        datetime(due_cutoff.year, due_cutoff.month, due_cutoff.day, tzinfo=timezone.utc)
        + timedelta(days=1)
    )

    activity_result = await session.execute(
        select(GarminActivity).where(
            and_(
                GarminActivity.start_time >= activity_start,
                GarminActivity.start_time < activity_end,
            )
        )
    )
    activities = list(activity_result.scalars().all())
    activities_by_day_and_discipline = _index_activities_by_day_and_discipline(
        activities
    )
    reconciliation = _reconcile_due_workouts_detailed(
        due_workouts, activities_by_day_and_discipline
    )
    strict_completed = reconciliation["strict_completed"]
    aligned_substitutions = reconciliation["aligned_substitutions"]
    same_day_substitutions = reconciliation["same_day_substitutions"]
    shifted_substitutions = reconciliation["shifted_substitutions"]
    missed = reconciliation["missed"]
    skipped = reconciliation["skipped"]
    match_rows = list(reconciliation.get("matches", []))
    done_rows = [
        row
        for row in match_rows
        if row.get("match_type")
        in {"strict", "aligned_same_day", "aligned_shifted_day"}
    ]
    fidelity_scores = [
        float(row.get("fidelity_score"))
        for row in done_rows
        if isinstance(row.get("fidelity_score"), (int, float))
    ]
    detail_points = sum(
        float(row.get("fidelity_score") or 0.0)
        for row in match_rows
        if isinstance(row, dict)
    )
    detail_compliance_pct = round(detail_points / due_planned * 100, 1)
    completed_detail_compliance_pct = (
        round(sum(fidelity_scores) / len(fidelity_scores) * 100, 1)
        if fidelity_scores
        else 0.0
    )
    high_fidelity_completed = sum(1 for score in fidelity_scores if score >= 0.85)
    low_fidelity_completed = sum(1 for score in fidelity_scores if score < 0.85)

    duration_component_values = [
        float(components.get("duration"))
        for row in done_rows
        if isinstance(row.get("fidelity_components"), dict)
        for components in [row["fidelity_components"]]
        if isinstance(components.get("duration"), (int, float))
    ]
    distance_component_values = [
        float(components.get("distance"))
        for row in done_rows
        if isinstance(row.get("fidelity_components"), dict)
        for components in [row["fidelity_components"]]
        if isinstance(components.get("distance"), (int, float))
    ]
    timing_component_values = [
        float(components.get("timing"))
        for row in done_rows
        if isinstance(row.get("fidelity_components"), dict)
        for components in [row["fidelity_components"]]
        if isinstance(components.get("timing"), (int, float))
    ]
    duration_match_pct = (
        round(sum(duration_component_values) / len(duration_component_values) * 100, 1)
        if duration_component_values
        else 0.0
    )
    distance_match_pct = (
        round(sum(distance_component_values) / len(distance_component_values) * 100, 1)
        if distance_component_values
        else None
    )
    on_schedule_pct = (
        round(sum(timing_component_values) / len(timing_component_values) * 100, 1)
        if timing_component_values
        else 0.0
    )

    completed = strict_completed + aligned_substitutions
    return {
        "total_planned": total_planned,
        "due_planned": due_planned,
        "pending_future": pending_future,
        "completed": completed,
        "strict_completed": strict_completed,
        "aligned_substitutions": aligned_substitutions,
        "same_day_substitutions": same_day_substitutions,
        "shifted_substitutions": shifted_substitutions,
        "missed": missed,
        "skipped": skipped,
        "completion_pct": round(completed / due_planned * 100, 1),
        "strict_completion_pct": round(strict_completed / due_planned * 100, 1),
        "detail_compliance_pct": detail_compliance_pct,
        "completed_detail_compliance_pct": completed_detail_compliance_pct,
        "high_fidelity_completed": high_fidelity_completed,
        "low_fidelity_completed": low_fidelity_completed,
        "duration_match_pct": duration_match_pct,
        "distance_match_pct": distance_match_pct,
        "on_schedule_pct": on_schedule_pct,
    }


async def get_current_plan(session: AsyncSession) -> dict | None:
    """Get the active training plan."""
    query = select(TrainingPlan).order_by(TrainingPlan.created_at.desc()).limit(1)
    if _assistant_mode():
        query = select(TrainingPlan).where(TrainingPlan.source == "assistant").order_by(
            TrainingPlan.created_at.desc()
        ).limit(1)
    result = await session.execute(query)
    plan = result.scalar_one_or_none()
    if not plan:
        return None
    return {
        "id": str(plan.id),
        "name": plan.name,
        "source": plan.source,
        "start_date": plan.start_date.isoformat() if plan.start_date else None,
        "end_date": plan.end_date.isoformat() if plan.end_date else None,
    }
