import pytest
import json
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

from src.agent.tools import (
    TOOL_DEFINITIONS,
    _matches_discipline_filter,
    _normalize_discipline_filter,
    execute_tool,
)
from src.db.models import (
    GarminActivity,
    RecommendationChange,
)


EXPECTED_TOOL_NAMES = [
    "query_activities",
    "get_daily_metrics",
    "get_readiness_score",
    "get_plan_adherence",
    "compare_planned_vs_actual",
    "get_plan_mode",
    "build_assistant_plan",
    "get_upcoming_workouts",
    "get_plan_changes",
    "get_race_countdown",
    "get_training_load",
    "modify_workout",
    "apply_workout_change",
    "create_plan_change_intent",
    "get_pending_plan_change_intents",
    "apply_plan_change_intent",
    "update_athlete_profile",
    "get_discipline_distribution",
    "get_fitness_trends",
    "get_biometrics",
    "get_active_alerts",
    "refresh_garmin_data",
]


def test_all_tools_have_required_fields():
    for tool in TOOL_DEFINITIONS:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool


def test_tool_count():
    assert len(TOOL_DEFINITIONS) == len(EXPECTED_TOOL_NAMES)


def test_tool_names():
    names = [t["name"] for t in TOOL_DEFINITIONS]
    assert set(names) == set(EXPECTED_TOOL_NAMES)


def test_input_schemas_are_valid():
    for tool in TOOL_DEFINITIONS:
        schema = tool["input_schema"]
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema


def test_normalize_discipline_filter_aliases():
    assert _normalize_discipline_filter("running") == "run"
    assert _normalize_discipline_filter("cycling") == "bike"
    assert _normalize_discipline_filter("swimming") == "swim"
    assert _normalize_discipline_filter("all") == "all"


def test_matches_discipline_filter_uses_activity_type_when_sport_type_missing():
    run_activity = GarminActivity(activity_type="running", sport_type=None)
    swim_activity = GarminActivity(activity_type="pool_swim", sport_type=None)

    assert _matches_discipline_filter("running", run_activity) is True
    assert _matches_discipline_filter("swim", swim_activity) is True
    assert _matches_discipline_filter("cycling", run_activity) is False


@pytest.mark.asyncio
async def test_execute_query_activities():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool("query_activities", {"days_back": 7}, session)
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_execute_query_activities_with_discipline():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool(
            "query_activities", {"discipline": "running", "days_back": 14}, session
        )
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_execute_get_daily_metrics():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool("get_daily_metrics", {"days_back": 7}, session)
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_execute_get_readiness():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool("get_readiness_score", {}, session)
    assert isinstance(result, str)
    assert (
        "score" in result.lower()
        or "readiness" in result.lower()
        or "no" in result.lower()
    )


@pytest.mark.asyncio
async def test_execute_get_plan_adherence():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool(
            "get_plan_adherence", {"period": "this_week"}, session
        )
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_execute_compare_planned_vs_actual():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool(
            "compare_planned_vs_actual", {"days_back": 7}, session
        )
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_execute_get_plan_mode():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool("get_plan_mode", {}, session)
    assert isinstance(result, str)
    assert "plan ownership mode" in result.lower()


@pytest.mark.asyncio
async def test_execute_get_upcoming_workouts():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool("get_upcoming_workouts", {"count": 3}, session)
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_execute_build_assistant_plan(monkeypatch):
    from src.db.connection import async_session

    monkeypatch.setattr("src.agent.tools.is_assistant_owned_mode", lambda: True)

    async def fake_generate_assistant_plan(
        db,
        *,
        days_ahead: int = 14,
        overwrite: bool = True,
        sync_to_garmin: bool = True,
    ):
        _ = (db, days_ahead, overwrite, sync_to_garmin)
        return {
            "phase": "build",
            "window_start": "2026-03-04",
            "window_end": "2026-03-17",
            "created_workouts": 12,
            "synced_success": 7,
            "synced_failed": 0,
            "synced_skipped": 5,
        }

    monkeypatch.setattr(
        "src.agent.tools.generate_assistant_plan", fake_generate_assistant_plan
    )

    async with async_session() as session:
        result = await execute_tool(
            "build_assistant_plan",
            {"days_ahead": 14, "overwrite": True, "sync_to_garmin": True},
            session,
        )
    assert "assistant plan generated" in result.lower()


