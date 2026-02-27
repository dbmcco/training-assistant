import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_athlete_profile():
    """GET /api/v1/athlete/profile should return profile or null."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/athlete/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data is None or isinstance(data, dict)


@pytest.mark.asyncio
async def test_athlete_biometrics():
    """GET /api/v1/athlete/biometrics should return latest biometrics or null."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/athlete/biometrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data is None or isinstance(data, dict)


@pytest.mark.asyncio
async def test_athlete_records():
    """GET /api/v1/athlete/records should return a list."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/athlete/records")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        first = data[0]
        assert "display_value" in first
        assert "value_unit" in first
        assert "value_kind" in first


@pytest.mark.asyncio
async def test_athlete_gear():
    """GET /api/v1/athlete/gear should return a list."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/athlete/gear")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
