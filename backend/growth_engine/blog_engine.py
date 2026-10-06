"""Blog engine — detects ShowUpAI's own newly published blog posts.

READ-ONLY with respect to the production blog pipeline: this module only issues
``find``/``aggregate`` against ``blog_posts``. It never writes to blog_posts,
never calls ``publish_due``, never touches the pSEO scheduler, and never marks a
post as used. Deduplication for the Growth Engine lives in its own
``growth_campaigns`` collection. ``social_posts`` is only READ, to skip posts the
existing social autopilot has already promoted (no double posting).

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
    done |= await promoted_by_social_autopilot(db, [r.get("slug") or "" for r in recent])
    fresh = [r for r in recent if r.get("slug") and r["slug"] not in done]
    return fresh[:want]


async def promoted_by_social_autopilot(db, slugs: List[str]) -> set:
    """Slugs the existing social.py autopilot already queued a blog promo for.

    Read-only. social.queue_blog_promo fires at publish time (auto-approved by
    default), so without this check the same post would go out twice on the
    same channels: once from social_posts and once from growth_campaigns.
    """
    slugs = [s for s in slugs if s]
    if not slugs:
        return set()
    rows = await db.social_posts.find(
        {"kind": "blog", "source_slug": {"$in": slugs}}, {"_id": 0, "source_slug": 1}
    ).to_list(len(slugs))
    return {r["source_slug"] for r in rows if r.get("source_slug")}


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


async def build_blog_campaign(db, post: Dict[str, Any], **overrides: Any) -> Optional[CampaignDraft]:
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
        **overrides,
    )


# ── evergreen + competitor picks ─────────────────────────────────────────────

EVERGREEN_COOLDOWN_DAYS = 30

# Slugs/titles that read as "us vs them". "-vs-" alone is not enough: plenty of
# posts compare two approaches (live vs on-demand), so it must also name a tool.
_ALT_WORDS = ("alternative", "alternatives")
_TOOL_NAMES = ("zoom", "webex", "livestorm", "goto", "gotowebinar", "on24", "bigmarker", "demio",
               "hubspot", "mailchimp", "streamyard", "airmeet", "hopin", "riverside", "teams",
               "eventbrite", "luma", "restream", "vimeo", "contrast", "zuddl", "hubilo", "cvent")


def is_competitor_post(post: Dict[str, Any]) -> bool:
    text = f"{post.get('slug') or ''} {post.get('title') or ''}".lower()
    if any(w in text for w in _ALT_WORDS):
        return True
    has_vs = "-vs-" in text or " vs " in text or " vs. " in text or "versus" in text
    return has_vs and any(t in text for t in _TOOL_NAMES)


async def _recently_used(db, kinds: List[str], days: int) -> set:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = await db[COLLECTIONS["campaigns"]].find(
        {"kind": {"$in": kinds}, "created_at": {"$gte": cutoff}}, {"_id": 0, "source_slug": 1}
    ).to_list(1000)
    return {r["source_slug"] for r in rows if r.get("source_slug")}


async def _all_published(db, limit: int = 500) -> List[Dict[str, Any]]:
    return await db.blog_posts.find(
        {"published": True},
        {"_id": 0, "slug": 1, "title": 1, "excerpt": 1, "content": 1,
         "keyword": 1, "published_at": 1, "sources": 1, "reading_time": 1},
    ).sort("published_at", -1).to_list(limit)


def _rotate(rows: List[Dict[str, Any]], seed: str) -> Optional[Dict[str, Any]]:
    if not rows:
        return None
    return rows[sum(seed.encode()) % len(rows)]


async def pick_blog_post(db, seed: str = "") -> Optional[Dict[str, Any]]:
    """Today's fresh post if there is one, else an older post not promoted recently.

    The weekly plan has blog days even when pSEO published nothing new, and the
    library is worth resurfacing: a good article keeps earning clicks.
    """
    fresh = await pick_todays_posts(db, want=1)
    if fresh:
        return fresh[0]
    used = await _recently_used(db, ["blog", "competitor"], EVERGREEN_COOLDOWN_DAYS)
    # Comparison articles are saved for the competitor day.
    rows = [r for r in await _all_published(db)
            if r.get("slug") and r["slug"] not in used and not is_competitor_post(r)]
    return _rotate(rows, seed)


async def pick_competitor_post(db, seed: str = "") -> Optional[Dict[str, Any]]:
    """A published alternative / vs article not used for a competitor post recently."""
    used = await _recently_used(db, ["competitor"], EVERGREEN_COOLDOWN_DAYS)
    rows = [r for r in await _all_published(db)
            if r.get("slug") and r["slug"] not in used and is_competitor_post(r)]
    return _rotate(rows, seed)


async def build_competitor_campaign(db, post: Dict[str, Any], **overrides: Any) -> Optional[CampaignDraft]:
    """Alternative / vs post built from one of our own comparison articles."""
    from .content_engine import build_campaign

    slug = post.get("slug") or ""
    angle = (
        "COMPETITOR / ALTERNATIVE post built from our own comparison article. Help someone who is "
        "choosing a tool right now. Be fair and specific: say who the other option suits, then "
        "where ShowUpAI is the better fit. Only state differences the article itself states. "
        "Never mock or attack the other product. Never claim pricing, features or numbers about "
        "another company that are not in the article."
    )
    return await build_campaign(
        "competitor",
        source_title=post.get("title") or "",
        source_body=post.get("content") or "",
        source_url=blog_url(slug),
        source_slug=slug,
        source_type="blog",
        link_url=blog_url(slug),
        link_title=post.get("title") or "",
        fact_block=f"{_fact_block(post)}\n\n{_source_note(post)}",
        seed=f"competitor:{slug}",
        angle_hint=angle,
        **overrides,
    )


__all__ = [
    "fetch_recent_published",
    "pick_todays_posts",
    "unprocessed_slugs",
    "build_blog_campaign",
    "build_competitor_campaign",
    "pick_blog_post",
    "pick_competitor_post",
    "is_competitor_post",
    "blog_url",
    "DEFAULT_WINDOW_HOURS",
    "CampaignKind",
]