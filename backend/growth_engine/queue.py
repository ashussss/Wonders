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
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

from . import (
    APPROVAL_MODE,
    CAMPAIGN_KINDS,
    COLLECTIONS,
    DEFAULT_WEEKLY_PLAN,
    GROWTH_PLATFORMS,
    GROWTH_SLOTS_IST,
    GROWTH_WEEKLY_PLAN,
    IST,
    SITE_URL,
    VISUAL_FORMATS,
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


# Used when there is no published alternative/vs article to build from. These
# compare APPROACHES, never named products, so nothing about a competitor is invented.
COMPETITOR_ANGLES = [
    "Your webinar platform's built-in reminder emails vs a multi-channel reminder sequence",
    "Manual reminder emails from your marketing tool vs an automated pre-event sequence",
    "Email-only reminders vs email plus LinkedIn, WhatsApp and calendar",
    "Sending the replay to everyone vs a separate follow-up for attendees and no-shows",
]


def _pick_angle(pool: List[str], seed: str) -> str:
    """Rotate through ``pool`` across days and within a day.

    ``seed`` is "YYYY-MM-DD-n". The day's ordinal shifts the start each day and
    ``n`` steps within the day, so two campaigns on one day differ and the same
    slot gets a different angle tomorrow. Unparseable seeds fall back to a hash.
    """
    day, _, n = seed.rpartition("-")
    try:
        idx = datetime.fromisoformat(day).date().toordinal() * 2 + int(n)
    except ValueError:
        idx = sum(seed.encode())
    return pool[idx % len(pool)]


async def build_original_campaign(kind: CampaignKind, seed: str, **overrides: Any) -> Optional[CampaignDraft]:
    """pain_point = webinar/event-marketing lead-gen. engagement = conversation.
    competitor = approach-vs-approach comparison (no named products).

    All three are ORIGINAL content (no blog, no news): the model picks the angle, so
    we deliberately seed it with a rotating set of real, defensible pain points
    rather than asking it to invent a topic from nothing.
    """
    if kind == "pain_point":
        angle = _pick_angle(PAIN_ANGLES, seed)
        hint = (
            "ORIGINAL lead-gen campaign. The pain point is fixed by the brief below; write to it directly. "
            "The reader is an event host who is losing registrants. Make it practical and specific, "
            "not inspirational. Give away the fix, then point to showupai.live as the way to run it "
            "on autopilot. "
            f"Brief pain point: {angle}"
        )
    elif kind == "competitor":
        angle = _pick_angle(COMPETITOR_ANGLES, seed)
        hint = (
            "ORIGINAL comparison campaign for someone choosing how to run webinar reminders. "
            "Compare the two approaches in the brief honestly: where the usual way is fine, and "
            "where it breaks. Do NOT name any company or product other than ShowUpAI. "
            f"Brief: {angle}"
        )
    else:
        angle = _pick_angle(ENGAGEMENT_ANGLES, seed)
        hint = (
            "ORIGINAL engagement campaign designed to start a conversation, not to sell. "
            "Take a clear side, then ask a real question people will answer in the comments. "
            "No pitch in the caption. "
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
        **overrides,
    )


# ── daily plan ───────────────────────────────────────────────────────────────

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def parse_weekly_plan(spec: str) -> Dict[int, List[Dict[str, Any]]]:
    """'mon=blog:carousel@linkedin+facebook,...' -> {0: [{kind, format, platforms}], ...}.

    Unknown days, kinds or formats are skipped with a log line rather than failing
    the whole day. An empty or fully invalid spec falls back to the default plan.
    """
    plan: Dict[int, List[Dict[str, Any]]] = {}
    for entry in (spec or "").split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        day, _, rest = entry.partition("=")
        day = day.strip().lower()[:3]
        rest, _, plats = rest.partition("@")
        kind, _, fmt = rest.strip().partition(":")
        kind, fmt = kind.strip().lower(), fmt.strip().lower()
        platforms = [p.strip().lower() for p in plats.split("+") if p.strip()] if plats else []
        platforms = [p for p in platforms if p in GROWTH_PLATFORMS]
        if day not in _DAYS or kind not in CAMPAIGN_KINDS or (fmt and fmt not in VISUAL_FORMATS):
            logger.warning(f"weekly plan: skipping invalid entry '{entry}'")
            continue
        if plats and not platforms:
            logger.warning(f"weekly plan: '{entry}' names no enabled platform, skipping")
            continue
        plan.setdefault(_DAYS.index(day), []).append(
            {"kind": kind, "format": fmt, "platforms": platforms})
    if not plan and spec != DEFAULT_WEEKLY_PLAN:
        logger.warning("weekly plan: nothing valid in GROWTH_WEEKLY_PLAN, using the default")
        return parse_weekly_plan(DEFAULT_WEEKLY_PLAN)
    return plan


def plan_for(day: str) -> List[Dict[str, Any]]:
    """The posts planned for one ISO date."""
    weekday = datetime.fromisoformat(day).date().weekday()
    return parse_weekly_plan(GROWTH_WEEKLY_PLAN).get(weekday, [])


async def _build_planned(db, item: Dict[str, Any], day: str, n: int) -> Optional[CampaignDraft]:
    """Build one planned post, falling back to the next-best source when the
    planned one has nothing today (no fresh news, no comparison article)."""
    from . import blog_engine, news_engine

    kind = item["kind"]
    seed = f"{day}-{n}"
    over: Dict[str, Any] = {"visual_format": item.get("format") or ""}
    if item.get("platforms"):
        over["platforms"] = item["platforms"]

    if kind == "news":
        news = await news_engine.pick_news(db, want=1)
        if news:
            return await news_engine.build_news_campaign(news[0], **over)
        logger.info("generate_day: no fresh news, using a blog post instead")
        kind = "blog"
    if kind == "competitor":
        post = await blog_engine.pick_competitor_post(db, seed=seed)
        if post:
            return await blog_engine.build_competitor_campaign(db, post, **over)
        return await build_original_campaign("competitor", seed=seed, **over)
    if kind == "blog":
        post = await blog_engine.pick_blog_post(db, seed=seed)
        if post:
            return await blog_engine.build_blog_campaign(db, post, **over)
        logger.info("generate_day: no blog post available, using a pain-point post instead")
        kind = "pain_point"
    return await build_original_campaign(cast(CampaignKind, kind), seed=seed, **over)


async def generate_day(db, day: Optional[str] = None, render: bool = True,
                       force: bool = False) -> Dict[str, Any]:
    """Build the day's planned posts (idempotent unless force=True)."""
    day = day or plan_day()
    await ensure_indexes(db)

    if not force and await db[COLLECTIONS["campaigns"]].find_one({"plan_day": day}, {"_id": 1}):
        return {"ok": True, "note": "already generated for this day", "created": [], "day": day}

    items = plan_for(day)
    if not items:
        return {"ok": True, "day": day, "note": "nothing planned for this weekday",
                "created": [], "count": 0}

    slots = _slots(day)
    created: List[Dict[str, Any]] = []
    for n, item in enumerate(items):
        when = slots[n % len(slots)] if slots else datetime.now(timezone.utc)
        kind = item["kind"]
        try:
            draft = await _build_planned(db, item, day, n)
        except Exception as e:                                 # noqa: BLE001
            logger.error(f"generate_day: {kind} #{n} failed: {e}")
            created.append({"kind": kind, "error": str(e)[:200]})
            continue

        if not draft:
            created.append({"kind": kind, "note": "no draft produced"})
            continue
        if await already_queued(db, draft.kind, draft.source_slug or "", day):
            created.append({"kind": draft.kind, "note": "already queued today"})
            continue
        stored = await enqueue(db, draft, when, day, render=render)
        if not stored:
            created.append({"kind": draft.kind, "note": "enqueue failed"})
            continue
        created.append({
            "id": stored["id"], "kind": draft.kind, "status": stored["status"],
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


async def _with_linkedin_oauth(db, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Prefer the Growth Engine's own LinkedIn OAuth connection for publishing.

    The connection belongs to the brand account (SOCIAL_ACCOUNT_EMAIL), the same
    owner social.account_settings() reads. When it is connected and not expired,
    its token and member URN replace the legacy settings values, so posts go out
    as the connected member. Otherwise the legacy settings are used unchanged.
    """
    from social import SOCIAL_ACCOUNT_EMAIL
    from . import linkedin as li

    if not SOCIAL_ACCOUNT_EMAIL:
        return settings
    user = await db.users.find_one({"email": SOCIAL_ACCOUNT_EMAIL}, {"_id": 0, "id": 1})
    if not user:
        return settings
    conn = await li.get_connection(db, user["id"], li.PLATFORM)
    if not conn or conn.get("status") != "connected" or not conn.get("platform_user_id"):
        return settings
    expires = conn.get("expires_at")
    if expires:
        try:
            if datetime.fromisoformat(expires) <= datetime.now(timezone.utc):
                logger.warning("linkedin oauth token expired, reconnect on /app/integrations")
                return settings
        except ValueError:
            pass
    token = await li.get_access_token(db, user["id"], li.PLATFORM)
    if not token or token.startswith("enc::"):          # missing, or could not decrypt
        return settings
    return {**settings, "linkedin_marketing_token": token,
            "linkedin_org_urn": f"urn:li:person:{conn['platform_user_id']}"}


async def _with_meta_oauth(db, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Prefer the brand account's Facebook/Instagram OAuth connection over the legacy Settings token."""
    from social import SOCIAL_ACCOUNT_EMAIL
    from . import meta

    if not SOCIAL_ACCOUNT_EMAIL:
        return settings
    user = await db.users.find_one({"email": SOCIAL_ACCOUNT_EMAIL}, {"_id": 0, "id": 1})
    if not user:
        return settings
    extra = await meta.publishing_settings(db, user["id"])
    if not extra:
        return settings
    merged = {**settings, **extra}
    if "instagram_business_id" not in extra:
        # The selected Page has no Instagram account: don't pair its token with a legacy IG id.
        merged.pop("instagram_business_id", None)
    return merged


LINKEDIN_API_VERSION = os.environ.get("LINKEDIN_API_VERSION", "202604").strip()


async def post_linkedin_poll(settings: Dict[str, Any], text: str, question: str,
                             options: List[str], duration: str = "THREE_DAYS") -> Dict[str, Any]:
    """Native LinkedIn poll through the versioned Posts API (ugcPosts has no polls).

    Facebook Pages and Instagram have no poll API, so those platforms post the poll
    card image and ask people to comment their letter instead.
    """
    import httpx

    token, author = settings.get("linkedin_marketing_token"), settings.get("linkedin_org_urn")
    body = {
        "author": author,
        "commentary": text[:2900],
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [],
                         "thirdPartyDistributionChannels": []},
        "content": {"poll": {
            "question": question[:140],
            "options": [{"text": o[:30]} for o in options[:4]],
            "settings": {"duration": duration},
        }},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    headers = {"Authorization": f"Bearer {token}", "LinkedIn-Version": LINKEDIN_API_VERSION,
               "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post("https://api.linkedin.com/rest/posts", headers=headers, json=body)
    if r.status_code >= 400:
        return {"ok": False, "detail": f"poll:{r.status_code}: {r.text[:200]}"}
    return {"ok": True, "id": r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id")}


async def publish_campaign(db, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Publish ONE approved campaign to its platforms. Writes to growth_campaigns only.

    Reuses social.py's platform helpers (read-only use of those functions).
    """
    import social

    settings = await social.account_settings()
    settings = await _with_linkedin_oauth(db, settings)
    settings = await _with_meta_oauth(db, settings)
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
                vis = doc.get("visual") or {}
                if vis.get("format") == "poll" and len(vis.get("rows") or []) >= 2:
                    res = await post_linkedin_poll(settings, text, (vis.get("title") or "").replace("*", ""),
                                                   [str(r).replace("*", "") for r in vis.get("rows") or []])
                elif imgs:
                    res = await social.post_linkedin(settings, text, image_urls=imgs)
                else:
                    res = await social.post_linkedin(settings, text, link=link or None,
                                                    link_title=doc.get("link_title", ""))
            elif platform == "facebook":
                fb_link = None if (imgs and link and link.lower() in text.lower()) else (link or None)
                res = await social.post_facebook(settings, text, link=fb_link, image_urls=imgs)
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
        # Atomic claim: only the tick that flips approved -> publishing posts it,
        # so overlapping ticks or a second server instance cannot double-post.
        claimed = await db[COLLECTIONS["campaigns"]].update_one(
            {"id": d["id"], "status": "approved"},
            {"$set": {"status": "publishing", "updated_at": now_iso()}})
        if not claimed.modified_count:
            continue
        out.append(await publish_campaign(db, d))
    return {"ok": True, "published": len(out), "results": out}


__all__ = [
    "now_iso", "plan_day", "ensure_indexes", "enqueue", "generate_day",
    "approve", "reject", "edit", "publish_campaign", "dispatch_due",
    "build_original_campaign", "PAIN_ANGLES", "ENGAGEMENT_ANGLES", "_slots",
]