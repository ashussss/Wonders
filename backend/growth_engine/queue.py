"""Queue + orchestration for the Growth Engine.

Owns the Growth Engine's own collections only:

    growth_campaigns   the queue (never social_posts)
    growth_sources      news provenance
    growth_assets_fs    GridFS bucket for rendered visuals

Publishing reuses social.py's three platform helpers but writes results into
growth_campaigns — it never calls social.publish_post and never mutates
social_posts. Approval mode gates all dispatch.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

from . import (
    APPROVAL_MODE,
    COLLECTIONS,
    GROWTH_BLOG_CAMPAIGNS,
    GROWTH_ENGAGEMENT_CAMPAIGNS,
    GROWTH_NEWS_CAMPAIGNS,
    GROWTH_PAIN_CAMPAIGNS,
    GROWTH_PLATFORMS,
    GROWTH_SLOTS_IST,
    IST,
    SITE_URL,
)
from .content_engine import build_campaign
from .models import CampaignDraft, CampaignKind

logger = logging.getLogger("showup.growth.queue")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def plan_day() -> str:
    return datetime.now(IST).date().isoformat()


def _slots(day: Optional[str] = None, count: Optional[int] = None) -> List[datetime]:
    """IST posting slots for the day, as UTC datetimes."""
    d = datetime.fromisoformat(day) if day else datetime.now(IST)
    out = []
    for t in (GROWTH_SLOTS_IST[: count] if count else GROWTH_SLOTS_IST):
        try:
            hh, mm = (int(x) for x in t.split(":"))
        except ValueError:
            continue
        out.append(datetime(d.year, d.month, d.day, hh, mm, tzinfo=IST).astimezone(timezone.utc))
    return out


async def ensure_indexes(db) -> None:
    """Indexes for the Growth Engine collections. Safe to call repeatedly."""
    await db[COLLECTIONS["campaigns"]].create_index("plan_day")
    await db[COLLECTIONS["campaigns"]].create_index([("kind", 1), ("status", 1)])
    await db[COLLECTIONS["campaigns"]].create_index([("kind", 1), ("source_slug", 1)])
    await db[COLLECTIONS["campaigns"]].create_index("status")
    await db[COLLECTIONS["sources"]].create_index("published_at")
    await db[COLLECTIONS["prospects"]].create_index([("score", -1)])
    await db[COLLECTIONS["prospects"]].create_index("linkedin_url")


async def already_queued(db, kind: str, source_slug: str, day: str) -> bool:
    if await db[COLLECTIONS["campaigns"]].find_one(
        {"kind": kind, "source_slug": source_slug, "plan_day": day}, {"_id": 1}
    ):
        return True
    return False


async def enqueue(db, draft: CampaignDraft, when: datetime, day: str,
                  render: bool = True) -> Optional[Dict[str, Any]]:
    """Persist one draft as a pending campaign. Returns the stored doc."""
    from . import visual_engine as ve

    doc = draft.model_dump()
    doc.update({
        "id": uuid.uuid4().hex,
        "plan_day": day,
        "status": "pending_review",
        "scheduled_at": when.astimezone(timezone.utc).isoformat(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "asset_ids": [],
        "asset_urls": [],
        "results": {},
        "review": {"mode": "approval", "reviewed_by": None, "reviewed_at": None, "notes": ""},
        "metrics": {},
    })

    if render:
        assets = await ve.store_assets(db, draft.visual, seed=f"{draft.kind}:{draft.source_slug}")
        doc["asset_ids"] = assets.get("asset_ids") or []
        doc["asset_urls"] = assets.get("asset_urls") or []
        if assets.get("error"):
            doc["review"]["visual_error"] = assets["error"]

    await db[COLLECTIONS["campaigns"]].insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"queued {draft.kind} '{draft.strategy.hook[:50]}' -> {doc['status']} "
                f"({len(doc['asset_ids'])} asset(s))")
    return doc


# ── original (no external source) campaigns ──────────────────────────────────

PAIN_ANGLES = [
    "The reminder sequence nobody sends because it takes too long",
    "Why registrants go quiet after the confirmation email",
    "The 3 days before your webinar are where attendance is won or lost",
    "Registration numbers are vanity metrics without a show-up rate",
    "Calendar invites are the cheapest attendance lever nobody uses",
    "The post-event no-show follow-up most hosts never write",
]

ENGAGEMENT_ANGLES = [
    "A question the whole audience argues about",
    "An unpopular opinion about webinar follow-up",
    "A number the industry gets wrong",
    "The most common mistake new event hosts make",
]


async def build_original_campaign(kind: CampaignKind, seed: str) -> Optional[CampaignDraft]:
    """pain_point = webinar/event-marketing lead-gen. engagement = conversation.

    Both are ORIGINAL content (no blog, no news): the model picks the angle, so
    we deliberately seed it with a rotating set of real, defensible pain points
    rather than asking it to invent a topic from nothing.
    """
    if kind == "pain_point":
        angle_pool = PAIN_ANGLES
        angle = angle_pool[int(seed[-2:]) % len(angle_pool)] if seed[-2:].isdigit() else angle_pool[0]
        hint = (
            "ORIGINAL lead-gen campaign. The pain point is fixed by the brief below — write to it directly. "
            "The reader is an event host who is losing registrants. Make it practical and specific, "
            "not inspirational. Aim to earn a click to the blog or a signup. "
            f"Brief pain point: {angle}"
        )
    else:
        angle_pool = ENGAGEMENT_ANGLES
        angle = angle_pool[int(seed[-2:]) % len(angle_pool)] if seed[-2:].isdigit() else angle_pool[0]
        hint = (
            "ORIGINAL engagement campaign designed to start a conversation, not to sell. "
            "Ask a real question people will answer in the comments. No pitch in the caption. "
            f"Brief: {angle}"
        )

    return await build_campaign(
        kind,
        source_title="",
        source_body="",
        source_url="",
        source_slug=f"{kind}-{seed}",
        source_type="original",
        link_url=f"{SITE_URL}/blog",
        link_title="ShowUpAI blog",
        fact_block=(
            "SOURCED FACTS: none. Do not state any statistic or study finding. "
            "Write practical, experience-based advice only."
        ),
        seed=f"{kind}:{seed}",
        angle_hint=hint,
    )


# ── daily plan ───────────────────────────────────────────────────────────────

async def generate_day(db, day: Optional[str] = None, render: bool = True,
                       force: bool = False) -> Dict[str, Any]:
    """Build one day of campaigns (idempotent unless force=True)."""
    from . import blog_engine, news_engine

    day = day or plan_day()
    await ensure_indexes(db)

    if not force and await db[COLLECTIONS["campaigns"]].find_one({"plan_day": day}, {"_id": 1}):
        return {"ok": True, "note": "already generated for this day", "created": [], "day": day}

    targets = [
        ("blog", GROWTH_BLOG_CAMPAIGNS),
        ("news", GROWTH_NEWS_CAMPAIGNS),
        ("pain_point", GROWTH_PAIN_CAMPAIGNS),
        ("engagement", GROWTH_ENGAGEMENT_CAMPAIGNS),
    ]
    # Spread the day out: allocate slots round-robin across kinds.
    slots = _slots(day)
    created: List[Dict[str, Any]] = []
    slot_i = 0

    for kind, count in targets:
        if count <= 0:
            continue
        blog_sources: List[Any] = []
        news_sources: List[Any] = []
        # Select this kind's sources ONCE per run. Re-picking inside the loop
        # would return the same top posts every iteration (they only become
        # "used" once enqueued), so iterations 2+ would collide on one source.
        try:
            if kind == "blog":
                blog_sources = await blog_engine.pick_todays_posts(db, want=count)
            elif kind == "news":
                news_sources = await news_engine.pick_news(db, want=count)
            else:
                blog_sources = news_sources = []
        except Exception as e:                                  # noqa: BLE001
            logger.error(f"generate_day: could not select {kind} sources: {e}")
            created.append({"kind": kind, "error": str(e)[:200]})
            continue

        for n in range(count):
            when = slots[slot_i % len(slots)] if slots else datetime.now(timezone.utc)
            slot_i += 1
            draft = None
            try:
                if kind == "blog":
                    if n < len(blog_sources):
                        draft = await blog_engine.build_blog_campaign(db, blog_sources[n])
                elif kind == "news":
                    if n < len(news_sources):
                        draft = await news_engine.build_news_campaign(news_sources[n])
                else:
                    draft = await build_original_campaign(
                        cast(CampaignKind, kind), seed=f"{day}-{n}")
            except Exception as e:                             # noqa: BLE001
                logger.error(f"generate_day: {kind} #{n} failed: {e}")
                created.append({"kind": kind, "error": str(e)[:200]})
                continue

            if not draft:
                created.append({"kind": kind, "note": "no draft produced"})
                continue
            if await already_queued(db, kind, draft.source_slug or "", day):
                created.append({"kind": kind, "note": "already queued today"})
                continue
            stored = await enqueue(db, draft, when, day, render=render)
            if not stored:
                created.append({"kind": kind, "note": "enqueue failed"})
                continue
            created.append({
                "id": stored["id"], "kind": kind, "status": stored["status"],
                "scheduled_at": stored["scheduled_at"], "assets": len(stored["asset_ids"]),
                "visual": draft.visual.format, "platforms": stored["platforms"],
            })

    return {"ok": True, "day": day, "approval_mode": APPROVAL_MODE,
            "created": created, "count": len([c for c in created if c.get("id")])}


# ── approval + dispatch ──────────────────────────────────────────────────────

async def approve(db, ids: Optional[List[str]] = None, all_pending: bool = False,
                  notes: str = "") -> Dict[str, Any]:
    """Approve campaigns. The ONLY transition into a publishable state."""
    if all_pending:
        q = {"status": "pending_review"}
    elif ids:
        q = {"id": {"$in": ids}, "status": "pending_review"}
    else:
        return {"ok": False, "error": "provide ids or all_pending=true"}
    upd = {"$set": {"status": "approved", "updated_at": now_iso(),
                    "review.reviewed_at": now_iso(), "review.notes": notes}}
    r = await db[COLLECTIONS["campaigns"]].update_many(q, upd)
    return {"ok": True, "approved": r.modified_count}


async def reject(db, ids: List[str], notes: str = "") -> Dict[str, Any]:
    r = await db[COLLECTIONS["campaigns"]].update_many(
        {"id": {"$in": ids or []}, "status": "pending_review"},
        {"$set": {"status": "rejected", "updated_at": now_iso(), "review.notes": notes}})
    return {"ok": True, "rejected": r.modified_count}


async def edit(db, cid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Apply human edits to copy/visual fields before approval."""
    allowed = {"platform_copy", "visual", "scheduled_at", "platforms", "strategy", "link_url"}
    clean = {k: v for k, v in (patch or {}).items() if k in allowed}
    if not clean:
        return {"ok": False, "error": f"no editable fields in {sorted((patch or {}).keys())}"}
    clean["updated_at"] = now_iso()
    r = await db[COLLECTIONS["campaigns"]].update_one({"id": cid}, {"$set": clean})
    return {"ok": bool(r.modified_count)}


