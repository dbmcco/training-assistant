"""Recommendation change lifecycle helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import (
    AssistantPlanEntry,
    DailyBriefing,
    PlannedWorkout,
    RecommendationChange,
)
from src.services.garmin_refresh import refresh_garmin_daily_data_on_demand
from src.services.garmin_writeback import (
    fallback_writeback_payload,
    write_recommendation_change,
)
from src.services.assistant_plan import DayTemplate, _build_workout_prescription

ALLOWED_DECISIONS = {"approved", "rejected", "changes_requested"}


def _assistant_mode() -> bool:
    return settings.plan_ownership_mode.strip().lower() == "assistant"


async def recommendation_table_available(db: AsyncSession) -> bool:
    """Return True if recommendation_changes exists in the connected DB."""
    result = await db.execute(
        text("SELECT to_regclass('public.recommendation_changes')")
    )
    return result.scalar_one_or_none() is not None


def _parse_uuid(value: Any) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _normalise_discipline(value: Any) -> str | None:
    if not value:
        return None
    raw = str(value).strip().lower()
    if raw.startswith("run"):
        return "run"
    if raw.startswith("bike") or "cycl" in raw:
        return "bike"
    if raw.startswith("swim"):
        return "swim"
    if raw.startswith("strength"):
        return "strength"
    if raw:
        return raw
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sanitize_workout_steps(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    steps: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        duration = _coerce_int(raw.get("duration_minutes"))
        if duration is None or duration <= 0:
            continue
        step_type = str(raw.get("type") or "interval").strip().lower() or "interval"
        notes = str(raw.get("notes") or raw.get("label") or "").strip()
        target = str(raw.get("target") or "").strip()
        cue = str(raw.get("cue") or "").strip()
        if target:
            notes = f"{notes} @ {target}".strip()
        if cue:
            notes = f"{notes} - {cue}".strip()
        steps.append(
            {
                "type": step_type,
                "duration_minutes": duration,
                "notes": notes[:480] if notes else "",
            }
        )
    return steps or None


def _workout_snapshot(workout: PlannedWorkout | None) -> dict[str, Any] | None:
    if not workout:
        return None
    return {
        "id": str(workout.id),
        "date": workout.date.isoformat() if workout.date else None,
        "discipline": workout.discipline,
        "workout_type": workout.workout_type,
        "target_duration": workout.target_duration,
        "target_distance": workout.target_distance,
        "target_hr_zone": workout.target_hr_zone,
        "description": workout.description,
        "status": workout.status,
    }


def _append_event(
    rec: RecommendationChange,
    *,
    event: str,
    payload: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    log = rec.training_impact_log or {}
    events = list(log.get("events", []))
    events.append({"at": now, "event": event, **(payload or {})})
    rec.training_impact_log = {**log, "events": events}


def _sanitize_proposed_workout(raw_change: Any) -> dict[str, Any]:
    if not isinstance(raw_change, dict):
        return {}
    parsed_workout_date = _parse_date(raw_change.get("workout_date"))
    payload: dict[str, Any] = {
        "workout_id": str(raw_change.get("workout_id")).strip()
        if raw_change.get("workout_id")
        else None,
        "workout_date": parsed_workout_date.isoformat()
        if parsed_workout_date
        else None,
        "discipline": _normalise_discipline(raw_change.get("discipline")),
        "workout_type": str(raw_change.get("workout_type")).strip()
        if raw_change.get("workout_type")
        else None,
        "target_duration": _coerce_int(raw_change.get("target_duration")),
        "target_distance": _coerce_float(raw_change.get("target_distance")),
        "target_hr_zone": _coerce_int(raw_change.get("target_hr_zone")),
        "description": str(raw_change.get("description")).strip()
        if raw_change.get("description")
        else None,
        "reason": str(raw_change.get("reason")).strip()
        if raw_change.get("reason")
        else None,
    }
    workout_steps = _sanitize_workout_steps(raw_change.get("workout_steps"))
    if workout_steps:
        payload["workout_steps"] = workout_steps
    return payload


def _hydrate_proposed_workout_details(
    proposed: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(proposed, dict):
        return {}

    discipline = _normalise_discipline(proposed.get("discipline"))
    workout_type = str(proposed.get("workout_type") or "").strip().lower()
    duration = _coerce_int(proposed.get("target_duration")) or 45
    if not discipline or not workout_type:
        return proposed

    needs_steps = not isinstance(proposed.get("workout_steps"), list)
    description_text = str(proposed.get("description") or "").strip()
    needs_rich_description = (
        not description_text or "Session Plan:" not in description_text
    )
    if not needs_steps and not needs_rich_description:
        return proposed

    try:
        template = DayTemplate(
            discipline=discipline,
            workout_type=workout_type,
            duration_min=max(duration, 20),
            description=description_text or "Structured session",
        )
        prescription = _build_workout_prescription(
            template=template,
            phase="build",
            week_index=0,
        )
    except Exception:
        return proposed

    if needs_steps and prescription.workout_steps:
        proposed["workout_steps"] = prescription.workout_steps
    if needs_rich_description and prescription.description:
        proposed["description"] = prescription.description
    if (
        proposed.get("target_distance") is None
        and prescription.target_distance_meters is not None
    ):
        proposed["target_distance"] = float(prescription.target_distance_meters)
    if (
        proposed.get("target_hr_zone") is None
        and prescription.target_hr_zone is not None
    ):
        proposed["target_hr_zone"] = int(prescription.target_hr_zone)
    return proposed


def _needs_change(raw_change: Any, recommendation_text: str | None) -> bool:
    if isinstance(raw_change, dict) and isinstance(
        raw_change.get("needs_change"), bool
    ):
        return bool(raw_change["needs_change"])
    text = (recommendation_text or "").lower()
    if not text:
        return False
    keep_tokens = (
        "no change",
        "as planned",
        "keep",
        "confirm today's",
        "confirm today",
    )
    return not any(token in text for token in keep_tokens)


async def _find_target_workout(
    db: AsyncSession,
    *,
    workout_id: UUID | None,
    workout_date: date | None,
    discipline: str | None,
) -> PlannedWorkout | None:
    if workout_id:
        by_id = await db.execute(
            select(PlannedWorkout).where(PlannedWorkout.id == workout_id)
        )
        row = by_id.scalar_one_or_none()
        if row:
            return row

    if not workout_date:
        return None

    query = select(PlannedWorkout).where(PlannedWorkout.date == workout_date)
    if discipline:
        query = query.where(PlannedWorkout.discipline.ilike(f"%{discipline}%"))
    query = query.order_by(PlannedWorkout.created_at.desc(), PlannedWorkout.id)
    result = await db.execute(query.limit(1))
    return result.scalar_one_or_none()


async def _load_assistant_entry_for_workout(
    db: AsyncSession,
    *,
    workout: PlannedWorkout | None,
) -> AssistantPlanEntry | None:
    if workout is None or workout.id is None:
        return None
    result = await db.execute(
        select(AssistantPlanEntry).where(
            AssistantPlanEntry.planned_workout_id == workout.id
        )
    )
    return result.scalar_one_or_none()


def serialize_recommendation(rec: RecommendationChange) -> dict[str, Any]:
    return {
        "id": str(rec.id),
        "source": rec.source,
        "source_ref_id": str(rec.source_ref_id) if rec.source_ref_id else None,
        "planned_workout_id": str(rec.planned_workout_id)
        if rec.planned_workout_id
        else None,
        "workout_date": rec.workout_date.isoformat() if rec.workout_date else None,
        "recommendation_text": rec.recommendation_text,
        "proposed_workout": rec.proposed_workout,
        "status": rec.status,
        "decision_notes": rec.decision_notes,
        "requested_changes": rec.requested_changes,
        "garmin_sync_status": rec.garmin_sync_status,
        "garmin_sync_payload": rec.garmin_sync_payload,
        "garmin_sync_result": rec.garmin_sync_result,
        "training_impact_log": rec.training_impact_log,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "decided_at": rec.decided_at.isoformat() if rec.decided_at else None,
        "applied_at": rec.applied_at.isoformat() if rec.applied_at else None,
    }


async def get_briefing_recommendation(
    db: AsyncSession, briefing_id: UUID
) -> RecommendationChange | None:
    if not await recommendation_table_available(db):
        return None
    result = await db.execute(
        select(RecommendationChange)
        .where(
            and_(
                RecommendationChange.source == "briefing",
                RecommendationChange.source_ref_id == briefing_id,
            )
        )
        .order_by(RecommendationChange.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_recommendation_from_briefing(
    db: AsyncSession,
    *,
    briefing: DailyBriefing,
    parsed_payload: dict[str, Any],
) -> RecommendationChange | None:
    if not await recommendation_table_available(db):
        return None

    if not briefing.id:
        return None

    existing = await get_briefing_recommendation(db, briefing.id)
    if existing:
        return existing

    recommendation_text = parsed_payload.get("workout_recommendation")
    raw_change = parsed_payload.get("recommendation_change")
    if not _needs_change(raw_change, recommendation_text):
        return None

    proposed = _sanitize_proposed_workout(raw_change)
    proposed = _hydrate_proposed_workout_details(proposed)
    workout_id = _parse_uuid(proposed.get("workout_id"))
    workout_date = _parse_date(proposed.get("workout_date")) or briefing.date
    discipline = _normalise_discipline(proposed.get("discipline"))

    target_workout = await _find_target_workout(
        db,
        workout_id=workout_id,
        workout_date=workout_date,
        discipline=discipline,
    )

    now = datetime.now(timezone.utc)
    rec = RecommendationChange(
        source="briefing",
        source_ref_id=briefing.id,
        planned_workout_id=target_workout.id if target_workout else None,
        workout_date=workout_date,
        recommendation_text=recommendation_text,
        proposed_workout=proposed,
        status="pending",
        garmin_sync_status="pending",
        created_at=now,
    )
    _append_event(
        rec,
        event="created",
        payload={
            "recommendation_text": recommendation_text,
            "target_workout": _workout_snapshot(target_workout),
        },
    )
    db.add(rec)
    await db.flush()
    return rec


def _apply_proposed_workout(workout: PlannedWorkout, proposed: dict[str, Any]) -> None:
    new_date = _parse_date(proposed.get("workout_date"))
    if new_date:
        workout.date = new_date

    new_discipline = _normalise_discipline(proposed.get("discipline"))
    if new_discipline:
        workout.discipline = new_discipline

    if proposed.get("workout_type"):
        workout.workout_type = str(proposed.get("workout_type")).strip()

    new_duration = _coerce_int(proposed.get("target_duration"))
    if new_duration is not None and new_duration > 0:
        workout.target_duration = new_duration
    new_distance = _coerce_float(proposed.get("target_distance"))
    if new_distance is not None and new_distance > 0:
        workout.target_distance = new_distance
    new_hr_zone = _coerce_int(proposed.get("target_hr_zone"))
    if new_hr_zone is not None and new_hr_zone > 0:
        workout.target_hr_zone = new_hr_zone

    if proposed.get("description"):
        workout.description = str(proposed.get("description")).strip()

    # Preserve coach-approved intent through future auto-regenerations.
    workout.status = "modified"


async def decide_recommendation(
    db: AsyncSession,
    *,
    recommendation: RecommendationChange,
    decision: str,
    note: str | None,
    requested_changes: str | None = None,
) -> RecommendationChange:
    decision = decision.strip().lower()
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(f"Invalid decision: {decision}")

    now = datetime.now(timezone.utc)
    recommendation.status = decision
    recommendation.decision_notes = note
    recommendation.requested_changes = requested_changes
    recommendation.decided_at = now

    if decision == "approved":
        proposed = recommendation.proposed_workout or {}
        proposed = _hydrate_proposed_workout_details(proposed)
        recommendation.proposed_workout = proposed
        target_id = recommendation.planned_workout_id
        workout_id = target_id or _parse_uuid(proposed.get("workout_id"))

        # Resolve target workout and assistant entry before autoflush can
        # fire on the dirty recommendation row (avoids statement timeout).
        with db.no_autoflush:
            target = await _find_target_workout(
                db,
                workout_id=workout_id,
                workout_date=recommendation.workout_date,
                discipline=_normalise_discipline(proposed.get("discipline")),
            )
            assistant_entry = await _load_assistant_entry_for_workout(
                db,
                workout=target,
            )
        replace_workout_id = None
        if assistant_entry and assistant_entry.garmin_workout_id:
            candidate = str(assistant_entry.garmin_workout_id).strip()
            if candidate:
                replace_workout_id = candidate

        before_snapshot = _workout_snapshot(target)
        if target and proposed:
            _apply_proposed_workout(target, proposed)
            recommendation.planned_workout_id = target.id
        after_snapshot = _workout_snapshot(target)

        payload = fallback_writeback_payload(
            workout_date=(
                target.date.isoformat()
                if target and target.date
                else recommendation.workout_date.isoformat()
                if recommendation.workout_date
                else proposed.get("workout_date")
            ),
            discipline=(target.discipline if target else proposed.get("discipline")),
            workout_type=(
                target.workout_type if target else proposed.get("workout_type")
            ),
            target_duration=(
                target.target_duration
                if target
                else _coerce_int(proposed.get("target_duration"))
            ),
            description=(target.description if target else proposed.get("description")),
            workout_steps=(
                proposed.get("workout_steps")
                if isinstance(proposed.get("workout_steps"), list)
                else None
            ),
            replace_workout_id=replace_workout_id,
            recommendation_text=recommendation.recommendation_text,
        )
        recommendation.garmin_sync_payload = payload
        writeback = await write_recommendation_change(payload)
        verification_status = str(
            writeback.get("verification_status", writeback.get("status", "failed"))
        ).lower()
        refresh_result: dict[str, Any] | None = None
        if verification_status in ("success", "synced_unverified"):
            refresh_result = await refresh_garmin_daily_data_on_demand(
                include_calendar=not _assistant_mode(),
                force=True,
            )
            if isinstance(refresh_result, dict):
                writeback = {**writeback, "calendar_refresh": refresh_result}
        recommendation.garmin_sync_result = writeback
        recommendation.garmin_sync_status = verification_status
        recommendation.applied_at = now

        if assistant_entry is not None:
            assistant_entry.garmin_sync_status = verification_status
            assistant_entry.garmin_sync_result = writeback
            assistant_entry.updated_at = now
            if verification_status == "success":
                new_workout_id = str(writeback.get("workout_id") or "").strip()
                if new_workout_id:
                    assistant_entry.garmin_workout_id = new_workout_id

        _append_event(
            recommendation,
            event="approved",
            payload={
                "note": note,
                "before": before_snapshot,
                "after": after_snapshot,
                "garmin": {
                    "status": verification_status,
                    "result": writeback,
                    "calendar_refresh": refresh_result,
                },
            },
        )

        verification_event = (
            "writeback_verified"
            if verification_status == "success"
            else "writeback_unverified"
        )
        _append_event(
            recommendation,
            event=verification_event,
            payload={
                "verification_status": verification_status,
                "verification_details": writeback.get("verification_details"),
                "verification_error": writeback.get("verification_error"),
            },
        )
    elif decision == "rejected":
        recommendation.garmin_sync_status = "skipped"
        _append_event(
            recommendation,
            event="rejected",
            payload={"note": note},
        )
    else:
        recommendation.garmin_sync_status = "skipped"
        _append_event(
            recommendation,
            event="changes_requested",
            payload={
                "note": note,
                "requested_changes": requested_changes,
            },
        )

    await db.flush()
    return recommendation


async def create_coach_recommendation_intent(
    db: AsyncSession,
    *,
    recommendation_text: str,
    proposed_workout: dict[str, Any],
    source: str = "coach_intent",
) -> RecommendationChange:
    if not await recommendation_table_available(db):
        raise ValueError("Recommendation pipeline is not available.")

    proposed = _sanitize_proposed_workout(proposed_workout)
    proposed = _hydrate_proposed_workout_details(proposed)
    if not proposed:
        raise ValueError("Intent requires a proposed workout payload.")

    target_workout = await _find_target_workout(
        db,
        workout_id=_parse_uuid(proposed.get("workout_id")),
        workout_date=_parse_date(proposed.get("workout_date")),
        discipline=_normalise_discipline(proposed.get("discipline")),
    )
    workout_date = _parse_date(proposed.get("workout_date")) or (
        target_workout.date if target_workout else None
    )

    now = datetime.now(timezone.utc)
    rec = RecommendationChange(
        source=source,
        source_ref_id=None,
        planned_workout_id=target_workout.id if target_workout else None,
        workout_date=workout_date,
        recommendation_text=(recommendation_text or "").strip(),
        proposed_workout=proposed,
        status="pending",
        garmin_sync_status="pending",
        created_at=now,
    )
    _append_event(
        rec,
        event="intent_created",
        payload={
            "target_workout": _workout_snapshot(target_workout),
            "proposed": proposed,
        },
    )
    db.add(rec)
    await db.flush()
    return rec