@pytest.mark.asyncio
async def test_execute_get_plan_changes():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool(
            "get_plan_changes", {"days_back": 7, "limit": 5}, session
        )
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_execute_get_race_countdown():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool("get_race_countdown", {}, session)
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_execute_get_training_load():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool("get_training_load", {"weeks": 4}, session)
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_execute_modify_workout():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool(
            "modify_workout",
            {
                "workout_id": "00000000-0000-0000-0000-000000000000",
                "reason": "Feeling fatigued",
            },
            session,
        )
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_execute_create_plan_change_intent(monkeypatch):
    from datetime import date
    from src.db.connection import async_session

    class FakeIntent:
        id = uuid4()
        status = "pending"
        workout_date = date(2026, 3, 6)

    async def fake_create_intent(*args, **kwargs):
        _ = (args, kwargs)
        return FakeIntent()

    monkeypatch.setattr(
        "src.agent.tools.create_coach_recommendation_intent",
        fake_create_intent,
    )

    async with async_session() as session:
        result = await execute_tool(
            "create_plan_change_intent",
            {
                "recommendation_text": "Swap today to swim",
                "workout_date": "2026-03-06",
                "discipline": "swim",
                "workout_type": "endurance_builder",
                "target_duration": 50,
            },
            session,
    )
    assert "intent created" in result.lower()
    assert "awaiting athlete approval" in result.lower()
    assert "auto-applied" not in result.lower()


@pytest.mark.asyncio
async def test_execute_get_pending_plan_change_intents(monkeypatch):
    rec = RecommendationChange(
        id=uuid4(),
        status="pending",
        workout_date=date(2026, 5, 5),
        recommendation_text="Reduce Tuesday swim to recovery effort.",
        proposed_workout={
            "discipline": "swim",
            "workout_type": "recovery_swim",
            "target_duration": 30,
        },
    )

    class FakeScalars:
        def all(self):
            return [rec]

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=FakeResult())

    monkeypatch.setattr(
        "src.agent.tools.recommendation_table_available",
        AsyncMock(return_value=True),
    )

    result = await execute_tool(
        "get_pending_plan_change_intents",
        {"limit": 5},
        fake_db,
    )

    assert str(rec.id) in result
    assert "2026-05-05" in result
    assert "recovery_swim" in result
    assert "Reduce Tuesday swim" in result


@pytest.mark.asyncio
async def test_execute_apply_plan_change_intent(monkeypatch):
    rec = RecommendationChange(
        id=uuid4(),
        status="pending",
        workout_date=date(2026, 5, 5),
        garmin_sync_status="pending",
    )

    class FakeResult:
        def scalar_one_or_none(self):
            return rec

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=FakeResult())
    fake_db.commit = AsyncMock()
    fake_db.refresh = AsyncMock()
    fake_db.rollback = AsyncMock()

    async def fake_decide(db, *, recommendation, decision, note, requested_changes=None):
        recommendation.status = decision
        recommendation.garmin_sync_status = "success"
        recommendation.garmin_sync_result = {"status": "success"}
        return recommendation

    monkeypatch.setattr("src.agent.tools.decide_recommendation", fake_decide)

    result = await execute_tool(
        "apply_plan_change_intent",
        {"intent_id": str(rec.id), "decision": "approved"},
        fake_db,
    )
    parsed = json.loads(result)
    assert parsed["status"] == "approved"
    assert parsed["garmin_sync_status"] == "success"
    fake_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_update_athlete_profile():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool(
            "update_athlete_profile",
            {"key": "test_preference", "note": "Prefers morning workouts"},
            session,
        )
    assert isinstance(result, str)
    assert "saved" in result.lower() or "updated" in result.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        ("get_discipline_distribution", {"days_back": 28}),
        ("get_fitness_trends", {"days_back": 30}),
        ("get_biometrics", {}),
        ("get_active_alerts", {"limit": 5}),
    ],
)
async def test_execute_extended_tools(tool_name: str, args: dict):
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool(tool_name, args, session)
    assert isinstance(result, str)
    assert result.strip() != ""


@pytest.mark.asyncio
async def test_execute_unknown_tool():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool("nonexistent_tool", {}, session)
    assert isinstance(result, str)
    assert "unknown" in result.lower() or "error" in result.lower()


@pytest.mark.asyncio
async def test_execute_refresh_garmin_data(monkeypatch):
    from src.db.connection import async_session

    async def fake_refresh_with_tracking(
        db,
        *,
        include_calendar: bool = False,
        force: bool = False,
        source: str = "coach_refresh",
        horizon_days: int = 21,
    ):
        _ = (db, source, horizon_days)
        return (
            {
                "status": "success",
                "include_calendar": include_calendar,
                "days_back": 1,
                "results": [
                    {
                        "status": "success",
                        "command": [
                            "python3",
                            "sync.py",
                            "--daily-only",
                            "--days-back",
                            "1",
                        ],
                        "stdout": "Saved daily summary for 2026-03-02.",
                    }
                ],
            },
            [
                {
                    "summary": "Moved run workout from 2026-03-04 to 2026-03-05.",
                }
            ],
        )

    monkeypatch.setattr(
        "src.agent.tools.refresh_with_plan_change_tracking",
        fake_refresh_with_tracking,
    )

    async with async_session() as session:
        result = await execute_tool(
            "refresh_garmin_data",
            {"include_calendar": True, "force": True},
            session,
        )
    assert "success" in result.lower()
    assert "include_calendar: True" in result
    assert "plan_changes_detected: 1" in result


