import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_latest_briefing():
    """GET /api/v1/briefings/latest should return briefing or null."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/briefings/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data is None or isinstance(data, dict)


@pytest.mark.asyncio
async def test_list_briefings_default():
    """GET /api/v1/briefings should return a list (last 7 by default)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/briefings")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 7


@pytest.mark.asyncio
async def test_list_briefings_with_limit():
    """GET /api/v1/briefings?limit=3 should return at most 3."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/briefings", params={"limit": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 3


@pytest.mark.asyncio
async def test_briefing_structure():
    """Briefings should have expected fields when they exist."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/briefings")
    data = resp.json()
    for briefing in data:
        assert "id" in briefing
        assert "date" in briefing
        assert "content" in briefing
