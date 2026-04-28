# ABOUTME: Standalone script for weekly training plan review.
# ABOUTME: Runs Claude-driven plan intelligence and defaults to approval-gated recommendations.

"""Generate next week's intelligent training plan.

Usage:
    uv run python -m src.scripts.plan_generate
    uv run python -m src.scripts.plan_generate --apply
    uv run python -m src.scripts.plan_generate --apply --no-garmin
    uv run python -m src.scripts.plan_generate --apply --template-fallback
"""

import asyncio
import argparse
import logging
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("plan_generate")


async def run(*, apply: bool = False, sync_to_garmin: bool = True) -> dict:
    from src.db.connection import async_session
    from src.services.plan_intelligence import (
        run_intelligent_plan_generation,
        run_intelligent_plan_review,
    )

    async with async_session() as session:
        if not apply:
            return await run_intelligent_plan_review(session)

        result = await run_intelligent_plan_generation(
            session, sync_to_garmin=sync_to_garmin,
        )

    return result


async def run_template_fallback(sync_to_garmin: bool = True) -> dict:
    from src.db.connection import async_session
    from src.services.assistant_plan import generate_assistant_plan

    async with async_session() as session:
        result = await generate_assistant_plan(
            session,
            days_ahead=14,
            overwrite=True,
            sync_to_garmin=sync_to_garmin,
        )
        await session.commit()

    return result


def main():
    parser = argparse.ArgumentParser(description="Review weekly training plan")
    parser.add_argument(
        "--apply", action="store_true",
        help="Write the generated plan immediately. Scheduled runs should omit this.",
    )
    parser.add_argument(
        "--no-garmin", action="store_true",
        help="Skip Garmin sync when used with --apply",
    )
    parser.add_argument(
        "--template-fallback", action="store_true",
        help="Use template-based generation with --apply (skip AI)",
    )
    args = parser.parse_args()

    sync = not args.no_garmin
    start = datetime.now()
    logger.info(
        "Starting plan %s (sync_to_garmin=%s)",
        "generation" if args.apply else "review",
        sync if args.apply else False,
    )

    try:
        if args.template_fallback:
            if not args.apply:
                raise ValueError("--template-fallback requires --apply")
            logger.info("Using template fallback")
            result = asyncio.run(run_template_fallback(sync_to_garmin=sync))
        else:
            result = asyncio.run(run(apply=args.apply, sync_to_garmin=sync))
    except Exception:
        if not args.apply:
            logger.exception("Intelligent plan review failed")
            sys.exit(1)

        logger.exception("Intelligent plan generation failed, falling back to templates")
        try:
            result = asyncio.run(run_template_fallback(sync_to_garmin=sync))
        except Exception:
            logger.exception("Template fallback also failed")
            sys.exit(1)

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(
        "Plan %s in %.1fs: phase=%s, recommendations=%d, workouts=%d, garmin_synced=%d",
        "generated" if args.apply else "reviewed",
        elapsed,
        result.get("phase", "?"),
        result.get("created_recommendations", 0),
        result.get("created_workouts", 0),
        result.get("synced_success", 0),
    )
    if result.get("reasoning"):
        logger.info("Reasoning: %s", result["reasoning"][:200])


if __name__ == "__main__":
    main()
