import pytest

from src.agent.tools import (
    TOOL_DEFINITIONS,
    _matches_discipline_filter,
    _normalize_discipline_filter,
    execute_tool,
)
from src.db.models import GarminActivity


EXPECTED_TOOL_NAMES = [
    "query_activities",
    "get_daily_metrics",
    "get_readiness_score",
    "get_plan_adherence",
    "get_upcoming_workouts",
    "get_race_countdown",
    "get_training_load",
    "modify_workout",
    "update_athlete_profile",
    "get_discipline_distribution",
    "get_fitness_trends",
    "get_biometrics",
    "get_active_alerts",
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
    assert "score" in result.lower() or "readiness" in result.lower() or "no" in result.lower()


@pytest.mark.asyncio
async def test_execute_get_plan_adherence():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool("get_plan_adherence", {"period": "this_week"}, session)
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_execute_get_upcoming_workouts():
    from src.db.connection import async_session

    async with async_session() as session:
        result = await execute_tool("get_upcoming_workouts", {"count": 3}, session)
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
            {"workout_id": "00000000-0000-0000-0000-000000000000", "reason": "Feeling fatigued"},
            session,
        )
    assert isinstance(result, str)


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
