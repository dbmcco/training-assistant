import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_current_plan():
    """GET /api/v1/plan/current should return plan or null."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/plan/current")
    assert resp.status_code == 200
    # Returns a plan dict or null
    data = resp.json()
    assert data is None or isinstance(data, dict)


@pytest.mark.asyncio
async def test_list_workouts():
    """GET /api/v1/plan/workouts should return a list."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/plan/workouts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_workouts_with_date_filters():
    """GET /api/v1/plan/workouts with date params should work."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/plan/workouts",
            params={"start_date": "2026-01-01", "end_date": "2026-12-31"},
        )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_activities():
    """GET /api/v1/plan/activities should return a list."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/plan/activities")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_activities_with_date_filters():
    """GET /api/v1/plan/activities with date params should work."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/plan/activities",
            params={"start_date": "2026-01-01", "end_date": "2026-12-31"},
        )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_update_workout_not_found():
    """PUT /api/v1/plan/workouts/:id with bad ID should return 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            f"/api/v1/plan/workouts/{fake_id}",
            json={"status": "completed"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_plan_adherence():
    """GET /api/v1/plan/adherence should return adherence stats."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/plan/adherence")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_planned" in data
    assert "completed" in data
    assert "completion_pct" in data


@pytest.mark.asyncio
async def test_plan_adherence_with_dates():
    """GET /api/v1/plan/adherence with date range should work."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/plan/adherence",
            params={"start": "2026-01-01", "end": "2026-02-28"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_planned" in data
