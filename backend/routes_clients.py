"""Agency mode: one agency login runs many client workspaces.

A client workspace is its own account (users row with agency_id), so everything that
is already per account stays per client with no extra code: email provider and
sender, LinkedIn and Facebook connections, brand kit, webinars, touches, invite
lists and the scheduler. The agency switches into a client with a token that names
both (sub=client, agency=agency id); client workspaces have no login of their own.
"""
from __future__ import annotations

import secrets
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException

from auth_utils import get_user, make_token
from billing import entitlement
from database import db

router = APIRouter(prefix="/api/clients")

MAX_CLIENTS = 200
CLIENT_EMAIL_DOMAIN = "clients.showupai.live"

# Collections whose rows belong to one webinar and carry the owner's id.
WEBINAR_COLLECTIONS = ("touches", "registrants", "invitees", "lead_magnets", "social_images", "adhoc_posts")


async def agency_of(user: Dict[str, Any]) -> Dict[str, Any]:
    """The agency account behind this request: the user, or the agency acting in a client."""
    return user.get("_agency") or user


def _can_manage(agency: Dict[str, Any]) -> bool:
    return entitlement(agency).get("plan") == "agency"


def _public(c: Dict[str, Any], webinars: int = 0) -> Dict[str, Any]:
    email = c.get("email") or ""
    return {"id": c["id"], "name": c.get("name") or "", "webinars": webinars,
            "email": "" if email.endswith("@" + CLIENT_EMAIL_DOMAIN) else email,
            "created_at": c.get("created_at")}


async def _client_of(agency_id: str, cid: str) -> Dict[str, Any]:
    c = await db.users.find_one({"id": cid, "agency_id": agency_id}, {"_id": 0, "password": 0})
    if not c:
        raise HTTPException(404, "Client not found")
    return c


@router.get("")
async def list_clients(user=Depends(get_user)):
    agency = await agency_of(user)
    rows = await db.users.find({"agency_id": agency["id"]}, {"_id": 0, "password": 0}) \
        .sort("name", 1).to_list(MAX_CLIENTS)
    out: List[Dict[str, Any]] = []
    for c in rows:
        out.append(_public(c, await db.webinars.count_documents({"owner_id": c["id"]})))
    return {"can_manage": _can_manage(agency), "clients": out,
            "agency": {"id": agency["id"], "name": agency.get("name") or "", "email": agency.get("email") or ""},
            "current": user["id"]}


@router.post("")
async def create_client(payload: dict = Body(default={}), user=Depends(get_user)):
    from routes_auth import create_user
    agency = await agency_of(user)
    if not _can_manage(agency):
        raise HTTPException(402, "Client workspaces come with the Agency plan.")
    name = (payload.get("name") or "").strip()[:80]
    if not name:
        raise HTTPException(400, "Client name required")
    if await db.users.count_documents({"agency_id": agency["id"]}) >= MAX_CLIENTS:
        raise HTTPException(400, f"Up to {MAX_CLIENTS} clients per agency")
    email = (payload.get("email") or "").strip().lower()
    if email and "@" not in email:
        raise HTTPException(400, "That email doesn't look right")
    cid_hint = uuid.uuid4().hex[:12]
    c = await create_user(email or f"client-{cid_hint}@{CLIENT_EMAIL_DOMAIN}", name,
                          secrets.token_urlsafe(24), agency_id=agency["id"])
    return _public(c)


@router.patch("/{cid}")
async def rename_client(cid: str, payload: dict = Body(default={}), user=Depends(get_user)):
    agency = await agency_of(user)
    await _client_of(agency["id"], cid)
    name = (payload.get("name") or "").strip()[:80]
    if not name:
        raise HTTPException(400, "Client name required")
    await db.users.update_one({"id": cid}, {"$set": {"name": name}})
    return {"ok": True}


@router.post("/{cid}/switch")
async def switch_to_client(cid: str, user=Depends(get_user)):
    agency = await agency_of(user)
    c = await _client_of(agency["id"], cid)
    return {"token": make_token(c["id"], agency_id=agency["id"]),
            "user": {"id": c["id"], "name": c.get("name"), "email": _public(c)["email"], "role": "user"}}


@router.post("/switch-back")
async def switch_back(user=Depends(get_user)):
    agency = await agency_of(user)
    return {"token": make_token(agency["id"]),
            "user": {"id": agency["id"], "name": agency.get("name"), "email": agency.get("email"),
                     "role": agency.get("role", "user")}}


@router.post("/move-webinar")
async def move_webinar(payload: dict = Body(default={}), user=Depends(get_user)):
    """Move a webinar, with its touches, registrants and invite list, to another
    workspace of the same agency (a client, or back to the agency itself)."""
    agency = await agency_of(user)
    wid = payload.get("webinar_id") or ""
    target = payload.get("to") or ""
    ids = {agency["id"]} | {c["id"] for c in await db.users.find(
        {"agency_id": agency["id"]}, {"_id": 0, "id": 1}).to_list(MAX_CLIENTS)}
    if target not in ids:
        raise HTTPException(404, "Client not found")
    w = await db.webinars.find_one({"id": wid}, {"_id": 0, "id": 1, "owner_id": 1})
    if not w or w.get("owner_id") not in ids:
        raise HTTPException(404, "Webinar not found")
    if w["owner_id"] == target:
        return {"ok": True, "moved": 0}
    await db.webinars.update_one({"id": wid}, {"$set": {"owner_id": target}})
    moved = 1
    for name in WEBINAR_COLLECTIONS:
        r = await db[name].update_many({"webinar_id": wid}, {"$set": {"owner_id": target}})
        moved += r.modified_count
    return {"ok": True, "moved": moved}


