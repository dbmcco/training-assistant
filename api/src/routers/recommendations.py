"""Recommendation change routes."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.models import RecommendationChange
from src.services.recommendations import (
    decide_recommendation,
    recommendation_table_available,
    serialize_recommendation,
)

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


class RecommendationDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected", "changes_requested"]
    note: str | None = None
    requested_changes: str | None = None


@router.get("")
async def list_recommendations(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    if not await recommendation_table_available(db):
        return []

    query = select(RecommendationChange).order_by(RecommendationChange.created_at.desc()).limit(limit)
    if status:
        query = query.where(RecommendationChange.status == status)
    result = await db.execute(query)
    rows = result.scalars().all()
    return [serialize_recommendation(row) for row in rows]


@router.get("/{recommendation_id}")
async def get_recommendation(
    recommendation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    if not await recommendation_table_available(db):
        raise HTTPException(status_code=404, detail="Recommendation not found")

    result = await db.execute(
        select(RecommendationChange).where(RecommendationChange.id == recommendation_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return serialize_recommendation(row)


@router.post("/{recommendation_id}/decision")
async def submit_recommendation_decision(
    recommendation_id: UUID,
    body: RecommendationDecisionRequest,
    db: AsyncSession = Depends(get_db),
):
    if not await recommendation_table_available(db):
        raise HTTPException(status_code=404, detail="Recommendation not found")

    result = await db.execute(
        select(RecommendationChange).where(RecommendationChange.id == recommendation_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    try:
        updated = await decide_recommendation(
            db,
            recommendation=row,
            decision=body.decision,
            note=body.note,
            requested_changes=body.requested_changes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(updated)
    return serialize_recommendation(updated)
