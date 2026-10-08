"""Turns stored touch copy into the exact text each person receives.

AI copy is written with placeholders ({{first_name}}, {{join_link}}, ...). Emails and
WhatsApp are filled per registrant; social posts are filled for a public audience, where
the "join" link is the registration page (the live room link stays private) and there is
no first name to greet. Rendering also strips the tells that make copy read machine-made,
so copy generated before the voice rules changed is cleaned at send time too.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://showupai.live").rstrip("/")

PERSONAL_CHANNELS = {"email", "whatsapp"}

_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_GREETING = re.compile(r"^\s*(hi|hey|hello|dear)\s+\{\{\s*first_name\s*\}\}\s*[,!.:]?\s*", re.I | re.M)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️⃣←-⇿]")
_DASH = re.compile(r"\s*[—–]\s*")
# Channels where people write plainly. Instagram and WhatsApp keep emojis if the copy has them.
_NO_EMOJI = {"email", "linkedin", "linkedin_page", "linkedin_personal", "facebook", "facebook_page", "circle"}


def webinar_tz(w: Dict[str, Any]) -> ZoneInfo:
    try:
        return ZoneInfo((w.get("timezone") or "UTC").strip())
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def parse_start(w: Dict[str, Any]) -> Optional[datetime]:
    raw = w.get("starts_at") or ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def registration_url(w: Dict[str, Any]) -> str:
    return w.get("registration_link") or f"{FRONTEND_URL}/r/{w.get('id', '')}"


def calendar_url(w: Dict[str, Any]) -> str:
    """Google Calendar 'add event' link (works without the attached .ics)."""
    start = parse_start(w)
    if not start:
        return ""
    end = start + timedelta(hours=1)
    fmt = "%Y%m%dT%H%M%SZ"
    details = (w.get("description") or "")[:500]
    if w.get("join_link"):
        details += f"\n\nJoin: {w['join_link']}"
    q = urlencode({"action": "TEMPLATE", "text": w.get("title") or "Webinar",
                   "dates": f"{start.astimezone(timezone.utc):{fmt}}/{end.astimezone(timezone.utc):{fmt}}",
                   "details": details, "location": w.get("join_link") or ""})
    return f"https://calendar.google.com/calendar/render?{q}"


def first_name(registrant: Optional[Dict[str, Any]]) -> str:
    name = ((registrant or {}).get("name") or "").strip()
    if not name or "@" in name:
        return ""
    first = name.split()[0]
    return first.capitalize() if first.islower() or first.isupper() else first


def values(w: Dict[str, Any], registrant: Optional[Dict[str, Any]] = None,
           public: bool = False) -> Dict[str, str]:
    start = parse_start(w)
    local = start.astimezone(webinar_tz(w)) if start else None
    reg_url = registration_url(w)
    return {
        "first_name": first_name(registrant) or ("" if public else "there"),
        "webinar_title": w.get("title") or "",
        "webinar_date": f"{local:%A}, {local.day} {local:%B}" if local else "",
        "webinar_time": f"{local:%I:%M %p}".lstrip("0") + f" {local.tzname()}" if local else "",
        "join_link": reg_url if public else (w.get("join_link") or reg_url),
        "registration_link": reg_url,
        "calendar_link": calendar_url(w),
        "recording_link": w.get("recording_url") or reg_url,
        "speaker": (w.get("speakers") or w.get("speaker") or "").split(",")[0].strip(),
    }


def clean(text: str, channel: str) -> str:
    t = _DASH.sub(", ", text)
    if channel in _NO_EMOJI:
        t = _EMOJI.sub("", t)
    t = re.sub(r" +([,.!?])", r"\1", t)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def render(text: str, w: Dict[str, Any], channel: str,
           registrant: Optional[Dict[str, Any]] = None) -> str:
    """Fill placeholders for one recipient (email/WhatsApp) or for a public post."""
    if not text:
        return ""
    public = channel not in PERSONAL_CHANNELS
    vals = values(w, registrant, public=public)
    if not vals["first_name"]:
        text = _GREETING.sub("", text)
    text = _PLACEHOLDER.sub(lambda m: vals.get(m.group(1).lower(), ""), text)
    return clean(text, channel)
