"""Social autopilot for ShowUpAI's own brand channels.

1. Blog promo: every time a blog post is published, a post (cover image + link) is queued for
   LinkedIn, Facebook and Instagram, ~20 minutes later (after the Netlify rebuild so link previews work).
2. Daily posts: every morning SOCIAL_POSTS_PER_DAY (default 4) posts are generated from published articles
   and verified stats: a carousel, an infographic, a stat card and an older article resurfaced.
   They are spread over SOCIAL_TIMES_IST and wait for approval unless SOCIAL_AUTO_APPROVE=true.

Credentials come from the ShowUpAI app's own Settings of the account in SOCIAL_ACCOUNT_EMAIL
(LinkedIn token + org/person URN, Meta page token + page id + Instagram business id).
Reddit and Substack are not automated: see DOCUMENTATION.md for why.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from bson import Binary

import pseo
import social_images as si
from config import PUBLIC_BACKEND_URL
from crypto_utils import decrypt_settings
from database import db

logger = logging.getLogger("showup.social")

SOCIAL_ACCOUNT_EMAIL = os.environ.get("SOCIAL_ACCOUNT_EMAIL", "").strip().lower()
SOCIAL_PLATFORMS = [p.strip() for p in os.environ.get("SOCIAL_PLATFORMS", "linkedin,facebook,instagram").split(",") if p.strip()]
SOCIAL_POSTS_PER_DAY = int(os.environ.get("SOCIAL_POSTS_PER_DAY", "4"))
SOCIAL_TIMES_IST = [t.strip() for t in os.environ.get("SOCIAL_TIMES_IST", "09:30,12:30,16:00,19:00").split(",") if t.strip()]
SOCIAL_AUTO_APPROVE = os.environ.get("SOCIAL_AUTO_APPROVE", "false").lower() == "true"
SOCIAL_AUTO_BLOG = os.environ.get("SOCIAL_AUTO_BLOG", "true").lower() == "true"  # blog promos skip approval
META_GRAPH_URL = "https://graph.facebook.com/v25.0"
IST = timezone(timedelta(hours=5, minutes=30))
BRAND = pseo.BRAND
SITE = pseo.SITE_URL

# Sourced numbers for stat cards (same sources as pseo.FACTS)
STAT_CARDS = [
    {"number": "60%", "label": "Average registration-to-attendee conversion on ON24's platform in 2025", "source": "ON24 Digital Engagement Benchmarks 2026"},
    {"number": "49 min", "label": "Average webinar engagement time on ON24's platform in 2025", "source": "ON24 Digital Engagement Benchmarks 2026"},
    {"number": "51.3%", "label": "Average webinar show-up rate across industries on Livestorm's platform", "source": "Livestorm"},
    {"number": "38%", "label": "Average live-session attendance rate for Demio customers in 2022", "source": "Banzai / Demio 2023 webinar stats"},
    {"number": "307", "label": "Average sign-ups per webinar, with a 58% attendance rate", "source": "TwentyThree, via Zoom's webinar statistics"},
    {"number": "50-55%", "label": "Response rate for webinars held during business hours, vs 25-30% outside them", "source": "BigMarker, via Zoom's webinar statistics"},
    {"number": "8.74%", "label": "Average webinar CTA click-through rate (top performers reach 17.5%)", "source": "BigMarker, via Zoom's webinar statistics"},
    {"number": "35%", "label": "Share of organisations with dedicated webinar program managers or teams", "source": "TwentyThree State of Webinars 2025"},
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- credentials

async def account_settings() -> dict:
    if not SOCIAL_ACCOUNT_EMAIL:
        return {}
    user = await db.users.find_one({"email": SOCIAL_ACCOUNT_EMAIL}, {"_id": 0, "id": 1})
    if not user:
        return {}
    s = await db.settings.find_one({"owner_id": user["id"]}, {"_id": 0}) or {}
    return decrypt_settings(s)


def connected(settings: dict) -> dict:
    return {
        "linkedin": bool(settings.get("linkedin_marketing_token") and settings.get("linkedin_org_urn")),
        "facebook": bool(settings.get("meta_graph_token") and settings.get("meta_page_id")),
        "instagram": bool(settings.get("meta_graph_token") and settings.get("instagram_business_id")),
    }


# ---------------------------------------------------------------- images

async def store_image(jpg: bytes) -> str:
    iid = uuid.uuid4().hex
    await db.social_images.insert_one({"id": iid, "jpg": Binary(jpg), "created_at": now_iso()})
    return iid


def image_url(iid: str) -> str:
    return f"{PUBLIC_BACKEND_URL.rstrip('/')}/api/social/img/{iid}.jpg"


def cover_url(slug: str) -> str:
    return f"{PUBLIC_BACKEND_URL.rstrip('/')}/api/blog/{slug}/cover.jpg"


async def _image_bytes(url: str) -> bytes:
    if "/api/social/img/" in url:
        iid = url.rsplit("/", 1)[-1].split(".")[0]
        doc = await db.social_images.find_one({"id": iid})
        if doc:
            return bytes(doc["jpg"])
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content


# ---------------------------------------------------------------- platform publishers

async def post_linkedin(settings, text, link=None, link_title="", image_urls=None):
    token, author = settings.get("linkedin_marketing_token"), settings.get("linkedin_org_urn")
    h = {"Authorization": f"Bearer {token}", "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
    media, category = [], "NONE"
    async with httpx.AsyncClient(timeout=60) as c:
        if image_urls:
            category = "IMAGE"
            for u in image_urls[:9]:
                reg = await c.post("https://api.linkedin.com/v2/assets?action=registerUpload", headers=h, json={
                    "registerUploadRequest": {
                        "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"], "owner": author,
                        "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}],
                    }})
                if reg.status_code >= 400:
                    return {"ok": False, "detail": f"register:{reg.status_code}: {reg.text[:200]}"}
                v = reg.json()["value"]
                up = v["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
                put = await c.put(up, content=await _image_bytes(u), headers={"Authorization": f"Bearer {token}"})
                if put.status_code >= 400:
                    return {"ok": False, "detail": f"upload:{put.status_code}"}
                media.append({"status": "READY", "media": v["asset"]})
        elif link:
            category = "ARTICLE"
            media = [{"status": "READY", "originalUrl": link, "title": {"text": link_title[:200]}}]
        content = {"shareCommentary": {"text": text[:2900]}, "shareMediaCategory": category}
        if media:
            content["media"] = media
        r = await c.post("https://api.linkedin.com/v2/ugcPosts", headers=h, json={
            "author": author, "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": content},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        })
    if r.status_code >= 400:
        return {"ok": False, "detail": f"{r.status_code}: {r.text[:200]}"}
    return {"ok": True, "id": r.headers.get("x-restli-id")}


async def post_facebook(settings, text, link=None, image_urls=None):
    token, page = settings.get("meta_graph_token"), settings.get("meta_page_id")
    async with httpx.AsyncClient(timeout=60) as c:
        if image_urls and len(image_urls) == 1:
            msg = f"{text}\n\n{link}" if link else text
            r = await c.post(f"{META_GRAPH_URL}/{page}/photos", data={"url": image_urls[0], "caption": msg, "access_token": token})
        elif image_urls:
            ids = []
            for u in image_urls[:10]:
                p = await c.post(f"{META_GRAPH_URL}/{page}/photos", data={"url": u, "published": "false", "access_token": token})
                if p.status_code >= 400:
                    return {"ok": False, "detail": f"photo:{p.status_code}: {p.text[:200]}"}
                ids.append(p.json()["id"])
            data = {"message": f"{text}\n\n{link}" if link else text, "access_token": token}
            for i, pid in enumerate(ids):
                data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
            r = await c.post(f"{META_GRAPH_URL}/{page}/feed", data=data)
        else:
            data = {"message": text, "access_token": token}
            if link:
                data["link"] = link
            r = await c.post(f"{META_GRAPH_URL}/{page}/feed", data=data)
    if r.status_code >= 400:
        return {"ok": False, "detail": f"{r.status_code}: {r.text[:200]}"}
    j = r.json()
    return {"ok": True, "id": j.get("post_id") or j.get("id")}


async def post_instagram(settings, caption, image_urls):
    token, ig = settings.get("meta_graph_token"), settings.get("instagram_business_id")
    if not image_urls:
        return {"ok": False, "detail": "Instagram needs at least one image"}
    async with httpx.AsyncClient(timeout=90) as c:
        if len(image_urls) == 1:
            m = await c.post(f"{META_GRAPH_URL}/{ig}/media", data={"image_url": image_urls[0], "caption": caption, "access_token": token})
            if m.status_code >= 400:
                return {"ok": False, "detail": f"media:{m.status_code}: {m.text[:200]}"}
            cid = m.json()["id"]
        else:
            kids = []
            for u in image_urls[:10]:
                k = await c.post(f"{META_GRAPH_URL}/{ig}/media", data={"image_url": u, "is_carousel_item": "true", "access_token": token})
                if k.status_code >= 400:
                    return {"ok": False, "detail": f"item:{k.status_code}: {k.text[:200]}"}
                kids.append(k.json()["id"])
            m = await c.post(f"{META_GRAPH_URL}/{ig}/media", data={"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption, "access_token": token})
            if m.status_code >= 400:
                return {"ok": False, "detail": f"carousel:{m.status_code}: {m.text[:200]}"}
            cid = m.json()["id"]
        await asyncio.sleep(3)  # give Instagram a moment to process the container
        p = await c.post(f"{META_GRAPH_URL}/{ig}/media_publish", data={"creation_id": cid, "access_token": token})
    if p.status_code >= 400:
        return {"ok": False, "detail": f"publish:{p.status_code}: {p.text[:200]}"}
    return {"ok": True, "id": p.json().get("id")}


# ---------------------------------------------------------------- captions (AI)

CAPTION_RULES = f"""Brand: {BRAND} (website showupai.live) helps webinar hosts make registrants actually show up, with an
AI-written 11-touch reminder sequence across email, LinkedIn, Facebook, Instagram, WhatsApp/SMS, Circle and calendar
invites; the host approves every message. Never write "ShowUp.ai". Do not invent statistics, customers or quotes; use
only numbers given to you. Tone: practical, direct, no hype words (unlock, game-changer, revolutionary).
Captions:
- caption_linkedin: 600-1100 characters, strong first line hook, short paragraphs, 1 question to invite comments,
  3 relevant hashtags at the end. Do not include any URL (it is added separately).
