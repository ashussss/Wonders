"""News engine — finds relevant industry news for content opportunities.

HOW IT GETS NEWS (compliance note)
-----------------------------------
Public RSS/Atom feeds fetched over plain HTTPS. No headless browser, no logged-in
session replay, no scraping of LinkedIn/Google SERPs. Google News RSS is a public,
machine-readable endpoint intended for consumption.

Filtering: only items whose title/summary match the tracked webinar/event-marketing
topic vocabulary survive, and only within ``GROWTH_NEWS_MAX_AGE_HOURS``. Items are
recorded in the Growth Engine's own ``growth_sources`` collection for provenance,
so a reviewer can see exactly which headline produced a campaign.
"""

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import httpx

from . import BRAND_NAME, COLLECTIONS, GROWTH_NEWS_FEEDS, GROWTH_NEWS_MAX_AGE_HOURS, IST
from .content_engine import ai_json
from .models import CampaignKind, CampaignDraft

logger = logging.getLogger("showup.growth.news")

USER_AGENT = "ShowUpAI-GrowthEngine/1.0 (+https://showupai.live) RSS reader"

# Only stories that touch our actual subject matter become campaigns.
RELEVANCE_TERMS = {
    "webinar": 3, "webinars": 3, "attendance": 3, "show-up": 3, "show up rate": 3,
    "registrant": 2, "registration": 1, "event marketing": 3, "event tech": 2,
    "virtual event": 3, "hybrid event": 3, "livestream": 2, "live stream": 2,
    "demand generation": 2, "demand gen": 2, "lead generation": 2, "b2b marketing": 2,
    "marketing automation": 2, "email marketing": 2, "linkedin": 2, "engagement rate": 2,
    "benchmark": 1, "report": 1, "conversion rate": 2, "no-show": 3, "community": 1,
    "personalisation": 1, "personalization": 1, "social selling": 2, "pipeline": 1,
}

# These make a story unusable for us no matter how well it matches.
BLOCK_TERMS = ("crypto", "nft", "bitcoin", "election", "football", "recipe", "horoscope")


_ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
             "&#39;": "'", "&apos;": "'", "&nbsp;": " ", "&hellip;": "…",
             "&mdash;": "—", "&ndash;": "–", "&rsquo;": "’", "&lsquo;": "‘",
             "&ldquo;": "“", "&rdquo;": "”", "&middot;": "·", "&bull;": "•"}


def _clean_text(t: str) -> str:
    """Strip tags then decode entities (named + numeric) and collapse whitespace."""
    t = re.sub(r"<[^>]+>", " ", t or "")
    for ent, ch in _ENTITIES.items():
        t = t.replace(ent, ch)
    t = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), t)
    t = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), t)
    t = re.sub(r"&[a-zA-Z]+;", " ", t)          # any remaining unknown entity -> space
    return re.sub(r"\s+", " ", t).strip()


def relevance_score(title: str, summary: str = "") -> int:
    """How on-topic is this story for a webinar-attendance product?"""
    blob = f"{title} {summary}".lower()
    if any(b in blob for b in BLOCK_TERMS):
        return 0
    return sum(w for term, w in RELEVANCE_TERMS.items() if term in blob)


def _parse_date(entry: ET.Element) -> Optional[datetime]:
    for tag in ("pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}updated"):
        raw = entry.findtext(tag)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


_HTML_ENTITY_RE = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|nbsp|#\d+|#x[0-9a-fA-F]+);)([a-zA-Z][a-zA-Z0-9]*);")


def _repair_entity(m: "re.Match[str]") -> str:
    """Known HTML entity -> its character, otherwise a space."""
    return _ENTITIES.get("&" + m.group(1).lower() + ";", " ")


def _parse_xml(xml: bytes):
    """Parse a feed, repairing undeclared HTML entities that break strict XML.

    Real publishers (and Google News) emit raw `&mdash;`-style entities that are
    not part of the XML spec. Without this, one such item aborts the whole feed and
    the engine silently finds zero news. Replace them with their character (or a
    space when unknown) before parsing.
    """
    try:
        return ET.fromstring(xml)
    except ET.ParseError:
        pass
    try:
        text = xml.decode("utf-8", "replace")
        repaired = _HTML_ENTITY_RE.sub(_repair_entity, text).encode("utf-8")
        return ET.fromstring(repaired)
    except (ET.ParseError, UnicodeError) as e:
        logger.warning(f"news_engine: unparseable feed: {e}")
        return None


def _parse_feed(xml: bytes, feed_url: str, cutoff: datetime) -> List[Dict[str, Any]]:
    root = _parse_xml(xml)
    if root is None:
        return []

    # RSS items and Atom entries share the same field names we need.
    nodes = root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry")
    out: List[Dict[str, Any]] = []
    for n in nodes:
        title = _clean_text(n.findtext("title") or "")
        if not title:
            continue
        link = (n.findtext("link") or "").strip()
        if not link:
            for a in n.findall(".//{http://www.w3.org/2005/Atom}link"):
                if a.get("rel") in (None, "alternate") and a.get("href"):
                    link = str(a.get("href"))
                    break
        summary = _clean_text(n.findtext("description") or n.findtext("summary") or "")[:1200]
        source = _clean_text(n.findtext("source") or n.findtext("author") or "")[:80]

        published = _parse_date(n)
        if published and published < cutoff:
            continue

        score = relevance_score(title, summary)
        if score < 3:
            continue

        out.append({
            "id": hashlib.md5(f"{feed_url}|{link or title}".encode()).hexdigest()[:16],
            "title": title[:300],
            "url": link,
            "summary": summary,
            "source": source or feed_url,
            "feed": feed_url,
            "published_at": (published or datetime.now(timezone.utc)).isoformat(),
            "relevance": score,
        })
    return out


