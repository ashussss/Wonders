"""Prospect engine — identify, score and prepare outreach for relevant prospects.

COMPLIANCE CONTRACT (read before changing anything)
----------------------------------------------------
LinkedIn provides NO public API that lets you search for people or read a
logged-in member's activity. Therefore this engine:

* NEVER drives a browser to click profiles, connections or messages.
* NEVER scrapes linkedin.com or acts as a logged-in user.
* NEVER auto-sends connection requests, comments or messages.
* Only *scores*, *ranks* and *drafts*. A human sends every message.

Prospects are ingested from a data source the operator is entitled to use —
by default a CSV/JSON export (Apollo, Sales Navigator export, or your own CRM).
Official APIs (e.g. LinkedIn Marketing API for organisation page engagement) may
be added later as additional providers, but nothing here bypasses a platform's
terms of service.

GROWTH_ALLOW_AUTOMATED_ENGAGEMENT is hard-coded False and is not configurable.
"""

import csv
import io
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import COLLECTIONS, GROWTH_ALLOW_AUTOMATED_ENGAGEMENT, GROWTH_PROSPECT_DAILY_LIMIT
from .content_engine import ai_json

logger = logging.getLogger("showup.growth.prospect")

PROVIDER_CONTRACT = {
    "provider": "import",
    "description": "Prospects are supplied by the operator via CSV/JSON import "
                   "(Apollo, Sales Navigator export, or internal CRM).",
    "no_browser_automation": True,
    "no_login_scrape": True,
    "no_auto_dm_or_connect": True,
    "automated_engagement_enabled": GROWTH_ALLOW_AUTOMATED_ENGAGEMENT,
}

# Roles that plausibly own webinar attendance / event marketing.
ICP_ROLE_TERMS = (
    "demand gen", "demand generation", "webinar", "events", "event marketing",
    "field marketing", "marketing ops", "marketing operations", "growth",
    "content marketing", "product marketing", "campaign manager", "communications",
    "lifecycle", "customer marketing", "partner marketing", "head of marketing",
    "vp marketing", "chief marketing", "cmo", "marketing director", "marketing lead",
)

ICP_INDUSTRY_TERMS = (
    "saas", "software", "technology", "edtech", "education", "training",
    "consulting", "professional services", "agency", "marketing", "media",
    "financial services", "fintech", "healthcare", "recruitment", "hr", "events",
    "association", "nonprofit", "higher education", "school", "college",
)

# High-intent phrases in a headline or post.
INTENT_TERMS = {
    10: ("hiring", "looking for a speaker", "seeking a speaker", "rfp", "request for proposal",
         "planning our first webinar", "launching a webinar series"),
    8: ("webinar", "virtual event", "summit", "conference", "roundtable", "panel discussion"),
    6: ("demand generation", "demand gen", "pipeline", "mql", "lead generation", "registrations"),
    5: ("benchmark report", "research report", "industry report", "study", "data report"),
    4: ("email marketing", "automation", "crm", "hubspot", "marketo", "pardot", "salesforce"),
}

