"""Link engine — genuine, trust-first link building and brand mentions for showupai.live.

WHAT IT DOES
------------
* Keeps a curated catalog of real places where a B2B SaaS earns trust: launch
  sites (Product Hunt), review directories (G2, Capterra), publishing platforms
  (Substack, Medium, LinkedIn articles), expert-quote services and communities.
* Drafts copy written for each place (a listing, a launch kit, a newsletter issue,
  a pitch, an answer to a journalist) from verified product facts and the blog.
* Paces itself: a few new opportunities per week, so links grow at a natural rate.
* Tracks every opportunity through a review queue and checks that live links
  still exist.

WHAT IT NEVER DOES (anti-spam contract — do not relax without the owner's say-so)
-------------------------------------------------------------------------------
* Never submits, posts, comments or emails anywhere by itself. A human approves the
  draft and submits it from their own account. None of these sites offer an
  approved API for this anyway, and content sent out cannot be taken back.
* No paid links, link exchanges, PBNs, blog-comment or forum link drops.
* No identical copy across sites: each draft is written for one site, and earlier
  taglines are passed in so the model avoids repeating them.
* No invented numbers. Only PRODUCT_FACTS and the cited FACTS from pseo.py.

Flow: todo -> pending_review (drafted) -> approved -> submitted -> live
      (any state -> skipped / rejected; live -> lost when the link disappears)
"""

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

import pseo

from . import BRAND_NAME, COLLECTIONS, SITE_URL, _int
from .content_engine import _clean, ai_json

logger = logging.getLogger("showup.growth.links")

# New catalog opportunities drafted per weekly run. Three a week keeps link
# velocity natural for a young domain; syndication drafts come on top.
LINKS_PER_WEEK = _int("GROWTH_LINKS_PER_WEEK", 3)

STATUSES = ("todo", "pending_review", "approved", "submitted", "live", "lost", "skipped", "rejected")

GUARDRAILS = [
    "Nothing is submitted, posted or emailed automatically. You submit from your own account.",
    "No paid links, link swaps, PBNs, or link drops in comments and forums.",
    "Every site gets its own wording. Never paste the same description everywhere.",
    "Community answers must help on their own. Link only when it truly answers the question.",
    "Only real numbers: product facts and cited benchmarks. No invented stats or reviews.",
    "Never ask for upvotes or reviews in exchange for anything (Product Hunt and G2 ban it).",
]

