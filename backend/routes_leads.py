"""Public lead-capture endpoints (no login).

POST /api/leads/reminder-kit  -> saves the lead and returns six reminder messages written for the
visitor's own webinar (see lead_kit.py). Optionally emails the kit from the ShowUpAI account named
in LEAD_KIT_SENDER_ACCOUNT, using that account's email provider from Settings.
"""
import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException, Request

import lead_kit
from auth_utils import now_iso
from database import db
from routes_webinars import limiter as _web_limiter

logger = logging.getLogger("showup.leads")
router = APIRouter(prefix="/api")

SITE = os.environ.get("PUBLIC_SITE_URL", "https://showupai.live").rstrip("/")
# How many kits a day may use the LLM; past this, visitors still get the (good) template copy.
DAILY_LLM_CAP = int(os.environ.get("LEAD_KIT_DAILY_LLM_CAP", "300"))
LLM_TIMEOUT = float(os.environ.get("LEAD_KIT_LLM_TIMEOUT", "25"))
# Email of the ShowUpAI account whose Settings email provider (Brevo etc.) sends the kit. Empty = don't email.
SENDER_ACCOUNT = os.environ.get("LEAD_KIT_SENDER_ACCOUNT", "").strip().lower()

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[a-zA-Z]{2,24}$")


async def save_subscriber(email: str, name: str, slug: str, placement: str) -> None:
    """Same record shape as POST /api/blog/subscribe, so leads land in one list (and its CSV export)."""
    ts = now_iso()
    source = {"slug": slug[:120], "placement": placement[:40], "at": ts}
    await db.blog_subscribers.update_one(
        {"email": email},
        {"$setOnInsert": {"email": email, "created_at": ts, "first_source": source, "status": "subscribed"},
         "$set": {"name": name, "updated_at": ts},
         "$push": {"sources": {"$each": [source], "$slice": -20}}},
        upsert=True,
    )


async def _llm_kit(title: str, when: str, audience: str) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    used = await db.lead_kits.count_documents({"day": today, "source": "ai"})
    if used >= DAILY_LLM_CAP:
        return {}
    try:
        from ai import _call_llm
        raw = await asyncio.wait_for(_call_llm(lead_kit.build_prompt(title, when, audience), max_tokens=2000),
                                     timeout=LLM_TIMEOUT)
        return lead_kit.parse_llm(raw)
    except Exception as ex:  # timeout, provider down: the template copy is still a good kit
        logger.warning(f"reminder kit LLM failed: {ex}")
        return {}


async def _email_kit(kit_id: str, email: str, name: str, title: str, when: str, items: list) -> None:
    if not SENDER_ACCOUNT:
        return
    try:
        from crypto_utils import decrypt_settings
        from senders import send_email
        owner = await db.users.find_one({"email": SENDER_ACCOUNT}, {"_id": 0, "id": 1})
        if not owner:
            logger.warning("LEAD_KIT_SENDER_ACCOUNT has no ShowUpAI account; kit not emailed")
            return
        settings = decrypt_settings(await db.settings.find_one({"owner_id": owner["id"]}, {"_id": 0}) or {})
        res = await send_email(settings, email, f"Your reminder messages for {title}",
                               lead_kit.email_html(name, title, when, items, SITE))
        await db.lead_kits.update_one({"id": kit_id}, {"$set": {"emailed": bool(res.get("ok")),
                                                                 "email_detail": str(res.get("detail") or "")[:200]}})
    except Exception as ex:
        logger.warning(f"reminder kit email failed: {ex}")


@router.post("/leads/reminder-kit")
@_web_limiter.limit("4/minute")
async def reminder_kit(request: Request, payload: dict = Body(default={})):
    """Body: {name, email, title, starts_at (ISO, local time as typed), when_label?, audience?, slug?,
    placement?, website? (honeypot)}. Returns {ok, items: [...], emailed: bool}."""
    title = lead_kit.clean(payload.get("title"), 140)
    when_raw = lead_kit.clean(payload.get("starts_at"), 40)
    when = lead_kit.when_text(when_raw)
    audience = lead_kit.clean(payload.get("audience"), 100)
    if payload.get("website"):  # bots fill hidden fields: hand back the template kit, save nothing
        return {"ok": True, "items": lead_kit.assemble(title, when, audience, None, {}), "emailed": False}
    email = str(payload.get("email", "")).strip().lower()
    name = lead_kit.clean(payload.get("name"), 80)
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "Please enter a valid email")
    if not name:
        raise HTTPException(400, "Please enter your name")
    if len(title) < 3:
        raise HTTPException(400, "Please enter your webinar's title")
    slug = lead_kit.clean(payload.get("slug"), 120)
    placement = lead_kit.clean(payload.get("placement"), 40) or "reminder-kit"

    await save_subscriber(email, name, slug, f"kit:{placement}"[:40])
    generated = await _llm_kit(title, when, audience)
    items = lead_kit.assemble(title, when, audience, lead_kit.parse_start(when_raw), generated)

    kit_id = str(uuid.uuid4())
    await db.lead_kits.insert_one({
        "id": kit_id, "email": email, "name": name, "title": title, "starts_at": when_raw, "audience": audience,
        "slug": slug, "placement": placement, "source": "ai" if generated else "template",
        "day": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "created_at": now_iso(), "emailed": False,
    })
    emailing = bool(SENDER_ACCOUNT)
    if emailing:
        asyncio.create_task(_email_kit(kit_id, email, name, title, when, items))
    return {"ok": True, "items": items, "emailed": emailing}
