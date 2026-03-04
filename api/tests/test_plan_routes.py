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


@pytest.mark.asyncio
async def test_plan_changes():
    """GET /api/v1/plan/changes should return change events list."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/plan/changes",
            params={"days_back": 7, "limit": 10},
        )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_plan_owner_mode():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/plan/owner")
    assert resp.status_code == 200
    data = resp.json()
    assert "mode" in data
    assert "assistant_owned" in data


@pytest.mark.asyncio
async def test_assistant_generate_plan_not_enabled(monkeypatch):
    monkeypatch.setattr("src.routers.plan.is_assistant_owned_mode", lambda: False)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/plan/assistant/generate")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_assistant_generate_plan_success(monkeypatch):
    monkeypatch.setattr("src.routers.plan.is_assistant_owned_mode", lambda: True)

    async def fake_generate_assistant_plan(
        db,
        *,
        days_ahead: int,
        overwrite: bool,
        sync_to_garmin: bool,
    ):
        _ = (db, days_ahead, overwrite, sync_to_garmin)
        return {
            "mode": "assistant",
            "created_workouts": 10,
            "synced_success": 7,
            "synced_failed": 0,
            "synced_skipped": 3,
            "phase": "build",
            "window_start": "2026-03-04",
            "window_end": "2026-03-17",
            "days_ahead": 14,
            "plan_id": "00000000-0000-0000-0000-000000000000",
            "deleted_existing": 0,
            "workouts": [],
            "race": None,
        }

    monkeypatch.setattr(
        "src.routers.plan.generate_assistant_plan",
        fake_generate_assistant_plan,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/plan/assistant/generate",
            params={"days_ahead": 14, "overwrite": "true", "sync_to_garmin": "true"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created_workouts"] == 10