# ── Catalog ──────────────────────────────────────────────────────────────────
# priority: 1 = do first (highest trust per hour of effort), 3 = later / optional.
# cadence:  once = one-time listing; weekly = recurring syndication;
#           on_demand = drafted when you paste a query or target.
# link:     honest note on what the link is worth. Most UGC/directory links are
#           nofollow; their value is trust, referral traffic and AI-answer mentions.
CATALOG: List[Dict[str, Any]] = [
    # launch
    {"key": "product_hunt", "name": "Product Hunt", "domain": "producthunt.com",
     "submit_url": "https://www.producthunt.com/posts/new", "category": "launch", "asset": "launch_kit",
     "priority": 1, "cadence": "once",
     "link": "Nofollow, but a strong trust signal; launches get picked up by newsletters and AI answers.",
     "requirements": "Maker account (use your own profile, active for a few weeks first), logo 240x240, "
                     "3-5 gallery images, optional demo video. Launch Tue-Thu at 12:01 AM PT."},
    {"key": "betalist", "name": "BetaList", "domain": "betalist.com",
     "submit_url": "https://betalist.com/submit", "category": "launch", "asset": "listing",
     "priority": 2, "cadence": "once",
     "link": "Early-adopter traffic and an editorial listing.",
     "requirements": "Free queue can take weeks; product must be early-stage."},
    {"key": "indie_hackers", "name": "Indie Hackers", "domain": "indiehackers.com",
     "submit_url": "https://www.indiehackers.com/products", "category": "community", "asset": "profile",
     "priority": 2, "cadence": "once",
     "link": "Product page plus build-in-public posts; founders read and share these.",
     "requirements": "Personal account. Post a genuine milestone or lesson, not an ad."},
    # review directories
    {"key": "g2", "name": "G2", "domain": "g2.com",
     "submit_url": "https://sell.g2.com/", "category": "directory", "asset": "listing",
     "priority": 1, "cadence": "once",
     "link": "Free profile. G2 pages rank for '<category> software' searches and AI answers cite them.",
     "requirements": "Work email on the showupai.live domain. Reviews must come from real users, no incentives "
                     "beyond G2's own allowed gift-card programme."},
    {"key": "capterra", "name": "Capterra / GetApp / Software Advice", "domain": "capterra.com",
     "submit_url": "https://digitalmarkets.gartner.com/", "category": "directory", "asset": "listing",
     "priority": 1, "cadence": "once",
     "link": "One free Gartner Digital Markets listing appears on all three sites.",
     "requirements": "Vendor account, product screenshots, pricing page URL."},
    {"key": "saashub", "name": "SaaSHub", "domain": "saashub.com",
     "submit_url": "https://www.saashub.com/", "category": "directory", "asset": "listing",
     "priority": 2, "cadence": "once",
     "link": "Free listing with alternatives pages next to Livestorm, Demio and others.",
     "requirements": "Account; verify ownership via the site."},
    {"key": "alternativeto", "name": "AlternativeTo", "domain": "alternativeto.net",
     "submit_url": "https://alternativeto.net/", "category": "directory", "asset": "listing",
     "priority": 2, "cadence": "once",
     "link": "Shows up for 'alternative to <competitor>' searches.",
     "requirements": "Account; list as an alternative to the webinar tools you actually work with."},
    {"key": "crunchbase", "name": "Crunchbase", "domain": "crunchbase.com",
     "submit_url": "https://www.crunchbase.com/", "category": "directory", "asset": "profile",
     "priority": 2, "cadence": "once",
     "link": "Company entity record; helps Google and AI tools recognise the brand.",
     "requirements": "Personal account linked to the company."},
    {"key": "ai_directories", "name": "AI tool directories (There's An AI For That, Futurepedia)",
     "domain": "theresanaiforthat.com", "submit_url": "https://theresanaiforthat.com/", "category": "directory",
     "asset": "listing", "priority": 3, "cadence": "once",
     "link": "Mostly paid placements. Only worth it if there is budget; skip otherwise.",
     "requirements": "Submission fee on most of these."},
    # publishing / syndication (recurring, canonical points back to the blog)
    {"key": "substack", "name": "Substack newsletter", "domain": "substack.com",
     "submit_url": "https://substack.com/", "category": "publishing", "asset": "syndication",
     "priority": 1, "cadence": "weekly",
     "link": "Your own newsletter; each issue links to the full post. Substack's network recommends it to readers.",
     "requirements": "Create a publication once (e.g. 'ShowUp Weekly'). Paste the weekly draft."},
    {"key": "medium", "name": "Medium (import with canonical)", "domain": "medium.com",
     "submit_url": "https://medium.com/p/import", "category": "publishing", "asset": "syndication",
     "priority": 2, "cadence": "weekly",
     "link": "Use Medium's import tool so the canonical stays on showupai.live (no duplicate-content risk).",
     "requirements": "Medium account. Import the blog URL, then submit to a relevant publication."},
    {"key": "linkedin_article", "name": "LinkedIn newsletter article", "domain": "linkedin.com",
     "submit_url": "https://www.linkedin.com/article/new/", "category": "publishing", "asset": "syndication",
     "priority": 1, "cadence": "weekly",
     "link": "Personal-profile articles reach your network and get indexed.",
     "requirements": "Post from your own profile, not the company page (the Growth Engine already covers that)."},
    # expert quotes / digital PR (you paste a journalist query, it drafts the answer)
    {"key": "qwoted", "name": "Qwoted", "domain": "qwoted.com",
     "submit_url": "https://www.qwoted.com/", "category": "pr", "asset": "pr_answer",
     "priority": 1, "cadence": "on_demand",
     "link": "Quotes in real publications; often a do-follow mention.",
     "requirements": "Free expert profile. Answer only queries about webinars, events, B2B marketing."},
    {"key": "featured", "name": "Featured", "domain": "featured.com",
     "submit_url": "https://featured.com/", "category": "pr", "asset": "pr_answer",
     "priority": 1, "cadence": "on_demand",
     "link": "Expert answers published on partner sites.",
     "requirements": "Free expert profile."},
    {"key": "help_b2b_writer", "name": "Help a B2B Writer", "domain": "helpab2bwriter.com",
     "submit_url": "https://helpab2bwriter.com/", "category": "pr", "asset": "pr_answer",
     "priority": 2, "cadence": "on_demand",
     "link": "B2B writers looking for practitioner quotes.",
     "requirements": "Free source signup."},
    {"key": "sourcebottle", "name": "SourceBottle", "domain": "sourcebottle.com",
     "submit_url": "https://www.sourcebottle.com/", "category": "pr", "asset": "pr_answer",
     "priority": 3, "cadence": "on_demand",
     "link": "APAC/India journalist call-outs.",
     "requirements": "Free account."},
    # communities (answers only, drafted on demand from a thread you paste)
    {"key": "reddit", "name": "Reddit (r/marketing, r/b2bmarketing, r/webinars)", "domain": "reddit.com",
     "submit_url": "https://www.reddit.com/", "category": "community", "asset": "answer",
     "priority": 2, "cadence": "on_demand",
     "link": "Reddit threads rank and feed AI answers. Help first; mention ShowUpAI only when asked and disclose it.",
     "requirements": "Aged personal account with real participation. Follow each subreddit's self-promo rules."},
    {"key": "quora", "name": "Quora", "domain": "quora.com",
     "submit_url": "https://www.quora.com/", "category": "community", "asset": "answer",
     "priority": 3, "cadence": "on_demand",
     "link": "Long-lived answers to 'how to increase webinar attendance' questions.",
     "requirements": "Personal profile with credentials line. Disclose you built ShowUpAI."},
]

