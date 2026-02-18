import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_readiness_today():
    """GET /api/v1/readiness/today should return a readiness score."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/readiness/today")
    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert "label" in data
    assert "components" in data


@pytest.mark.asyncio
async def test_readiness_history_default():
    """GET /api/v1/readiness/history should return readiness for last 7 days by default."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/readiness/history")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 7


@pytest.mark.asyncio
async def test_readiness_history_with_days():
    """GET /api/v1/readiness/history?days=14 should return up to 14 days."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/readiness/history", params={"days": 14}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 14


@pytest.mark.asyncio
async def test_readiness_history_entries_have_date_and_score():
    """Each history entry should have date, score, and label."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/readiness/history")
    data = resp.json()
    for entry in data:
        assert "date" in entry
        assert "score" in entry
        assert "label" in entry
