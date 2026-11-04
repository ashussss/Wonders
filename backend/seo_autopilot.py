"""SEO autopilot: use real Google Search Console data to improve the blog without anyone in the loop.

Why: by Nov 2026 the blog had ~150 indexed posts but ~30 impressions a month. Writing more posts was not moving
anything; the posts Google already tests (shows on page 1-4) are the cheapest wins. Every step here is free.

Jobs (registered in server.py):
1. sync()      Wed 07:30 UTC (13:00 IST). Pull the last 28 days of page+query rows from the Search Console API (service account
               in GSC_SERVICE_ACCOUNT_BASE64, added as a user on the property) and store per-post totals and top
               queries on blog_posts.gsc. Full rows go to seo_gsc_rows for later analysis.
2. refresh()   Daily 07:45 UTC. Rewrite up to SEO_REFRESH_PER_DAY published posts that Google shows at average
               position 5-40, steering the rewrite to the queries people actually typed. The old version is backed
               up to blog_posts_backup; a rewrite that fails the normal quality gate is thrown away. Slug and
               publish date are kept, so links and rankings carry over.
3. harvest()   Part of sync(). Queries with impressions that no post targets yet are added to the keyword queue,
               so new posts follow real demand instead of guesses.

GET /api/seo/autopilot-status shows the last run of each without exposing content.
"""

import asyncio
import base64
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from database import db
import pseo

logger = logging.getLogger("showup.seo_autopilot")

GSC_SITE_URL = os.environ.get("GSC_SITE_URL", "sc-domain:showupai.live")
REFRESH_PER_DAY = int(os.environ.get("SEO_REFRESH_PER_DAY", "2"))
REFRESH_MIN_POS = float(os.environ.get("SEO_REFRESH_MIN_POSITION", "5"))
REFRESH_MAX_POS = float(os.environ.get("SEO_REFRESH_MAX_POSITION", "40"))
REFRESH_MIN_IMPRESSIONS = int(os.environ.get("SEO_REFRESH_MIN_IMPRESSIONS", "1"))
REFRESH_COOLDOWN_DAYS = int(os.environ.get("SEO_REFRESH_COOLDOWN_DAYS", "30"))
HARVEST_MIN_IMPRESSIONS = int(os.environ.get("SEO_HARVEST_MIN_IMPRESSIONS", "1"))
HARVEST_MAX_PER_SYNC = int(os.environ.get("SEO_HARVEST_MAX_PER_SYNC", "10"))
HARVEST_SIMILARITY = float(os.environ.get("SEO_HARVEST_SIMILARITY", "0.5"))
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
STATE_ID = "seo_autopilot"


def _raw_key() -> str:
    """The service account key: GSC_SERVICE_ACCOUNT_BASE64, or GSC_SERVICE_ACCOUNT_JSON (the file pasted as is)."""
    return (os.environ.get("GSC_SERVICE_ACCOUNT_BASE64", "") or os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "")).strip()


def _credentials():
    raw = _raw_key()
    if not raw:
        return None
    try:
        info = json.loads(raw if raw.startswith("{") else base64.b64decode(raw).decode("utf-8"))
        from google.oauth2 import service_account
        return service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
    except Exception as e:
        logger.warning(f"GSC credentials unusable: {e}")
        return None


def configured() -> bool:
    return bool(_raw_key())


def _token(creds) -> str:
    from google.auth.transport.requests import Request
    creds.refresh(Request())
    return creds.token


async def fetch_rows(days: int = 28) -> list:
    """Search Analytics rows (page, query) for the last `days` days. Raises on API errors."""
    creds = _credentials()
    if not creds:
        raise RuntimeError("GSC_SERVICE_ACCOUNT_BASE64 not set or invalid")
    token = await asyncio.get_running_loop().run_in_executor(None, _token, creds)
    end = datetime.now(timezone.utc).date() - timedelta(days=2)
    start = end - timedelta(days=days - 1)
    url = f"https://searchconsole.googleapis.com/webmasters/v3/sites/{quote(GSC_SITE_URL, safe='')}/searchAnalytics/query"
    import httpx
    rows, start_row = [], 0
    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            r = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json={
                "startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": ["page", "query"],
                "rowLimit": 25000, "startRow": start_row, "dataState": "all"})
            if r.status_code >= 400:
                raise RuntimeError(f"Search Console API {r.status_code}: {r.text[:300]}")
            batch = r.json().get("rows") or []
            rows += batch
            if len(batch) < 25000:
                break
            start_row += len(batch)
    return [{"page": x["keys"][0], "query": x["keys"][1], "clicks": x.get("clicks", 0),
             "impressions": x.get("impressions", 0), "position": x.get("position", 0)} for x in rows]


