"""Analytics — performance tracking so the engine can learn what works.

Records per-campaign/per-platform metrics and aggregates them along the five
dimensions the engine wants to learn:

    topic      (blog slug / news id / campaign angle keywords)
    hook       (the first line)
    visual     (format: carousel / infographic / stat_card / ...)
    cta        (the call to action)
    platform   (linkedin / facebook / instagram)

Everything lives in ``growth_metrics`` + ``growth_learning`` (both new
collections). Nothing reads or writes social_posts analytics.

Metric sources are pluggable: manual entry via the API, or (future) official
platform insights APIs. There is no scraping and no browser automation.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import COLLECTIONS

logger = logging.getLogger("showup.growth.analytics")

# Metrics we understand, and how "better" is measured for each.
METRICS = {
    "impressions": True,
    "reach": True,
    "engagements": True,
    "likes": True,
    "comments": True,
    "shares": True,
    "reactions": True,
    "clicks": True,
    "ctr": True,
    "followers_gained": True,
    "leads": True,
    "registrations": True,
}

# Channels a metric payload may be keyed by (validated separately from METRICS).
PLATFORM_NAMES = {"linkedin", "facebook", "instagram"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def campaign_dims(doc: Dict[str, Any]) -> Dict[str, str]:
    """The learnable dimensions of a campaign, derived from the stored draft."""
    strategy = doc.get("strategy") or {}
    visual = doc.get("visual") or {}
    keywords = strategy.get("keywords") or []
    topic = (doc.get("source_slug") or "")
    if not topic and keywords:
        topic = str(keywords[0])
    return {
        "kind": doc.get("kind") or "",
        "topic": topic,
        "topic_label": (doc.get("source_title") or doc.get("source_slug") or "")[:120],
        "hook": str(strategy.get("hook") or "")[:200],
        "cta": str(strategy.get("cta") or "")[:200],
        "visual": visual.get("format") or "",
        "funnel_stage": strategy.get("funnel_stage") or "",
        "pain_point": str(strategy.get("pain_point") or "")[:200],
    }


async def record(db, campaign_id: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Record performance for one campaign. metrics: {"linkedin": {...}, ...}."""
    doc = await db[COLLECTIONS["campaigns"]].find_one({"id": campaign_id}, {"_id": 0})
    if not doc:
        return {"ok": False, "error": f"campaign {campaign_id} not found"}

    dims = campaign_dims(doc)
    stored = dict(doc.get("metrics") or {})
    rows: List[Dict[str, Any]] = []

    for platform, vals in (metrics or {}).items():
        # `platform` is a channel name (linkedin/facebook/instagram), NOT a metric
        # name — checking it against METRICS silently dropped every sample.
        if platform not in PLATFORM_NAMES:
            continue
        if not isinstance(vals, dict):
            continue
        clean = {}
        for k, v in vals.items():
            if k not in METRICS:
                continue
            try:
                clean[k] = float(v)
            except (TypeError, ValueError):
                continue
        if not clean:
            continue
        stored.setdefault(platform, {}).update(clean)
        # dims must include platform too, otherwise grouping by "platform" reads
        # dims.platform (missing) and collapses every sample into "unknown".
        row_dims = {**dims, "platform": platform}
        rows.append({"campaign_id": campaign_id, "platform": platform,
                     "metrics": clean, "dims": row_dims, "at": now_iso()})

    await db[COLLECTIONS["campaigns"]].update_one(
        {"id": campaign_id},
        {"$set": {"metrics": stored, "metrics_updated_at": now_iso()}},
    )
    if rows:
        await db[COLLECTIONS["metrics"]].insert_many(rows)
    return {"ok": True, "recorded": len(rows), "dims": dims}


def _agg(rows: List[Dict[str, Any]], metric: str, dim: str) -> Dict[str, Any]:
    """Sum metric across rows grouped by one dimension."""
    totals: Dict[str, float] = defaultdict(float)
    counts: Dict[str, int] = defaultdict(int)
    for r in rows:
        val = (r.get("metrics") or {}).get(metric)
        if val is None:
            continue
        key = (r.get("dims") or {}).get(dim) or "unknown"
        totals[key] += float(val)
        counts[key] += 1
    return {k: {"total": round(v, 2), "campaigns": counts[k],
                "avg": round(v / counts[k], 2) if counts[k] else 0}
            for k, v in sorted(totals.items(), key=lambda kv: -kv[1])}


