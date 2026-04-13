"""Assistant-owned plan generation and sync orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import (
    AssistantPlanEntry,
    PlannedWorkout,
    Race,
    RecommendationChange,
    TrainingPlan,
)
from src.services.garmin_writeback import (
    fallback_writeback_payload,
    write_recommendation_change,
)


def is_assistant_owned_mode() -> bool:
    return settings.plan_ownership_mode.strip().lower() == "assistant"


async def assistant_plan_table_available(db: AsyncSession) -> bool:
    result = await db.execute(
        text("SELECT to_regclass('public.assistant_plan_entries')")
    )
    return result.scalar_one_or_none() is not None


async def ensure_assistant_plan_table(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS assistant_plan_entries (
                id UUID PRIMARY KEY,
                planned_workout_id UUID NOT NULL UNIQUE REFERENCES planned_workouts(id),
                is_locked BOOLEAN NOT NULL DEFAULT FALSE,
                garmin_workout_id TEXT NULL,
                garmin_sync_status TEXT NULL,
                garmin_sync_result JSONB NULL,
                created_at TIMESTAMPTZ NULL,
                updated_at TIMESTAMPTZ NULL
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_assistant_plan_entries_created_at
                ON assistant_plan_entries (created_at)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_assistant_plan_entries_is_locked
                ON assistant_plan_entries (is_locked)
            """
        )
    )


async def _recommendation_table_available(db: AsyncSession) -> bool:
    result = await db.execute(
        text("SELECT to_regclass('public.recommendation_changes')")
    )
    return result.scalar_one_or_none() is not None


@dataclass(frozen=True)
class DayTemplate:
    discipline: str
    workout_type: str
    duration_min: int
    description: str


@dataclass(frozen=True)
class WorkoutPrescription:
    description: str
    target_distance_meters: float | None
    target_hr_zone: int | None
    workout_steps: list[dict[str, Any]]


def _miles_to_meters(miles: float) -> float:
    return round(miles * 1609.344, 1)


def _yards_to_meters(yards: float) -> float:
    return round(yards * 0.9144, 1)


def _step(
    *,
    step_type: str,
    duration_minutes: int,
    label: str,
    target: str | None = None,
    cue: str | None = None,
) -> dict[str, Any]:
    return {
        "type": step_type,
        "duration_minutes": max(int(duration_minutes), 1),
        "label": label.strip(),
        "target": target.strip()
        if isinstance(target, str) and target.strip()
        else None,
        "cue": cue.strip() if isinstance(cue, str) and cue.strip() else None,
    }


def _render_description(
    *,
    summary: str,
    steps: list[dict[str, Any]],
    cues: list[str],
) -> str:
    lines: list[str] = [summary.strip(), "", "Session Plan:"]
    for index, item in enumerate(steps, start=1):
        segment = item.get("label", "Step")
        if item.get("target"):
            segment += f" @ {item['target']}"
        if item.get("cue"):
            segment += f" ({item['cue']})"
        lines.append(f"{index}. {segment}")

    if cues:
        lines.extend(["", "Coaching Cues:"])
        lines.extend(
            f"- {cue.strip()}" for cue in cues if isinstance(cue, str) and cue.strip()
        )

    return "\n".join(lines).strip()


def _to_garmin_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    garmin_steps: list[dict[str, Any]] = []
    for item in steps:
        duration = int(item.get("duration_minutes") or 0)
        if duration <= 0:
            continue
        notes = str(item.get("label") or "Step").strip()
        if item.get("target"):
            notes += f" @ {item['target']}"
        if item.get("cue"):
            notes += f" - {item['cue']}"
        garmin_steps.append(
            {
                "type": str(item.get("type") or "interval"),
                "duration_minutes": duration,
                "notes": notes[:480],
            }
        )
    return garmin_steps


