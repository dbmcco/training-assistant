from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.config import settings
from src.db.models import PlannedWorkout, RecommendationChange
from src.services.recommendations import decide_recommendation


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

    with (
        patch.object(settings, "plan_ownership_mode", "assistant"),
        patch(
            "src.services.recommendations._find_target_workout",
            AsyncMock(return_value=target),
        ),
        patch(
            "src.services.recommendations.write_recommendation_change",
            AsyncMock(return_value={"status": "success", "workout_id": "garmin-123"}),
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
    assert isinstance(updated.garmin_sync_result, dict)
    assert updated.garmin_sync_result.get("calendar_refresh", {}).get("status") == "success"
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

    with (
        patch(
            "src.services.recommendations._find_target_workout",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.services.recommendations.write_recommendation_change",
            AsyncMock(return_value={"status": "failed", "error": "auth"}),
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
    assert updated.garmin_sync_result == {"status": "failed", "error": "auth"}
    db.flush.assert_awaited()
