"""Tests for build_training_context and training context injection into the coach prompt."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.agent.coach import (
    _classify_activity_discipline_lite,
    _format_training_summary,
    _normalize_planned_discipline,
    build_training_context,
)


def _make_activity(
    sport_type: str = "running",
    activity_type: str | None = None,
    duration_seconds: float = 1800.0,
    distance_meters: float = 5000.0,
    start_time: datetime | None = None,
):
    a = MagicMock()
    a.sport_type = sport_type
    a.activity_type = activity_type if activity_type is not None else sport_type
    a.duration_seconds = duration_seconds
    a.distance_meters = distance_meters
    a.start_time = start_time or datetime.now(timezone.utc) - timedelta(hours=12)
    return a


def _make_planned_workout(
    discipline: str = "run",
    workout_date: date | None = None,
    target_duration: int = 60,
    target_distance: float = 10000.0,
):
    w = MagicMock()
    w.discipline = discipline
    w.date = workout_date or date.today()
    w.target_duration = target_duration
    w.target_distance = target_distance
    return w


class TestClassifyActivityDisciplineLite:
    def test_run(self):
        a = _make_activity(sport_type="running")
        assert _classify_activity_discipline_lite(a) == "run"

    def test_trail_run(self):
        a = _make_activity(sport_type="trail_running")
        assert _classify_activity_discipline_lite(a) == "run"

    def test_cycling(self):
        a = _make_activity(sport_type="cycling")
        assert _classify_activity_discipline_lite(a) == "bike"

    def test_swimming(self):
        a = _make_activity(sport_type="swimming")
        assert _classify_activity_discipline_lite(a) == "swim"

    def test_strength(self):
        a = _make_activity(sport_type="strength_training")
        assert _classify_activity_discipline_lite(a) == "strength"

    def test_other(self):
        a = _make_activity(sport_type="yoga")
        assert _classify_activity_discipline_lite(a) == "other"


class TestNormalizePlannedDiscipline:
    def test_running(self):
        assert _normalize_planned_discipline("running") == "run"

    def test_cycling(self):
        assert _normalize_planned_discipline("cycling") == "bike"

    def test_swim(self):
        assert _normalize_planned_discipline("swim") == "swim"

    def test_strength(self):
        assert _normalize_planned_discipline("strength") == "strength"

    def test_none(self):
        assert _normalize_planned_discipline(None) == "other"

    def test_empty(self):
        assert _normalize_planned_discipline("") == "other"


class TestFormatTrainingSummary:
    def test_empty_returns_empty(self):
        result = _format_training_summary([], [], None)
        assert result == ""

    def test_single_run_activity(self):
        activities = [_make_activity("running", "running", 2520, 8046.72)]
        result = _format_training_summary(activities, [], None)
        assert "Run:" in result
        assert "1 session completed" in result
        assert "42min total" in result
        assert "5.0 mi" in result

    def test_bike_shows_hours(self):
        activities = [_make_activity("cycling", "cycling", 5400, 40000)]
        result = _format_training_summary(activities, [], None)
        assert "Bike:" in result
        assert "1 session completed" in result
        assert "1.5 hrs total" in result

    def test_swim_shows_yards(self):
        activities = [_make_activity("swimming", "pool_swim", 2400, 1737.36)]
        result = _format_training_summary(activities, [], None)
        assert "Swim:" in result
        assert "1900 yd" in result

    def test_missed_workouts(self):
        planned = [_make_planned_workout("strength", date.today(), 45)]
        result = _format_training_summary([], planned, None)
        assert "Strength:" in result
        assert "0 sessions completed" in result
        assert "1 planned, 1 missed" in result

    def test_partial_completion(self):
        activities = [_make_activity("running", "running", 1800, 5000)]
        planned = [
            _make_planned_workout("run", date.today()),
            _make_planned_workout("run", date.today() - timedelta(days=1)),
        ]
        result = _format_training_summary(activities, planned, None)
        assert "Run:" in result
        assert "2 planned, 1 missed" in result

    def test_adherence_included(self):
        adherence = {
            "completed": 5,
            "due_planned": 7,
            "completion_pct": 71.4,
            "missed": 2,
        }
        activities = [_make_activity("running", "running", 1800, 5000)]
        result = _format_training_summary(activities, [], adherence)
        assert "Plan adherence: 71%" in result
        assert "5/7 planned workouts completed" in result
        assert "2 missed" in result

    def test_adherence_zero_due_not_shown(self):
        adherence = {
            "completed": 0,
            "due_planned": 0,
            "completion_pct": 0.0,
            "missed": 0,
        }
        result = _format_training_summary([], [], adherence)
        assert result == ""

    def test_out_of_range_planned_ignored(self):
        planned = [_make_planned_workout("run", date.today() - timedelta(days=10))]
        activities = [_make_activity("running", "running", 1800, 5000)]
        result = _format_training_summary(activities, planned, None)
        assert "Run:" in result
        assert "missed" not in result

    def test_multiple_disciplines(self):
        activities = [
            _make_activity("running", "running", 2520, 8046.72),
            _make_activity("cycling", "cycling", 3600, 30000),
            _make_activity("swimming", "pool_swim", 2400, 1737.36),
        ]
        result = _format_training_summary(activities, [], None)
        assert "Run:" in result
        assert "Bike:" in result
        assert "Swim:" in result


class TestBuildTrainingContext:
    @pytest.mark.asyncio
    async def test_returns_string(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "src.services.plan_engine.get_plan_adherence", new_callable=AsyncMock
        ) as mock_adh:
            mock_adh.return_value = {
                "completed": 0,
                "due_planned": 0,
                "completion_pct": 0.0,
                "missed": 0,
            }
            result = await build_training_context(mock_db)

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_with_activities_and_adherence(self):
        mock_db = AsyncMock()
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                a = _make_activity("running", "running", 2520, 8046.72)
                mock_result.scalars.return_value.all.return_value = [a]
            else:
                mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_db.execute = mock_execute

        with patch(
            "src.services.plan_engine.get_plan_adherence", new_callable=AsyncMock
        ) as mock_adh:
            mock_adh.return_value = {
                "completed": 3,
                "due_planned": 4,
                "completion_pct": 75.0,
                "missed": 1,
            }
            result = await build_training_context(mock_db)

        assert "Run:" in result
        assert "1 session completed" in result
        assert "Plan adherence: 75%" in result

    @pytest.mark.asyncio
    async def test_handles_adherence_error_gracefully(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "src.services.plan_engine.get_plan_adherence", new_callable=AsyncMock
        ) as mock_adh:
            mock_adh.side_effect = Exception("db error")
            result = await build_training_context(mock_db)

        assert isinstance(result, str)
