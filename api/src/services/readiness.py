"""Readiness scoring service.

Computes a composite readiness score (0-100) from physiological metrics.
Weights are redistributed when data is missing so the score is always meaningful.
"""

from dataclasses import dataclass


@dataclass
class ReadinessComponent:
    name: str
    value: float | None
    normalized: float  # 0-100
    weight: float
    detail: str


@dataclass
class ReadinessScore:
    score: int  # 0-100
    label: str  # High, Moderate, Low
    components: list[ReadinessComponent]


def compute_readiness(
    hrv_last_night: int | None,
    hrv_7d_avg: int | None,
    sleep_score: int | None,
    body_battery_wake: int | None,
    recovery_time_hours: float | None,
    training_load_7d: float | None,
    training_load_28d: float | None,
) -> ReadinessScore:
    """Compute composite readiness from available metrics.

    Components and default weights:
        HRV (0.25): last night vs 7-day average ratio
        Sleep (0.20): raw sleep score
        Body battery (0.20): wake value
        Recovery time (0.15): 0h = fully recovered, 48h+ = depleted
        Load balance (0.20): acute/chronic ratio, ideal 0.8-1.2
    """
    components: list[ReadinessComponent] = []
    total_weight = 0.0

    # HRV component (25%)
    if hrv_last_night is not None and hrv_7d_avg is not None and hrv_7d_avg > 0:
        ratio = hrv_last_night / hrv_7d_avg
        hrv_norm = min(100.0, max(0.0, ratio * 100.0))
        components.append(
            ReadinessComponent(
                "hrv",
                hrv_last_night,
                hrv_norm,
                0.25,
                f"{hrv_last_night}ms vs {hrv_7d_avg}ms avg",
            )
        )
        total_weight += 0.25

    # Sleep component (20%)
    if sleep_score is not None:
        components.append(
            ReadinessComponent(
                "sleep",
                sleep_score,
                min(100.0, max(0.0, float(sleep_score))),
                0.20,
                f"Sleep score: {sleep_score}",
            )
        )
        total_weight += 0.20

    # Body battery component (20%)
    if body_battery_wake is not None:
        components.append(
            ReadinessComponent(
                "body_battery",
                body_battery_wake,
                min(100.0, max(0.0, float(body_battery_wake))),
                0.20,
                f"Woke at {body_battery_wake}",
            )
        )
        total_weight += 0.20

    # Recovery time component (15%) — 0 hours = 100, 48+ hours = 0
    if recovery_time_hours is not None:
        rec_norm = max(0.0, 100.0 - (recovery_time_hours / 48.0 * 100.0))
        rec_hours_text = (
            f"{int(recovery_time_hours)}"
            if float(recovery_time_hours).is_integer()
            else f"{recovery_time_hours:.1f}"
        )
        components.append(
            ReadinessComponent(
                "recovery",
                recovery_time_hours,
                rec_norm,
                0.15,
                f"{rec_hours_text}h recovery needed",
            )
        )
        total_weight += 0.15

    # Load balance component (20%) — acute:chronic ratio
    if (
        training_load_7d is not None
        and training_load_28d is not None
        and training_load_28d > 0
    ):
        acr = training_load_7d / training_load_28d
        if 0.8 <= acr <= 1.2:
            load_norm = 100.0
        elif acr > 1.2:
            load_norm = max(0.0, 100.0 - ((acr - 1.2) / 0.3 * 100.0))
        else:
            load_norm = max(0.0, 50.0 + (acr / 0.8 * 50.0))
        components.append(
            ReadinessComponent(
                "load_balance",
                round(acr, 2),
                load_norm,
                0.20,
                f"Acute/chronic ratio: {acr:.2f}",
            )
        )
        total_weight += 0.20

    # Compute weighted score
    if total_weight == 0:
        return ReadinessScore(50, "Moderate", [])

    weighted_sum = sum(c.normalized * (c.weight / total_weight) for c in components)
    final_score = int(round(weighted_sum))

    if final_score >= 70:
        label = "High"
    elif final_score >= 45:
        label = "Moderate"
    else:
        label = "Low"

    return ReadinessScore(score=final_score, label=label, components=components)
