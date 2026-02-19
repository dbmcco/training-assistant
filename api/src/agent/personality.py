"""Coach personality and system prompt builder for the training assistant.

Informed by Matt Wilpers' methodology: periodization, power zones, recovery
as training, and sport-specificity for triathlon race demands.
"""

from datetime import date, timedelta
from typing import Any


COACH_SYSTEM_PROMPT = """You are Coach — a personal triathlon training coach informed by Matt Wilpers' methodology.

## Your Principles

- **Train Hard, Train Smart, Have Fun** — quality and consistency over heroic volume.
- **Power zone training**: 7 zones based on FTP. Every workout has a purpose tied to a zone.
- **Periodization**: base → build → peak → taper, driven by A-race date.
- **Recovery is training** — respect HRV, body battery, sleep signals. Never push through bad recovery data without clear explanation.
- **Sport-specificity**: training distribution should match race demands (70.3: ~25% swim, 40% bike, 30% run by time).
- **Test, don't guess** — prompt threshold retests when zones go stale (>8 weeks).
- **The athlete has a life** — fit training around it, not the other way around.
- **Flag grey zone sessions** — not easy enough to recover, not hard enough to adapt.

## Your Personality

- **Data-driven but human.** Always reference the athlete's numbers, but frame them in terms of how they feel and what the numbers mean for their goals.
- **Structured and methodical.** Think in periodization, progressive overload, and training phases. Every recommendation connects to the bigger picture.
- **Encouraging without cheerleading.** "That's solid work" not "AMAZING JOB!!!" Acknowledge effort without being performative.
- **Direct when it matters.** If they should rest, say so clearly. "Take the day off. Your body needs it."
- **Teacher mentality.** Explain the *why* behind recommendations. You want them to understand training principles.

## Communication Style

- Lead with the recommendation, follow with reasoning.
- Reference specific metrics: "Your acute/chronic ratio is at 1.3 — that's overreach territory" not "you've been training hard."
- Frame rest as productive: "Recovery is where the adaptation happens."
- Connect today's workout to the race goal: "This tempo builds your half marathon pace floor."
- Keep responses concise. No walls of text. Get to the point.
- Never use excessive exclamation marks or hype language.
- Never guilt trip about missed workouts — ever.
- Never give medical advice — defer to a doctor for injuries or pain.
- Never use generic motivational quotes.

## Tools

You have tools to query the athlete's training data, recovery state, fitness trends, discipline distribution, and planned workouts. Use them to ground your advice in real data.

You can suggest workout modifications. Always propose changes and get confirmation before applying.

## Reasoning Checklist (use on every substantive interaction)

1. Where are we in the season? (weeks to A-race → current phase)
2. Is training volume appropriate for the phase?
3. Is discipline distribution matching race demands?
4. Is intensity distribution right for the phase?
5. Is fitness improving? (FTP, VO2, race predictions)
6. Is recovery sufficient? (HRV, sleep, body battery, load ratio)
7. What should we do next? (plan + recovery + missed sessions)
8. Are zones current? (time since last threshold test)

{athlete_context}

{athlete_profile}

{view_context}

Today is {today}. {race_context}
"""


def determine_phase(race_date: date) -> str:
    """Determine training periodization phase based on weeks to race."""
    days_out = (race_date - date.today()).days
    weeks_out = days_out / 7

    if days_out <= 7:
        return "race_week"
    elif weeks_out <= 2:
        return "taper"
    elif weeks_out <= 6:
        return "peak"
    elif weeks_out <= 12:
        return "build"
    else:
        return "base"


def compute_load_ratio(
    acute: float | None, chronic: float | None
) -> float | None:
    """Compute acute:chronic training load ratio."""
    if acute is None or chronic is None or chronic == 0:
        return None
    return round(acute / chronic, 2)


def assess_discipline_balance(
    distribution: dict[str, dict[str, float]],
    race_type: str = "70.3",
) -> dict[str, Any]:
    """Assess discipline balance vs target for race type."""
    targets = {
        "70.3": {"swim": 25, "bike": 40, "run": 30},
        "140.6": {"swim": 20, "bike": 45, "run": 30},
        "marathon": {"swim": 0, "bike": 10, "run": 85},
        "half_marathon": {"swim": 0, "bike": 10, "run": 85},
        "olympic": {"swim": 25, "bike": 35, "run": 35},
    }
    target = targets.get(race_type, targets["70.3"])

    undertrained = []
    overtrained = []
    for disc, target_pct in target.items():
        actual_pct = distribution.get(disc, {}).get("pct", 0)
        if target_pct > 0 and actual_pct < target_pct * 0.6:
            undertrained.append(disc)
        elif actual_pct > target_pct * 1.5 and target_pct > 0:
            overtrained.append(disc)

    return {
        "target": target,
        "actual": {d: distribution.get(d, {}).get("pct", 0) for d in target},
        "undertrained": undertrained,
        "overtrained": overtrained,
    }


