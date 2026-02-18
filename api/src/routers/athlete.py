"""Athlete profile, biometrics, records, and gear routes."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.models import AthleteProfile, AthleteBiometrics, Gear, PersonalRecord

router = APIRouter(prefix="/api/v1/athlete", tags=["athlete"])


@router.get("/profile")
async def athlete_profile(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AthleteProfile).limit(1))
    profile = result.scalar_one_or_none()
    if not profile:
        return None
    return {
        "id": str(profile.id),
        "notes": profile.notes,
        "goals": profile.goals,
        "injury_history": profile.injury_history,
        "preferences": profile.preferences,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@router.get("/biometrics")
async def athlete_biometrics(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AthleteBiometrics).order_by(AthleteBiometrics.date.desc()).limit(1)
    )
    bio = result.scalar_one_or_none()
    if not bio:
        return None
    return {
        "id": str(bio.id),
        "date": bio.date.isoformat() if bio.date else None,
        "weight_kg": bio.weight_kg,
        "body_fat_pct": bio.body_fat_pct,
        "muscle_mass_kg": bio.muscle_mass_kg,
        "bmi": bio.bmi,
        "fitness_age": bio.fitness_age,
        "actual_age": bio.actual_age,
        "lactate_threshold_hr": bio.lactate_threshold_hr,
        "lactate_threshold_pace": bio.lactate_threshold_pace,
        "cycling_ftp": bio.cycling_ftp,
    }


@router.get("/records")
async def athlete_records(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PersonalRecord).order_by(PersonalRecord.recorded_at.desc())
    )
    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "record_type": r.record_type,
            "activity_type": r.activity_type,
            "value": r.value,
            "activity_id": r.activity_id,
            "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
        }
        for r in records
    ]


@router.get("/gear")
async def athlete_gear(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Gear).order_by(Gear.date_begin.desc()))
    gear_list = result.scalars().all()
    return [
        {
            "id": str(g.id),
            "garmin_gear_uuid": g.garmin_gear_uuid,
            "name": g.name,
            "gear_type": g.gear_type,
            "brand": g.brand,
            "model": g.model,
            "date_begin": g.date_begin.isoformat() if g.date_begin else None,
            "max_distance_km": g.max_distance_km,
            "total_distance_km": g.total_distance_km,
            "total_activities": g.total_activities,
        }
        for g in gear_list
    ]