def _build_workout_prescription(
    *,
    template: DayTemplate,
    phase: str,
    week_index: int,
) -> WorkoutPrescription:
    duration = max(template.duration_min, 20)
    workout_type = (template.workout_type or "").strip().lower()

    if workout_type == "endurance_run":
        steady_miles = 4.0 if duration >= 50 else 3.0
        cooldown_miles = 0.8 if duration >= 50 else 0.6
        steps = [
            _step(
                step_type="warmup",
                duration_minutes=10,
                label="1.0 mi warm-up jog",
                target="9:00-9:30/mi",
                cue="Relax shoulders and keep cadence light",
            ),
            _step(
                step_type="interval",
                duration_minutes=max(duration - 18, 22),
                label=f"{steady_miles:.1f} mi steady aerobic run",
                target="7:50-8:20/mi",
                cue="Conversational effort, no surging",
            ),
            _step(
                step_type="interval",
                duration_minutes=4,
                label="4 x 20s strides with 60s easy jog",
                target="5k cadence pop",
                cue="Quick feet, full recovery between reps",
            ),
            _step(
                step_type="cooldown",
                duration_minutes=4,
                label=f"{cooldown_miles:.1f} mi cool-down jog",
                target="9:05-9:40/mi",
            ),
        ]
        total_miles = round(1.0 + steady_miles + cooldown_miles, 1)
        return WorkoutPrescription(
            description=_render_description(
                summary="Aerobic run with controlled cadence strides.",
                steps=steps,
                cues=[
                    "Stay in zone 2 for the steady block.",
                    "If HR drifts high, back pace off by ~10-15 sec/mi.",
                    "Finish feeling like you could do one more mile.",
                ],
            ),
            target_distance_meters=_miles_to_meters(total_miles),
            target_hr_zone=2,
            workout_steps=_to_garmin_steps(steps),
        )

    if workout_type == "long_run":
        finish_segment_minutes = 8 if phase in {"build", "peak"} else 0
        steady_minutes = max(duration - 22, 40) - finish_segment_minutes
        cool_minutes = max(duration - 10 - steady_minutes - finish_segment_minutes, 8)
        steady_minutes = max(steady_minutes, 30)

        steady_miles = round(steady_minutes / 8.35, 1)
        finish_miles = (
            round(finish_segment_minutes / 7.7, 1) if finish_segment_minutes else 0.0
        )
        cool_miles = round(cool_minutes / 9.2, 1)

        steps = [
            _step(
                step_type="warmup",
                duration_minutes=10,
                label="1.0 mi warm-up jog",
                target="9:00-9:30/mi",
                cue="Easy breathing and tall posture",
            ),
            _step(
                step_type="interval",
                duration_minutes=steady_minutes,
                label=f"{steady_miles:.1f} mi aerobic long-run block",
                target="8:05-8:40/mi",
                cue="Lock in rhythm and fueling cadence",
            ),
        ]
        if finish_segment_minutes > 0:
            steps.append(
                _step(
                    step_type="interval",
                    duration_minutes=finish_segment_minutes,
                    label=f"{finish_miles:.1f} mi steady finish",
                    target="7:35-7:55/mi",
                    cue="Strong but controlled, never all-out",
                )
            )
        steps.append(
            _step(
                step_type="cooldown",
                duration_minutes=cool_minutes,
                label=f"{cool_miles:.1f} mi cool-down jog",
                target="9:05-9:45/mi",
            )
        )

        total_miles = round(1.0 + steady_miles + finish_miles + cool_miles, 1)
        return WorkoutPrescription(
            description=_render_description(
                summary="Long aerobic run with race-specific pacing discipline.",
                steps=steps,
                cues=[
                    "Take in fluids every 15-20 min.",
                    "Aim 30-50g carbs/hour for runs longer than 75 minutes.",
                    "Hold back in the first 20 minutes; patience wins this session.",
                ],
            ),
            target_distance_meters=_miles_to_meters(total_miles),
            target_hr_zone=2,
            workout_steps=_to_garmin_steps(steps),
        )

    if workout_type == "endurance_builder":
        total_yards = 1900 if phase in {"build", "peak"} else 1700
        base_steps = [
            _step(
                step_type="warmup",
                duration_minutes=8,
                label="300 yd easy swim + breathing reset",
                target="2:20-2:30/100yd",
                cue="Long strokes, relaxed exhale",
            ),
            _step(
                step_type="interval",
                duration_minutes=5,
                label="4 x 50 yd drill set on 1:15",
                target="Technique first",
                cue="Catch-up or fingertip drag each 50",
            ),
            _step(
                step_type="interval",
                duration_minutes=18,
                label="8 x 100 yd main set",
                target="2:05/100yd on 2:20 send-off",
                cue="Even pacing across all 8 reps",
            ),
            _step(
                step_type="interval",
                duration_minutes=10,
                label="4 x 100 yd pull set",
                target="2:10/100yd on 2:25 send-off",
                cue="Engage lats and maintain body line",
            ),
            _step(
                step_type="cooldown",
                duration_minutes=6,
                label="200 yd easy cool-down",
                target="Relaxed form",
            ),
        ]
        extra_minutes = max(duration - 47, 0)
        if extra_minutes:
            base_steps.insert(
                -1,
                _step(
                    step_type="interval",
                    duration_minutes=extra_minutes,
                    label="Technique reset (kick or pull) before cool-down",
                    target="Easy aerobic",
                ),
            )

        return WorkoutPrescription(
            description=_render_description(
                summary="Swim endurance builder focused on repeatable pace.",
                steps=base_steps,
                cues=[
                    "Hold water on each pull; don't rush turnover.",
                    "Take 10-15s extra rest only if pace slips by >3s/100yd.",
                    "Prioritize form over force in the final 400 yd.",
                ],
            ),
            target_distance_meters=_yards_to_meters(total_yards),
            target_hr_zone=2,
            workout_steps=_to_garmin_steps(base_steps),
        )

    if workout_type == "quality_intervals":
        interval_count = 4 if duration >= 65 else 3
        warm_minutes = 15 if duration >= 65 else 12
        recovery_minutes = 3
        interval_minutes = 8
        cool_minutes = max(
            duration
            - warm_minutes
            - (interval_count * interval_minutes)
            - ((interval_count - 1) * recovery_minutes),
            8,
        )

        steps: list[dict[str, Any]] = [
            _step(
                step_type="warmup",
                duration_minutes=warm_minutes,
                label=f"{warm_minutes} min progressive warm-up",
                target="Z1 -> Z2, 85-95 rpm",
                cue="Last 3 min include short cadence pickups",
            )
        ]
        for rep in range(interval_count):
            steps.append(
                _step(
                    step_type="interval",
                    duration_minutes=interval_minutes,
                    label=f"Rep {rep + 1}/{interval_count}: threshold block",
                    target="88-92% FTP @ 85-95 rpm",
                    cue="Steady output; avoid power spikes",
                )
            )
            if rep < interval_count - 1:
                steps.append(
                    _step(
                        step_type="recovery",
                        duration_minutes=recovery_minutes,
                        label="Easy spin recovery",
                        target="Z1 @ 90+ rpm",
                    )
                )
        steps.append(
            _step(
                step_type="cooldown",
                duration_minutes=cool_minutes,
                label=f"{cool_minutes} min cool-down spin",
                target="Z1-Z2",
            )
        )

        return WorkoutPrescription(
            description=_render_description(
                summary="Bike quality session to raise sustainable race power.",
                steps=steps,
                cues=[
                    "Fuel early: 30-45g carbs during this session.",
                    "Keep seated torque smooth through each interval.",
                    "If power fades >5%, cut one rep and protect quality.",
                ],
            ),
            target_distance_meters=None,
            target_hr_zone=3,
            workout_steps=_to_garmin_steps(steps),
        )

    if workout_type == "easy_spin":
        warm_minutes = 10
        cadence_block_minutes = 24
        endurance_minutes = max(duration - warm_minutes - cadence_block_minutes - 6, 8)
        cool_minutes = max(
            duration - warm_minutes - cadence_block_minutes - endurance_minutes, 4
        )
        steps = [
            _step(
                step_type="warmup",
                duration_minutes=warm_minutes,
                label="Easy roll-in",
                target="Z1-Z2 @ 85-90 rpm",
                cue="Keep effort conversational",
            ),
            _step(
                step_type="interval",
                duration_minutes=cadence_block_minutes,
                label="6 x 2 min high-cadence with 2 min easy between",
                target="95-105 rpm, light resistance",
                cue="Neuromuscular work, not cardio stress",
            ),
            _step(
                step_type="interval",
                duration_minutes=endurance_minutes,
                label="Steady endurance spin",
                target="Z2 @ 85-95 rpm",
                cue="Settle and smooth out pedal stroke",
            ),
            _step(
                step_type="cooldown",
                duration_minutes=cool_minutes,
                label="Cool-down spin",
                target="Z1",
            ),
        ]
        return WorkoutPrescription(
            description=_render_description(
                summary="Low-stress bike session for recovery and leg turnover.",
                steps=steps,
                cues=[
                    "Keep this honestly easy even if legs feel fresh.",
                    "Nasal breathing check: if you can't, back off.",
                ],
            ),
            target_distance_meters=None,
            target_hr_zone=2,
            workout_steps=_to_garmin_steps(steps),
        )

    if workout_type == "long_ride":
        block_minutes = 22 if duration >= 140 else 20
        blocks = 3
        recovery_minutes = 8
        warm_minutes = 20
        block_total = (blocks * block_minutes) + ((blocks - 1) * recovery_minutes)
        endurance_minutes = max(duration - warm_minutes - block_total - 10, 15)
        cool_minutes = max(duration - warm_minutes - block_total - endurance_minutes, 8)

        steps: list[dict[str, Any]] = [
            _step(
                step_type="warmup",
                duration_minutes=warm_minutes,
                label="Progressive warm-up",
                target="Z1 -> mid Z2",
                cue="Settle heart rate before tempo work",
            )
        ]
        for rep in range(blocks):
            steps.append(
                _step(
                    step_type="interval",
                    duration_minutes=block_minutes,
                    label=f"Tempo block {rep + 1}/{blocks}",
                    target="80-85% FTP @ 80-90 rpm",
                    cue="Race-specific pressure, smooth cadence",
                )
            )
            if rep < blocks - 1:
                steps.append(
                    _step(
                        step_type="recovery",
                        duration_minutes=recovery_minutes,
                        label="Easy spin between tempo blocks",
                        target="Z1-Z2",
                    )
                )
        steps.extend(
            [
                _step(
                    step_type="interval",
                    duration_minutes=endurance_minutes,
                    label="Aerobic endurance finish",
                    target="Mid Z2",
                    cue="Stay aero and practice fueling schedule",
                ),
                _step(
                    step_type="cooldown",
                    duration_minutes=cool_minutes,
                    label="Cool-down spin",
                    target="Z1",
                ),
            ]
        )
        return WorkoutPrescription(
            description=_render_description(
                summary="Long ride with tempo control and race fueling rehearsal.",
                steps=steps,
                cues=[
                    "Fuel 60-90g carbs/hour and 500-750ml fluids/hour.",
                    "Take in sodium based on sweat rate and weather.",
                    "Cadence target: mostly 80-90 rpm, avoid grinding.",
                ],
            ),
            target_distance_meters=None,
            target_hr_zone=2,
            workout_steps=_to_garmin_steps(steps),
        )

    if workout_type == "mobility_strength":
        cooldown_minutes = max(duration - 27, 5)
        steps = [
            _step(
                step_type="warmup",
                duration_minutes=5,
                label="Dynamic warm-up flow",
                target="Mobility prep",
                cue="Ankles, hips, thoracic spine",
            ),
            _step(
                step_type="interval",
                duration_minutes=12,
                label="Circuit A x2 rounds: squat x12, reverse lunge x10/leg, push-up x10, plank x45s",
                target="Controlled quality reps",
                cue="No grinders; stop 1-2 reps before failure",
            ),
            _step(
                step_type="interval",
                duration_minutes=10,
                label="Circuit B x2 rounds: single-leg RDL x8/leg, glute bridge x15, dead bug x10/side, side plank x30s/side",
                target="Tempo 2-0-2",
                cue="Stability and posture over load",
            ),
            _step(
                step_type="cooldown",
                duration_minutes=cooldown_minutes,
                label="Mobility cool-down + breathing reset",
                target="Downshift",
                cue="Hips, calves, and diaphragm breathing",
            ),
        ]
        return WorkoutPrescription(
            description=_render_description(
                summary="Bodyweight durability session for triathlon resilience.",
                steps=steps,
                cues=[
                    "Keep every movement crisp; this is tissue quality work.",
                    "If sore from prior sessions, reduce one round and focus mobility.",
                ],
            ),
            target_distance_meters=None,
            target_hr_zone=None,
            workout_steps=_to_garmin_steps(steps),
        )

    fallback_steps = [
        _step(
            step_type="interval",
            duration_minutes=duration,
            label="Steady aerobic session",
            target="Zone 2",
        )
    ]
    return WorkoutPrescription(
        description=_render_description(
            summary=template.description or "Steady session.",
            steps=fallback_steps,
            cues=["Keep effort controlled and consistent."],
        ),
        target_distance_meters=None,
        target_hr_zone=2 if template.discipline in {"run", "bike", "swim"} else None,
        workout_steps=_to_garmin_steps(fallback_steps),
    )


