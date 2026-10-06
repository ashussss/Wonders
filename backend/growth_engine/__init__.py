"""ShowUpAI Growth Engine — isolated autonomous growth/content + prospecting system.

This package is deliberately SEPARATE from the production social/webinar system:

* It never writes to ``social_posts``, ``webinars``, ``touches``, ``registrants``
  or any other existing collection. It only READS ``blog_posts`` (blog detection).
* It owns its own queue (``growth_campaigns``), its own asset bucket
  (``growth_assets_fs``) and its own prospecting/analytics collections.
* It has its own API prefix ``/api/growth`` and its own scheduler job.
* Publishing reuses the read-only platform helpers in ``social.py``
  (``post_linkedin`` / ``post_facebook`` / ``post_instagram``) but writes its own
  results to its own collection. ``social.publish_post`` is never called.

SAFETY: approval mode is the default. Nothing is published until a campaign has
been explicitly approved AND GROWTH_AUTO_PUBLISH=true. See APPROVAL_MODE below.
"""

import os
from datetime import timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _csv(name: str, default: str) -> list:
    return [p.strip() for p in os.environ.get(name, default).split(",") if p.strip()]


# ── Master switches ──────────────────────────────────────────────────────────
# GROWTH_ENABLED gates the daily generation job (draft creation only).
GROWTH_ENABLED = _flag("GROWTH_ENABLED", "true")

# APPROVAL MODE — the hard default. Campaigns sit in `pending_review` until a
# human approves them. The dispatcher will not publish while this is True.
APPROVAL_MODE = _flag("GROWTH_APPROVAL_MODE", "true")

# Second, independent gate. Both must be open before anything reaches a platform.
GROWTH_AUTO_PUBLISH = _flag("GROWTH_AUTO_PUBLISH", "false")

# ── Campaign targets ─────────────────────────────────────────────────────────
GROWTH_CAMPAIGNS_PER_DAY = _int("GROWTH_CAMPAIGNS_PER_DAY", 9)
GROWTH_BLOG_CAMPAIGNS = _int("GROWTH_BLOG_CAMPAIGNS", 4)   # from today's blogs
GROWTH_NEWS_CAMPAIGNS = _int("GROWTH_NEWS_CAMPAIGNS", 2)   # industry news
GROWTH_PAIN_CAMPAIGNS = _int("GROWTH_PAIN_CAMPAIGNS", 2)   # webinar/event pain-point lead-gen
GROWTH_ENGAGEMENT_CAMPAIGNS = _int("GROWTH_ENGAGEMENT_CAMPAIGNS", 1)

GROWTH_PLATFORMS = _csv("GROWTH_PLATFORMS", "linkedin,facebook,instagram")
GROWTH_SLOTS_IST = _csv(
    "GROWTH_SLOTS_IST",
    # 4 blog + 2 news + 2 pain + 1 engagement = 9 slots across the working day
    "09:00,10:15,11:30,12:45,14:00,15:15,16:30,18:00,19:30",
)

# ── Prospecting ──────────────────────────────────────────────────────────────
# LinkedIn has no public people-search API for the Marketing API tier. We never
# emulate a browser or scrape a logged-in session. Prospects are imported from a
# user-provided, ToS-compliant source (e.g. an Apollo export or a Sales Navigator
# CSV the user is entitled to use). See prospect_engine.PROVIDER_CONTRACT.
GROWTH_PROSPECT_PROVIDER = os.environ.get("GROWTH_PROSPECT_PROVIDER", "import").strip().lower()
GROWTH_PROSPECT_DAILY_LIMIT = _int("GROWTH_PROSPECT_DAILY_LIMIT", 25)
# Hard guardrail: the engine may RECOMMEND engagement, never execute it.
GROWTH_ALLOW_AUTOMATED_ENGAGEMENT = False  # not configurable by design

# ── News discovery ───────────────────────────────────────────────────────────
# Plain public RSS over HTTP. No headless browser, no authenticated scraping.
FEEDS_ENV = "GROWTH_NEWS_FEEDS"

# Default: real trade publications that publish every weekday. Google News
# *search* RSS was removed deliberately — it is dominated by evergreen vendor
# pages whose pubDate can be years old, which silently starves the pipeline.
# Measured 2026-10-04: search feeds returned 0 items under 48h; these return 5-15.
_DEFAULT_FEEDS = [
    "https://www.marketingdive.com/feeds/news/",     # B2B marketing news, daily
    "https://www.marketingweek.com/feed/",           # UK/EU agency + B2B, daily
    "https://www.b2bmarketing.net/feed",             # demand gen / events, daily
    "https://martech.org/feed/",                     # martech + AI in marketing
]
# Verified dead / not resolving as of 2026-10-04 — kept out of the defaults:
#   mybestwebinars.com/blog/feed, webinarbureau.com/blog/feed (NXDOMAIN)
# Add your own via GROWTH_NEWS_FEEDS; every feed failure is non-fatal.

GROWTH_NEWS_MAX_AGE_HOURS = _int("GROWTH_NEWS_MAX_AGE_HOURS", 96)

# ── News discovery ───────────────────────────────────────────────────────────
# Plain public RSS over HTTP. No headless browser, no authenticated scraping.
GROWTH_NEWS_FEEDS = _csv("GROWTH_NEWS_FEEDS", ",".join(_DEFAULT_FEEDS))

# ── Brand ────────────────────────────────────────────────────────────────────
SITE_URL = os.environ.get("SITE_URL", "https://showupai.live")
BRAND_NAME = os.environ.get("BRAND_NAME", "ShowUpAI")

# ── Collections (all new — nothing existing is reused or mutated) ────────────
COLLECTIONS = {
    "campaigns": "growth_campaigns",
    "sources": "growth_sources",
    "assets": "growth_assets",
    "prospects": "growth_prospects",
    "activity": "growth_prospect_activity",
    "metrics": "growth_metrics",
    "learning": "growth_learning",
}

ASSET_BUCKET = "growth_assets_fs"

CAMPAIGN_KINDS = ("blog", "news", "pain_point", "engagement")

FUNNEL_STAGES = ("awareness", "consideration", "intent", "conversion", "retention")

VISUAL_FORMATS = (
    "carousel",
    "infographic",
    "stat_card",
    "checklist",
    "comparison",
    "quote",
)

__all__ = [
    "IST",
    "APPROVAL_MODE",
    "GROWTH_ENABLED",
    "GROWTH_AUTO_PUBLISH",
    "GROWTH_CAMPAIGNS_PER_DAY",
    "GROWTH_BLOG_CAMPAIGNS",
    "GROWTH_NEWS_CAMPAIGNS",
    "GROWTH_PAIN_CAMPAIGNS",
    "GROWTH_ENGAGEMENT_CAMPAIGNS",
    "GROWTH_PLATFORMS",
    "GROWTH_SLOTS_IST",
    "GROWTH_NEWS_FEEDS",
    "GROWTH_NEWS_MAX_AGE_HOURS",
    "GROWTH_ALLOW_AUTOMATED_ENGAGEMENT",
    "COLLECTIONS",
    "ASSET_BUCKET",
    "CAMPAIGN_KINDS",
    "FUNNEL_STAGES",
    "VISUAL_FORMATS",
    "SITE_URL",
    "BRAND_NAME",
]