# ABOUTME: Tests for intelligent weekly plan generation service.
# ABOUTME: Covers context gathering, prompt building, plan parsing, and DB write path.

import json
import pytest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from src.db.connection import async_session


@pytest.mark.asyncio
async def test_gather_planning_context_returns_required_keys():
    """Context package should contain all fields the planning prompt needs."""
    from src.services.plan_intelligence import gather_planning_context

    async with async_session() as session:
        ctx = await gather_planning_context(session)

    required = [
        "today",
        "races",
        "phase",
        "recent_activities",
        "adherence",
        "recovery_trend",
        "load",
        "discipline_balance",
        "biometrics",
        "planning_window_start",
        "planning_window_end",
    ]
    for key in required:
        assert key in ctx, f"Missing key: {key}"


@pytest.mark.asyncio
async def test_gather_planning_context_types():
    """Verify context value types are prompt-ready."""
    from src.services.plan_intelligence import gather_planning_context

    async with async_session() as session:
        ctx = await gather_planning_context(session)

    assert isinstance(ctx["today"], str)
    assert isinstance(ctx["races"], list)
    assert isinstance(ctx["phase"], str)
    assert isinstance(ctx["recent_activities"], list)
    assert isinstance(ctx["adherence"], dict)
    assert isinstance(ctx["recovery_trend"], list)
    assert isinstance(ctx["load"], dict)
    assert isinstance(ctx["discipline_balance"], dict)


def test_build_planning_prompt_includes_context():
    """Planning prompt should embed the context data."""
    from src.services.plan_intelligence import build_planning_prompt

    ctx = {
        "today": "2026-03-19",
        "races": [{"name": "Test 70.3", "date": "2026-06-07", "distance_type": "70.3", "weeks_out": 11}],
        "phase": "build",
        "recent_activities": [
            {"date": "2026-03-18", "discipline": "run", "type": "endurance_run", "duration_min": 55, "distance_km": 9.3, "avg_hr": 145, "training_effect": 3.5}
        ],
        "adherence": {"completed": 5, "planned": 6, "rate_pct": 83.3, "missed": 1},
        "recovery_trend": [
            {"date": "2026-03-18", "readiness": 72, "sleep": 80, "body_battery_wake": 85, "hrv_7d": 45}
        ],
        "load": {"acute": 520, "chronic": 480, "acwr": 1.08, "band": "balanced"},
        "discipline_balance": {"run": 45, "bike": 35, "swim": 15, "other": 5},
        "biometrics": {"ftp": 210, "lthr": 165, "weight_kg": 82.5},
        "planning_window_start": "2026-03-23",
        "planning_window_end": "2026-03-29",
    }

    system, user = build_planning_prompt(ctx)

    assert "Matt Wilpers" in system or "Wilpers" in system or "Coach" in system
    assert "build" in user.lower()
    assert "Test 70.3" in user
    assert "endurance_run" in user
    assert "Monday 2026-03-23 through Sunday 2026-03-29" in user
    assert "Monday=2026-03-23" in user


def test_parse_plan_response_valid_json():
    """Should parse a well-formed plan JSON response."""
    from src.services.plan_intelligence import parse_plan_response

    raw = json.dumps({
        "reasoning": "Recovery is strong, push this week.",
        "workouts": [
            {
                "day": "monday",
                "discipline": "strength",
                "workout_type": "mobility_strength",
                "duration_minutes": 35,
                "summary": "Durability session",
                "session_plan": [
                    {"label": "Dynamic warm-up", "target": "Mobility prep", "cue": "Ankles, hips"}
                ],
                "coaching_cues": ["Keep it crisp"],
            }
        ],
    })

    result = parse_plan_response(raw)

    assert result["reasoning"] is not None
    assert len(result["workouts"]) == 1
    assert result["workouts"][0]["discipline"] == "strength"


