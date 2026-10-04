"""Blog engine — detects ShowUpAI's own newly published blog posts.

READ-ONLY with respect to the production blog pipeline: this module only issues
``find``/``aggregate`` against ``blog_posts``. It never writes to blog_posts,
never calls ``publish_due``, never touches the pSEO scheduler, and never marks a
post as used. Deduplication for the Growth Engine lives in its own
``growth_campaigns`` collection, so the existing ``social_posts`` dedupe
(``source_slug`` + ``social_used_at``) is left completely untouched.

Detection window: any post published within the last N hours that has not yet had
a Growth Engine campaign built for it.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import COLLECTIONS, GROWTH_BLOG_CAMPAIGNS, SITE_URL
from .content_engine import ai_json
from .models import CampaignKind, CampaignDraft

logger = logging.getLogger("showup.growth.blog")

DEFAULT_WINDOW_HOURS = 30          # pSEO publishes up to 4/day, so look back a day+


def blog_url(slug: str) -> str:
    return f"{SITE_URL}/blog/{slug}"


def _as_dt(value: Any) -> Optional[datetime]:
    """blog_posts timestamps are ISO strings, but tolerate datetimes too."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


async def fetch_recent_published(db, window_hours: int = DEFAULT_WINDOW_HOURS,
                                 limit: int = 50) -> List[Dict[str, Any]]:
    """Return recently published blog posts, newest first."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    rows = await db.blog_posts.find(
        {"published": True},
        {"_id": 0, "slug": 1, "title": 1, "excerpt": 1, "content": 1,
         "keyword": 1, "published_at": 1, "sources": 1, "reading_time": 1},
    ).sort("published_at", -1).to_list(limit)

    out = []
    for r in rows:
        dt = _as_dt(r.get("published_at"))
        if dt and dt >= cutoff:
            r["published_dt"] = dt
            out.append(r)
    return out


async def unprocessed_slugs(db, slugs: List[str]) -> set:
    """Which of these slugs already have a Growth Engine campaign?

    Uses only the Growth Engine's own collection — the existing social_posts
    dedupe is deliberately not consulted, so the two systems stay independent.
    """
    slugs = [s for s in slugs if s]
    if not slugs:
        return set()
    rows = await db[COLLECTIONS["campaigns"]].find(
        {"kind": "blog", "source_slug": {"$in": slugs}}, {"_id": 0, "source_slug": 1}
    ).to_list(len(slugs))
    return {r["source_slug"] for r in rows if r.get("source_slug")}


async def pick_todays_posts(db, want: int = GROWTH_BLOG_CAMPAIGNS,
                            window_hours: int = DEFAULT_WINDOW_HOURS) -> List[Dict[str, Any]]:
    """Pick up to ``want`` recent posts that have no Growth campaign yet."""
    recent = await fetch_recent_published(db, window_hours=window_hours, limit=100)
    if not recent:
        return []
    done = await unprocessed_slugs(db, [r.get("slug") or "" for r in recent])
    fresh = [r for r in recent if r.get("slug") and r["slug"] not in done]
    return fresh[:want]


def _fact_block(post: Dict[str, Any]) -> str:
    """Only pass through sources the post actually cites — prevents invention."""
    sources = post.get("sources") or []
    lines = []
    for s in sources[:6]:
        if isinstance(s, dict) and s.get("source"):
            lines.append(f"- {s['source']}: {s.get('url') or ''}".strip())
    if not lines:
        return ("SOURCED FACTS: none provided for this post. Do NOT state any statistic "
                "or study finding in the copy. Write practical advice instead.")
    return ("SOURCED FACTS — you may cite ONLY these, naming the source exactly:\n"
            + "\n".join(lines))


def _source_note(post: Dict[str, Any]) -> str:
    """Prevents the AI from inventing facts that aren't in the article."""
    wc = post.get("word_count") or 0
    bits = []
    if post.get("keyword"):
        bits.append(f"Target keyword: {post['keyword']}")
    if wc:
        bits.append(f"Article length: {wc} words")
    if post.get("reading_time"):
        bits.append(f"Reading time: {post['reading_time']} min")
    return "ARTICLE FACTS: " + ("; ".join(bits) if bits else "none provided") + \
        "\nOnly make claims that are actually supported by the article body above."


async def build_blog_campaign(db, post: Dict[str, Any]) -> Optional[CampaignDraft]:
    """Build one campaign from a published blog post. Does NOT persist it."""
    from .content_engine import build_campaign

    slug = post.get("slug") or ""
    body = post.get("content") or ""
    title = post.get("title") or ""

    angle = (
        "This is a native social campaign promoting a ShowUpAI article that already exists. "
        "Lead with the single most useful, specific takeaway a reader would steal for their next "
        "webinar. Do not summarise the whole article — give one concrete idea worth clicking through. "
        "Link to the article; the caption itself must not contain a URL."
    )

    return await build_campaign(
        "blog",
        source_title=title,
        source_body=body,
        source_url=blog_url(slug),
        source_slug=slug,
        source_type="blog",
        link_url=blog_url(slug),
        link_title=title,
        fact_block=f"{_fact_block(post)}\n\n{_source_note(post)}",
        seed=f"blog:{slug}",
        angle_hint=angle,
    )


__all__ = [
    "fetch_recent_published",
    "pick_todays_posts",
    "unprocessed_slugs",
    "build_blog_campaign",
    "blog_url",
    "DEFAULT_WINDOW_HOURS",
    "CampaignKind",
]