"""Campaign status for a webinar: what each touch will do, what it did, and how it went.

One read-only view for the host (or the agency's client) of:
- the send schedule, with a plain state per touch (needs approval, scheduled, sending, sent...)
- email results per touch (invite list and registrants, sent / failed, live progress)
- the posts each touch made (LinkedIn / Facebook links) and, where LinkedIn allows it,
  likes and comments on the LinkedIn posts.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger("showup.campaign_status")

SOCIAL = ("linkedin", "linkedin_personal", "linkedin_page", "facebook", "facebook_page", "instagram", "circle")
LI_CHANNELS = ("linkedin", "linkedin_personal", "linkedin_page")
LI_STATS_TTL = timedelta(minutes=30)


def touch_state(t: Dict[str, Any], auto_send: bool, now_iso: str) -> str:
    """One word the UI can colour: sent, failed, sending, queued, scheduled, manual,
    needs_approval, missed, rejected, on_registration, limit_wait (daily email limit
    reached, the rest of the list goes out the next day)."""
    s = t.get("sent_status") or "planned"
    if t.get("invite_backlog") and s == "planned":
        return "limit_wait"
    if s in ("sent", "failed", "sending", "queued"):
        return s
    if t.get("approval_status") == "rejected":
        return "rejected"
    if not t.get("scheduled_at"):
        return "on_registration"
    past = t["scheduled_at"] <= now_iso
    if t.get("approval_status") != "approved":
        return "missed" if past else "needs_approval"
    if not auto_send:
        return "manual"
    return "scheduled"


def email_counts(log: List[Dict[str, Any]], progress: Optional[Dict[str, Any]]) -> Dict[str, int]:
    out = {"invite_sent": 0, "invite_failed": 0, "invite_total": 0, "invite_held": 0, "reg_sent": 0, "reg_failed": 0}
    for d in log or []:
        if d.get("channel") != "email":
            continue
        if "invite_sent" in d:
            out["invite_sent"] += int(d.get("invite_sent") or 0)
            out["invite_failed"] += int(d.get("invite_failed") or 0)
            out["invite_total"] += int(d.get("invite_total") or 0)
            out["invite_held"] += int(d.get("invite_held") or 0)
        elif str(d.get("recipient") or "").startswith("invite list"):
            # Older log line: "invite list: 12 sent, 3 failed (...)"
            import re
            m = re.search(r"(\d+) sent, (\d+) failed", d.get("detail") or "")
            if m:
                out["invite_sent"] += int(m.group(1))
                out["invite_failed"] += int(m.group(2))
        elif d.get("recipient"):
            out["reg_sent" if d.get("ok") else "reg_failed"] += 1
    # While a list is going out the log is empty: show the live counter instead.
    if progress and not progress.get("done") and not out["invite_total"]:
        out["invite_sent"] = int(progress.get("sent") or 0)
        out["invite_failed"] = int(progress.get("failed") or 0)
        out["invite_total"] = int(progress.get("total") or 0)
    return out


def posts(log: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for d in log or []:
        if d.get("channel") in SOCIAL:
            out.append({"channel": d["channel"], "ok": bool(d.get("ok")), "url": d.get("url") or "",
                        "external_id": d.get("external_id") or "",
                        "detail": "" if d.get("ok") else (d.get("detail") or "")[:200]})
    return out


def errors(log: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    """First few distinct failure reasons, for the touch's row."""
    seen: List[str] = []
    for d in log or []:
        if d.get("ok") and not d.get("invite_failed"):
            continue
        msg = f"{d.get('channel')}: {(d.get('detail') or '')[:160]}"
        if msg not in seen:
            seen.append(msg)
        if len(seen) >= limit:
            break
    return seen