def _phase_label(days_to_race: int | None) -> str:
    if days_to_race is None:
        return "base"
    if days_to_race <= 14:
        return "taper"
    if days_to_race <= 42:
        return "peak"
    if days_to_race <= 84:
        return "build"
    return "base"


def _template_for_day(
    *,
    day: date,
    phase: str,
    week_index: int,
) -> DayTemplate | None:
    weekday = day.weekday()  # Mon=0..Sun=6

    # Keep predictable structure; agent can later modify day-by-day with approvals.
    if weekday == 0:
        return DayTemplate(
            discipline="strength",
            workout_type="mobility_strength",
            duration_min=35,
            description="Mobility + functional strength. Keep it crisp and controlled.",
        )
    if weekday == 1:
        return DayTemplate(
            discipline="bike",
            workout_type="quality_intervals",
            duration_min=70 if phase in {"build", "peak"} else 60,
            description="Bike quality set. Controlled hard work with full recoveries.",
        )
    if weekday == 2:
        return DayTemplate(
            discipline="run",
            workout_type="endurance_run",
            duration_min=55 if phase in {"build", "peak"} else 45,
            description="Aerobic endurance run. Steady effort, no racing.",
        )
    if weekday == 3:
        return DayTemplate(
            discipline="swim",
            workout_type="endurance_builder",
            duration_min=50,
            description="Swim endurance + form focus. Maintain relaxed technique under load.",
        )
    if weekday == 4:
        return DayTemplate(
            discipline="bike",
            workout_type="easy_spin",
            duration_min=50,
            description="Easy spin and leg turnover. Keep intensity low.",
        )
    if weekday == 5:
        long_run = 75 + (10 * min(week_index, 4))
        if phase == "taper":
            long_run = 55
        if phase == "peak":
            long_run = min(long_run + 10, 120)
        return DayTemplate(
            discipline="run",
            workout_type="long_run",
            duration_min=long_run,
            description="Long aerobic run. Smooth pacing and fueling practice.",
        )
    if weekday == 6:
        long_ride = 120 + (15 * min(week_index, 4))
        if phase == "taper":
            long_ride = 75
        if phase == "peak":
            long_ride = min(long_ride + 15, 210)
        return DayTemplate(
            discipline="bike",
            workout_type="long_ride",
            duration_min=long_ride,
            description="Long ride with race-day fueling and cadence discipline.",
        )
    return None


