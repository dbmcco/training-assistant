"""Athlete profile, biometrics, records, and gear routes."""

from math import isfinite

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.models import AthleteProfile, AthleteBiometrics, Gear, PersonalRecord
from src.services.units import format_distance_from_meters

router = APIRouter(prefix="/api/v1/athlete", tags=["athlete"])


def _looks_like_time_record(record_type: str) -> bool:
    normalized = record_type.strip().lower()
    time_tokens = (
        "fastest",
        "best",
        "1k",
        "5k",
        "10k",
        "half marathon",
        "marathon",
        "1 mile",
        "mile",
    )
    return any(token in normalized for token in time_tokens)


def _looks_like_distance_record(record_type: str) -> bool:
    normalized = record_type.strip().lower()
    distance_tokens = ("distance", "longest")
    return any(token in normalized for token in distance_tokens)


def _format_duration(seconds: float | None) -> str:
    if seconds is None or not isfinite(seconds) or seconds <= 0:
        return "--"

    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _record_display_value(record: PersonalRecord) -> tuple[str, str, str]:
    raw_value = record.value
    if raw_value is None:
        return "--", "", "unknown"

    record_type = record.record_type or ""
    activity = record.activity_type or ""

    if _looks_like_time_record(record_type):
        return _format_duration(raw_value), "time", "duration"
    if _looks_like_distance_record(record_type):
        return format_distance_from_meters(raw_value, activity), "distance", "distance"

    return f"{raw_value:.2f}".rstrip("0").rstrip("."), "value", "numeric"


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
    payload = []
    for record in records:
        display_value, value_unit, value_kind = _record_display_value(record)
        payload.append(
            {
                "id": str(record.id),
                "record_type": record.record_type,
                "activity_type": record.activity_type,
                "value": record.value,
                "display_value": display_value,
                "value_unit": value_unit,
                "value_kind": value_kind,
                "activity_id": record.activity_id,
                "recorded_at": (
                    record.recorded_at.isoformat() if record.recorded_at else None
                ),
            }
        )
    return payload


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