CATALOG_BY_KEY = {c["key"]: c for c in CATALOG}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _coll(db):
    return db[COLLECTIONS["links"]]


def _public(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return doc
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


# ── Catalog seeding ──────────────────────────────────────────────────────────

async def seed_catalog(db) -> Dict[str, Any]:
    """Upsert catalog rows. Catalog fields refresh; status, drafts and history are kept."""
    added = 0
    for item in CATALOG:
        meta = {k: v for k, v in item.items() if k != "key"}
        res = await _coll(db).update_one(
            {"key": item["key"]},
            {"$set": {**meta, "source": "catalog", "updated_at": _now()},
             "$setOnInsert": {"id": str(uuid.uuid4()), "key": item["key"], "status": "todo",
                              "draft": None, "history": [], "created_at": _now()}},
            upsert=True,
        )
        added += 1 if res.upserted_id else 0
    return {"ok": True, "added": added, "catalog": len(CATALOG)}


# ── Drafting ─────────────────────────────────────────────────────────────────

ASSET_SPECS = {
    "listing": (
        '{"tagline": "<=60 chars, plain, no hype", "short_description": "<=160 chars", '
        '"long_description": "150-250 words, what it does, who it is for, how it works with Zoom/Teams/Livestorm", '
        '"key_features": ["5 items, each <=12 words"], "categories": ["3-5 categories this site would use"], '
        '"alternatives_to": ["webinar tools it complements or replaces, only real ones"], "pricing_note": "..."}'
    ),
    "launch_kit": (
        '{"tagline": "<=60 chars", "description": "<=260 chars", '
        '"maker_comment": "120-200 words in first person from the founder: why it was built, who it is for, '
        'one honest limitation, and a request for FEEDBACK (never for upvotes)", '
        '"topics": ["3 Product Hunt topics"], "gallery_ideas": ["5 screenshot/visual ideas with a caption each"], '
        '"launch_day_plan": ["8-10 concrete steps for launch day, none of them asking for upvotes"]}'
    ),
    "profile": (
        '{"one_liner": "<=80 chars", "about": "80-150 words", '
        '"first_post_title": "a genuine lesson or milestone title", '
        '"first_post": "150-250 words, build-in-public tone, one concrete lesson, link only at the end"}'
    ),
    "syndication": (
        '{"title": "issue title, not the same as the blog title", "subtitle": "<=120 chars", '
        '"body_markdown": "350-600 words adapted for newsletter readers: a short personal intro, the 3 most useful '
        'points, then a line linking to the full post", "cta": "one line"}'
    ),
    "pitch": (
        '{"subject": "<=70 chars", "email_body": "<=150 words, references the target site specifically, '
        'no flattery templates", "topic_ideas": [{"title": "...", "angle": "why their readers need it", '
        '"outline": ["4-6 points"]}]}'
    ),
    "pr_answer": (
        '{"answer": "100-200 words, first-hand, specific, directly answers the query", '
        '"credentials": "one line on who is answering", "suggested_link": "the single most relevant URL or empty"}'
    ),
    "answer": (
        '{"answer": "120-250 words that fully help without a click", '
        '"disclosure": "one line disclosing you built ShowUpAI, only if ShowUpAI is mentioned", '
        '"link_if_relevant": "a blog URL only if it genuinely adds something, else empty"}'
    ),
}

DRAFT_PROMPT = """You write marketing copy for {brand} ({site}). The founder will review and submit it by hand.

PRODUCT FACTS (the only product claims you may make):
{product}

CITED BENCHMARKS (only numbers you may use, always name the source):
{facts}

RECENT BLOG POSTS (link to one only where it truly helps):
{posts}

TARGET: {name} ({domain}), a {category} site. Notes: {link}
{extra}
RULES:
- Write for this site's readers and format. Plain, specific, human. Short sentences.
- No hype words (revolutionary, game-changer, unlock, seamless, cutting-edge), no emojis, no exclamation marks.
- Do not invent customers, reviews, user counts, awards or results.
- Do not reuse these earlier taglines or their wording: {avoid}
- Never ask anyone for upvotes, reviews or links.

Return JSON only, exactly this shape:
{spec}
"""


async def _recent_posts(db, limit: int = 6) -> List[Dict[str, Any]]:
    rows = await db.blog_posts.find(
        {"published": True}, {"_id": 0, "slug": 1, "title": 1, "meta_description": 1},
    ).sort("published_at", -1).limit(limit).to_list(limit)
    return rows


def _post_lines(posts: List[Dict[str, Any]]) -> str:
    return "\n".join(f"- {p.get('title')} — {SITE_URL}/blog/{p.get('slug')}" for p in posts) or "- (none yet)"


async def _used_taglines(db, exclude_key: str) -> List[str]:
    rows = await _coll(db).find({"key": {"$ne": exclude_key}, "draft.tagline": {"$exists": True}},
                                {"_id": 0, "draft.tagline": 1}).to_list(100)
    return [r["draft"]["tagline"] for r in rows if r.get("draft", {}).get("tagline")]


async def build_draft(db, item: Dict[str, Any], extra: str = "") -> Dict[str, Any]:
    """Ask the model for site-specific copy. Raises on an empty or malformed reply."""
    asset = item.get("asset", "listing")
    spec = ASSET_SPECS.get(asset)
    if not spec:
        raise ValueError(f"unknown asset type {asset!r}")
    posts = await _recent_posts(db)
    avoid = await _used_taglines(db, item.get("key", ""))
    prompt = DRAFT_PROMPT.format(
        brand=BRAND_NAME, site=SITE_URL, product=pseo.PRODUCT_FACTS,
        facts="\n".join(f"- {f['fact']} (Source: {f['source']}, {f['url']})" for f in pseo.FACTS),
        posts=_post_lines(posts), name=item.get("name", ""), domain=item.get("domain", ""),
        category=item.get("category", ""), link=item.get("link", ""),
        extra=(extra.strip() + "\n") if extra and extra.strip() else "",
        avoid="; ".join(avoid) or "(none)", spec=spec,
    )
    data = await ai_json(prompt)
    if not isinstance(data, dict) or not data:
        raise ValueError("model returned no draft")
    return _clean(data)


async def draft(db, key: str, extra: str = "") -> Dict[str, Any]:
    """(Re)draft one opportunity and put it in the review queue."""
    item = await _coll(db).find_one({"key": key})
    if not item:
        raise KeyError(key)
    if item.get("asset") == "syndication":
        posts = await _recent_posts(db, 1)
        if posts:
            p = posts[0]
            extra = (f"Adapt THIS post: {p.get('title')} — {SITE_URL}/blog/{p.get('slug')}. "
                     f"Summary: {p.get('meta_description', '')}\n{extra}")
    body = await build_draft(db, item, extra)
    await _coll(db).update_one(
        {"key": key},
        {"$set": {"draft": body, "status": "pending_review", "drafted_at": _now(), "updated_at": _now()},
         "$push": {"history": {"at": _now(), "event": "drafted"}}},
    )
    return _public(await _coll(db).find_one({"key": key}))


async def draft_on_demand(db, kind: str, text: str, url: str = "", site: str = "",
                          key: str = "", source: str = "on_demand") -> Dict[str, Any]:
    """Draft from something the owner pasted: a journalist query, a thread, or a guest-post target.

    kind: pr_answer | answer | pitch. Creates its own queue row (not a catalog row).
    """
    kind = kind.strip().lower()
    if kind not in ("pr_answer", "answer", "pitch"):
        raise ValueError("kind must be pr_answer, answer or pitch")
    if not (text or "").strip():
        raise ValueError("paste the query, thread or target notes")
    domain = re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0] or site or "unknown"
    item = {
        "key": key or f"{kind}-{uuid.uuid4().hex[:8]}", "name": site or domain, "domain": domain,
        "submit_url": url, "category": {"pr_answer": "pr", "answer": "community", "pitch": "guest_post"}[kind],
        "asset": kind, "priority": 1, "cadence": "on_demand",
        "link": {"pr_answer": "Journalist query.", "answer": "Community thread. Help first.",
                 "pitch": "Guest post target. Pitch ideas only their readers would want."}[kind],
    }
    label = {"pr_answer": "JOURNALIST QUERY", "answer": "THREAD / QUESTION", "pitch": "TARGET SITE NOTES"}[kind]
    body = await build_draft(db, item, f"{label}:\n{text.strip()[:4000]}")
    doc = {**item, "id": str(uuid.uuid4()), "source": source, "input": text.strip()[:4000],
           "status": "pending_review", "draft": body, "history": [{"at": _now(), "event": "drafted"}],
           "created_at": _now(), "updated_at": _now(), "drafted_at": _now()}
    await _coll(db).insert_one(doc)
    return _public(doc)