- caption_facebook: 250-500 characters, conversational, no URL, 1-2 hashtags.
- caption_instagram: 300-900 characters, hook first line, end with "Link in bio" and 8-12 relevant hashtags."""


def _ai(prompt: str) -> dict:
    return pseo._groq_json(prompt)


async def _ai_async(prompt: str) -> dict:
    return await asyncio.get_running_loop().run_in_executor(None, _ai, prompt)


def _clean(d: dict) -> dict:
    return {k: pseo.rebrand(pseo.normalize_text(v)) if isinstance(v, str) else v for k, v in d.items()}


# ---------------------------------------------------------------- queue helpers

async def _queue(kind, captions, images=None, link=None, link_title="", source_slug="", when=None, approved=False, extra=None):
    doc = {
        "id": uuid.uuid4().hex, "kind": kind, "source_slug": source_slug, "link": link, "link_title": link_title,
        "captions": captions, "images": images or [], "platforms": SOCIAL_PLATFORMS,
        "scheduled_at": (when or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "status": "approved" if approved else "pending", "results": {}, "created_at": now_iso(),
    }
    if extra:
        doc.update(extra)
    await db.social_posts.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def queue_blog_promo(slug: str):
    """Called when a blog post is published."""
    if await db.social_posts.find_one({"kind": "blog", "source_slug": slug}, {"_id": 1}):
        return None
    post = await db.blog_posts.find_one({"slug": slug}, {"_id": 0, "title": 1, "excerpt": 1, "content": 1, "keyword": 1})
    if not post:
        return None
    body = (post.get("content") or "")[:3500]
    caps = _clean(await _ai_async(f"""{CAPTION_RULES}

