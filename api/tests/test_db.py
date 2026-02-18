import pytest
from sqlalchemy import func, select

from src.db.connection import async_session
from src.db.models import GarminActivity, GarminDailySummary


@pytest.mark.asyncio
async def test_can_read_garmin_activities():
    async with async_session() as session:
        result = await session.execute(
            select(func.count()).select_from(GarminActivity)
        )
        count = result.scalar()
    assert count > 0, "Expected existing garmin_activities rows"


@pytest.mark.asyncio
async def test_can_read_garmin_daily_summary():
    async with async_session() as session:
        result = await session.execute(
            select(func.count()).select_from(GarminDailySummary)
        )
        count = result.scalar()
    assert count > 0, "Expected existing garmin_daily_summary rows"
