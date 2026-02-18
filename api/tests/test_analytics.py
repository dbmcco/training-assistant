import pytest
from datetime import date, timedelta

from src.db.connection import async_session
from src.services.analytics import (
    weekly_volume_by_discipline,
    training_load_trend,
    activity_stats,
)


@pytest.mark.asyncio
async def test_weekly_volume_by_discipline():
    """Should return volume grouped by discipline for recent data."""
    async with async_session() as session:
        end = date.today()
        start = end - timedelta(days=7)
        result = await weekly_volume_by_discipline(session, start, end)
    assert isinstance(result, dict)
    # Result should be keyed by discipline with hours and distance
    for discipline, data in result.items():
        assert "hours" in data
        assert "distance_km" in data
        assert isinstance(data["hours"], (int, float))
        assert isinstance(data["distance_km"], (int, float))


@pytest.mark.asyncio
async def test_training_load_trend():
    """Should return weekly load data."""
    async with async_session() as session:
        result = await training_load_trend(session, weeks=4)
    assert isinstance(result, list)
    # 4 calendar weeks can span up to 5 ISO weeks (partial weeks at boundaries)
    assert len(result) <= 5
    for entry in result:
        assert "week_start" in entry
        assert "load_7d" in entry


@pytest.mark.asyncio
async def test_activity_stats():
    """Should return aggregate stats from real garmin_activities data."""
    async with async_session() as session:
        end = date.today()
        start = end - timedelta(days=30)
        result = await activity_stats(session, start, end)
    assert isinstance(result, dict)
    assert "total_activities" in result
    assert "total_hours" in result
    assert "total_distance_km" in result
    assert result["total_activities"] >= 0
