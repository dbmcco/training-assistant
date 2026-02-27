"""Daily briefing routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.models import DailyBriefing
from src.services.briefing import generate_briefing
from src.services.recommendations import get_briefing_recommendation, serialize_recommendation

router = APIRouter(prefix="/api/v1/briefings", tags=["briefings"])


async def _briefing_to_dict(db: AsyncSession, b: DailyBriefing) -> dict:
    recommendation_row = await get_briefing_recommendation(db, b.id)
    return {
        "id": str(b.id),
        "date": b.date.isoformat() if b.date else None,
        "content": b.content,
        "readiness_summary": b.readiness_summary,
        "workout_recommendation": b.workout_recommendation,
        "alerts": b.alerts,
        "recommendation_change": serialize_recommendation(recommendation_row) if recommendation_row else None,
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
    return await _briefing_to_dict(db, briefing)


@router.post("/generate")
async def generate_daily_briefing(db: AsyncSession = Depends(get_db)):
    """Generate today's briefing (idempotent — returns existing if already generated)."""
    return await generate_briefing(db)


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
    return [await _briefing_to_dict(db, b) for b in briefings]