Write social captions promoting this new blog article. Tease the most useful insight so people want to read it.
Title: {post.get('title')}
Summary: {post.get('excerpt')}
Article (start): {body}

Return ONLY JSON: {{"caption_linkedin": "...", "caption_facebook": "...", "caption_instagram": "..."}}"""))
    await db.blog_posts.update_one({"slug": slug}, {"$set": {"social_used_at": now_iso()}})
    return await _queue(
        "blog", caps, images=[cover_url(slug)], link=f"{SITE}/blog/{slug}", link_title=post.get("title", ""),
        source_slug=slug, when=datetime.now(timezone.utc) + timedelta(minutes=20), approved=SOCIAL_AUTO_BLOG,
    )


async def _pick_article(exclude=()):
    rows = await db.blog_posts.find({"published": True, "slug": {"$nin": list(exclude)}},
                                    {"_id": 0, "slug": 1, "title": 1, "excerpt": 1, "content": 1, "social_used_at": 1}).to_list(500)
    if not rows:
        return None
    rows.sort(key=lambda r: r.get("social_used_at") or "")
    return rows[0]


async def _make_carousel(when):
    art = await _pick_article()
    if not art:
        return None
    j = _clean(await _ai_async(f"""{CAPTION_RULES}

Turn this article into an Instagram/LinkedIn carousel of practical tips.
Title: {art['title']}
Article: {(art.get('content') or '')[:6000]}