# ── Connect link: the client connects their own accounts, no login needed ──────
# The agency sends the client one link. On it the client connects their LinkedIn
# and Facebook Page and adds their own email sender; everything lands in their
# workspace. The raw token only lives in the URL; we store its SHA-256.

import hashlib
import os
import time

from fastapi import Request

CONNECT_TTL_DAYS = 14
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://showupai.live").rstrip("/")
public_router = APIRouter(prefix="/api/connect")


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("/{cid}/connect-link")
async def create_connect_link(cid: str, user=Depends(get_user)):
    agency = await agency_of(user)
    c = await _client_of(agency["id"], cid)
    raw = secrets.token_urlsafe(32)
    await db.client_connect_links.insert_one({
        "token_hash": _hash(raw), "client_id": c["id"], "agency_id": agency["id"],
        "expires_ts": time.time() + CONNECT_TTL_DAYS * 86400, "created_at": time.time()})
    return {"url": f"{FRONTEND_URL}/connect/{raw}", "expires_in_days": CONNECT_TTL_DAYS}


async def _link(raw: str) -> Dict[str, Any]:
    doc = await db.client_connect_links.find_one(
        {"token_hash": _hash(raw or ""), "expires_ts": {"$gt": time.time()}}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "This link has expired. Ask for a new one.")
    client = await db.users.find_one({"id": doc["client_id"], "agency_id": doc["agency_id"]},
                                     {"_id": 0, "password": 0})
    if not client:
        raise HTTPException(404, "This link has expired. Ask for a new one.")
    return {**doc, "client": client}


@public_router.get("/{raw}")
async def connect_page(raw: str):
    from growth_engine import linkedin as li, meta
    from crypto_utils import decrypt_settings
    link = await _link(raw)
    c = link["client"]
    agency = await db.users.find_one({"id": link["agency_id"]}, {"_id": 0, "name": 1}) or {}
    lconn = await li.get_connection(db, c["id"], li.PLATFORM)
    mconn = await li.get_connection(db, c["id"], meta.PLATFORM)
    s = decrypt_settings(await db.settings.find_one({"owner_id": c["id"]}, {"_id": 0}) or {})
    return {
        "client_name": c.get("name") or "", "agency_name": agency.get("name") or "",
        "linkedin": {"configured": li.configured(), "connected": li.public_view(lconn).get("connected", False),
                     "name": (lconn or {}).get("name") or ""},
        "facebook": {"configured": meta.configured(), **meta.public_view(mconn)},
        "email": {"connected": bool(s.get("brevo_api_key")), "sender_email": s.get("brevo_sender_email") or "",
                  "sender_name": s.get("brevo_sender_name") or ""},
    }


@public_router.post("/{raw}/linkedin")
async def connect_linkedin(raw: str):
    from growth_engine import linkedin as li
    link = await _link(raw)
    if not li.configured():
        raise HTTPException(503, "LinkedIn isn't available right now")
    await li.ensure_indexes(db)
    state = await li.create_state(db, link["client_id"], return_path=f"/connect/{raw}")
    return {"authorization_url": li.build_authorization_url(state)}


@public_router.post("/{raw}/facebook")
async def connect_facebook(raw: str):
    from growth_engine import linkedin as li, meta
    link = await _link(raw)
    if not meta.configured():
        raise HTTPException(503, "Facebook isn't available right now")
    await li.ensure_indexes(db)
    state = await li.create_state(db, link["client_id"], platform=meta.PLATFORM, return_path=f"/connect/{raw}")
    return {"authorization_url": meta.build_authorization_url(state)}


@public_router.post("/{raw}/email")
async def connect_email(raw: str, payload: dict = Body(default={})):
    """The client's own Brevo account: their key and their sender, so mail goes out
    from their domain. The key is encrypted like every other secret in Settings."""
    from crypto_utils import encrypt_settings
    link = await _link(raw)
    key = (payload.get("api_key") or "").strip()
    sender = (payload.get("sender_email") or "").strip().lower()
    name = (payload.get("sender_name") or "").strip()[:80]
    if not key.startswith("xkeysib-") or len(key) < 30:
        raise HTTPException(400, "That doesn't look like a Brevo API key (it starts with xkeysib-)")
    if "@" not in sender or "." not in sender.split("@")[-1]:
        raise HTTPException(400, "Sender email required")
    upd = encrypt_settings({"email_provider": "Brevo", "brevo_api_key": key,
                            "brevo_sender_email": sender, "brevo_sender_name": name or link["client"].get("name") or ""})
    await db.settings.update_one({"owner_id": link["client_id"]}, {"$set": upd}, upsert=True)
    return {"ok": True}
