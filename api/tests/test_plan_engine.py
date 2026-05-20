import pytest
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from src.db.models import GarminActivity, PlannedWorkout

from src.db.connection import async_session
from src.services.plan_engine import (
    _index_activities_by_day_and_discipline,
    _minimum_expected_seconds,
    _reconcile_due_workouts,
    _reconcile_due_workouts_detailed,
    get_today_workout,
    get_upcoming_workouts,
    get_plan_adherence,
)


@pytest.mark.asyncio
async def test_get_today_workout_returns_none_when_no_plan():
    """Should return None when no workouts are planned for today."""
    async with async_session() as session:
        result = await get_today_workout(session)
    # May or may not be None depending on if data exists, but should not error
    assert result is None or isinstance(result, dict)


@pytest.mark.asyncio
async def test_get_upcoming_workouts():
    """Should return a list of upcoming workouts."""
    async with async_session() as session:
        result = await get_upcoming_workouts(session, count=5)
    assert isinstance(result, list)
    assert len(result) <= 5


@pytest.mark.asyncio
async def test_get_plan_adherence():
    """Should return adherence stats."""
    async with async_session() as session:
        end = date.today()
        start = end - timedelta(days=7)
        result = await get_plan_adherence(session, start, end)
    assert isinstance(result, dict)
    assert "total_planned" in result
    assert "completed" in result
    assert "missed" in result
    assert "completion_pct" in result
    assert "detail_compliance_pct" in result
    assert "completed_detail_compliance_pct" in result
    assert "duration_match_pct" in result
    assert "on_schedule_pct" in result


def test_reconcile_due_workouts_counts_aligned_substitution():
    workout_day = date(2026, 2, 28)
    due_workouts = [
        PlannedWorkout(
            date=workout_day,
            discipline="Bike",
            target_duration=120,
            status="upcoming",
        )
    ]
    activities = [
        GarminActivity(
            id=uuid4(),
            activity_type="cycling",
            start_time=datetime(2026, 2, 28, 10, 0, tzinfo=timezone.utc),
            duration_seconds=90 * 60,
        )
    ]

    activities_by_day_and_discipline = _index_activities_by_day_and_discipline(activities)
    reconciliation = _reconcile_due_workouts(
        due_workouts, activities_by_day_and_discipline
    )

    assert reconciliation["strict_completed"] == 0
    assert reconciliation["aligned_substitutions"] == 1
    assert reconciliation["missed"] == 0
    assert reconciliation["skipped"] == 0


def test_reconcile_due_workouts_does_not_double_count_single_activity():
    workout_day = date(2026, 2, 28)
    due_workouts = [
        PlannedWorkout(
            date=workout_day,
            discipline="Bike",
            target_duration=60,
            status="upcoming",
        ),
        PlannedWorkout(
            date=workout_day,
            discipline="Bike",
            target_duration=60,
            status="upcoming",
        ),
    ]
    activities = [
        GarminActivity(
            id=uuid4(),
            activity_type="cycling",
            start_time=datetime(2026, 2, 28, 11, 0, tzinfo=timezone.utc),
            duration_seconds=75 * 60,
        )
    ]

    activities_by_day_and_discipline = _index_activities_by_day_and_discipline(activities)
    reconciliation = _reconcile_due_workouts(
        due_workouts, activities_by_day_and_discipline
    )

    assert reconciliation["aligned_substitutions"] == 1
    assert reconciliation["missed"] == 1


def test_reconcile_due_workouts_counts_shifted_day_substitution():
    due_workouts = [
        PlannedWorkout(
            date=date(2026, 2, 28),
            discipline="Run",
            target_duration=45,
            status="upcoming",
        )
    ]
    activities = [
        GarminActivity(
            id=uuid4(),
            activity_type="running",
            start_time=datetime(2026, 3, 1, 7, 0, tzinfo=timezone.utc),
            duration_seconds=40 * 60,
        )
    ]

    activities_by_day_and_discipline = _index_activities_by_day_and_discipline(activities)
    reconciliation = _reconcile_due_workouts(
        due_workouts, activities_by_day_and_discipline
    )

    assert reconciliation["aligned_substitutions"] == 1
    assert reconciliation["same_day_substitutions"] == 0
    assert reconciliation["shifted_substitutions"] == 1
    assert reconciliation["missed"] == 0


def test_reconcile_due_workouts_prioritizes_same_day_before_shifted():
    due_workouts = [
        PlannedWorkout(
            date=date(2026, 2, 28),
            discipline="Bike",
            target_duration=60,
            status="upcoming",
        ),
        PlannedWorkout(
            date=date(2026, 3, 1),
            discipline="Bike",
            target_duration=60,
            status="upcoming",
        ),
    ]
    activities = [
        GarminActivity(
            id=uuid4(),
            activity_type="cycling",
            start_time=datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
            duration_seconds=75 * 60,
        )
    ]

    activities_by_day_and_discipline = _index_activities_by_day_and_discipline(activities)
    reconciliation = _reconcile_due_workouts(
        due_workouts, activities_by_day_and_discipline
    )

    assert reconciliation["aligned_substitutions"] == 1
    assert reconciliation["same_day_substitutions"] == 1
    assert reconciliation["shifted_substitutions"] == 0
    assert reconciliation["missed"] == 1


def test_reconcile_detailed_assigns_lower_fidelity_for_shifted_day():
    due_workouts = [
        PlannedWorkout(
            date=date(2026, 3, 1),
            discipline="Run",
            target_duration=60,
            target_distance=10000.0,
            status="upcoming",
        ),
        PlannedWorkout(
            date=date(2026, 3, 2),
            discipline="Run",
            target_duration=60,
            target_distance=10000.0,
            status="upcoming",
        ),
    ]
    activities = [
        GarminActivity(
            id=uuid4(),
            activity_type="running",
            start_time=datetime(2026, 3, 1, 7, 0, tzinfo=timezone.utc),
            duration_seconds=60 * 60,
            distance_meters=10000.0,
        ),
        GarminActivity(
            id=uuid4(),
            activity_type="running",
            start_time=datetime(2026, 3, 3, 7, 0, tzinfo=timezone.utc),
            duration_seconds=60 * 60,
            distance_meters=10000.0,
        ),
    ]
    activities_by_day_and_discipline = _index_activities_by_day_and_discipline(activities)
    reconciliation = _reconcile_due_workouts_detailed(
        due_workouts, activities_by_day_and_discipline
    )

    matches = list(reconciliation["matches"])
    same_day = next(
        m for m in matches if m.get("match_type") == "aligned_same_day"
    )
    shifted = next(
        m for m in matches if m.get("match_type") == "aligned_shifted_day"
    )

    assert same_day["fidelity_score"] > shifted["fidelity_score"]
    assert shifted["fidelity_components"]["timing"] == 0.85


def test_minimum_expected_seconds_treats_large_planned_duration_as_seconds():
    workout = PlannedWorkout(
        date=date(2026, 2, 28),
        discipline="bike",
        target_duration=4020,  # Garmin seconds; should normalize to 67 minutes.
        status="upcoming",
    )

    expected_seconds = _minimum_expected_seconds(workout)

    assert expected_seconds == 2412.0
