"""Growth Engine API — mounted at /api/growth. Separate from the existing social API.

Auth: like the other admin surfaces (routes_social / routes_blog), every endpoint
except the asset image route requires X-API-KEY == SUPERADMIN_SECRET. The asset
route is public-read because Meta must be able to fetch the image bytes.

This router never writes to social_posts, webinars, touches, registrants or the
pSEO/blog pipeline. It only reads blog_posts.
"""

import logging

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import Response

from database import db
from routes_blog import _require_key

from . import (
    APPROVAL_MODE,
    COLLECTIONS,
    GROWTH_AUTO_PUBLISH,
    GROWTH_BLOG_CAMPAIGNS,
    GROWTH_CAMPAIGNS_PER_DAY,
    GROWTH_ENGAGEMENT_CAMPAIGNS,
    GROWTH_NEWS_CAMPAIGNS,
    GROWTH_PAIN_CAMPAIGNS,
    GROWTH_PLATFORMS,
    GROWTH_SLOTS_IST,
)
from . import analytics, blog_engine, news_engine, prospect_engine, queue, visual_engine

logger = logging.getLogger("showup.growth.api")

router = APIRouter(prefix="/api/growth")


# ── config / status ──────────────────────────────────────────────────────────

@router.get("/status")
async def growth_status(request: Request):
    _require_key(request)
    counts = {}
    for key in ("campaigns", "prospects", "sources", "metrics"):
        counts[key] = await db[COLLECTIONS[key]].estimated_document_count()
    pending = await db[COLLECTIONS["campaigns"]].count_documents({"status": "pending_review"})
    return {
        "ok": True,
        "approval_mode": APPROVAL_MODE,
        "auto_publish": GROWTH_AUTO_PUBLISH,
        "publishing_blocked": APPROVAL_MODE or not GROWTH_AUTO_PUBLISH,
        "targets_per_day": GROWTH_CAMPAIGNS_PER_DAY,
        "mix": {"blog": GROWTH_BLOG_CAMPAIGNS, "news": GROWTH_NEWS_CAMPAIGNS,
                "pain_point": GROWTH_PAIN_CAMPAIGNS, "engagement": GROWTH_ENGAGEMENT_CAMPAIGNS},
        "platforms": GROWTH_PLATFORMS,
        "slots_ist": GROWTH_SLOTS_IST,
        "counts": counts,
        "pending_review": pending,
        "collections": COLLECTIONS,
    }


@router.get("/config")
async def growth_config(request: Request):
    """Everything an operator needs to reason about the engine's behaviour."""
    _require_key(request)
    return {
        "approval_mode": APPROVAL_MODE,
        "auto_publish": GROWTH_AUTO_PUBLISH,
        "prospect_compliance": prospect_engine.PROVIDER_CONTRACT,
        "note": "Approval mode is ON by default. Set GROWTH_APPROVAL_MODE=false AND "
                "GROWTH_AUTO_PUBLISH=true to let the scheduler publish approved items.",
    }


# ── queue / campaigns ────────────────────────────────────────────────────────

@router.get("/queue")
async def growth_queue(request: Request, status: str = "", kind: str = "", day: str = ""):
    """List Growth Engine campaigns. Never touches social_posts."""
    _require_key(request)
    q: dict = {}
    if status:
        q["status"] = status
    if kind:
        q["kind"] = kind
    if day:
        q["plan_day"] = day
    return await db[COLLECTIONS["campaigns"]].find(q, {"_id": 0}).sort("scheduled_at", -1).to_list(200)


