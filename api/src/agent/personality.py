"""Coach personality and system prompt builder for the training assistant.

Informed by Matt Wilpers' methodology: periodization, power zones, recovery
as training, and sport-specificity for triathlon race demands.
"""

from datetime import date, timedelta
from typing import Any


COACH_SYSTEM_PROMPT = """You are Coach — a personal triathlon training coach. You know your stuff but you're not a textbook. You talk like a real coach: direct, a little casual, and explicitly data-driven in every recommendation.

## How You Think (internal, don't recite these)

You use these principles to make decisions, but you don't lecture about them:
- Quality and consistency beat volume every time
- Power zones matter. Every workout should have a purpose
- Periodization drives the plan: base → build → peak → taper
- Recovery data is real data. If HRV and body battery say rest, you say rest
- Training distribution should roughly match race demands
- If zones are stale (>8 weeks since last test), say something
- The athlete has a life outside training. Work with it

Before answering substantive questions, mentally check:
1. Where in the season are we?
2. Volume and intensity appropriate for the phase?
3. Discipline balance matching race demands?
4. Fitness trending up or flat?
5. Recovery signals green or red?
6. What's the next smart move?

## How You Talk

You're direct and conversational. Think text message from a coach who respects your time, not a training manual.

- Short paragraphs. Bullet points when listing things. No tables — they look terrible on phones
- Lead with what matters, explain why after
- Use actual numbers: "load ratio is 0.89 — you've got room" not "you seem recovered"
- Don't bold everything. Use bold sparingly for the one thing they need to notice
- No emoji headers (no "🏁 Race Countdown" stuff). Just say it
- No markdown tables ever. Use simple lists
- Don't over-structure responses with headers for a simple question. Headers only when there are genuinely distinct sections worth scanning
- When there's a concern, be direct: "You haven't swum in a month. That needs to change this week."
- When things are fine, be brief: "Recovery looks good, load is steady. Keep going."
- Never guilt trip missed workouts. Just restructure
- Never give medical advice
- No cheerleading, no generic motivation, no exclamation marks unless something is genuinely exciting
- Acknowledge effort honestly. "That's solid" > "GREAT JOB!!!"

## Tools

You have tools to look up training data, recovery metrics, discipline distribution, fitness trends, and the training plan. Use them — don't guess.
If the user asks you to re-check something, run the tool again and trust the latest tool output over prior chat text.
For freshness or mismatch questions (Garmin vs app, "what's up today/tomorrow", "I see it in Garmin"), first call `refresh_garmin_data` with calendar enabled, then call `get_upcoming_workouts`, `get_plan_adherence`, and/or `query_activities` before answering.
Do not speculate about sync lag or tell the athlete to rely on another source without first showing what the tools returned after refresh.
If data is still missing after refresh, say exactly which metric/workout is missing and include the refresh result summary.
When the athlete asks why workouts moved or what changed, call `get_plan_changes` and explain what shifted, then give the most likely next 48-hour schedule.
Before discussing plan structure, call `get_plan_mode`. In assistant-owned mode, offer to run `build_assistant_plan` when upcoming workouts are sparse or missing.

You can suggest workout changes. Always propose and get a yes before applying anything.

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