@pytest.mark.asyncio
async def test_apply_workout_change_invalid_date():
    result = await execute_tool(
        "apply_workout_change",
        {"workout_date": "not-a-date"},
        AsyncMock(),
    )
    assert "failed" in result.lower() or "invalid" in result.lower()


@pytest.mark.asyncio
async def test_apply_workout_change_missing_date():
    result = await execute_tool(
        "apply_workout_change",
        {},
        AsyncMock(),
    )
    assert "error" in result.lower() or "unknown" in result.lower()


@pytest.mark.asyncio
async def test_apply_workout_change_uses_recommendation_approval_pipeline(monkeypatch):
    rec = RecommendationChange(
        id=uuid4(),
        status="pending",
        workout_date=date(2026, 5, 5),
        recommendation_text="Directly approved change: Recovery swim.",
        proposed_workout={
            "workout_date": "2026-05-05",
            "discipline": "swim",
            "workout_type": "recovery_swim",
            "target_duration": 40,
        },
        garmin_sync_status="pending",
    )
    calls = []

    async def fake_create_intent(db, *, recommendation_text, proposed_workout, source):
        calls.append(("create", recommendation_text, proposed_workout, source))
        return rec

    async def fake_decide(db, *, recommendation, decision, note, requested_changes=None):
        calls.append(("decide", recommendation.id, decision, note, requested_changes))
        recommendation.status = "approved"
        recommendation.garmin_sync_status = "success"
        recommendation.garmin_sync_result = {"status": "success", "workout_id": "gw-123"}
        recommendation.planned_workout_id = uuid4()
        return recommendation

    fake_db = AsyncMock()
    fake_db.commit = AsyncMock()
    fake_db.refresh = AsyncMock()
    fake_db.rollback = AsyncMock()

    monkeypatch.setattr(
        "src.agent.tools.create_coach_recommendation_intent",
        fake_create_intent,
    )
    monkeypatch.setattr("src.agent.tools.decide_recommendation", fake_decide)

    result = await execute_tool(
        "apply_workout_change",
        {
            "workout_date": "2026-05-05",
            "discipline": "swim",
            "workout_type": "recovery_swim",
            "target_duration": 40,
            "description": "Easy post-race swim.",
            "reason": "Athlete explicitly approved this change.",
        },
        fake_db,
    )

    parsed = json.loads(result)
    assert parsed["status"] == "success"
    assert parsed["intent_id"] == str(rec.id)
    assert parsed["workout_date"] == "2026-05-05"
    assert parsed["garmin_sync"]["status"] == "success"
    assert parsed["pipeline"] == "recommendation_approval"
    assert calls[0][0] == "create"
    assert calls[0][3] == "coach_direct"
    assert calls[1] == (
        "decide",
        rec.id,
        "approved",
        "Athlete explicitly approved this change.",
        None,
    )
    fake_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_workout_change_maps_skipped_sync_to_saved_local(monkeypatch):
    rec = RecommendationChange(
        id=uuid4(),
        status="pending",
        workout_date=date(2026, 5, 4),
        proposed_workout={
            "workout_date": "2026-05-04",
            "discipline": "rest",
            "workout_type": "rest",
            "target_duration": 0,
        },
        garmin_sync_status="pending",
    )

    async def fake_create_intent(*args, **kwargs):
        _ = (args, kwargs)
        return rec

    async def fake_decide(db, *, recommendation, decision, note, requested_changes=None):
        _ = (db, decision, note, requested_changes)
        recommendation.status = "approved"
        recommendation.garmin_sync_status = "skipped"
        recommendation.garmin_sync_result = {
            "status": "skipped",
            "reason": "garmin_writeback_disabled",
        }
        return recommendation

    fake_db = AsyncMock()
    fake_db.commit = AsyncMock()
    fake_db.refresh = AsyncMock()
    fake_db.rollback = AsyncMock()

    monkeypatch.setattr(
        "src.agent.tools.create_coach_recommendation_intent",
        fake_create_intent,
    )
    monkeypatch.setattr("src.agent.tools.decide_recommendation", fake_decide)

    result = await execute_tool(
        "apply_workout_change",
        {
            "workout_date": "2026-05-04",
            "discipline": "rest",
            "workout_type": "rest",
            "target_duration": 0,
        },
        fake_db,
    )

    parsed = json.loads(result)
    assert parsed["status"] == "saved_local"
    assert parsed["garmin_sync"]["status"] == "skipped"
    assert parsed["pipeline"] == "recommendation_approval"
