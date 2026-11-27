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
    registered, and anyone who unsubscribed from this host before.

    Three lookups and one insert_many for the whole batch. It used to be up to four
    round trips per row, so an 1,800-row CSV took minutes and the request timed out
    with "Adding..." on screen and nothing saved."""
    inserted = deduped = registered = suppressed = 0
    rows: Dict[str, Dict[str, str]] = {}
    for it in items:
        email = (it.get("email") or "").strip().lower()
        if not email:
            continue
        if email in rows:
            deduped += 1
            continue
        rows[email] = it
    emails = list(rows)
    on_list = {d["email"] for d in await db.invitees.find(
        {"webinar_id": wid, "email": {"$in": emails}}, {"_id": 0, "email": 1}).to_list(None)}
    regs = {d["email"] for d in await db.registrants.find(
        {"webinar_id": wid, "email": {"$in": emails}}, {"_id": 0, "email": 1}).to_list(None)}
    unsub = {d["email"] for d in await db.invitees.find(
        {"owner_id": owner_id, "email": {"$in": emails}, "unsubscribed": True}, {"_id": 0, "email": 1}).to_list(None)}
    docs = []
    for email, it in rows.items():
        if email in on_list:
            deduped += 1
        elif email in regs:
            registered += 1
        elif email in unsub:
            suppressed += 1
        else:
            docs.append(new_invitee(wid, owner_id, it.get("name") or "", email))
    inserted = await _insert_many(db.invitees, docs)
    deduped += len(docs) - inserted
    return {"inserted": inserted, "deduped": deduped, "already_registered": registered,
            "unsubscribed_before": suppressed}


async def _insert_many(coll, docs: List[Dict[str, Any]]) -> int:
    """Unordered insert_many; a row that races a unique index is skipped, not fatal."""
    if not docs:
        return 0
    from pymongo.errors import BulkWriteError
    try:
        r = await coll.insert_many(docs, ordered=False)
        return len(r.inserted_ids)
    except BulkWriteError as e:
        return int((e.details or {}).get("nInserted", 0))


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