# ── Weekly run ───────────────────────────────────────────────────────────────

async def weekly_run(db, limit: int = LINKS_PER_WEEK) -> Dict[str, Any]:
    """Seed the catalog, draft the next few one-time opportunities, refresh syndication drafts."""
    await seed_catalog(db)
    drafted, errors = [], []
    todo = await _coll(db).find({"status": "todo", "cadence": "once"}, {"_id": 0, "key": 1}) \
        .sort([("priority", 1), ("created_at", 1)]).limit(max(0, limit)).to_list(limit or 1)
    weekly = await _coll(db).find({"cadence": "weekly", "status": {"$nin": ["skipped", "rejected"]}},
                                  {"_id": 0, "key": 1}).to_list(20)
    for row in todo + weekly:
        try:
            await draft(db, row["key"])
            drafted.append(row["key"])
        except Exception as e:                                    # noqa: BLE001
            errors.append(f"{row['key']}: {str(e)[:120]}")
    if errors:
        logger.warning(f"link weekly run errors: {errors}")
    return {"ok": True, "drafted": drafted, "errors": errors}


# ── Review actions ───────────────────────────────────────────────────────────

ALLOWED_MOVES = {
    "approved": {"pending_review"},
    "submitted": {"approved", "pending_review"},
    "live": {"submitted", "lost"},
    "skipped": set(STATUSES),
    "rejected": set(STATUSES),
    "todo": {"skipped", "rejected"},
}


