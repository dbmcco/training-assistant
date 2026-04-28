import pytest
import json
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from src.agent.tools import (
    TOOL_DEFINITIONS,
    _matches_discipline_filter,
    _normalize_discipline_filter,
    execute_tool,
)
from src.db.models import AssistantPlanEntry, GarminActivity, PlannedWorkout


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
    assert "auto-applied" in result.lower() or "pending" in result.lower()


@pytest.mark.asyncio
async def test_execute_apply_plan_change_intent():
    result = await execute_tool(
        "apply_plan_change_intent",
        {"intent_id": str(uuid4()), "decision": "approved"},
        AsyncMock(),
    )
    assert isinstance(result, str)
    assert "no-op" in result.lower() or "alias" in result.lower()


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


def _make_apply_workout_change_patches(
    monkeypatch, *, writeback_enabled=True, workout=None, lock_succeeds=True
):
    import json as _json
    from datetime import date as _date
    from uuid import uuid4 as _uuid4

    monkeypatch.setattr("src.agent.tools.is_assistant_owned_mode", lambda: False)

    async def fake_acquire_lock(db, workout_id):
        return lock_succeeds

    async def fake_release_lock(db, workout_id):
        return True

    monkeypatch.setattr("src.agent.tools.acquire_workout_lock", fake_acquire_lock)
    monkeypatch.setattr("src.agent.tools.release_workout_lock", fake_release_lock)

    class FakeQueryResult:
        def scalar_one_or_none(self):
            return workout

    class FakeExecute:
        def __await__(self):
            return FakeQueryResult().__await__()

    async def fake_execute(stmt):
        return FakeQueryResult()

    async def fake_flush():
        pass

    async def fake_commit():
        pass

    async def fake_refresh(obj):
        pass

    import src.config as _cfg

    monkeypatch.setattr(_cfg.settings, "garmin_writeback_enabled", writeback_enabled)
    monkeypatch.setattr(_cfg.settings, "garmin_writeback_verify_enabled", False)

    async def fake_writeback(payload):
        return {
            "status": "success",
            "verification_status": "success",
            "workout_id": "gw-123",
        }

    monkeypatch.setattr(
        "src.services.garmin_writeback.write_recommendation_change", fake_writeback
    )

    return fake_execute, fake_flush, fake_commit, fake_refresh


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
async def test_apply_workout_change_creates_new_workout(monkeypatch):
    fake_execute, fake_flush, fake_commit, fake_refresh = (
        _make_apply_workout_change_patches(
            monkeypatch,
            workout=None,
        )
    )

    fake_db = AsyncMock()
    fake_db.execute = fake_execute
    fake_db.flush = fake_flush
    fake_db.commit = fake_commit
    fake_db.refresh = fake_refresh
    fake_db.rollback = AsyncMock()
    fake_db.no_autoflush = _no_autoflush_ctx()

    result = await execute_tool(
        "apply_workout_change",
        {
            "workout_date": "2026-04-20",
            "discipline": "run",
            "workout_type": "endurance_run",
            "target_duration": 60,
            "reason": "Test creation",
        },
        fake_db,
    )

    import json

    parsed = json.loads(result)
    assert parsed["status"] in ("success", "saved_local", "synced_unverified")
    assert parsed["workout_date"] == "2026-04-20"
    assert parsed.get("created_new") is True


@pytest.mark.asyncio
async def test_apply_workout_change_assistant_created_workout_is_visible(monkeypatch):
    fake_execute, fake_flush, fake_commit, fake_refresh = (
        _make_apply_workout_change_patches(
            monkeypatch,
            writeback_enabled=False,
            workout=None,
        )
    )
    monkeypatch.setattr("src.agent.tools.is_assistant_owned_mode", lambda: True)

    added = []
    fake_db = AsyncMock()
    fake_db.add = added.append
    fake_db.execute = fake_execute
    fake_db.flush = fake_flush
    fake_db.commit = fake_commit
    fake_db.refresh = fake_refresh
    fake_db.rollback = AsyncMock()

    result = await execute_tool(
        "apply_workout_change",
        {
            "workout_date": "2026-05-04",
            "discipline": "rest",
            "workout_type": "rest",
            "target_duration": 0,
            "description": "Full rest after Mount Archer.",
        },
        fake_db,
    )

    parsed = json.loads(result)
    assert parsed.get("created_new") is True
    assert any(isinstance(obj, PlannedWorkout) for obj in added)
    assert any(isinstance(obj, AssistantPlanEntry) for obj in added)


@pytest.mark.asyncio
async def test_apply_workout_change_can_change_existing_workout_discipline(
    monkeypatch,
):
    existing = PlannedWorkout(
        id=uuid4(),
        date=date(2026, 5, 3),
        discipline="strength",
        workout_type="mobility_strength",
        target_duration=30,
        description="Mobility and activation work",
        status="upcoming",
        created_at=datetime.now(timezone.utc),
    )

    monkeypatch.setattr("src.agent.tools.is_assistant_owned_mode", lambda: True)
    monkeypatch.setattr("src.config.settings.garmin_writeback_enabled", False)

    async def fake_acquire_lock(db, workout_id):
        return True

    async def fake_release_lock(db, workout_id):
        return True

    monkeypatch.setattr("src.agent.tools.acquire_workout_lock", fake_acquire_lock)
    monkeypatch.setattr("src.agent.tools.release_workout_lock", fake_release_lock)

    class FakeQueryResult:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    execute_results = [None, existing]

    async def fake_execute(stmt):
        return FakeQueryResult(execute_results.pop(0))

    added = []
    fake_db = AsyncMock()
    fake_db.add = added.append
    fake_db.execute = fake_execute
    fake_db.flush = AsyncMock()
    fake_db.commit = AsyncMock()
    fake_db.refresh = AsyncMock()
    fake_db.rollback = AsyncMock()

    result = await execute_tool(
        "apply_workout_change",
        {
            "workout_date": "2026-05-03",
            "discipline": "run",
            "workout_type": "race",
            "target_duration": 105,
            "description": "Mount Archer Trail Race.",
        },
        fake_db,
    )

    parsed = json.loads(result)
    assert parsed["status"] == "saved_local"
    assert parsed.get("created_new") is None
    assert existing.discipline == "run"
    assert existing.workout_type == "race"
    assert existing.target_duration == 105
    assert existing.description.startswith("Mount Archer Trail Race.")
    assert added == []


@pytest.mark.asyncio
async def test_apply_workout_change_writeback_disabled(monkeypatch):
    fake_execute, fake_flush, fake_commit, fake_refresh = (
        _make_apply_workout_change_patches(
            monkeypatch,
            writeback_enabled=False,
            workout=None,
        )
    )

    fake_db = AsyncMock()
    fake_db.execute = fake_execute
    fake_db.flush = fake_flush
    fake_db.commit = fake_commit
    fake_db.refresh = fake_refresh
    fake_db.rollback = AsyncMock()
    fake_db.no_autoflush = _no_autoflush_ctx()

    result = await execute_tool(
        "apply_workout_change",
        {
            "workout_date": "2026-04-21",
            "discipline": "bike",
            "target_duration": 45,
        },
        fake_db,
    )

    import json

    parsed = json.loads(result)
    assert parsed["status"] == "saved_local"
    assert parsed["garmin_sync"]["status"] == "skipped"


class _no_autoflush_ctx:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