_SLUG = re.compile(r"^https?://(?:www\.)?showupai\.live/blog/([a-z0-9-]+)/?(?:[?#].*)?$")


def slug_of(page: str) -> str | None:
    m = _SLUG.match(page or "")
    return m.group(1) if m else None


def per_post(rows: list) -> dict:
    """slug -> {impressions, clicks, position (impression-weighted), queries: top 10 by impressions}.
    /blog/x and /blog/x/ are the same post."""
    out = {}
    for r in rows:
        slug = slug_of(r["page"])
        if not slug:
            continue
        p = out.setdefault(slug, {"impressions": 0, "clicks": 0, "_pos": 0.0, "_q": {}})
        p["impressions"] += r["impressions"]
        p["clicks"] += r["clicks"]
        p["_pos"] += r["position"] * r["impressions"]
        q = p["_q"].setdefault(r["query"], {"query": r["query"], "impressions": 0, "clicks": 0, "_pos": 0.0})
        q["impressions"] += r["impressions"]
        q["clicks"] += r["clicks"]
        q["_pos"] += r["position"] * r["impressions"]
    for p in out.values():
        imp = p["impressions"] or 1
        p["position"] = round(p.pop("_pos") / imp, 1)
        qs = sorted(p.pop("_q").values(), key=lambda q: (-q["impressions"], q["_pos"]))[:10]
        for q in qs:
            q["position"] = round(q.pop("_pos") / (q["impressions"] or 1), 1)
        p["queries"] = qs
    return out


def pick_refresh(posts: list, now: datetime, limit: int) -> list:
    """Published posts Google already shows in striking distance, best opportunity first, skipping ones
    refreshed in the last REFRESH_COOLDOWN_DAYS."""
    cutoff = (now - timedelta(days=REFRESH_COOLDOWN_DAYS)).isoformat()
    ok = []
    for p in posts:
        g = p.get("gsc") or {}
        if not p.get("published") or (p.get("autopilot_refreshed_at") or "") > cutoff:
            continue
        if g.get("impressions", 0) < REFRESH_MIN_IMPRESSIONS:
            continue
        if not (REFRESH_MIN_POS <= (g.get("position") or 0) <= REFRESH_MAX_POS):
            continue
        ok.append(p)
    # more impressions first, then closer to page 1
    ok.sort(key=lambda p: (-p["gsc"]["impressions"], p["gsc"]["position"]))
    return ok[:limit]


def harvest_keywords(rows: list, existing: list, limit: int) -> list:
    """Queries with impressions that no existing post or queued keyword covers. `existing` is a list of
    keyword/title strings."""
    totals = {}
    for r in rows:
        q = pseo.normalize_text(r["query"]).strip().lower()
        if len(q.split()) < 2 or pseo.BRAND.lower() in q.replace(" ", "") or "showup" in q:
            continue  # brand and one-word queries are not topics
        totals[q] = totals.get(q, 0) + r["impressions"]
    picked = []
    for q, imp in sorted(totals.items(), key=lambda kv: -kv[1]):
        if imp < HARVEST_MIN_IMPRESSIONS:
            break
        if any(pseo.topic_similarity(q, e) >= HARVEST_SIMILARITY for e in existing + picked):
            continue
        picked.append(q)
        if len(picked) >= limit:
            break
    return picked


async def _state(**kw):
    await db.site_state.update_one({"_id": STATE_ID}, {"$set": kw}, upsert=True)


async def sync() -> dict:
    """Weekly: store Search Console numbers on each post and queue keywords from real queries."""
    if not configured():
        await _state(sync={"at": pseo.now_iso(), "ok": False, "error": "GSC_SERVICE_ACCOUNT_JSON / _BASE64 not set"})
        return {"ok": False, "error": "not configured"}
    try:
        rows = await fetch_rows()
    except Exception as e:
        logger.warning(f"SEO autopilot sync failed: {e}")
        await _state(sync={"at": pseo.now_iso(), "ok": False, "error": str(e)[:300]})
        return {"ok": False, "error": str(e)[:300]}
    stats = per_post(rows)
    now = pseo.now_iso()
    await db.seo_gsc_rows.delete_many({})
    if rows:
        await db.seo_gsc_rows.insert_many([{**r, "synced_at": now} for r in rows])
    await db.blog_posts.update_many({"gsc": {"$exists": True}}, {"$set": {
        "gsc": {"impressions": 0, "clicks": 0, "position": 0, "queries": [], "synced_at": now}}})
    for slug, s in stats.items():
        await db.blog_posts.update_one({"slug": slug}, {"$set": {"gsc": {**s, "synced_at": now}}})
    posts = await db.blog_posts.find({}, {"_id": 0, "keyword": 1, "title": 1}).to_list(5000)
    queued = await db.seo_candidates.find({}, {"_id": 0, "keyword": 1}).to_list(5000)
    existing = [x for p in posts for x in (p.get("keyword"), p.get("title")) if x] + [c["keyword"] for c in queued]
    added = []
    for q in harvest_keywords(rows, existing, HARVEST_MAX_PER_SYNC):
        if await pseo.add_keyword(q, notes="", created_at=pseo._PRIORITY_AT):
            added.append(q)
    summary = {"at": now, "ok": True, "rows": len(rows), "posts_with_impressions": len(stats),
               "impressions": sum(r["impressions"] for r in rows), "clicks": sum(r["clicks"] for r in rows),
               "keywords_added": added}
    await _state(sync=summary)
    logger.info(f"SEO autopilot sync: {summary}")
    return summary


