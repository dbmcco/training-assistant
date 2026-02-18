"""Daily briefing routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.models import DailyBriefing

router = APIRouter(prefix="/api/v1/briefings", tags=["briefings"])


def _briefing_to_dict(b: DailyBriefing) -> dict:
    return {
        "id": str(b.id),
        "date": b.date.isoformat() if b.date else None,
        "content": b.content,
        "readiness_summary": b.readiness_summary,
        "workout_recommendation": b.workout_recommendation,
        "alerts": b.alerts,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


@router.get("/latest")
async def latest_briefing(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DailyBriefing)
        .order_by(DailyBriefing.date.desc())
        .limit(1)
    )
    briefing = result.scalar_one_or_none()
    if not briefing:
        return None
    return _briefing_to_dict(briefing)


@router.get("")
async def list_briefings(
    limit: int = Query(default=7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DailyBriefing)
        .order_by(DailyBriefing.date.desc())
        .limit(limit)
    )
    briefings = result.scalars().all()
    return [_briefing_to_dict(b) for b in briefings]