async def set_status(db, key: str, status: str, live_url: str = "", note: str = "",
                     draft_edit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    item = await _coll(db).find_one({"key": key})
    if not item:
        raise KeyError(key)
    if status not in ALLOWED_MOVES:
        raise ValueError(f"cannot set status {status!r}")
    if item.get("status") not in ALLOWED_MOVES[status]:
        raise ValueError(f"cannot move from {item.get('status')} to {status}")
    upd: Dict[str, Any] = {"status": status, "updated_at": _now()}
    if draft_edit:
        upd["draft"] = {**(item.get("draft") or {}), **draft_edit}
    if live_url:
        if not re.match(r"^https?://", live_url):
            raise ValueError("live_url must start with http(s)://")
        upd["live_url"] = live_url
    if status == "submitted":
        upd["submitted_at"] = _now()
    # Weekly items go back to the start of the loop once this week's issue is out.
    if status == "submitted" and item.get("cadence") == "weekly":
        upd["last_submitted_at"] = _now()
    await _coll(db).update_one({"key": key}, {"$set": upd, "$push": {
        "history": {"at": _now(), "event": status, "note": note[:300], "live_url": live_url}}})
    return _public(await _coll(db).find_one({"key": key}))


async def list_items(db, status: str = "", category: str = "") -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if category:
        q["category"] = category
    rows = await _coll(db).find(q, {"_id": 0, "history": 0}).sort(
        [("priority", 1), ("updated_at", -1)]).to_list(500)
    return rows


async def summary(db) -> Dict[str, Any]:
    counts = {s: await _coll(db).count_documents({"status": s}) for s in STATUSES}
    return {"counts": counts, "per_week": LINKS_PER_WEEK, "guardrails": GUARDRAILS}


# ── Live-link verification (read-only HTTP GET) ──────────────────────────────

_HOST = re.sub(r"^https?://(www\.)?", "", SITE_URL).rstrip("/")
_ANCHOR = re.compile(r"<a\b[^>]*>", re.I)


def find_backlink(html: str, host: str = _HOST) -> Dict[str, Any]:
    """Return whether the page links to our host, and whether that link is nofollow/ugc/sponsored."""
    for tag in _ANCHOR.findall(html or ""):
        href = re.search(r"""href\s*=\s*["']([^"']+)["']""", tag, re.I)
        if not href or host not in href.group(1).lower():
            continue
        rel = re.search(r"""rel\s*=\s*["']([^"']*)["']""", tag, re.I)
        rel_val = (rel.group(1).lower() if rel else "").split()
        return {"found": True, "href": href.group(1),
                "follow": not any(r in rel_val for r in ("nofollow", "ugc", "sponsored")), "rel": " ".join(rel_val)}
    return {"found": host in (html or "").lower(), "href": "", "follow": False, "rel": "mention-only"}


async def verify_live(db, max_age_days: int = 6) -> Dict[str, Any]:
    """Re-check submitted/live URLs. submitted -> live when the link appears; live -> lost when it goes."""
    cutoff = _now() - timedelta(days=max_age_days)
    q: Dict[str, Any] = {"status": {"$in": ["submitted", "live", "lost"]}, "live_url": {"$exists": True}}
    if max_age_days > 0:
        q["$or"] = [{"checked_at": {"$exists": False}}, {"checked_at": {"$lt": cutoff}}]
    rows = await _coll(db).find(q, {"_id": 0, "key": 1, "live_url": 1, "status": 1}).to_list(200)
    checked, changed = 0, []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True,
                                 headers={"User-Agent": f"{BRAND_NAME}-linkcheck/1.0 (+{SITE_URL})"}) as client:
        for r in rows:
            try:
                resp = await client.get(r["live_url"])
                result = find_backlink(resp.text if resp.status_code < 400 else "")
                result["http"] = resp.status_code
            except Exception as e:                                # noqa: BLE001
                result = {"found": False, "error": str(e)[:120]}
            new = r["status"]
            if result.get("found"):
                new = "live"
            elif r["status"] == "live" and "error" not in result:
                new = "lost"
            upd = {"check": result, "checked_at": _now(), "status": new}
            push = {"history": {"at": _now(), "event": f"check:{new}"}} if new != r["status"] else None
            await _coll(db).update_one({"key": r["key"]}, {"$set": upd, **({"$push": push} if push else {})})
            checked += 1
            if new != r["status"]:
                changed.append(f"{r['key']}: {r['status']} -> {new}")
    return {"ok": True, "checked": checked, "changed": changed}


__all__ = [
    "CATALOG", "CATALOG_BY_KEY", "GUARDRAILS", "LINKS_PER_WEEK", "STATUSES",
    "seed_catalog", "build_draft", "draft", "draft_on_demand", "weekly_run",
    "set_status", "list_items", "summary", "find_backlink", "verify_live",
]
