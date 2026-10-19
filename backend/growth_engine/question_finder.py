"""Question finder — real people asking about webinar attendance, drafted answers for review.

Reads PUBLIC feeds only (Reddit search RSS, Hacker News' Algolia search API) over
plain HTTP GET. No login, no browser, no posting, voting or following. Each match
becomes a link-queue row (asset "answer") with a draft reply the owner reads,
edits and posts by hand from their own account.

Pacing: GROWTH_QUESTIONS_PER_DAY (default 3) new drafts a day, newest and most
relevant first, never the same thread twice.
"""

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx

from . import BRAND_NAME, COLLECTIONS, SITE_URL, _csv, _int
from .news_engine import _clean_text, _parse_date, _parse_xml

logger = logging.getLogger("showup.growth.questions")

QUESTIONS_PER_DAY = _int("GROWTH_QUESTIONS_PER_DAY", 3)
MAX_AGE_DAYS = _int("GROWTH_QUESTIONS_MAX_AGE_DAYS", 7)

SUBREDDITS = _csv("GROWTH_QUESTION_SUBREDDITS",
                  "marketing,b2bmarketing,webinars,eventprofs,digital_marketing,SaaS,startups")
QUERIES = _csv("GROWTH_QUESTION_QUERIES",
               "webinar attendance,webinar no-show,webinar reminders,webinar show up rate,"
               "virtual event attendance")

USER_AGENT = f"{BRAND_NAME}-questions/1.0 (+{SITE_URL})"

# A thread is worth answering when it is about our problem AND reads like a question.
TOPIC_TERMS = ("webinar", "no-show", "no show", "noshow", "attendance", "show up", "show-up",
               "registrants", "virtual event", "live session", "reminder")
QUESTION_HINTS = ("?", "how do", "how to", "how can", "any tips", "advice", "recommend",
                  "what tool", "what works", "help", "struggling", "anyone")


def score(title: str, body: str = "") -> int:
    """0 = skip. Topic match is required; a question shape doubles the weight."""
    text = f"{title} {body}".lower()
    topic = sum(1 for t in TOPIC_TERMS if t in text)
    if not topic:
        return 0
    asks = any(h in title.lower() for h in QUESTION_HINTS) or "?" in body[:400]
    return topic * (2 if asks else 1)


def reddit_feeds() -> List[str]:
    return [f"https://www.reddit.com/r/{sub}/search.rss?q={quote_plus(q)}&restrict_sr=1&sort=new&t=week"
            for sub in SUBREDDITS for q in QUERIES[:2]]


def hn_url(query: str) -> str:
    return f"https://hn.algolia.com/api/v1/search_by_date?tags=ask_hn&query={quote_plus(query)}"


def _rid(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def parse_reddit(xml: bytes, cutoff: datetime) -> List[Dict[str, Any]]:
    root = _parse_xml(xml)
    if root is None:
        return []
    out = []
    for n in root.findall(".//{http://www.w3.org/2005/Atom}entry") + root.findall(".//item"):
        title = _clean_text(n.findtext("{http://www.w3.org/2005/Atom}title") or n.findtext("title") or "")
        link = ""
        for a in n.findall("{http://www.w3.org/2005/Atom}link"):
            if a.get("href"):
                link = a.get("href")
                break
        link = link or (n.findtext("link") or "").strip()
        body = _clean_text(n.findtext("{http://www.w3.org/2005/Atom}content") or n.findtext("description") or "")
        published = _parse_date(n)
        if not title or not link or (published and published < cutoff):
            continue
        sub = re.search(r"reddit\.com/r/([^/]+)/", link)
        out.append({"title": title[:300], "url": link, "body": body[:2000], "platform": "reddit",
                    "site": f"r/{sub.group(1)}" if sub else "Reddit",
                    "published_at": (published or datetime.now(timezone.utc)).isoformat()})
    return out


def parse_hn(data: Dict[str, Any], cutoff: datetime) -> List[Dict[str, Any]]:
    out = []
    for h in (data or {}).get("hits", []):
        created = h.get("created_at_i")
        when = datetime.fromtimestamp(created, timezone.utc) if created else None
        if when and when < cutoff:
            continue
        oid = h.get("objectID")
        if not oid or not h.get("title"):
            continue
        out.append({"title": _clean_text(h["title"])[:300], "url": f"https://news.ycombinator.com/item?id={oid}",
                    "body": _clean_text(h.get("story_text") or "")[:2000], "platform": "hackernews",
                    "site": "Hacker News", "published_at": (when or datetime.now(timezone.utc)).isoformat()})
    return out


async def fetch_questions(max_age_days: int = MAX_AGE_DAYS) -> List[Dict[str, Any]]:
    """All matching public threads, best first. Feed failures are logged and skipped."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    found: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as c:
        for url in reddit_feeds():
            try:
                r = await c.get(url)
                if r.status_code < 400:
                    found.extend(parse_reddit(r.content, cutoff))
                else:
                    logger.info(f"question feed {url} -> HTTP {r.status_code}")
            except Exception as e:                                # noqa: BLE001
                logger.info(f"question feed {url} failed: {e}")
        for q in QUERIES:
            try:
                r = await c.get(hn_url(q))
                if r.status_code < 400:
                    found.extend(parse_hn(r.json(), cutoff))
            except Exception as e:                                # noqa: BLE001
                logger.info(f"hn search {q!r} failed: {e}")

    best: Dict[str, Dict[str, Any]] = {}
    for f in found:
        f["score"] = score(f["title"], f["body"])
        if f["score"] and f["url"] not in best:
            best[f["url"]] = f
    return sorted(best.values(), key=lambda x: (x["score"], x["published_at"]), reverse=True)


async def run_daily(db, limit: int = QUESTIONS_PER_DAY,
                    questions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Draft answers for the best new threads. Never posts anything."""
    from . import link_engine

    questions = questions if questions is not None else await fetch_questions()
    coll = db[COLLECTIONS["links"]]
    drafted, errors = [], []
    for q in questions:
        if len(drafted) >= limit:
            break
        if await coll.find_one({"submit_url": q["url"]}, {"_id": 1}):
            continue
        text = f"{q['title']}\n\n{q['body']}".strip()
        try:
            row = await link_engine.draft_on_demand(db, "answer", text, q["url"], q["site"],
                                                    key=f"answer-{_rid(q['url'])}", source="finder")
            drafted.append(row["key"])
        except Exception as e:                                    # noqa: BLE001
            errors.append(f"{q['url']}: {str(e)[:120]}")
    return {"ok": True, "found": len(questions), "drafted": drafted, "errors": errors}


__all__ = ["score", "parse_reddit", "parse_hn", "fetch_questions", "run_daily", "QUESTIONS_PER_DAY"]
