from src.config import Settings
from src.model_routes import TRAINING_ASSISTANT_COACH_ROUTE, default_coach_model, model_for_route


def test_training_assistant_coach_route_preserves_previous_default_model():
    assert TRAINING_ASSISTANT_COACH_ROUTE == "training_assistant.coach"
    assert model_for_route(TRAINING_ASSISTANT_COACH_ROUTE) == "claude-sonnet-4-6"
    assert default_coach_model() == "claude-sonnet-4-6"


def test_settings_coach_model_default_resolves_from_registry():
    settings = Settings(_env_file=None)

    assert settings.coach_model == default_coach_model()


def test_settings_coach_model_override_still_wins():
    settings = Settings(coach_model="custom-coach-model")

    assert settings.coach_model == "custom-coach-model"

