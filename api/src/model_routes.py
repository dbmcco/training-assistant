"""Shared model route resolution for training assistant runtime calls."""
from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path

TRAINING_ASSISTANT_COACH_ROUTE = "training_assistant.coach"
_REGISTRY_ENV_VAR = "PAIA_MODEL_ROUTE_REGISTRY_PATH"


class ModelRouteError(RuntimeError):
    """Raised when the central model route registry cannot be resolved."""


def model_for_route(route_id: str) -> str:
    """Return the concrete model selected by the central route registry."""
    route = _load_routes().get(route_id.strip().lower())
    if route is None:
        raise ModelRouteError(f"Unknown model route: {route_id!r}")
    model = str(route.get("model", "")).strip()
    if not model:
        raise ModelRouteError(f"Model route {route_id!r} does not define a model")
    return model


def default_coach_model() -> str:
    """Return the default coaching model from the central registry."""
    return model_for_route(TRAINING_ASSISTANT_COACH_ROUTE)


@lru_cache(maxsize=1)
def _load_routes() -> dict[str, dict[str, object]]:
    path = _resolve_registry_path()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ModelRouteError(f"Failed to parse model route registry {path}: {exc}") from exc

    raw_routes = raw.get("model_routes")
    if not isinstance(raw_routes, dict):
        raise ModelRouteError(f"Registry {path} does not define model_routes")
    return {str(route_id).strip().lower(): route for route_id, route in raw_routes.items()}


def _resolve_registry_path() -> Path:
    configured = os.environ.get(_REGISTRY_ENV_VAR, "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return candidate
        raise ModelRouteError(
            f"{_REGISTRY_ENV_VAR}={configured!r} does not point at a readable file"
        )

    experiments_root = Path(__file__).resolve().parents[3]
    candidates = (
        Path.cwd() / "../../paia-agent-runtime/config/cognition-presets.toml",
        experiments_root / "paia-agent-runtime/config/cognition-presets.toml",
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved

    raise ModelRouteError(
        "Unable to locate the Paia model route registry "
        f"(set {_REGISTRY_ENV_VAR} or keep paia-agent-runtime beside training-assistant)"
    )
