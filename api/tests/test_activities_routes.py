import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_list_activities():
    """GET /api/v1/activities should return a paginated list."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/activities")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Default limit is 20
    assert len(data) <= 20


@pytest.mark.asyncio
async def test_list_activities_with_pagination():
    """GET /api/v1/activities with limit and offset should paginate."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/activities", params={"limit": 5, "offset": 0}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 5


@pytest.mark.asyncio
async def test_list_activities_with_date_filter():
    """GET /api/v1/activities with date params should filter."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/activities",
            params={"start_date": "2026-01-01", "end_date": "2026-02-28"},
        )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_activities_with_discipline():
    """GET /api/v1/activities with discipline param should filter."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/activities", params={"discipline": "running"}
        )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_activity_stats():
    """GET /api/v1/activities/stats should return stats dict."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/activities/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_activities" in data
    assert "total_hours" in data
    assert "total_distance_km" in data


@pytest.mark.asyncio
async def test_activity_stats_with_dates():
    """GET /api/v1/activities/stats with date range."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/activities/stats",
            params={"start": "2026-01-01", "end": "2026-02-28"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_activities" in data


@pytest.mark.asyncio
async def test_get_activity_not_found():
    """GET /api/v1/activities/:id with nonexistent ID should return 404."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/activities/9999999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_activity_by_garmin_id():
    """GET /api/v1/activities/:id should return an activity if it exists."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # First get the list to find a real garmin_activity_id
        list_resp = await client.get(
            "/api/v1/activities", params={"limit": 1}
        )
        activities = list_resp.json()
        if not activities:
            pytest.skip("No activities in database to test with")

        garmin_id = activities[0]["garmin_activity_id"]
        resp = await client.get(f"/api/v1/activities/{garmin_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["garmin_activity_id"] == garmin_id