Return ONLY JSON:
{{"hook": "slide 1 headline, max 12 words, promise a concrete outcome",
  "slides": [{{"title": "max 9 words", "body": "max 32 words, specific and actionable"}}],   // exactly 5 slides
  "cta": "last slide line, max 14 words, invites them to read the full guide",
  "caption_linkedin": "...", "caption_facebook": "...", "caption_instagram": "..."}}"""))
    slides = [s for s in (j.get("slides") or []) if isinstance(s, dict) and s.get("title")][:5]
    if len(slides) < 3:
        return None
    pages = si.render_carousel(j.get("hook") or art["title"], slides, j.get("cta") or "Read the full guide", seed=art["slug"])
    ids = [await store_image(p) for p in pages]
    await db.blog_posts.update_one({"slug": art["slug"]}, {"$set": {"social_used_at": now_iso()}})
    return await _queue("carousel", {k: j.get(k, "") for k in ("caption_linkedin", "caption_facebook", "caption_instagram")},
                        images=[image_url(i) for i in ids], link=f"{SITE}/blog/{art['slug']}", link_title=art["title"],
                        source_slug=art["slug"], when=when, approved=SOCIAL_AUTO_APPROVE)


async def _make_infographic(when):
    art = await _pick_article()
    if not art:
        return None
    j = _clean(await _ai_async(f"""{CAPTION_RULES}

Summarise this article as a vertical infographic checklist.
Title: {art['title']}
Article: {(art.get('content') or '')[:6000]}

Return ONLY JSON:
{{"title": "infographic title, max 9 words", "rows": ["5 steps or points, each max 12 words"],
  "caption_linkedin": "...", "caption_facebook": "...", "caption_instagram": "..."}}"""))
    rows = [r for r in (j.get("rows") or []) if isinstance(r, str) and r.strip()][:6]
    if len(rows) < 3:
        return None
    iid = await store_image(si.render_infographic(j.get("title") or art["title"], rows, seed=art["slug"] + "i"))
    await db.blog_posts.update_one({"slug": art["slug"]}, {"$set": {"social_used_at": now_iso()}})
    return await _queue("infographic", {k: j.get(k, "") for k in ("caption_linkedin", "caption_facebook", "caption_instagram")},
                        images=[image_url(iid)], link=f"{SITE}/blog/{art['slug']}", link_title=art["title"],
                        source_slug=art["slug"], when=when, approved=SOCIAL_AUTO_APPROVE)


async def _make_stat(when):
    used = await db.social_posts.count_documents({"kind": "stat"})
    card = STAT_CARDS[used % len(STAT_CARDS)]
    j = _clean(await _ai_async(f"""{CAPTION_RULES}

Write captions around this single sourced webinar statistic. Explain what it means for someone running webinars and
one practical thing to do about it. Mention the source by name.
Stat: {card['number']} - {card['label']} (source: {card['source']})

Return ONLY JSON: {{"caption_linkedin": "...", "caption_facebook": "...", "caption_instagram": "..."}}"""))
    iid = await store_image(si.render_stat_card(card["number"], card["label"], card["source"], seed=card["number"] + str(used)))
    return await _queue("stat", j, images=[image_url(iid)], link=f"{SITE}/blog", link_title=f"{BRAND} blog",
                        when=when, approved=SOCIAL_AUTO_APPROVE)


async def _make_resurface(when):
    recent = [p["source_slug"] for p in await db.social_posts.find({"kind": {"$in": ["blog", "resurface"]}},
              {"_id": 0, "source_slug": 1}).sort("created_at", -1).to_list(5)]
    art = await _pick_article(exclude=recent)
    if not art:
        return None
    j = _clean(await _ai_async(f"""{CAPTION_RULES}

Write captions that re-share this existing article with a fresh angle (a specific tip or mistake from it).
Title: {art['title']}
Article (start): {(art.get('content') or '')[:3500]}