def test_parse_plan_response_extracts_json_from_markdown():
    """Should handle Claude wrapping JSON in markdown code fences."""
    from src.services.plan_intelligence import parse_plan_response

    raw = '```json\n{"reasoning": "test", "workouts": []}\n```'
    result = parse_plan_response(raw)
    assert result["reasoning"] == "test"


def test_parse_plan_response_rejects_garbage():
    """Should return None for unparseable responses."""
    from src.services.plan_intelligence import parse_plan_response

    result = parse_plan_response("This is not JSON at all")
    assert result is None


def test_render_workout_description():
    """Should produce the Session Plan format the dashboard step cards parse."""
    from src.services.plan_intelligence import render_workout_description

    workout = {
        "summary": "Aerobic endurance run.",
        "session_plan": [
            {"label": "1.0 mi warm-up jog", "target": "9:00-9:30/mi", "cue": "Relax shoulders"},
            {"label": "4.0 mi steady run", "target": "7:50-8:20/mi", "cue": None},
        ],
        "coaching_cues": ["Stay in zone 2.", "Finish feeling fresh."],
    }

    desc = render_workout_description(workout)

    assert "Aerobic endurance run." in desc
    assert "Session Plan:" in desc
    assert "1. 1.0 mi warm-up jog @ 9:00-9:30/mi (Relax shoulders)" in desc
    assert "2. 4.0 mi steady run @ 7:50-8:20/mi" in desc
    assert "Coaching Cues:" in desc
    assert "- Stay in zone 2." in desc


def test_proposal_from_model_workout_maps_day_date_and_steps():
    from src.services.plan_intelligence import _proposal_from_model_workout

    proposal = _proposal_from_model_workout(
        date(2026, 5, 4),
        {
            "day": "wednesday",
            "discipline": "run",
            "workout_type": "endurance_run",
            "duration_minutes": 45,
            "summary": "Easy aerobic run.",
            "session_plan": [
                {"label": "Warm up", "target": "Z1", "cue": "Relax"},
                {"label": "Steady run", "target": "Z2", "cue": None},
            ],
            "coaching_cues": ["Keep it controlled."],
        },
    )

    assert proposal["workout_date"] == "2026-05-06"
    assert proposal["discipline"] == "run"
    assert proposal["target_duration"] == 45
    assert len(proposal["workout_steps"]) == 2
    assert proposal["workout_steps"][0]["duration_minutes"] == 22
    assert "Session Plan:" in proposal["description"]


@pytest.mark.asyncio
async def test_create_plan_review_intents_creates_pending_recommendations_without_writes():
    from src.services.plan_intelligence import create_plan_review_intents

    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)
    created_ids = [uuid4()]

    async def fake_create_intent(*args, **kwargs):
        assert kwargs["source"] == "proactive_plan"
        assert kwargs["proposed_workout"]["workout_date"] == "2026-05-04"
        return SimpleNamespace(id=created_ids[0])

    plan = {
        "reasoning": "Race added, keep the following week recovery-oriented.",
        "workouts": [
            {
                "day": "monday",
                "discipline": "swim",
                "workout_type": "recovery_swim",
                "duration_minutes": 35,
                "summary": "Recovery swim.",
                "session_plan": [{"label": "Easy swim", "target": "RPE 2"}],
            }
        ],
    }
    ctx = {
        "phase": "race_week",
        "planning_window_start": "2026-05-04",
        "planning_window_end": "2026-05-10",
    }

    with patch(
        "src.services.plan_intelligence.create_coach_recommendation_intent",
        AsyncMock(side_effect=fake_create_intent),
    ) as create_mock:
        result = await create_plan_review_intents(db, plan, ctx=ctx)

    create_mock.assert_awaited_once()
    assert result["created_recommendations"] == 1
    assert result["created_recommendation_ids"] == [str(created_ids[0])]
    assert result["created_workouts"] == 0
    assert result["synced_success"] == 0
