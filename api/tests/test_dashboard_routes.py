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
    if data["briefing"] is not None:
        assert "recommendation_change" in data["briefing"]

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
async def test_dashboard_refresh(monkeypatch):
    """POST /api/v1/dashboard/refresh should call refresh service and return status."""

    async def fake_refresh(*, include_calendar: bool = False, force: bool = False):
        return {
            "status": "success",
            "include_calendar": include_calendar,
            "force": force,
        }

    monkeypatch.setattr(
        "src.routers.dashboard.refresh_garmin_daily_data_on_demand",
        fake_refresh,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/dashboard/refresh",
            params={"include_calendar": "true", "force": "true"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["include_calendar"] is True
    assert data["force"] is True


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
    assert "requested_start" in data
    assert "requested_end" in data
    assert "range_adjusted" in data
    assert "earliest_data_date" in data
    assert "latest_data_date" in data
    assert "metric" in data
    assert "metric_options" in data
    assert "series" in data
    assert "series_summary" in data
    assert "volume" in data
    assert "activity_types" in data
    assert "stats" in data
    assert "analysis" in data
    assert "events" in data
    assert "coach_summary" in data
    assert "executive_summary" in data
    assert "insights" in data["analysis"]
    executive_summary = data["executive_summary"]
    assert "as_of" in executive_summary
    assert "status_level" in executive_summary
    assert "status" in executive_summary
    assert "summary" in executive_summary
    assert "recommendations" in executive_summary


@pytest.mark.asyncio
async def test_dashboard_trends_with_params():
    """GET /api/v1/dashboard/trends with explicit date range."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/dashboard/trends",
            params={"start": "2026-01-01", "end": "2026-01-31", "metric": "sleep_score"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["start"] == "2026-01-01"
    assert data["end"] == "2026-01-31"
    assert data["requested_start"] == "2026-01-01"
    assert data["requested_end"] == "2026-01-31"
    assert data["metric"] == "sleep_score"
    assert "series" in data
    assert "series_summary" in data
    assert "volume" in data
    assert "stats" in data
    assert "analysis" in data


@pytest.mark.asyncio
async def test_dashboard_trends_future_range_shifts_to_latest_data():
    """GET /api/v1/dashboard/trends should shift stale future ranges to available data."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/dashboard/trends",
            params={"start": "2099-01-01", "end": "2099-01-31", "metric": "readiness"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["requested_start"] == "2099-01-01"
    assert data["requested_end"] == "2099-01-31"
    if data["latest_data_date"] is not None:
        assert data["range_adjusted"] is True
        assert data["end"] == data["latest_data_date"]