def build_athlete_context_string(
    *,
    a_race: dict | None = None,
    phase: str | None = None,
    load_ratio: float | None = None,
    acute_load: float | None = None,
    chronic_load: float | None = None,
    discipline_balance: dict | None = None,
    recovery: dict | None = None,
    biometrics: dict | None = None,
    alerts: list[dict] | None = None,
) -> str:
    """Build structured athlete context string for system prompt injection."""
    lines = ["## Athlete Context (auto-generated from data)"]

    if a_race:
        race_date = a_race.get("date")
        if race_date:
            days_out = (race_date - date.today()).days
            lines.append(
                f"- **{days_out} days** to A-race: "
                f"{a_race.get('name', 'Unknown')} ({a_race.get('distance_type', '')})"
            )

    if phase:
        lines.append(f"- Current phase: **{phase.upper()}**")

    if load_ratio is not None:
        acute_str = f"{acute_load:.0f}" if acute_load else "?"
        chronic_str = f"{chronic_load:.0f}" if chronic_load else "?"
        warning = ""
        if load_ratio > 1.3:
            warning = " ⚠ OVERREACH"
        elif load_ratio < 0.8:
            warning = " (detraining risk)"
        lines.append(
            f"- Load ratio: **{load_ratio}** "
            f"(acute {acute_str} / chronic {chronic_str}){warning}"
        )

    if discipline_balance:
        actual = discipline_balance.get("actual", {})
        if actual:
            parts = [f"{d}: {actual.get(d, 0):.0f}%" for d in ["swim", "bike", "run"]]
            lines.append(f"- Discipline split (28d): {' / '.join(parts)}")
        if discipline_balance.get("undertrained"):
            lines.append(
                f"- **UNDERTRAINED**: {', '.join(discipline_balance['undertrained'])}"
            )

    rec = recovery or {}
    if rec.get("hrv_7d_avg"):
        lines.append(
            f"- HRV 7d avg: {rec['hrv_7d_avg']}ms "
            f"(last night: {rec.get('hrv_last_night', '?')}ms, "
            f"status: {rec.get('hrv_status', '?')})"
        )
    if rec.get("body_battery_at_wake") is not None:
        lines.append(f"- Body battery at wake: {rec['body_battery_at_wake']}")
    if rec.get("sleep_score") is not None:
        lines.append(f"- Sleep score: {rec['sleep_score']}")
    if rec.get("training_readiness_score") is not None:
        lines.append(f"- Training readiness: {rec['training_readiness_score']}")

    bio = biometrics or {}
    if bio.get("cycling_ftp"):
        lines.append(f"- FTP: {bio['cycling_ftp']}W (tested {bio.get('date', '?')})")
    if bio.get("lactate_threshold_hr"):
        lines.append(f"- Lactate threshold HR: {bio['lactate_threshold_hr']} bpm")
    if bio.get("weight_kg"):
        lines.append(f"- Weight: {bio['weight_kg']} kg")

    if alerts:
        lines.append(f"- **ACTIVE ALERTS ({len(alerts)}):**")
        for a in alerts[:5]:
            lines.append(f"  - [{a.get('severity', '?')}] {a.get('title', '?')}")

    if len(lines) <= 1:
        return ""

    return "\n".join(lines)


def build_system_prompt(
    athlete_profile: dict | None = None,
    view_context: dict | None = None,
    races: list[dict] | None = None,
    athlete_context: str = "",
) -> str:
    """Build the full system prompt with injected context.

    Args:
        athlete_profile: Dict with 'notes' key containing learned athlete info.
        view_context: Dict with 'current_view' and 'visible_data' from the frontend.
        races: List of dicts with 'name', 'date' (date object), 'distance_type'.
        athlete_context: Pre-built athlete context string from build_athlete_context_string.
    """
    profile_text = ""
    if athlete_profile:
        notes = athlete_profile.get("notes", {})
        if notes:
            profile_text = "## What You Know About This Athlete\n\n"
            for key, val in notes.items():
                profile_text += f"- **{key}:** {val}\n"

    view_text = ""
    if view_context:
        current_view = view_context.get("current_view", "dashboard")
        visible_data = view_context.get("visible_data", {})
        view_text = (
            f"## Current View Context\n\n"
            f"The athlete is viewing the **{current_view}** screen. "
            f"They can see: {visible_data}. "
            f"Assume questions refer to what's on screen unless they specify otherwise."
        )

    race_text = ""
    if races:
        race_lines = []
        today = date.today()
        for r in races:
            race_date = r["date"]
            weeks = (race_date - today).days // 7
            race_lines.append(
                f"- {r['name']} ({r['distance_type']}): {weeks} weeks out on {race_date}"
            )
        race_text = "Upcoming races:\n" + "\n".join(race_lines)

    return COACH_SYSTEM_PROMPT.format(
        athlete_context=athlete_context,
        athlete_profile=profile_text,
        view_context=view_text,
        today=date.today().isoformat(),
        race_context=race_text,
    )
