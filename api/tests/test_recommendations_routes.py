import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_list_recommendations():
    """GET /api/v1/recommendations should return a list."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/recommendations")

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_recommendation_not_found():
    """GET /api/v1/recommendations/:id should return 404 for bad ID."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/api/v1/recommendations/{fake_id}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_recommendation_decision_not_found():
    """POST /api/v1/recommendations/:id/decision should return 404 for bad ID."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/recommendations/{fake_id}/decision",
            json={"decision": "approved"},
        )

    assert resp.status_code == 404