async def _upcoming_race(db: AsyncSession) -> Race | None:
    result = await db.execute(
        select(Race).where(Race.date >= date.today()).order_by(Race.date.asc()).limit(1)
    )
    return result.scalar_one_or_none()


async def _ensure_assistant_training_plan(
    db: AsyncSession,
    *,
    start: date,
    end: date,
    race: Race | None,
) -> TrainingPlan:
    result = await db.execute(
        select(TrainingPlan)
        .where(TrainingPlan.source == "assistant")
        .order_by(TrainingPlan.created_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing and existing.end_date and existing.end_date >= end:
        return existing

    now = datetime.now(timezone.utc)
    plan_name = f"Assistant Rolling Plan ({start.isoformat()})"
    new_plan = TrainingPlan(
        race_id=race.id if race else None,
        name=plan_name,
        source="assistant",
        start_date=start,
        end_date=end,
        created_at=now,
    )
    db.add(new_plan)
    await db.flush()
    return new_plan


async def _delete_existing_assistant_window(
    db: AsyncSession,
    *,
    start: date,
    exclude_dates: set[date] | None = None,
) -> int:
    if not await assistant_plan_table_available(db):
        return 0

    query = (
        select(PlannedWorkout.id)
        .join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )
        .where(
            and_(
                PlannedWorkout.date >= start,
                AssistantPlanEntry.is_locked == False,
            )
        )
    )
    if exclude_dates:
        query = query.where(PlannedWorkout.date.notin_(sorted(exclude_dates)))

    result = await db.execute(query)
    ids = [row[0] for row in result.all()]
    if not ids:
        return 0

    await db.execute(
        delete(AssistantPlanEntry).where(AssistantPlanEntry.planned_workout_id.in_(ids))
    )
    deleted = await db.execute(delete(PlannedWorkout).where(PlannedWorkout.id.in_(ids)))
    return int(deleted.rowcount or 0)


def _slot_key_for_workout(
    *,
    workout_date: date | None,
    discipline: str | None,
    workout_type: str | None,
) -> tuple[date | None, str, str]:
    return (
        workout_date,
        str(discipline or "").strip().lower(),
        str(workout_type or "").strip().lower(),
    )


async def _existing_garmin_ids_by_slot(
    db: AsyncSession,
    *,
    start: date,
) -> dict[tuple[date | None, str, str], str]:
    if not await assistant_plan_table_available(db):
        return {}

    result = await db.execute(
        select(
            PlannedWorkout.date,
            PlannedWorkout.discipline,
            PlannedWorkout.workout_type,
            AssistantPlanEntry.garmin_workout_id,
            AssistantPlanEntry.updated_at,
            PlannedWorkout.created_at,
        )
        .join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )
        .where(
            and_(
                PlannedWorkout.date >= start,
                AssistantPlanEntry.garmin_workout_id.is_not(None),
            )
        )
        .order_by(
            AssistantPlanEntry.updated_at.desc(), PlannedWorkout.created_at.desc()
        )
    )
    rows = list(result.all())
    mapping: dict[tuple[date | None, str, str], str] = {}
    for row in rows:
        (
            workout_date,
            discipline,
            workout_type,
            garmin_workout_id,
            _updated_at,
            _created_at,
        ) = row
        garmin_id = str(garmin_workout_id or "").strip()
        if not garmin_id:
            continue
        key = _slot_key_for_workout(
            workout_date=workout_date,
            discipline=discipline,
            workout_type=workout_type,
        )
        if key not in mapping:
            mapping[key] = garmin_id
    return mapping