async def fetch_news(feeds: List[str] | None = None,
                     max_age_hours: int = GROWTH_NEWS_MAX_AGE_HOURS) -> List[Dict[str, Any]]:
    """Fetch + filter all configured feeds. Returns newest-relevant first."""
    feeds = feeds or GROWTH_NEWS_FEEDS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    items: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=25, follow_redirects=True,
                                 headers={"User-Agent": USER_AGENT}) as c:
        for feed in feeds:
            try:
                r = await c.get(feed)
                if r.status_code >= 400:
                    logger.warning(f"news_engine: feed {feed} -> HTTP {r.status_code}")
                    continue
                items.extend(_parse_feed(r.content, feed, cutoff))
            except Exception as e:                               # noqa: BLE001
                logger.warning(f"news_engine: feed {feed} failed: {e}")

    seen, uniq = set(), []
    for it in sorted(items, key=lambda x: (x["relevance"], x["published_at"]), reverse=True):
        key = (it["url"] or it["title"]).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return uniq


async def record_sources(db, items: List[Dict[str, Any]]) -> None:
    """Persist provenance so a reviewer can audit which headline produced what."""
    for it in items:
        await db[COLLECTIONS["sources"]].update_one(
            {"id": it["id"]},
            {"$set": {**it, "seen_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )


async def triage(items: List[Dict[str, Any]], want: int = 2) -> List[Dict[str, Any]]:
    """AI triage: pick the stories a webinar host would actually care about.

    The keyword gate is a cheap pre-filter and is deliberately strict, but it
    under-selects (measured 2026-10-04: only 2 of 14 fresh trade headlines scored
    >= 3 because most are general B2B news, not webinar-specific). Letting the
    model judge relevance on the survivors — with an explicit "return an empty
    list if none qualify" instruction — recovers usable items without loosening
    the hard gate into noise.

    Falls back to keyword order if the AI call fails.
    """
    candidates = [i for i in items if i.get("relevance", 0) >= 2][:20]
    if not candidates:
        return []
    if len(candidates) <= want:
        return candidates[:want]

    lines = "\n".join(
        f"{n+1}. [{i['source']}] {i['title']}\n   {(i.get('summary') or '')[:220]}"
        for n, i in enumerate(candidates))
    prompt = f"""You triage news for {BRAND_NAME}, a webinar-attendance tool for B2B event hosts.

Pick exactly {want} stories that a webinar or virtual-event host would find genuinely useful —
a story they could react to with expertise and grow their audience. Prefer:
- attendance, registration, no-show rates, engagement, event tech, webinars
- demand generation, lead generation, B2B marketing benchmarks and reports
- marketing automation / AI changes that affect how event teams run webinars

Reject: consumer-brand campaigns, agency gossip, product funding news, sports,
entertainment, anything about crypto, and stories with no angle for an event host.

Stories:
{lines}

Return ONLY JSON: {{"picks": [numbers...]}} — the indexes of the best {want} stories.
If genuinely none qualify, return {{"picks": []}}. Do not invent indexes."""

    try:
        raw = await ai_json(prompt)
    except Exception as e:                                       # noqa: BLE001
        logger.warning(f"news_engine: triage AI failed ({e}); using keyword order")
        return candidates[:want]

    picks = raw.get("picks")
    out: List[Dict[str, Any]] = []
    if isinstance(picks, list):
        for p in picks[:want]:
            try:
                idx = int(p) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(candidates) and candidates[idx] not in out:
                out.append(candidates[idx])
    return out[:want] if out else candidates[:want]


async def pick_news(db, want: int = 2, exclude_ids: List[str] | None = None) -> List[Dict[str, Any]]:
    """Top unused news items: not already used by a Growth campaign, newest wins."""
    items = await fetch_news()
    if not items:
        return []
    await record_sources(db, items)
    ids = [i["id"] for i in items]
    used_rows = await db[COLLECTIONS["campaigns"]].find(
        {"kind": "news", "source_slug": {"$in": ids}}, {"_id": 0, "source_slug": 1}
    ).to_list(len(ids))
    used = {d["source_slug"] for d in used_rows if d.get("source_slug")}
    if exclude_ids:
        used |= set(exclude_ids)
    fresh = [i for i in items if i["id"] not in used]
    return await triage(fresh, want=want)


async def build_news_campaign(item: Dict[str, Any]) -> Optional[CampaignDraft]:
    """Build a campaign that reacts to a real industry story.

    The link points at the ORIGINAL source, not our blog — commenting on someone
    else's news and sending traffic there is the correct behaviour here.
    """
    from .content_engine import build_campaign

    angle = (
        "This reacts to a genuine industry story. Add a point of view a webinar host "
        "would actually act on — do not merely restate the headline, and do not claim "
        "figures the story does not contain. Cite the source by name in the copy. "
        "Link the original article; no URL in the caption itself."
    )

    fact_block = (
        "STORY FACTS — you may only refer to what is written here. Never add numbers, "
        "outcomes or quotes that are not in this summary:\n"
        f"Headline: {item['title']}\n"
        f"Source: {item['source']}\n"
        f"Summary: {item.get('summary') or '(none provided)'}"
    )

    return await build_campaign(
        "news",
        source_title=item["title"],
        source_body=item.get("summary") or "",
        source_url=item.get("url") or "",
        source_slug=item["id"],
        source_type="news",
        link_url=item.get("url") or "",
        link_title=item["title"],
        fact_block=fact_block,
        seed=f"news:{item['id']}",
        angle_hint=angle,
    )


__all__ = [
    "fetch_news",
    "pick_news",
    "record_sources",
    "build_news_campaign",
    "relevance_score",
    "RELEVANCE_TERMS",
    "CampaignKind",
]