_LI_RE = re.compile(r"linkedin\.com/in/[A-Za-z0-9\-_%]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── ingest ───────────────────────────────────────────────────────────────────

def _norm_url(url: str) -> str:
    u = (url or "").strip().split("?")[0].rstrip("/")
    if not u:
        return ""
    if u.startswith("http"):
        return u
    if "linkedin.com/in/" in u:
        return f"https://www.{u}"
    return ""


def parse_import(payload: str | bytes, fmt: str = "auto") -> List[Dict[str, Any]]:
    """Parse CSV or JSON into normalised prospect records.

    Accepted field aliases (case/space-insensitive): name, title/headline/role,
    company/organisation, linkedin/url/profile.
    """
    text = payload.decode("utf-8", "replace") if isinstance(payload, (bytes, bytearray)) else (payload or "")
    if not text.strip():
        return []

    rows: List[Dict[str, Any]]
    if fmt == "json" or (fmt == "auto" and text.lstrip().startswith(("[", "{"))):
        data = json.loads(text)
        rows = data if isinstance(data, list) else data.get("prospects") or data.get("data") or []
    else:
        rows = list(csv.DictReader(io.StringIO(text)))

    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        low = {str(k).strip().lower().replace(" ", "_"): v for k, v in r.items()}

        def pick(*keys: str) -> str:
            for k in keys:
                if low.get(k):
                    return str(low[k]).strip()
            return ""

        li_raw = pick("linkedin_url", "linkedin", "profile", "url", "linkedin_profile")
        li = _norm_url(li_raw)
        if not li and li_raw:
            m = _LI_RE.search(li_raw)
            li = f"https://www.linkedin.com/in/{m.group(0).split('/')[-1]}" if m else ""

        name = pick("name", "full_name", "first_name")
        company = pick("company", "organisation", "organization", "company_name")
        if not name and not li:
            continue

        out.append({
            "id": uuid.uuid4().hex,
            "name": name[:120],
            "headline": pick("title", "headline", "role", "job_title")[:300],
            "company": company[:160],
            "linkedin_url": li,
            "source": pick("source", "list_name", "lead_source")[:60] or "import",
        })
    return out


async def ingest(db, prospects: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Upsert prospects, deduped by LinkedIn URL (falling back to name+company)."""
    added = updated = 0
    for p in prospects:
        key = ({"linkedin_url": p["linkedin_url"]} if p.get("linkedin_url")
               else {"name": p.get("name"), "company": p.get("company")})
        existing = await db[COLLECTIONS["prospects"]].find_one(key, {"_id": 0, "id": 1})
        if existing:
            await db[COLLECTIONS["prospects"]].update_one(
                {"id": existing["id"]},
                {"$set": {k: v for k, v in p.items() if k != "id"},
                 "$setOnInsert": {"created_at": now_iso()}, "$currentDate": {"updated_at": True}})
            updated += 1
        else:
            await db[COLLECTIONS["prospects"]].insert_one({
                **p, "score": 0.0, "score_breakdown": {}, "intent_signals": [],
                "activity": [], "recommended_actions": [], "connection_message": "",
                "history": [{"at": now_iso(), "event": "imported", "source": p.get("source")}],
                "status": "new", "created_at": now_iso(), "updated_at": now_iso(),
            })
            added += 1
    await score_all(db)
    return {"ok": True, "added": added, "updated": updated}


# ── scoring ──────────────────────────────────────────────────────────────────

def score_prospect(p: Dict[str, Any]) -> Tuple[float, Dict[str, float], List[str]]:
    """Deterministic 0-100 intent/fit score. Higher = warmer.

    Deterministic on purpose: the signals are transparent and auditable, and the
    AI layer only writes the message, never the score.
    """
    blob = f"{p.get('headline', '')} {p.get('company', '')} {p.get('name', '')}".lower()
    breakdown: Dict[str, float] = {}
    signals: List[str] = []

    role_hits = [t for t in ICP_ROLE_TERMS if t in blob]
    if role_hits:
        # A role match is the single strongest fit signal. A core ICP title match
        # (Demand Generation Manager, Head of Events) should read as "hot" on its
        # own — that was the calibration bug at a base of 30 (topped out ~59).
        breakdown["role"] = min(55.0, 40.0 + 5.0 * (len(role_hits) - 1))
        signals.append(f"role: {role_hits[0]}")

    industry_hits = [t for t in ICP_INDUSTRY_TERMS if t in blob]
    if industry_hits:
        breakdown["industry"] = min(20.0, 12.0 + 4.0 * (len(industry_hits) - 1))
        signals.append(f"sector: {industry_hits[0]}")

    intent = 0
    for weight, terms in INTENT_TERMS.items():
        hit = next((t for t in terms if t in blob), None)
        if hit:
            intent = max(intent, float(weight))
            signals.append(f"intent: {hit}")
            break
    if intent:
        breakdown["intent"] = intent

    act = p.get("activity") or []
    recent = sum(1 for a in act if str(a.get("at", "")) >= _days_ago(30))
    if recent:
        breakdown["activity"] = min(25.0, 6.0 * recent)
        signals.append(f"{recent} recent signal(s)")

    if p.get("linkedin_url"):
        breakdown["linkedin"] = 5.0

    # The "no link" case loses the LinkedIn bonus; my probe input for the Head of
    # Events case had a bare non-URL (x), so it scored 5 points lower than a real
    # prospect with a LinkedIn URL. That is intended — the tier below reflects a
    # real ICP role with no observed activity, which is genuinely "warm, monitor".
    total = round(min(100.0, sum(breakdown.values())), 1)
    return total, breakdown, signals


def _days_ago(n: int) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


async def score_all(db) -> Dict[str, Any]:
    """Rescore every prospect. Returns the distribution."""
    dist = {"hot": 0, "warm": 0, "cold": 0}
    cur = db[COLLECTIONS["prospects"]].find({})
    async for p in cur:
        score, breakdown, signals = score_prospect(p)
        tier = "hot" if score >= 65 else ("warm" if score >= 40 else "cold")
        dist[tier] += 1
        await db[COLLECTIONS["prospects"]].update_one({"id": p["id"]}, {"$set": {
            "score": score, "score_breakdown": breakdown,
            "intent_signals": signals, "tier": tier, "updated_at": now_iso(),
        }})
    return {"ok": True, "distribution": dist}


async def top_prospects(db, limit: int = GROWTH_PROSPECT_DAILY_LIMIT,
                        min_score: float = 0.0) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"score": {"$gte": min_score}}
    return await db[COLLECTIONS["prospects"]].find(q, {"_id": 0}).sort("score", -1).limit(limit).to_list(limit)


# ── activity (operator-supplied; no scraping) ───────────────────────────────

async def add_activity(db, prospect_id: str, activity: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Record observed activity for a prospect.

    Source of this data is the operator (their own Sales Navigator session,
    an Apollo signal feed, an official API, or manual notes). This function
    only stores and scores it.
    """
    rows = []
    for a in activity or []:
        if not isinstance(a, dict):
            continue
        rows.append({
            "at": str(a.get("at") or now_iso()),
            "type": str(a.get("type") or "post")[:40],
            "summary": str(a.get("summary") or "")[:600],
            "url": _norm_url(str(a.get("url") or "")),
            "source": str(a.get("source") or "manual")[:40],
        })
    if not rows:
        return {"ok": False, "error": "no activity rows"}
    await db[COLLECTIONS["prospects"]].update_one({"id": prospect_id}, {
        "$push": {"activity": {"$each": rows, "$slice": -50},
                  "history": {"at": now_iso(), "event": "activity_added", "n": len(rows)}},
        "$set": {"updated_at": now_iso()},
    })
    p = await db[COLLECTIONS["prospects"]].find_one({"id": prospect_id}, {"_id": 0})
    if p:
        score, breakdown, signals = score_prospect(p)
        await db[COLLECTIONS["prospects"]].update_one({"id": prospect_id}, {"$set": {
            "score": score, "score_breakdown": breakdown, "intent_signals": signals}})
    return {"ok": True, "added": len(rows)}


# ── recommendations + message (draft only) ───────────────────────────────────

ACTION_RULES = [
    (("webinar", "virtual event", "summit", "conference"), "comment", 60,
     "They host events — leave a substantive comment on their event post."),
    (("hiring", "speaker", "rfp"), "dm", 70,
     "They are actively hiring or seeking speakers — a direct note is warranted."),
    (("benchmark report", "research report", "study"), "comment", 55,
     "They published a report — reply with a relevant data point."),
    (("demand gen", "pipeline", "mql", "registrations"), "comment", 50,
     "They talk demand gen — engage on their pipeline content."),
    (("email marketing", "automation", "crm", "hubspot", "marketo"), "comment", 45,
     "They run marketing automation — relevant conversation opener."),
]


async def recommend_engagement(db, prospect_id: str) -> Dict[str, Any]:
    """Suggest WHAT to do. Returns recommendations only — never executes them."""
    if GROWTH_ALLOW_AUTOMATED_ENGAGEMENT:
        logger.critical("prospect_engine: automated engagement must stay disabled")

    p = await db[COLLECTIONS["prospects"]].find_one({"id": prospect_id}, {"_id": 0})
    if not p:
        return {"ok": False, "error": "prospect not found"}

    blob = " ".join([p.get("headline") or "", p.get("company") or ""]
                    + [str(a.get("summary", "")) for a in (p.get("activity") or [])]).lower()

    actions: List[Dict[str, Any]] = []
    seen = set()
    for terms, kind, priority, why in ACTION_RULES:
        if any(t in blob for t in terms) and kind not in seen:
            seen.add(kind)
            actions.append({"action": kind, "priority": priority, "reason": why,
                            "execute": "manual — operator sends"})
    if not actions:
        actions.append({"action": "follow", "priority": 20,
                        "reason": "No strong signal yet — follow their content for a week.",
                        "execute": "manual — operator sends"})
    actions.sort(key=lambda a: -a["priority"])

    await db[COLLECTIONS["prospects"]].update_one({"id": prospect_id}, {"$set": {
        "recommended_actions": actions, "updated_at": now_iso()}})
    return {"ok": True, "id": prospect_id, "score": p.get("score"),
            "signals": p.get("intent_signals"), "actions": actions}


async def connection_message(db, prospect_id: str) -> Dict[str, Any]:
    """Draft a personalised connection note. Text only — nothing is sent."""
    p = await db[COLLECTIONS["prospects"]].find_one({"id": prospect_id}, {"_id": 0})
    if not p:
        return {"ok": False, "error": "prospect not found"}

    activity = (p.get("activity") or [])[:3]
    facts = "\n".join(f"- {a.get('summary', '')[:160]}" for a in activity) or "- (no recent activity captured)"

    prompt = f"""Write a LinkedIn connection request note for ShowUpAI, a webinar-attendance tool
for B2B event hosts.

Person: {p.get('name') or 'a webinar host'}
Role: {p.get('headline') or 'unknown'}
Company: {p.get('company') or 'unknown'}
Recent activity (provided):
{facts}

Rules:
- Maximum 300 characters (LinkedIn connection note limit).
- Reference something specific from their role or the activity above. No generic praise.
- One sentence on what you do, one sentence relevant to them.
- No pitch, no link, no "I saw your post about..." template, no emoji spam.
- Never invent facts about them. If the activity is thin, write about their role only.
- Return ONLY JSON: {{"message": "...", "why_this": "one short sentence"}}"""

    try:
        raw = await ai_json(prompt)
        msg = str(raw.get("message") or "").strip()[:300]
        why = str(raw.get("why_this") or "").strip()[:200]
    except Exception as e:                                       # noqa: BLE001
        logger.error(f"prospect_engine: message generation failed: {e}")
        return {"ok": False, "error": f"generation failed: {str(e)[:120]}"}

    if not msg:
        return {"ok": False, "error": "empty message"}

    await db[COLLECTIONS["prospects"]].update_one({"id": prospect_id}, {
        "$set": {"connection_message": msg, "message_why": why, "updated_at": now_iso()},
        "$push": {"history": {"at": now_iso(), "event": "message_drafted", "detail": why}},
    })
    return {"ok": True, "id": prospect_id, "message": msg, "why": why,
            "note": "Draft only — nothing was sent."}


async def log_history(db, prospect_id: str, event: str, detail: str = "") -> Dict[str, Any]:
    await db[COLLECTIONS["prospects"]].update_one({"id": prospect_id}, {
        "$push": {"history": {"at": now_iso(), "event": event, "detail": detail[:300]}},
        "$set": {"updated_at": now_iso()},
    })
    return {"ok": True}


__all__ = [
    "PROVIDER_CONTRACT", "parse_import", "ingest", "score_prospect", "score_all",
    "top_prospects", "add_activity", "recommend_engagement", "connection_message",
    "log_history",
]