async def _locked_dates_to_preserve(
    db: AsyncSession,
    *,
    start: date,
    end: date,
) -> set[date]:
    if end < start:
        return set()
    if not await assistant_plan_table_available(db):
        return set()

    result = await db.execute(
        select(
            PlannedWorkout.date,
            AssistantPlanEntry.garmin_workout_id,
            AssistantPlanEntry.garmin_sync_status,
        )
        .join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )
        .where(
            and_(
                PlannedWorkout.date >= start,
                PlannedWorkout.date <= end,
            )
        )
    )

    preserved: set[date] = set()
    for workout_date, garmin_workout_id, garmin_sync_status in result.all():
        if workout_date is None:
            continue
        if str(garmin_sync_status or "").strip().lower() != "success":
            continue
        if not str(garmin_workout_id or "").strip():
            continue
        preserved.add(workout_date)
    return preserved


async def _modified_dates_to_preserve(
    db: AsyncSession,
    *,
    start: date,
    end: date,
) -> set[date]:
    if end < start:
        return set()
    if not await assistant_plan_table_available(db):
        return set()

    result = await db.execute(
        select(PlannedWorkout.date)
        .join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )
        .where(
            and_(
                PlannedWorkout.date >= start,
                PlannedWorkout.date <= end,
                PlannedWorkout.status == "modified",
            )
        )
    )
    return {row[0] for row in result.all() if row[0] is not None}


