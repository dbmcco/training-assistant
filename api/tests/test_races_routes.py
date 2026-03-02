import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_list_races():
    """GET /api/v1/races should return a list."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/races")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_race():
    """POST /api/v1/races should create a race and return it."""
    payload = {
        "name": "Test Sprint Tri",
        "date": "2026-06-15",
        "distance_type": "sprint",
        "goal_time": 5400,
        "notes": "First race of the season",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/races", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        race_id = data["id"]
        try:
            assert data["name"] == "Test Sprint Tri"
            assert data["distance_type"] == "sprint"
            assert "id" in data
        finally:
            await client.delete(f"/api/v1/races/{race_id}")


@pytest.mark.asyncio
async def test_create_and_update_race():
    """PUT /api/v1/races/:id should update a race."""
    payload = {
        "name": "Update Test Race",
        "date": "2026-07-01",
        "distance_type": "olympic",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post("/api/v1/races", json=payload)
        assert create_resp.status_code == 201
        race_id = create_resp.json()["id"]
        try:
            update_resp = await client.put(
                f"/api/v1/races/{race_id}",
                json={"name": "Updated Race Name", "goal_time": 7200},
            )
            assert update_resp.status_code == 200
            assert update_resp.json()["name"] == "Updated Race Name"
            assert update_resp.json()["goal_time"] == 7200
        finally:
            await client.delete(f"/api/v1/races/{race_id}")


@pytest.mark.asyncio
async def test_create_and_delete_race():
    """DELETE /api/v1/races/:id should delete a race."""
    payload = {
        "name": "Delete Me Race",
        "date": "2026-08-01",
        "distance_type": "half",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post("/api/v1/races", json=payload)
        assert create_resp.status_code == 201
        race_id = create_resp.json()["id"]

        delete_resp = await client.delete(f"/api/v1/races/{race_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True


@pytest.mark.asyncio
async def test_race_projection():
    """GET /api/v1/races/:id/projection should return race + weeks_out."""
    payload = {
        "name": "Projection Race",
        "date": "2026-09-01",
        "distance_type": "70.3",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post("/api/v1/races", json=payload)
        assert create_resp.status_code == 201
        race_id = create_resp.json()["id"]
        try:
            proj_resp = await client.get(f"/api/v1/races/{race_id}/projection")
            assert proj_resp.status_code == 200
            data = proj_resp.json()
            assert "weeks_out" in data
            assert data["name"] == "Projection Race"
        finally:
            await client.delete(f"/api/v1/races/{race_id}")


@pytest.mark.asyncio
async def test_update_nonexistent_race():
    """PUT /api/v1/races/:id with bad ID should return 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            f"/api/v1/races/{fake_id}", json={"name": "Nope"}
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_race():
    """DELETE /api/v1/races/:id with bad ID should return 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(f"/api/v1/races/{fake_id}")
    assert resp.status_code == 404