async def learn(db, metric: str = "engagements", days: int = 30,
                limit: int = 10) -> Dict[str, Any]:
    """Which topics / hooks / visuals / CTAs / platforms perform best on `metric`.

    Returns a per-dimension ranking. Requires at least one recorded sample;
    with no data it returns an explicit 'no_data' rather than fake rankings.
    """
    if metric not in METRICS:
        return {"ok": False, "error": f"unknown metric {metric}"}

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = await db[COLLECTIONS["metrics"]].find({"at": {"$gte": since}}).to_list(5000)
    if not rows:
        return {"ok": True, "metric": metric, "samples": 0, "no_data": True,
                "note": "No metrics recorded yet. POST them to /api/growth/metrics/{id} "
                        "or wire an official platform insights API."}

    out: Dict[str, Any] = {"ok": True, "metric": metric, "samples": len(rows)}
    for dim in ("visual", "platform", "kind", "funnel_stage", "cta", "topic", "hook"):
        out[dim] = list(_agg(rows, metric, dim).items())[:limit]

    # Per-platform breakdown with rate metrics when engagement is the measure.
    by_platform = defaultdict(lambda: {"impressions": 0.0, "clicks": 0.0, "engagements": 0.0, "n": 0})
    for r in rows:
        p = r.get("platform") or "unknown"
        m = r.get("metrics") or {}
        by_platform[p]["n"] += 1
        for k in ("impressions", "clicks", "engagements"):
            if m.get(k) is not None:
                by_platform[p][k] += float(m[k])
    out["platform_summary"] = {
        p: {**v,
            "eng_rate_pct": round(100 * v["engagements"] / v["impressions"], 2) if v["impressions"] else None,
            "ctr_pct": round(100 * v["clicks"] / v["impressions"], 2) if v["impressions"] else None}
        for p, v in by_platform.items()
    }
    return out


async def summary(db, days: int = 7) -> Dict[str, Any]:
    """Operational summary of the Growth Engine queue."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": {"kind": "$kind", "status": "$status"},
            "n": {"$sum": 1},
            "assets": {"$sum": {"$size": {"$ifNull": ["$asset_ids", []]}}},
        }},
        {"$sort": {"_id.kind": 1, "_id.status": 1}},
    ]
    rows = await db[COLLECTIONS["campaigns"]].aggregate(pipeline).to_list(200)

    by_kind: Dict[str, int] = defaultdict(int)
    by_status: Dict[str, int] = defaultdict(int)
    for r in rows:
        by_kind[r["_id"].get("kind") or "?"] += r["n"]
        by_status[r["_id"].get("status") or "?"] += r["n"]

    posted = await db[COLLECTIONS["campaigns"]].count_documents(
        {"status": {"$in": ["posted", "partial"]}})
    return {"ok": True, "days": days, "by_kind": dict(by_kind), "by_status": dict(by_status),
            "posted_or_partial": posted}


async def top_learnings(db, metric: str = "engagements", n: int = 3) -> str:
    """Compact natural-language digest fed back into the content prompt."""
    data = await learn(db, metric=metric)
    if data.get("no_data"):
        return ""
    lines = []
    for dim in ("visual", "kind", "cta"):
        rows = data.get(dim) or []
        if rows:
            top = ", ".join(f"{k} ({v['avg']} avg)" for k, v in rows[:n])
            lines.append(f"Best {dim}: {top}")
    plat = data.get("platform_summary") or {}
    if plat:
        best = max(plat.items(), key=lambda kv: (kv[1].get("eng_rate_pct") or 0))
        lines.append(f"Best platform by engagement rate: {best[0]}")
    return "; ".join(lines)


__all__ = ["METRICS", "record", "learn", "summary", "top_learnings", "campaign_dims"]