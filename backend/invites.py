"""Invite list: people the host wants at the session who haven't registered yet.

Registrants get the whole show-up sequence. Invitees (a client's past attendees,
newsletter list, members) get every touch that makes sense before they sign up:
the value emails and lead magnets (2-7), the day-before, 1-hour and live-now nudges
(8, 9, 12) as "last chance to grab a seat", and the post-event recap with the
recording (11). Their link is always the registration page, never the live room,
and every email carries an unsubscribe link. They never get touch 1 (confirmation)
or 10 (thanks for attending).
They are kept apart from registrants so counts, the ShowUp Score and the
"we're live" broadcast only ever mean people who signed up.

When an invitee registers they stop getting invite emails (they are a registrant now)
and the import counts them as converted.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

# Touches (config.TOUCH_DEFS) that also go to the invite list by email.
INVITE_TOUCHES = {2, 3, 4, 5, 6, 7, 8, 9, 11, 12}
MAX_INVITEES = 5000

INVITE_FOOTER = "You're getting this because you're on {host}'s list."


def unsubscribe_url(invitee_id: str) -> str:
    base = (os.environ.get("PUBLIC_BACKEND_URL") or "").rstrip("/")
    return f"{base}/api/unsubscribe/{invitee_id}" if base else ""


def new_invitee(wid: str, owner_id: str, name: str, email: str) -> Dict[str, Any]:
    from auth_utils import now_iso
    return {"id": str(uuid.uuid4()), "webinar_id": wid, "owner_id": owner_id,
            "name": name or email, "email": email.lower(), "unsubscribed": False,
            "registered_at": None, "added_at": now_iso(), "sends": 0}


async def import_invitees(db, wid: str, owner_id: str, items: List[Dict[str, str]]) -> Dict[str, int]:
    """Add people to a webinar's invite list. Skips duplicates, people already
    registered, and anyone who unsubscribed from this host before."""
    inserted = deduped = registered = suppressed = 0
    seen = set()
    for it in items:
        email = (it.get("email") or "").strip().lower()
        if not email or email in seen:
            deduped += 1 if email else 0
            continue
        seen.add(email)
        if await db.invitees.find_one({"webinar_id": wid, "email": email}):
            deduped += 1
            continue
        if await db.registrants.find_one({"webinar_id": wid, "email": email}):
            registered += 1
            continue
        if await db.invitees.find_one({"owner_id": owner_id, "email": email, "unsubscribed": True}):
            suppressed += 1
            continue
        await db.invitees.insert_one(new_invitee(wid, owner_id, it.get("name") or "", email))
        inserted += 1
    return {"inserted": inserted, "deduped": deduped, "already_registered": registered,
            "unsubscribed_before": suppressed}


async def invite_targets(db, t: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Invitees a warm-up touch should email: not unsubscribed, not registered."""
    if t.get("touch_num") not in INVITE_TOUCHES or "email" not in (t.get("channels") or []):
        return []
    rows = await db.invitees.find({"webinar_id": t["webinar_id"], "unsubscribed": {"$ne": True},
                                   "registered_at": None}, {"_id": 0}).to_list(MAX_INVITEES)
    if not rows:
        return []
    regs = await db.registrants.find({"webinar_id": t["webinar_id"]}, {"_id": 0, "email": 1}).to_list(20000)
    taken = {(r.get("email") or "").lower() for r in regs}
    return [r for r in rows if r.get("email") and r["email"] not in taken]


async def mark_registered(db, wid: str, email: str) -> None:
    from auth_utils import now_iso
    await db.invitees.update_one({"webinar_id": wid, "email": email.lower()},
                                 {"$set": {"registered_at": now_iso()}})


async def unsubscribe(db, invitee_id: str) -> Optional[Dict[str, Any]]:
    """Unsubscribe from every invite list of this host, not just this webinar."""
    row = await db.invitees.find_one({"id": invitee_id}, {"_id": 0})
    if not row:
        return None
    await db.invitees.update_many({"owner_id": row["owner_id"], "email": row["email"]},
                                  {"$set": {"unsubscribed": True}})
    return row


async def summary(db, wid: str) -> Dict[str, int]:
    total = await db.invitees.count_documents({"webinar_id": wid})
    unsub = await db.invitees.count_documents({"webinar_id": wid, "unsubscribed": True})
    converted = await db.invitees.count_documents({"webinar_id": wid, "registered_at": {"$ne": None}})
    reachable = await db.invitees.count_documents({"webinar_id": wid, "unsubscribed": {"$ne": True},
                                                   "registered_at": None})
    return {"total": total, "unsubscribed": unsub, "registered": converted, "reachable": reachable}
