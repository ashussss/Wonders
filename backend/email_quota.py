"""Daily email limit per account, so a big invite list goes out in batches.

Email plans cap sends per day (Brevo's free plan is 300). Without a limit a 1,800-person
touch sent 300 and the other 1,500 bounced off the cap and were lost. With
settings.email_daily_limit set, a touch emails up to what is left of today's allowance,
the rest wait, and the touch picks up again the next day at its usual time. People
who have had the fewest emails go first, so everyone on the list gets reached before
anyone gets a second one.

Days are counted in UTC, the way Brevo resets its daily quota.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


def limit_of(settings: Dict[str, Any]) -> int:
    try:
        return max(0, int(settings.get("email_daily_limit") or 0))
    except (TypeError, ValueError):
        return 0


def today(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


async def used_today(db, owner_id: str) -> int:
    row = await db.email_quota.find_one({"owner_id": owner_id, "day": today()}, {"_id": 0})
    return int((row or {}).get("count") or 0)


async def remaining(db, owner_id: str, settings: Dict[str, Any]) -> Optional[int]:
    """Emails this account can still send today; None means no limit is set."""
    lim = limit_of(settings)
    if not lim:
        return None
    return max(0, lim - await used_today(db, owner_id))


async def use(db, owner_id: str, settings: Dict[str, Any], n: int = 1) -> None:
    """Count sends only for accounts that set a limit."""
    if owner_id and n and limit_of(settings):
        await db.email_quota.update_one({"owner_id": owner_id, "day": today()},
                                        {"$inc": {"count": n}}, upsert=True)


def resume_at(scheduled_at: Optional[str], now: Optional[datetime] = None) -> str:
    """Next day (after today's quota resets) at the touch's own time of day."""
    now = now or datetime.now(timezone.utc)
    try:
        at = datetime.fromisoformat((scheduled_at or "").replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        at = now
    nxt = (now + timedelta(days=1)).replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return max(nxt, midnight).isoformat()