async def publish_campaign(db, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Publish ONE approved campaign to its platforms. Writes to growth_campaigns only.

    Reuses social.py's platform helpers (read-only use of those functions).
    """
    import social

    settings = await social.account_settings()
    conn = social.connected(settings)
    results = dict(doc.get("results") or {})
    copy = doc.get("platform_copy") or {}
    link = doc.get("link_url") or ""
    imgs = doc.get("asset_urls") or []

    for platform in doc.get("platforms") or GROWTH_PLATFORMS:
        if (results.get(platform) or {}).get("ok"):
            continue
        block = copy.get(platform) or {}
        text = str(block.get("caption") or "").strip()
        if not text:
            results[platform] = {"ok": False, "detail": "no caption for platform"}
            continue
        if not conn.get(platform):
            results[platform] = {"ok": False, "detail": "not connected"}
            continue
        try:
            if platform == "linkedin":
                if imgs:
                    res = await social.post_linkedin(settings, text, image_urls=imgs)
                else:
                    res = await social.post_linkedin(settings, text, link=link or None,
                                                    link_title=doc.get("link_title", ""))
            elif platform == "facebook":
                res = await social.post_facebook(settings, text, link=link or None, image_urls=imgs)
            elif platform == "instagram":
                if not imgs:
                    res = {"ok": False, "detail": "instagram needs an image"}
                else:
                    res = await social.post_instagram(settings, text, imgs)
            else:
                res = {"ok": False, "detail": "unsupported platform"}
        except Exception as e:                                  # noqa: BLE001
            res = {"ok": False, "detail": str(e)[:200]}
        res["at"] = now_iso()
        results[platform] = res

    oks = [bool(r.get("ok")) for r in results.values()]
    status = "posted" if oks and all(oks) else ("partial" if any(oks) else "failed")
    await db[COLLECTIONS["campaigns"]].update_one({"id": doc["id"]}, {"$set": {
        "results": results, "status": status, "posted_at": now_iso(), "updated_at": now_iso()}})
    return {"id": doc["id"], "status": status, "results": results}


async def dispatch_due(db, force: bool = False) -> Dict[str, Any]:
    """Scheduler tick: publish approved campaigns whose time has come.

    Refuses to publish at all while APPROVAL_MODE is on (unless force=True from an
    explicit admin "post now" call) or while GROWTH_AUTO_PUBLISH is off.
    """
    from . import GROWTH_AUTO_PUBLISH

    if APPROVAL_MODE and not force:
        return {"ok": True, "skipped": "approval_mode"}
    if not GROWTH_AUTO_PUBLISH and not force:
        return {"ok": True, "skipped": "auto_publish_disabled"}

    due = await db[COLLECTIONS["campaigns"]].find(
        {"status": "approved", "scheduled_at": {"$lte": now_iso()}}, {"_id": 0}
    ).to_list(10)
    if not due:
        return {"ok": True, "published": 0}
    out = []
    for d in due:
        await db[COLLECTIONS["campaigns"]].update_one({"id": d["id"]}, {"$set": {"status": "publishing"}})
        out.append(await publish_campaign(db, d))
    return {"ok": True, "published": len(out), "results": out}


__all__ = [
    "now_iso", "plan_day", "ensure_indexes", "enqueue", "generate_day",
    "approve", "reject", "edit", "publish_campaign", "dispatch_due",
    "build_original_campaign", "PAIN_ANGLES", "ENGAGEMENT_ANGLES", "_slots",
]