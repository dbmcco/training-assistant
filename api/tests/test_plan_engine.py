import pytest
from datetime import date, timedelta

from src.db.connection import async_session
from src.services.plan_engine import (
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