Return ONLY JSON: {{"caption_linkedin": "...", "caption_facebook": "...", "caption_instagram": "..."}}"""))
    await db.blog_posts.update_one({"slug": art["slug"]}, {"$set": {"social_used_at": now_iso()}})
    return await _queue("resurface", j, images=[cover_url(art["slug"])], link=f"{SITE}/blog/{art['slug']}",
                        link_title=art["title"], source_slug=art["slug"], when=when, approved=SOCIAL_AUTO_APPROVE)


MAKERS = [_make_carousel, _make_stat, _make_infographic, _make_resurface]


def _slots(day=None, count=None):
    day = day or datetime.now(IST).date()
    out = []
    for t in SOCIAL_TIMES_IST[: count or SOCIAL_POSTS_PER_DAY]:
        hh, mm = (int(x) for x in t.split(":"))
        out.append(datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST))
    return out


async def generate_daily(count: int = None):
    """Create today's posts (idempotent per day)."""
    day = datetime.now(IST).date().isoformat()
    if await db.social_posts.find_one({"plan_day": day}, {"_id": 1}) and count is None:
        return {"ok": True, "note": "already generated today", "created": []}
    created = []
    for i, when in enumerate(_slots(count=count)):
        maker = MAKERS[i % len(MAKERS)]
        try:
            doc = await maker(when)
            if doc:
                await db.social_posts.update_one({"id": doc["id"]}, {"$set": {"plan_day": day}})
                created.append({"id": doc["id"], "kind": doc["kind"], "scheduled_at": doc["scheduled_at"], "status": doc["status"]})
        except Exception as e:
            logger.error(f"social {maker.__name__} failed: {e}")
            created.append({"kind": maker.__name__, "error": str(e)[:200]})
    return {"ok": True, "created": created}


# ---------------------------------------------------------------- posting

async def publish_post(doc: dict, settings: dict = None) -> dict:
    settings = settings if settings is not None else await account_settings()
    conn = connected(settings)
    results = dict(doc.get("results") or {})
    caps = doc.get("captions") or {}
    link, imgs = doc.get("link"), doc.get("images") or []
    for platform in doc.get("platforms") or SOCIAL_PLATFORMS:
        if results.get(platform, {}).get("ok"):
            continue  # already posted there
        if not conn.get(platform):
            results[platform] = {"ok": False, "detail": "not connected"}
            continue
        try:
            if platform == "linkedin":
                text = (caps.get("caption_linkedin") or caps.get("caption_facebook") or "").strip()
                if link and doc["kind"] != "blog":
                    text += f"\n\nFull guide: {link}"
                if doc["kind"] in ("blog", "resurface"):
                    res = await post_linkedin(settings, text, link=link, link_title=doc.get("link_title", ""))
                else:
                    res = await post_linkedin(settings, text, image_urls=imgs)
            elif platform == "facebook":
                text = (caps.get("caption_facebook") or caps.get("caption_linkedin") or "").strip()
                if doc["kind"] in ("blog", "resurface"):
                    res = await post_facebook(settings, text, link=link)
                else:
                    res = await post_facebook(settings, text, link=link, image_urls=imgs)
            elif platform == "instagram":
                res = await post_instagram(settings, (caps.get("caption_instagram") or "").strip(), imgs)
            else:
                res = {"ok": False, "detail": "unsupported platform"}
        except Exception as e:
            res = {"ok": False, "detail": str(e)[:200]}
        res["at"] = now_iso()
        results[platform] = res
    oks = [r.get("ok") for r in results.values()]
    status = "posted" if oks and all(oks) else ("partial" if any(oks) else "failed")
    await db.social_posts.update_one({"id": doc["id"]}, {"$set": {"results": results, "status": status, "posted_at": now_iso()}})
    return {"status": status, "results": results}


async def post_due():
    """Scheduler job: post every approved item whose time has come."""
    now = now_iso()
    due = await db.social_posts.find({"status": "approved", "scheduled_at": {"$lte": now}}, {"_id": 0}).to_list(20)
    if not due:
        return []
    settings = await account_settings()
    out = []
    for d in due:
        await db.social_posts.update_one({"id": d["id"]}, {"$set": {"status": "posting"}})
        r = await publish_post(d, settings)
        out.append({"id": d["id"], **r})
    return out


def substack_markdown(post: dict) -> str:
    """Ready-to-paste Substack version (Substack has no official publishing API)."""
    url = f"{SITE}/blog/{post['slug']}"
    return (f"# {post['title']}\n\n*{post.get('excerpt', '')}*\n\n{post.get('content', '')}\n\n---\n\n"
            f"*Originally published on the [{BRAND} blog]({url}).* "
            f"[{BRAND}](https://showupai.live) helps webinar hosts make registrants actually show up.\n")