async def refresh_post(post: dict) -> dict:
    """Rewrite one published post around the queries it already gets. Keeps the old version if the new one
    fails the quality gate."""
    queries = [q["query"] for q in (post.get("gsc") or {}).get("queries", [])][:8]
    try:
        new = await pseo.generate_post(post.get("keyword") or post["title"], post.get("intent") or "informational",
                                       slug=post["slug"], save=False, search_queries=queries)
    except Exception as e:
        return {"slug": post["slug"], "error": str(e)[:200]}
    ok, why = pseo.passes_quality_gate(new, lenient=True)
    if not ok:
        await db.blog_posts.update_one({"slug": post["slug"]}, {"$set": {"autopilot_refreshed_at": pseo.now_iso(),
                                                                         "autopilot_kept": why}})
        return {"slug": post["slug"], "kept": why}
    old = await db.blog_posts.find_one({"slug": post["slug"]}, {"_id": 0})
    await db.blog_posts_backup.insert_one({"run_id": "seo-autopilot", "slug": post["slug"], "reason": "autopilot refresh",
                                           "saved_at": pseo.now_iso(), "post": old})
    keep = {"id", "slug", "status", "published", "published_at", "created_at", "publish_at", "gsc", "cover_image",
            "cover_url"}
    upd = {k: v for k, v in new.items() if k not in keep}
    upd.update({"autopilot_refreshed_at": pseo.now_iso(), "autopilot_queries": queries, "updated_at": pseo.now_iso()})
    await db.blog_posts.update_one({"slug": post["slug"]}, {"$set": upd, "$unset": {"autopilot_kept": ""}})
    return {"slug": post["slug"], "rewritten": True, "queries": queries}


async def refresh(limit: int | None = None) -> dict:
    """Daily: rewrite the best striking-distance posts, then relink, rebuild and ping IndexNow once."""
    limit = REFRESH_PER_DAY if limit is None else limit
    if limit <= 0:
        return {"ok": True, "skipped": "SEO_REFRESH_PER_DAY=0"}
    posts = await db.blog_posts.find({"published": True, "gsc": {"$exists": True}},
                                     {"_id": 0, "content": 0}).to_list(5000)
    picked = pick_refresh(posts, datetime.now(timezone.utc), limit)
    results = []
    for p in picked:
        results.append(await refresh_post(p))
    done = [r["slug"] for r in results if r.get("rewritten")]
    if done:
        from routes_blog import _trigger_rebuild, _indexnow_later
        for slug in done:
            await pseo.relink_all(slug)
        await _trigger_rebuild(f"autopilot refreshed {len(done)}")
        _indexnow_later([f"{pseo.SITE_URL}/blog/{s}" for s in done])
    summary = {"at": pseo.now_iso(), "candidates": len(picked), "results": results}
    await _state(refresh=summary)
    logger.info(f"SEO autopilot refresh: {summary}")
    return summary


async def status() -> dict:
    """Content-free view for diagnosing the autopilot without the admin key."""
    state = await db.site_state.find_one({"_id": STATE_ID}, {"_id": 0}) or {}
    top = await db.blog_posts.find({"published": True, "gsc.impressions": {"$gt": 0}},
                                   {"_id": 0, "slug": 1, "gsc.impressions": 1, "gsc.clicks": 1, "gsc.position": 1}
                                   ).sort("gsc.impressions", -1).to_list(10)
    return {"configured": configured(), "site": GSC_SITE_URL, "refresh_per_day": REFRESH_PER_DAY,
            "last_sync": state.get("sync"), "last_refresh": state.get("refresh"), "top_posts": top}