async def _any_touched_dates_to_preserve(
    db: AsyncSession,
    *,
    start: date,
    end: date,
) -> set[date]:
    if end < start:
        return set()
    if not await assistant_plan_table_available(db):
        return set()

    result = await db.execute(
        select(
            PlannedWorkout.date,
            PlannedWorkout.status,
            AssistantPlanEntry.garmin_sync_status,
            AssistantPlanEntry.updated_at,
            PlannedWorkout.created_at,
        )
        .join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )
        .where(
            and_(
                PlannedWorkout.date >= start,
                PlannedWorkout.date <= end,
            )
        )
    )

    preserved: set[date] = set()
    for (
        workout_date,
        status,
        garmin_sync_status,
        entry_updated_at,
        workout_created_at,
    ) in result.all():
        if workout_date is None:
            continue
        if status is not None and status != "upcoming":
            preserved.add(workout_date)
            continue
        if garmin_sync_status is not None and garmin_sync_status not in (
            "pending",
            "skipped",
        ):
            preserved.add(workout_date)
            continue
        if entry_updated_at is not None and workout_created_at is not None:
            if entry_updated_at > workout_created_at:
                preserved.add(workout_date)
    return preserved


async def acquire_workout_lock(db: AsyncSession, workout_id) -> bool:
    if not await assistant_plan_table_available(db):
        return False
    result = await db.execute(
        select(AssistantPlanEntry).where(
            AssistantPlanEntry.planned_workout_id == workout_id
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return False
    entry.is_locked = True
    entry.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return True


async def release_workout_lock(db: AsyncSession, workout_id) -> bool:
    if not await assistant_plan_table_available(db):
        return False
    result = await db.execute(
        select(AssistantPlanEntry).where(
            AssistantPlanEntry.planned_workout_id == workout_id
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return False
    entry.is_locked = False
    entry.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return True


async def _approved_recommendation_dates_to_preserve(
    db: AsyncSession,
    *,
    start: date,
    end: date,
) -> set[date]:
    if end < start:
        return set()
    if not await _recommendation_table_available(db):
        return set()

    result = await db.execute(
        select(RecommendationChange.workout_date).where(
            and_(
                RecommendationChange.status == "approved",
                RecommendationChange.workout_date.is_not(None),
                RecommendationChange.workout_date >= start,
                RecommendationChange.workout_date <= end,
            )
        )
    )
    return {row[0] for row in result.all() if row[0] is not None}


async def generate_assistant_plan(
    db: AsyncSession,
    *,
    days_ahead: int | None = None,
    overwrite: bool = True,
    sync_to_garmin: bool = True,
) -> dict[str, Any]:
    if not is_assistant_owned_mode():
        raise ValueError("Assistant-owned plan mode is not enabled.")

    await ensure_assistant_plan_table(db)

    today = date.today()
    horizon = max(days_ahead or settings.assistant_plan_default_days_ahead, 3)
    end = today + timedelta(days=horizon - 1)
    race = await _upcoming_race(db)
    days_to_race = (race.date - today).days if race else None
    phase = _phase_label(days_to_race)
    lock_window = max(settings.assistant_plan_lock_window_days, 1)
    lock_cutoff = today + timedelta(days=lock_window - 1)
    sync_window = max(settings.assistant_plan_sync_days, 0)
    sync_cutoff = today + timedelta(days=max(sync_window - 1, 0))

    plan = await _ensure_assistant_training_plan(
        db,
        start=today,
        end=end,
        race=race,
    )

    previous_slot_workout_ids: dict[tuple[date | None, str, str], str] = {}
    preserved_locked_dates: set[date] = set()
    preserved_modified_dates: set[date] = set()
    preserved_approved_recommendation_dates: set[date] = set()
    any_touched_dates: set[date] = set()
    preserved_dates: set[date] = set()
    if overwrite and sync_to_garmin:
        previous_slot_workout_ids = await _existing_garmin_ids_by_slot(
            db,
            start=today,
        )
    if overwrite:
        preserved_locked_dates = await _locked_dates_to_preserve(
            db,
            start=today,
            end=lock_cutoff,
        )
        preserved_modified_dates = await _modified_dates_to_preserve(
            db,
            start=today,
            end=end,
        )
        preserved_approved_recommendation_dates = (
            await _approved_recommendation_dates_to_preserve(
                db,
                start=today,
                end=end,
            )
        )
        any_touched_dates = await _any_touched_dates_to_preserve(
            db,
            start=today,
            end=end,
        )
        preserved_dates = (
            preserved_locked_dates
            | preserved_modified_dates
            | preserved_approved_recommendation_dates
            | any_touched_dates
        )

    deleted_count = 0
    if overwrite:
        deleted_count = await _delete_existing_assistant_window(
            db,
            start=today,
            exclude_dates=preserved_dates,
        )

    now = datetime.now(timezone.utc)
    created_rows: list[
        tuple[PlannedWorkout, AssistantPlanEntry, WorkoutPrescription]
    ] = []
    for offset in range(horizon):
        session_day = today + timedelta(days=offset)
        if overwrite and session_day in preserved_dates:
            continue
        week_index = offset // 7
        template = _template_for_day(
            day=session_day,
            phase=phase,
            week_index=week_index,
        )
        if template is None:
            continue
        prescription = _build_workout_prescription(
            template=template,
            phase=phase,
            week_index=week_index,
        )

        workout = PlannedWorkout(
            plan_id=plan.id,
            date=session_day,
            discipline=template.discipline,
            workout_type=template.workout_type,
            target_duration=template.duration_min,
            target_distance=prescription.target_distance_meters,
            target_hr_zone=prescription.target_hr_zone,
            description=prescription.description,
            status="upcoming",
            created_at=now,
        )
        db.add(workout)
        await db.flush()

        entry = AssistantPlanEntry(
            planned_workout_id=workout.id,
            is_locked=session_day <= today + timedelta(days=lock_window - 1),
            garmin_sync_status="pending" if sync_to_garmin else "skipped",
            created_at=now,
            updated_at=now,
        )
        db.add(entry)
        created_rows.append((workout, entry, prescription))

    synced_success = 0
    synced_failed = 0
    synced_skipped = 0
    if sync_to_garmin:
        for workout, entry, prescription in created_rows:
            if workout.date and workout.date > sync_cutoff:
                entry.garmin_sync_status = "skipped_out_of_window"
                entry.updated_at = datetime.now(timezone.utc)
                synced_skipped += 1
                continue

            replace_workout_id = previous_slot_workout_ids.get(
                _slot_key_for_workout(
                    workout_date=workout.date,
                    discipline=workout.discipline,
                    workout_type=workout.workout_type,
                )
            )
            payload = fallback_writeback_payload(
                workout_date=workout.date.isoformat() if workout.date else None,
                discipline=workout.discipline,
                workout_type=workout.workout_type,
                target_duration=workout.target_duration,
                description=workout.description,
                workout_steps=prescription.workout_steps,
                replace_workout_id=replace_workout_id,
                dedupe_by_title=True,
                recommendation_text=(f"Assistant-owned plan sync ({phase})"),
            )
            result = await write_recommendation_change(payload)
            status = str(result.get("status", "failed")).lower()
            entry.garmin_sync_result = result
            entry.updated_at = datetime.now(timezone.utc)
            if status == "success":
                entry.garmin_workout_id = str(result.get("workout_id") or "")
                entry.garmin_sync_status = "success"
                synced_success += 1
            else:
                entry.garmin_sync_status = "failed"
                synced_failed += 1

    await db.flush()

    return {
        "mode": settings.plan_ownership_mode,
        "phase": phase,
        "race": (
            {
                "id": str(race.id),
                "name": race.name,
                "date": race.date.isoformat(),
                "distance_type": race.distance_type,
                "days_to_race": days_to_race,
            }
            if race
            else None
        ),
        "window_start": today.isoformat(),
        "window_end": end.isoformat(),
        "days_ahead": horizon,
        "plan_id": str(plan.id),
        "deleted_existing": deleted_count,
        "preserved_locked": len(preserved_locked_dates),
        "preserved_modified": len(preserved_modified_dates),
        "preserved_approved_recommendations": len(
            preserved_approved_recommendation_dates
        ),
        "preserved_touched": len(any_touched_dates),
        "created_workouts": len(created_rows),
        "synced_success": synced_success,
        "synced_failed": synced_failed,
        "synced_skipped": synced_skipped,
        "workouts": [
            {
                "id": str(workout.id),
                "date": workout.date.isoformat() if workout.date else None,
                "discipline": workout.discipline,
                "workout_type": workout.workout_type,
                "target_duration": workout.target_duration,
                "target_distance": workout.target_distance,
                "target_hr_zone": workout.target_hr_zone,
                "description": workout.description,
                "status": workout.status,
                "is_locked": entry.is_locked,
                "garmin_sync_status": entry.garmin_sync_status,
                "garmin_workout_id": entry.garmin_workout_id,
            }
            for workout, entry, _prescription in created_rows
        ],
    }


async def list_assistant_workout_ids_for_range(
    db: AsyncSession,
    *,
    start: date,
    end: date,
) -> list[str]:
    if not await assistant_plan_table_available(db):
        return []
    result = await db.execute(
        select(PlannedWorkout.id)
        .join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )
        .where(
            and_(
                PlannedWorkout.date >= start,
                PlannedWorkout.date <= end,
            )
        )
    )
    return [str(row[0]) for row in result.all()]
