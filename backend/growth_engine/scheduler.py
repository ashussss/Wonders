"""Scheduler jobs for the Growth Engine.

Two independent jobs, both registered on the EXISTING app scheduler (database.scheduler)
with unique ids. Neither touches the existing touch-tick / blog-publish-due /
social-daily / pseo-daily jobs.

    growth-daily    02:00 IST — build the day's 9 campaigns (drafts only)
    growth-dispatch every 5 min — publish approved campaigns that are due

Safety: with the default GROWTH_APPROVAL_MODE=true the dispatch job is a no-op.
Nothing reaches a platform without an explicit approval first.
"""

import logging

from database import db, scheduler

from . import APPROVAL_MODE, GROWTH_ENABLED, GROWTH_PLATFORMS, IST
from . import queue

logger = logging.getLogger("showup.growth.scheduler")

DAILY_HOUR = 2          # 02:00 IST — drafts for the coming day are ready before the workday


async def run_daily() -> dict:
    """Build today's campaigns. Drafts only — always lands in pending_review."""
    if not GROWTH_ENABLED:
        return {"ok": True, "skipped": "growth_disabled"}
    try:
        res = await queue.generate_day(db)
        logger.info(f"growth daily: {res.get('count', 0)} campaign(s) queued for {res.get('day')}")
        return res
    except Exception as e:                                        # noqa: BLE001
        logger.error(f"growth daily failed: {e}")
        return {"ok": False, "error": str(e)[:300]}


async def run_dispatch() -> dict:
    """Publish approved, due campaigns. No-op in approval mode."""
    try:
        res = await queue.dispatch_due(db)
        if res.get("published"):
            logger.info(f"growth dispatch published {res['published']} campaign(s)")
        return res
    except Exception as e:                                        # noqa: BLE001
        logger.error(f"growth dispatch failed: {e}")
        return {"ok": False, "error": str(e)[:300]}


async def run_prospect_refresh() -> dict:
    """Rescore prospects (scores drift as new activity arrives)."""
    from . import prospect_engine

    try:
        return await prospect_engine.score_all(db)
    except Exception as e:                                        # noqa: BLE001
        logger.error(f"growth prospect refresh failed: {e}")
        return {"ok": False, "error": str(e)[:300]}


def register() -> None:
    """Register the Growth Engine jobs. Called once from server.py lifespan."""
    scheduler.add_job(run_daily, "cron", hour=DAILY_HOUR, minute=0, id="growth-daily",
                      replace_existing=True, misfire_grace_time=6 * 3600, coalesce=True)
    scheduler.add_job(run_dispatch, "interval", minutes=5, id="growth-dispatch",
                      replace_existing=True, coalesce=True)
    # Scoring is cheap; twice a day is plenty for a list that changes slowly.
    scheduler.add_job(run_prospect_refresh, "cron", hour=3, minute=15, id="growth-prospect-refresh",
                      replace_existing=True, misfire_grace_time=3 * 3600, coalesce=True)
    logger.info(f"Growth Engine jobs registered (approval_mode={APPROVAL_MODE}, "
                f"platforms={','.join(GROWTH_PLATFORMS)})")


__all__ = ["run_daily", "run_dispatch", "run_prospect_refresh", "register", "DAILY_HOUR"]