@router.get("/campaign/{cid}")
async def growth_campaign(cid: str, request: Request):
    _require_key(request)
    doc = await db[COLLECTIONS["campaigns"]].find_one({"id": cid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Campaign not found")
    return doc


@router.post("/generate")
async def growth_generate(request: Request, payload: dict = Body(default={})):
    """Build campaigns now. Creates drafts (pending_review) unless explicitly told otherwise.

    Body: {"day": "YYYY-MM-DD", "render": true, "force": false}
    """
    _require_key(request)
    return await queue.generate_day(
        db,
        day=payload.get("day"),
        render=bool(payload.get("render", True)),
        force=bool(payload.get("force", False)),
    )


@router.post("/approve")
async def growth_approve(request: Request, payload: dict = Body(default={})):
    """Approve campaigns. Body: {"id": "..."} | {"ids": [...]} | {"all_pending": true}."""
    _require_key(request)
    return await queue.approve(db, ids=payload.get("ids") or ([payload["id"]] if payload.get("id") else None),
                               all_pending=bool(payload.get("all_pending")),
                               notes=str(payload.get("notes") or ""))


@router.post("/reject")
async def growth_reject(request: Request, payload: dict = Body(default={})):
    _require_key(request)
    ids = payload.get("ids") or ([payload["id"]] if payload.get("id") else [])
    return await queue.reject(db, ids, notes=str(payload.get("notes") or ""))


@router.post("/edit/{cid}")
async def growth_edit(cid: str, request: Request, payload: dict = Body(default={})):
    """Edit copy / visual / schedule before approval."""
    _require_key(request)
    return await queue.edit(db, cid, payload)


@router.post("/post-now/{cid}")
async def growth_post_now(cid: str, request: Request):
    """Publish a single campaign immediately (admin override).

    Only campaigns that were explicitly APPROVED may be posted. Rejected and
    still-pending items are refused — otherwise a rejected campaign could be
    published by accident, which is exactly what the review step exists to stop.
    """
    _require_key(request)
    doc = await db[COLLECTIONS["campaigns"]].find_one({"id": cid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Campaign not found")
    if doc.get("status") == "rejected":
        raise HTTPException(400, "Campaign was rejected — approve it first if it should go out.")
    if doc.get("status") == "pending_review":
        raise HTTPException(400, "Campaign is still pending review — approve it first.")
    if doc.get("status") == "skipped":
        raise HTTPException(400, "Campaign was skipped.")
    return await queue.publish_campaign(db, doc)


@router.post("/dispatch")
async def growth_dispatch(request: Request, payload: dict = Body(default={})):
    """Run the dispatch job now. Honours approval mode unless force=true."""
    _require_key(request)
    return await queue.dispatch_due(db, force=bool(payload.get("force")))


# ── sources ──────────────────────────────────────────────────────────────────

@router.get("/news/preview")
async def growth_news_preview(request: Request, limit: int = 10):
    """Show what the news engine would consider right now (read-only)."""
    _require_key(request)
    items = await news_engine.fetch_news()
    return {"ok": True, "count": len(items), "items": items[:limit]}


@router.get("/blogs/detected")
async def growth_blogs_detected(request: Request, window_hours: int = 30):
    """Which recent blog posts are eligible for a campaign (and which are done)."""
    _require_key(request)
    posts = await blog_engine.fetch_recent_published(db, window_hours=window_hours, limit=50)
    done = await blog_engine.unprocessed_slugs(db, [p.get("slug") or "" for p in posts])
    return {
        "ok": True,
        "window_hours": window_hours,
        "published_recent": len(posts),
        "already_campaigned": sorted(done),
        "eligible": [p["slug"] for p in posts if p.get("slug") and p["slug"] not in done],
    }


# ── analytics ────────────────────────────────────────────────────────────────

@router.post("/metrics/{cid}")
async def growth_record_metrics(cid: str, request: Request, payload: dict = Body(default={})):
    """Record performance for a campaign. Body: {"linkedin": {"impressions": 1200, ...}}."""
    _require_key(request)
    return await analytics.record(db, cid, payload)


@router.get("/analytics/learn")
async def growth_learn(request: Request, metric: str = "engagements", days: int = 30):
    """What works: topic / hook / visual / CTA / platform rankings for `metric`."""
    _require_key(request)
    return await analytics.learn(db, metric=metric, days=days)


@router.get("/analytics/summary")
async def growth_summary(request: Request, days: int = 7):
    _require_key(request)
    return await analytics.summary(db, days=days)


# ── assets (public read so Meta can fetch bytes) ─────────────────────────────

@router.get("/asset/{aid}.jpg")
async def growth_asset(aid: str):
    data = await visual_engine.read_asset(db, aid)
    if not data:
        raise HTTPException(404, "Asset not found")
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=604800"})


# ── prospects ────────────────────────────────────────────────────────────────

@router.get("/prospects")
async def growth_prospects(request: Request, limit: int = 25, min_score: float = 0.0):
    _require_key(request)
    return await prospect_engine.top_prospects(db, limit=limit, min_score=min_score)


@router.post("/prospects/import")
async def growth_prospect_import(request: Request, payload: dict = Body(default={})):
    """Import prospects. Body: {"csv": "..."} or {"json": [...]} (raw provider export)."""
    _require_key(request)
    raw = payload.get("csv") or payload.get("json") or payload.get("data")
    if not raw:
        raise HTTPException(400, "Provide csv or json")
    fmt = payload.get("format") or "auto"
    prospects = prospect_engine.parse_import(raw, fmt)
    if not prospects:
        raise HTTPException(400, "Could not parse any prospects from the payload")
    return await prospect_engine.ingest(db, prospects)


@router.post("/prospects/{pid}/activity")
async def growth_prospect_activity(pid: str, request: Request, payload: dict = Body(default={})):
    """Record operator-observed activity (Sales Navigator/Apollo/manual). No scraping."""
    _require_key(request)
    return await prospect_engine.add_activity(db, pid, payload.get("activity") or [])


@router.post("/prospects/{pid}/recommend")
async def growth_prospect_recommend(pid: str, request: Request):
    _require_key(request)
    return await prospect_engine.recommend_engagement(db, pid)


@router.post("/prospects/{pid}/message")
async def growth_prospect_message(pid: str, request: Request):
    """Draft a personalised connection note. Returns text — never sends."""
    _require_key(request)
    return await prospect_engine.connection_message(db, pid)


@router.post("/prospects/{pid}/log")
async def growth_prospect_log(pid: str, request: Request, payload: dict = Body(default={})):
    _require_key(request)
    return await prospect_engine.log_history(db, pid, str(payload.get("event") or "note"),
                                             str(payload.get("detail") or ""))


__all__ = ["router"]