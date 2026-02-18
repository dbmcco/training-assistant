import pytest
from datetime import date, timedelta

from src.agent.personality import build_system_prompt


def test_build_system_prompt_minimal():
    prompt = build_system_prompt()
    assert "Coach" in prompt
    assert date.today().isoformat() in prompt


def test_build_system_prompt_with_athlete_profile():
    profile = {"notes": {"injury": "Left knee — avoid back-to-back run days", "preference": "Morning workouts"}}
    prompt = build_system_prompt(athlete_profile=profile)
    assert "Left knee" in prompt
    assert "Morning workouts" in prompt


def test_build_system_prompt_with_view_context():
    ctx = {"current_view": "plan", "visible_data": {"week": "2026-02-17", "planned_hours": 10.5}}
    prompt = build_system_prompt(view_context=ctx)
    assert "plan" in prompt
    assert "10.5" in prompt


def test_build_system_prompt_with_races():
    future = date.today() + timedelta(weeks=20)
    races = [{"name": "Half Iron Man", "date": future, "distance_type": "half_iron"}]
    prompt = build_system_prompt(races=races)
    assert "Half Iron Man" in prompt
    assert "20 weeks" in prompt or "19 weeks" in prompt  # allow for day rounding


def test_prompt_contains_personality_traits():
    prompt = build_system_prompt()
    assert "data-driven" in prompt.lower() or "Data-driven" in prompt
    assert "cheerleading" in prompt
    assert "guilt trip" in prompt
