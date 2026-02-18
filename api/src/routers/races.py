"""CRUD routes for races."""

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.models import Race

router = APIRouter(prefix="/api/v1/races", tags=["races"])


def _race_to_dict(race: Race) -> dict:
    return {
        "id": str(race.id),
        "name": race.name,
        "date": race.date.isoformat() if race.date else None,
        "distance_type": race.distance_type,
        "goal_time": race.goal_time,
        "notes": race.notes,
        "created_at": race.created_at.isoformat() if race.created_at else None,
    }


@router.get("")
async def list_races(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Race).order_by(Race.date))
    races = result.scalars().all()
    return [_race_to_dict(r) for r in races]


@router.post("", status_code=201)
async def create_race(body: dict, db: AsyncSession = Depends(get_db)):
    race = Race(
        name=body["name"],
        date=date.fromisoformat(body["date"]),
        distance_type=body["distance_type"],
        goal_time=body.get("goal_time"),
        notes=body.get("notes"),
        created_at=datetime.now(timezone.utc),
    )
    db.add(race)
    await db.commit()
    await db.refresh(race)
    return _race_to_dict(race)


@router.put("/{race_id}")
async def update_race(
    race_id: UUID, body: dict, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Race).where(Race.id == race_id))
    race = result.scalar_one_or_none()
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")

    for field in ("name", "date", "distance_type", "goal_time", "notes"):
        if field in body:
            value = body[field]
            if field == "date" and isinstance(value, str):
                value = date.fromisoformat(value)
            setattr(race, field, value)

    await db.commit()
    await db.refresh(race)
    return _race_to_dict(race)


@router.delete("/{race_id}")
async def delete_race(race_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Race).where(Race.id == race_id))
    race = result.scalar_one_or_none()
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")

    await db.delete(race)
    await db.commit()
    return {"deleted": True}


@router.get("/{race_id}/projection")
async def race_projection(race_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Race).where(Race.id == race_id))
    race = result.scalar_one_or_none()
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")

    weeks_out = (race.date - date.today()).days / 7 if race.date else None
    data = _race_to_dict(race)
    data["weeks_out"] = round(weeks_out, 1) if weeks_out is not None else None
    return data
