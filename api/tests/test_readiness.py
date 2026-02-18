import pytest

from src.services.readiness import ReadinessScore, compute_readiness


def test_readiness_all_good():
    score = compute_readiness(
        hrv_last_night=50,
        hrv_7d_avg=48,
        sleep_score=85,
        body_battery_wake=75,
        recovery_time_hours=0,
        training_load_7d=500,
        training_load_28d=450,
    )
    assert isinstance(score, ReadinessScore)
    assert 70 <= score.score <= 100
    assert score.label == "High"
    assert len(score.components) == 5


def test_readiness_overtrained():
    score = compute_readiness(
        hrv_last_night=30,
        hrv_7d_avg=48,
        sleep_score=45,
        body_battery_wake=25,
        recovery_time_hours=48,
        training_load_7d=800,
        training_load_28d=400,
    )
    assert score.score < 50
    assert score.label == "Low"


def test_readiness_moderate():
    score = compute_readiness(
        hrv_last_night=35,
        hrv_7d_avg=48,
        sleep_score=55,
        body_battery_wake=45,
        recovery_time_hours=24,
        training_load_7d=600,
        training_load_28d=450,
    )
    assert 45 <= score.score < 70
    assert score.label == "Moderate"


def test_readiness_missing_data_graceful():
    score = compute_readiness(
        hrv_last_night=None,
        hrv_7d_avg=None,
        sleep_score=70,
        body_battery_wake=60,
        recovery_time_hours=None,
        training_load_7d=None,
        training_load_28d=None,
    )
    assert score.score > 0
    assert len(score.components) == 2  # only sleep + body_battery available


def test_readiness_all_none():
    score = compute_readiness(
        hrv_last_night=None,
        hrv_7d_avg=None,
        sleep_score=None,
        body_battery_wake=None,
        recovery_time_hours=None,
        training_load_7d=None,
        training_load_28d=None,
    )
    assert score.score == 50  # fallback
    assert score.label == "Moderate"
    assert len(score.components) == 0


def test_readiness_components_have_required_fields():
    score = compute_readiness(
        hrv_last_night=50,
        hrv_7d_avg=48,
        sleep_score=80,
        body_battery_wake=70,
        recovery_time_hours=6,
        training_load_7d=500,
        training_load_28d=480,
    )
    for c in score.components:
        assert hasattr(c, "name")
        assert hasattr(c, "value")
        assert hasattr(c, "normalized")
        assert hasattr(c, "weight")
        assert hasattr(c, "detail")
        assert 0 <= c.normalized <= 100