async def build(db, w: Dict[str, Any], settings: Dict[str, Any], auto_send_fn) -> Dict[str, Any]:
    import invites
    wid, owner = w["id"], w["owner_id"]
    now = datetime.now(timezone.utc).isoformat()
    inv = await invites.summary(db, wid)
    reg_count = await db.registrants.count_documents({"webinar_id": wid, "owner_id": owner})
    rows = await db.touches.find({"webinar_id": wid, "owner_id": owner},
                                 {"_id": 0, "ai_copy": 0, "copy_overrides": 0}).sort("touch_num", 1).to_list(50)
    touches = []
    for t in rows:
        auto = bool(auto_send_fn(t, settings))
        log = t.get("delivery_log") or []
        chans = t.get("channels") or []
        reaches_invites = "email" in chans and t.get("touch_num") in invites.INVITE_TOUCHES
        touches.append({
            "id": t["id"], "touch_num": t.get("touch_num"), "name": t.get("name"),
            "scheduled_at": t.get("scheduled_at"), "channels": chans,
            "approval_status": t.get("approval_status"), "auto_send": auto,
            "sent_status": t.get("sent_status") or "planned", "sent_at": t.get("sent_at"),
            "state": touch_state(t, auto, now),
            "audience": {"invitees": inv["reachable"] if reaches_invites else 0,
                         "registrants": reg_count if "email" in chans else 0},
            "email": email_counts(log, t.get("send_progress")),
            "progress": t.get("send_progress"),
            "resume_at": t.get("retry_at") if t.get("invite_backlog") else None,
            "posts": posts(log),
            "linkedin_stats": t.get("li_stats") or {},
            "errors": errors(log),
        })
    nxt = next((x for x in touches if x["state"] == "scheduled" and (x["scheduled_at"] or "") > now), None)
    return {
        "webinar": {"id": wid, "title": w.get("title"), "starts_at": w.get("starts_at"),
                    "timezone": w.get("timezone") or "UTC"},
        "contacts": {**inv, "registrants": reg_count},
        "email_provider": (settings.get("email_provider") or "Brevo"),
        "email_daily_limit": int(settings.get("email_daily_limit") or 0),
        "linkedin_connected": bool(settings.get("linkedin_member_token") or settings.get("linkedin_marketing_token")),
        "facebook_connected": bool(settings.get("meta_graph_token") and settings.get("meta_page_id")),
        "next_send": {"touch_num": nxt["touch_num"], "name": nxt["name"], "at": nxt["scheduled_at"]} if nxt else None,
        "totals": {
            "emails_sent": sum(x["email"]["invite_sent"] + x["email"]["reg_sent"] for x in touches),
            "emails_failed": sum(x["email"]["invite_failed"] + x["email"]["reg_failed"] for x in touches),
            "posts_live": sum(1 for x in touches for p in x["posts"] if p["ok"]),
            "touches_sent": sum(1 for x in touches if x["state"] == "sent"),
            "touches_left": sum(1 for x in touches if x["state"] in ("scheduled", "manual", "needs_approval", "limit_wait")),
        },
        "touches": touches,
    }


async def linkedin_post_stats(token: str, urn: str) -> Dict[str, Any]:
    """Likes and comments on one post. LinkedIn only answers this for apps with the
    member/organization social *read* permission; without it we say so instead of guessing."""
    url = f"https://api.linkedin.com/v2/socialActions/{quote(urn, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {token}",
                                               "X-Restli-Protocol-Version": "2.0.0"})
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"LinkedIn didn't answer: {str(e)[:80]}"}
    if r.status_code in (401, 403):
        return {"available": False,
                "reason": "LinkedIn doesn't share likes and comments with this app yet (it needs LinkedIn's "
                          "Community Management approval). Open the post to see them."}
    if r.status_code >= 400:
        return {"available": False, "reason": f"LinkedIn error {r.status_code}"}
    j = r.json()
    return {"available": True,
            "likes": int((j.get("likesSummary") or {}).get("totalLikes") or 0),
            "comments": int((j.get("commentsSummary") or {}).get("aggregatedTotalComments")
                            or (j.get("commentsSummary") or {}).get("totalFirstLevelComments") or 0)}


async def refresh_linkedin_stats(db, owner: str, wid: str, settings: Dict[str, Any], force: bool = False) -> int:
    """Fetch likes/comments for this webinar's LinkedIn posts, cached on the touch for 30 min."""
    token = settings.get("linkedin_member_token") or settings.get("linkedin_marketing_token")
    if not token:
        return 0
    rows = await db.touches.find({"webinar_id": wid, "owner_id": owner, "delivery_log.channel": {"$in": list(LI_CHANNELS)}},
                                 {"_id": 0, "id": 1, "delivery_log": 1, "li_stats": 1}).to_list(50)
    fresh_before = (datetime.now(timezone.utc) - LI_STATS_TTL).isoformat()
    n = 0
    for t in rows:
        if not force and (t.get("li_stats") or {}).get("fetched_at", "") > fresh_before:
            continue
        stats: Dict[str, Any] = {}
        for d in t.get("delivery_log") or []:
            urn = d.get("external_id") or ""
            if d.get("channel") in LI_CHANNELS and d.get("ok") and urn.startswith("urn:li:"):
                stats[urn] = await linkedin_post_stats(token, urn)
        if stats:
            await db.touches.update_one({"id": t["id"]}, {"$set": {"li_stats": {
                "posts": stats, "fetched_at": datetime.now(timezone.utc).isoformat()}}})
            n += 1
    return n
