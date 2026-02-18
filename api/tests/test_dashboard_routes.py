import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_dashboard_today():
    """GET /api/v1/dashboard/today should return readiness, date, and metrics."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/dashboard/today")
    assert resp.status_code == 200
    data = resp.json()
    assert "date" in data
    assert "readiness" in data
    assert "today_workout" in data
    assert "races" in data
    assert "briefing" in data
    assert "training_status" in data
    assert "metrics" in data

    # Readiness should have score, label, components
    readiness = data["readiness"]
    assert "score" in readiness
    assert "label" in readiness
    assert "components" in readiness
    assert readiness["label"] in ("High", "Moderate", "Low")

    # Metrics should have expected keys
    metrics = data["metrics"]
    assert "sleep_score" in metrics
    assert "body_battery_wake" in metrics
    assert "hrv_last_night" in metrics
    assert "resting_hr" in metrics


@pytest.mark.asyncio
async def test_dashboard_weekly():
    """GET /api/v1/dashboard/weekly should return volume, adherence, load_trend."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/dashboard/weekly")
    assert resp.status_code == 200
    data = resp.json()
    assert "volume" in data
    assert "adherence" in data
    assert "load_trend" in data

    # Adherence should have expected keys
    adherence = data["adherence"]
    assert "total_planned" in adherence
    assert "completed" in adherence
    assert "completion_pct" in adherence

    # Load trend should be a list
    assert isinstance(data["load_trend"], list)


@pytest.mark.asyncio
async def test_dashboard_trends_default():
    """GET /api/v1/dashboard/trends without params should use 30-day default."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/dashboard/trends")
    assert resp.status_code == 200
    data = resp.json()
    assert "start" in data
    assert "end" in data
    assert "volume" in data
    assert "stats" in data


@pytest.mark.asyncio
async def test_dashboard_trends_with_params():
    """GET /api/v1/dashboard/trends with explicit date range."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/dashboard/trends",
            params={"start": "2026-01-01", "end": "2026-01-31"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["start"] == "2026-01-01"
    assert data["end"] == "2026-01-31"
    assert "volume" in data
    assert "stats" in data
