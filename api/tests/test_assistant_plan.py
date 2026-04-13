import pytest
from datetime import date, timedelta, datetime, timezone
from uuid import uuid4

from src.db.models import TrainingPlan, PlannedWorkout, AssistantPlanEntry
from src.db.connection import async_session
from src.services.assistant_plan import (
    _any_touched_dates_to_preserve,
    _delete_existing_assistant_window,
    acquire_workout_lock,
    release_workout_lock,
)

_TEST_DATE = date(2099, 6, 15)


async def _create_test_plan(session, start_offset=-30, end_offset=30):
    plan = TrainingPlan(
        id=uuid4(),
        race_id=None,
        name="Test Plan",
        source="test",
        start_date=_TEST_DATE + timedelta(days=start_offset),
        end_date=_TEST_DATE + timedelta(days=end_offset),
        created_at=datetime.now(timezone.utc),
    )
    session.add(plan)
    await session.flush()
    return plan


@pytest.mark.asyncio
async def test_preserve_non_upcoming_status():
    async with async_session() as session:
        plan = await _create_test_plan(session)
        workout = PlannedWorkout(
            id=uuid4(),
            plan_id=plan.id,
            date=_TEST_DATE,
            discipline="run",
            workout_type="endurance",
            status="completed",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        session.add(workout)
        await session.flush()

        entry = AssistantPlanEntry(
            id=uuid4(),
            planned_workout_id=workout.id,
            is_locked=False,
            garmin_sync_status=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(entry)
        await session.flush()

        preserved = await _any_touched_dates_to_preserve(
            session, start=_TEST_DATE, end=_TEST_DATE
        )
        assert _TEST_DATE in preserved


@pytest.mark.asyncio
async def test_preserve_garmin_sync_status_not_null():
    async with async_session() as session:
        plan = await _create_test_plan(session)
        workout = PlannedWorkout(
            id=uuid4(),
            plan_id=plan.id,
            date=_TEST_DATE,
            discipline="run",
            workout_type="endurance",
            status="upcoming",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        session.add(workout)
        await session.flush()

        entry = AssistantPlanEntry(
            id=uuid4(),
            planned_workout_id=workout.id,
            is_locked=False,
            garmin_sync_status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(entry)
        await session.flush()

        preserved = await _any_touched_dates_to_preserve(
            session, start=_TEST_DATE, end=_TEST_DATE
        )
        assert _TEST_DATE in preserved


@pytest.mark.asyncio
async def test_preserve_workout_modified_after_plan_creation():
    plan_created_time = datetime.now(timezone.utc) - timedelta(hours=2)

    async with async_session() as session:
        plan = await _create_test_plan(session)
        workout = PlannedWorkout(
            id=uuid4(),
            plan_id=plan.id,
            date=_TEST_DATE,
            discipline="run",
            workout_type="endurance",
            status="upcoming",
            created_at=plan_created_time,
        )
        session.add(workout)
        await session.flush()

        entry = AssistantPlanEntry(
            id=uuid4(),
            planned_workout_id=workout.id,
            is_locked=False,
            garmin_sync_status=None,
            created_at=plan_created_time,
            updated_at=plan_created_time + timedelta(hours=1),
        )
        session.add(entry)
        await session.flush()

        preserved = await _any_touched_dates_to_preserve(
            session, start=_TEST_DATE, end=_TEST_DATE
        )
        assert _TEST_DATE in preserved


@pytest.mark.asyncio
async def test_do_not_preserve_untouched_upcoming_workout():
    untouched_date = _TEST_DATE + timedelta(days=100)
    plan_created_time = datetime.now(timezone.utc) - timedelta(hours=1)

    async with async_session() as session:
        plan = await _create_test_plan(session)
        workout = PlannedWorkout(
            id=uuid4(),
            plan_id=plan.id,
            date=untouched_date,
            discipline="run",
            workout_type="endurance",
            status="upcoming",
            created_at=plan_created_time,
        )
        session.add(workout)
        await session.flush()

        entry = AssistantPlanEntry(
            id=uuid4(),
            planned_workout_id=workout.id,
            is_locked=False,
            garmin_sync_status=None,
            created_at=plan_created_time,
            updated_at=plan_created_time,
        )
        session.add(entry)
        await session.flush()

        preserved = await _any_touched_dates_to_preserve(
            session, start=untouched_date, end=untouched_date
        )
        assert untouched_date not in preserved


@pytest.mark.asyncio
async def test_delete_respects_locked_workouts():
    locked_date = _TEST_DATE + timedelta(days=200)

    async with async_session() as session:
        plan = await _create_test_plan(session)
        workout = PlannedWorkout(
            id=uuid4(),
            plan_id=plan.id,
            date=locked_date,
            discipline="run",
            workout_type="endurance",
            status="upcoming",
            created_at=datetime.now(timezone.utc),
        )
        session.add(workout)
        await session.flush()

        entry = AssistantPlanEntry(
            id=uuid4(),
            planned_workout_id=workout.id,
            is_locked=True,
            garmin_sync_status=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(entry)
        await session.flush()

        deleted_count = await _delete_existing_assistant_window(
            session, start=locked_date
        )
        assert deleted_count == 0

        await session.refresh(workout)
        assert workout.id is not None


@pytest.mark.asyncio
async def test_acquire_and_release_workout_lock():
    async with async_session() as session:
        plan = await _create_test_plan(session)
        workout = PlannedWorkout(
            id=uuid4(),
            plan_id=plan.id,
            date=_TEST_DATE,
            discipline="run",
            workout_type="endurance",
            status="upcoming",
            created_at=datetime.now(timezone.utc),
        )
        session.add(workout)
        await session.flush()

        entry = AssistantPlanEntry(
            id=uuid4(),
            planned_workout_id=workout.id,
            is_locked=False,
            garmin_sync_status=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(entry)
        await session.flush()

        success = await acquire_workout_lock(session, workout.id)
        assert success is True

        await session.refresh(entry)
        assert entry.is_locked is True

        success = await release_workout_lock(session, workout.id)
        assert success is True

        await session.refresh(entry)
        assert entry.is_locked is False


@pytest.mark.asyncio
async def test_acquire_lock_nonexistent_entry():
    async with async_session() as session:
        success = await acquire_workout_lock(session, uuid4())
        assert success is False


@pytest.mark.asyncio
async def test_release_lock_nonexistent_entry():
    async with async_session() as session:
        success = await release_workout_lock(session, uuid4())
        assert success is False
