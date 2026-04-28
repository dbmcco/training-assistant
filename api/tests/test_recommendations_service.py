from datetime import date
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from src.config import settings
from src.db.models import PlannedWorkout, RecommendationChange
from src.services.recommendations import decide_recommendation


def _last_event(rec: RecommendationChange, event_name: str) -> dict | None:
    events = (rec.training_impact_log or {}).get("events", [])
    for ev in reversed(events):
        if ev.get("event") == event_name:
            return ev
    return None


@pytest.mark.asyncio
async def test_approve_recommendation_refreshes_calendar_after_successful_writeback():
    rec = RecommendationChange(
        id=uuid4(),
        status="pending",
        workout_date=date.today(),
        recommendation_text="Swap to easier endurance run.",
        proposed_workout={
            "discipline": "run",
            "workout_type": "endurance",
            "target_duration": 50,
            "description": "Easy aerobic run",
        },
    )
    target = PlannedWorkout(
        id=uuid4(),
        date=date.today(),
        discipline="run",
        workout_type="tempo",
        target_duration=60,
        description="Original session",
        status="planned",
    )
    db = AsyncMock()
    db.add = Mock()

    with (
        patch.object(settings, "plan_ownership_mode", "assistant"),
        patch(
            "src.services.recommendations._find_target_workout",
            AsyncMock(return_value=target),
        ),
        patch(
            "src.services.recommendations._load_assistant_entry_for_workout",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.services.recommendations.write_recommendation_change",
            AsyncMock(
                return_value={
                    "status": "success",
                    "verification_status": "success",
                    "workout_id": "garmin-123",
                    "verification_details": {"title": "Running endurance"},
                }
            ),
        ),
        patch(
            "src.services.recommendations.refresh_garmin_daily_data_on_demand",
            AsyncMock(return_value={"status": "success", "include_calendar": True}),
        ) as refresh_mock,
    ):
        updated = await decide_recommendation(
            db,
            recommendation=rec,
            decision="approved",
            note="Looks good",
        )

    refresh_mock.assert_awaited_once_with(include_calendar=False, force=True)
    assert updated.status == "approved"
    assert updated.garmin_sync_status == "success"
    assert target.status == "modified"
    assert isinstance(updated.garmin_sync_result, dict)
    assert (
        updated.garmin_sync_result.get("calendar_refresh", {}).get("status")
        == "success"
    )
    assert _last_event(updated, "writeback_verified") is not None
    assert (
        _last_event(updated, "writeback_verified")["verification_status"] == "success"
    )
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_approve_recommendation_skips_calendar_refresh_when_writeback_fails():
    rec = RecommendationChange(
        id=uuid4(),
        status="pending",
        workout_date=date.today(),
        recommendation_text="Move long ride to Sunday.",
        proposed_workout={
            "discipline": "bike",
            "workout_type": "long ride",
            "target_duration": 120,
        },
    )
    db = AsyncMock()
    db.add = Mock()

    with (
        patch(
            "src.services.recommendations._find_target_workout",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.services.recommendations._load_assistant_entry_for_workout",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.services.recommendations.write_recommendation_change",
            AsyncMock(
                return_value={
                    "status": "failed",
                    "verification_status": "failed",
                    "error": "auth",
                }
            ),
        ),
        patch(
            "src.services.recommendations.refresh_garmin_daily_data_on_demand",
            AsyncMock(return_value={"status": "success"}),
        ) as refresh_mock,
    ):
        updated = await decide_recommendation(
            db,
            recommendation=rec,
            decision="approved",
            note="Apply anyway",
        )

    refresh_mock.assert_not_awaited()
    assert updated.garmin_sync_status == "failed"
    assert updated.garmin_sync_result["status"] == "failed"
    assert updated.garmin_sync_result["error"] == "auth"
    assert _last_event(updated, "writeback_unverified") is not None
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_approve_recommendation_passes_replace_workout_and_updates_assistant_entry():
    rec = RecommendationChange(
        id=uuid4(),
        status="pending",
        workout_date=date.today(),
        recommendation_text="Swap bike to swim.",
        proposed_workout={
            "discipline": "swim",
            "workout_type": "endurance_builder",
            "target_duration": 50,
            "description": "Swim focus",
        },
    )
    target = PlannedWorkout(
        id=uuid4(),
        date=date.today(),
        discipline="bike",
        workout_type="easy_spin",
        target_duration=50,
        description="Bike easy",
        status="upcoming",
    )
    assistant_entry = type(
        "Entry",
        (),
        {
            "garmin_workout_id": "bike-old-123",
            "garmin_sync_status": "success",
            "garmin_sync_result": None,
            "updated_at": None,
        },
    )()
    db = AsyncMock()

    with (
        patch.object(settings, "plan_ownership_mode", "assistant"),
        patch(
            "src.services.recommendations._find_target_workout",
            AsyncMock(return_value=target),
        ),
        patch(
            "src.services.recommendations._load_assistant_entry_for_workout",
            AsyncMock(return_value=assistant_entry),
        ),
        patch(
            "src.services.recommendations.write_recommendation_change",
            AsyncMock(
                return_value={
                    "status": "success",
                    "verification_status": "success",
                    "workout_id": "swim-new-456",
                }
            ),
        ),
        patch(
            "src.services.recommendations.refresh_garmin_daily_data_on_demand",
            AsyncMock(return_value={"status": "success"}),
        ),
    ):
        updated = await decide_recommendation(
            db,
            recommendation=rec,
            decision="approved",
            note="approved",
        )

    assert isinstance(updated.garmin_sync_payload, dict)
    assert updated.garmin_sync_payload.get("replace_workout_id") == "bike-old-123"
    assert assistant_entry.garmin_workout_id == "swim-new-456"
    assert assistant_entry.garmin_sync_status == "success"
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_approve_recommendation_hydrates_missing_workout_steps_and_description():
    rec = RecommendationChange(
        id=uuid4(),
        status="pending",
        workout_date=date.today(),
        recommendation_text="Swap to swim with details.",
        proposed_workout={
            "discipline": "swim",
            "workout_type": "endurance_builder",
            "target_duration": 50,
            "description": "Swim focus today",
        },
    )
    target = PlannedWorkout(
        id=uuid4(),
        date=date.today(),
        discipline="bike",
        workout_type="easy_spin",
        target_duration=50,
        description="Original bike session",
        status="upcoming",
    )
    db = AsyncMock()
    db.add = Mock()

    with (
        patch.object(settings, "plan_ownership_mode", "assistant"),
        patch(
            "src.services.recommendations._find_target_workout",
            AsyncMock(return_value=target),
        ),
        patch(
            "src.services.recommendations._load_assistant_entry_for_workout",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.services.recommendations.write_recommendation_change",
            AsyncMock(
                return_value={
                    "status": "success",
                    "verification_status": "success",
                    "workout_id": "garmin-999",
                }
            ),
        ),
        patch(
            "src.services.recommendations.refresh_garmin_daily_data_on_demand",
            AsyncMock(return_value={"status": "success"}),
        ),
    ):
        updated = await decide_recommendation(
            db,
            recommendation=rec,
            decision="approved",
            note="approved",
        )

    payload = updated.garmin_sync_payload or {}
    assert isinstance(payload.get("workout_steps"), list)
    assert len(payload.get("workout_steps", [])) >= 4
    assert "Session Plan:" in str(target.description)
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_synced_unverified_triggers_calendar_refresh():
    rec = RecommendationChange(
        id=uuid4(),
        status="pending",
        workout_date=date.today(),
        recommendation_text="Swap run to intervals.",
        proposed_workout={
            "discipline": "run",
            "workout_type": "interval",
            "target_duration": 45,
            "description": "Intervals",
        },
    )
    db = AsyncMock()
    db.add = Mock()

    with (
        patch(
            "src.services.recommendations._find_target_workout",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.services.recommendations._load_assistant_entry_for_workout",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.services.recommendations.write_recommendation_change",
            AsyncMock(
                return_value={
                    "status": "success",
                    "verification_status": "synced_unverified",
                    "workout_id": "garmin-789",
                    "verification_error": "no_matching_workout_found",
                }
            ),
        ),
        patch(
            "src.services.recommendations.refresh_garmin_daily_data_on_demand",
            AsyncMock(return_value={"status": "success"}),
        ) as refresh_mock,
    ):
        updated = await decide_recommendation(
            db,
            recommendation=rec,
            decision="approved",
            note="Go ahead",
        )

    refresh_mock.assert_awaited_once()
    assert updated.garmin_sync_status == "synced_unverified"
    assert _last_event(updated, "writeback_unverified") is not None
    assert (
        _last_event(updated, "writeback_unverified")["verification_status"]
        == "synced_unverified"
    )
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_synced_unverified_does_not_update_garmin_workout_id():
    rec = RecommendationChange(
        id=uuid4(),
        status="pending",
        workout_date=date.today(),
        recommendation_text="Swap bike to swim.",
        proposed_workout={
            "discipline": "swim",
            "workout_type": "drills",
            "target_duration": 40,
            "description": "Drill session",
        },
    )
    target = PlannedWorkout(
        id=uuid4(),
        date=date.today(),
        discipline="bike",
        workout_type="easy_spin",
        target_duration=50,
        description="Bike easy",
        status="upcoming",
    )
    assistant_entry = type(
        "Entry",
        (),
        {
            "garmin_workout_id": "bike-old-111",
            "garmin_sync_status": "success",
            "garmin_sync_result": None,
            "updated_at": None,
        },
    )()
    db = AsyncMock()

    with (
        patch.object(settings, "plan_ownership_mode", "assistant"),
        patch(
            "src.services.recommendations._find_target_workout",
            AsyncMock(return_value=target),
        ),
        patch(
            "src.services.recommendations._load_assistant_entry_for_workout",
            AsyncMock(return_value=assistant_entry),
        ),
        patch(
            "src.services.recommendations.write_recommendation_change",
            AsyncMock(
                return_value={
                    "status": "success",
                    "verification_status": "synced_unverified",
                    "workout_id": "swim-new-222",
                    "verification_error": "verification_timeout",
                }
            ),
        ),
        patch(
            "src.services.recommendations.refresh_garmin_daily_data_on_demand",
            AsyncMock(return_value={"status": "success"}),
        ),
    ):
        updated = await decide_recommendation(
            db,
            recommendation=rec,
            decision="approved",
            note="approved",
        )

    assert updated.garmin_sync_status == "synced_unverified"
    assert assistant_entry.garmin_workout_id == "bike-old-111"
    assert assistant_entry.garmin_sync_status == "synced_unverified"
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_failed_writeback_does_not_update_garmin_workout_id():
    rec = RecommendationChange(
        id=uuid4(),
        status="pending",
        workout_date=date.today(),
        recommendation_text="Try a new workout.",
        proposed_workout={
            "discipline": "run",
            "workout_type": "tempo",
            "target_duration": 40,
        },
    )
    target = PlannedWorkout(
        id=uuid4(),
        date=date.today(),
        discipline="run",
        workout_type="easy",
        target_duration=45,
        description="Easy run",
        status="upcoming",
    )
    assistant_entry = type(
        "Entry",
        (),
        {
            "garmin_workout_id": "run-old-333",
            "garmin_sync_status": "success",
            "garmin_sync_result": None,
            "updated_at": None,
        },
    )()
    db = AsyncMock()

    with (
        patch.object(settings, "plan_ownership_mode", "assistant"),
        patch(
            "src.services.recommendations._find_target_workout",
            AsyncMock(return_value=target),
        ),
        patch(
            "src.services.recommendations._load_assistant_entry_for_workout",
            AsyncMock(return_value=assistant_entry),
        ),
        patch(
            "src.services.recommendations.write_recommendation_change",
            AsyncMock(
                return_value={
                    "status": "failed",
                    "verification_status": "failed",
                    "error": "garmin_repo_not_found",
                }
            ),
        ),
        patch(
            "src.services.recommendations.refresh_garmin_daily_data_on_demand",
            AsyncMock(return_value={"status": "success"}),
        ) as refresh_mock,
    ):
        updated = await decide_recommendation(
            db,
            recommendation=rec,
            decision="approved",
            note="try it",
        )

    refresh_mock.assert_not_awaited()
    assert updated.garmin_sync_status == "failed"
    assert assistant_entry.garmin_workout_id == "run-old-333"
    assert assistant_entry.garmin_sync_status == "failed"
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_approve_recommendation_without_existing_target_creates_local_workout():
    rec = RecommendationChange(
        id=uuid4(),
        status="pending",
        workout_date=date(2026, 5, 6),
        recommendation_text="Add recovery swim after race weekend.",
        proposed_workout={
            "workout_date": "2026-05-06",
            "discipline": "swim",
            "workout_type": "recovery_swim",
            "target_duration": 35,
            "description": "Easy recovery swim",
        },
    )
    added = []
    db = AsyncMock()
    db.add = Mock(side_effect=added.append)

    with (
        patch.object(settings, "plan_ownership_mode", "assistant"),
        patch(
            "src.services.recommendations._find_target_workout",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.services.recommendations._load_assistant_entry_for_workout",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.services.recommendations.write_recommendation_change",
            AsyncMock(
                return_value={
                    "status": "success",
                    "verification_status": "success",
                    "workout_id": "swim-created-123",
                }
            ),
        ),
        patch(
            "src.services.recommendations.refresh_garmin_daily_data_on_demand",
            AsyncMock(return_value={"status": "success"}),
        ),
    ):
        updated = await decide_recommendation(
            db,
            recommendation=rec,
            decision="approved",
            note="approved",
        )

    created_workouts = [item for item in added if isinstance(item, PlannedWorkout)]
    assert len(created_workouts) == 1
    created = created_workouts[0]
    assert created.date == date(2026, 5, 6)
    assert created.discipline == "swim"
    assert created.workout_type == "recovery_swim"
    assert created.target_duration == 35
    assert created.status == "modified"
    assert updated.planned_workout_id == created.id
    assert updated.garmin_sync_status == "success"
    assert any(getattr(item, "planned_workout_id", None) == created.id for item in added)
    db.flush.assert_awaited()
