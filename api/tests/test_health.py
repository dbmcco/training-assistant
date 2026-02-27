import pytest
from httpx import ASGITransport, AsyncClient

import src.main as main_mod

app = main_mod.app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_ready_ok(monkeypatch):
    async def _db_ready() -> bool:
        return True

    monkeypatch.setattr(main_mod, "check_db_ready", _db_ready)
    app.state.startup_warmup = {"ok": True, "error": None, "duration_ms": 1.0}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health/ready")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db_ok"] is True
    assert body["warmup_ok"] is True


@pytest.mark.asyncio
async def test_health_ready_degraded_when_db_unavailable(monkeypatch):
    async def _db_not_ready() -> bool:
        return False

    monkeypatch.setattr(main_mod, "check_db_ready", _db_not_ready)
    app.state.startup_warmup = {"ok": True, "error": None, "duration_ms": 1.0}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health/ready")

    assert resp.status_code == 503
    assert resp.json()["detail"]["status"] == "degraded"
