"""Free "reminder kit" lead magnet.

A visitor on the blog, a free tool or a compare page types their webinar's title and date,
then gives their name and email to unlock six ready-to-send reminder messages written for
that webinar (email, WhatsApp, SMS, LinkedIn), each with the moment it should go out.

This module holds the pure parts (kit layout, fallback copy, LLM prompt + parsing, the
delivery email) so they can be tested without MongoDB. The HTTP route is in routes_leads.py.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Six messages that cover the moments with the biggest effect on show-up: the confirmation,
# the day-before and hour-before nudges, "we're live", a LinkedIn post to the registrant's
# network, and the replay email to no-shows. offset = minutes relative to the start time;
# None = send the moment someone registers.
KIT_ITEMS: List[Dict[str, Any]] = [
    {"key": "confirmation", "channel": "Email", "label": "Registration confirmation", "offset": None, "subject": True,
     "brief": "Sent the second they register. Confirm date and time with timezone, ask them to add it to their "
              "calendar now, and ask them to reply with the one question they want answered."},
    {"key": "day_before", "channel": "Email", "label": "24 hours before", "offset": -24 * 60, "subject": True,
     "brief": "Remind them it is tomorrow. Give one concrete thing they will walk away with, the time, "
              "and the join link. Short."},
    {"key": "linkedin", "channel": "LinkedIn post", "label": "Host's LinkedIn post, 2 days before",
     "offset": -48 * 60, "subject": False,
     "brief": "A post from the host: a sharp hook line about the problem, 2-3 short lines on what the session "
              "covers, the date, and a call to comment or register. No hashtag spam (max 3)."},
    {"key": "hour_before", "channel": "WhatsApp", "label": "1 hour before", "offset": -60, "subject": False,
     "brief": "Casual WhatsApp message, under 60 words. Starts in 1 hour, one reason to show up live, join link."},
    {"key": "live_now", "channel": "SMS", "label": "At start time", "offset": 0, "subject": False,
     "brief": "SMS under 160 characters: we're live now, join link."},
    {"key": "replay", "channel": "Email", "label": "No-show replay, next morning", "offset": 18 * 60, "subject": True,
     "brief": "To registrants who missed it. No guilt. Give the replay link, the single best moment to jump to, "
              "and a reason to watch within 48 hours."},
]
KIT_KEYS = [i["key"] for i in KIT_ITEMS]

LINK = "[join link]"
REPLAY = "[replay link]"


def clean(v: Any, limit: int) -> str:
    """Single-line, trimmed, length-capped user input."""
    return re.sub(r"\s+", " ", str(v or "")).strip()[:limit]


def parse_start(value: Any) -> Optional[datetime]:
    """Accept an ISO date-time ("2026-12-01T11:00", with or without offset). Naive = UTC."""
    s = clean(value, 40)
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def when_text(label: str) -> str:
    """The date/time exactly as the visitor typed it, made readable ("Tue 1 Dec, 7:00 PM")."""
    s = clean(label, 60)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", s)
    if not m:
        return s or "the scheduled time"
    dt = datetime(*[int(x) for x in m.groups()])
    hour = dt.hour % 12 or 12
    return f"{dt:%a} {dt.day} {dt:%b}, {hour}:{dt:%M} {'AM' if dt.hour < 12 else 'PM'}"


def fallback_kit(title: str, when: str, audience: str = "") -> Dict[str, Dict[str, str]]:
    """Good, deterministic copy used when the LLM is unavailable or over budget."""
    t = title or "our webinar"
    who = f" for {audience}" if audience else ""
    return {
        "confirmation": {
            "subject": f"You're in: {t} ({when})",
            "body": (f"Hi {{first_name}},\n\nYou're registered for {t}{who}, live on {when}.\n\n"
                     f"Two things so you don't miss it:\n1. Add it to your calendar now: {LINK}\n"
                     f"2. Hit reply and tell me the one question you want answered. I'll cover the most common ones live.\n\n"
                     f"See you there,\n{{host_name}}")},
        "day_before": {
            "subject": f"Tomorrow: {t}",
            "body": (f"Hi {{first_name}},\n\nQuick reminder: {t} is tomorrow, {when}.\n\n"
                     f"You'll leave with a plan you can use the same day, and you can ask your question live.\n\n"
                     f"Join here: {LINK}\n\n{{host_name}}")},
        "linkedin": {
            "subject": "",
            "body": (f"Most people who sign up for a webinar never show up.\n\n"
                     f"On {when} I'm running {t}{who}.\n\n"
                     f"We'll go through what actually works, with real examples, and leave time for your questions.\n\n"
                     f"Comment \"in\" and I'll send you the link.")},
        "hour_before": {
            "subject": "",
            "body": (f"Hi {{first_name}}! {t} starts in 1 hour. Come live so you can ask your question "
                     f"while we're on it. Join: {LINK}")},
        "live_now": {
            "subject": "",
            "body": f"We're live now: {t}. Join here: {LINK}"},
        "replay": {
            "subject": f"The replay of {t} (watch the best 10 minutes)",
            "body": (f"Hi {{first_name}},\n\nWe missed you live, no worries. Here's the replay: {REPLAY}\n\n"
                     f"Short on time? Skip to the Q&A, that's where the most useful answers were.\n\n"
                     f"The replay comes down in 48 hours.\n\n{{host_name}}")},
    }


def build_prompt(title: str, when: str, audience: str = "") -> str:
    lines = "\n".join(
        f'- "{i["key"]}" ({i["channel"]}, {i["label"]}): {i["brief"]}'
        + (" Include a subject line." if i["subject"] else "")
        for i in KIT_ITEMS)
    return (
        "You write webinar reminder messages that get registrants to actually show up.\n"
        f"Webinar title: {title}\nDate and time: {when}\n"
        f"Audience: {audience or 'not given, infer it from the title'}\n\n"
        "Write these messages:\n" + lines + "\n\n"
        "Rules: plain human tone, short sentences, no hype words (unlock, supercharge, game-changer, delve), "
        "no emojis except at most one in WhatsApp. Use {first_name} and {host_name} as placeholders, "
        f"{LINK} for the join link and {REPLAY} for the replay link. Never invent statistics. "
        "Mention the actual webinar topic, not a generic one.\n\n"
        'Reply with JSON only: {"items": {"<key>": {"subject": "...", "body": "..."}}} using exactly the keys above. '
        'Use "" as subject for messages without one.'
    )


def parse_llm(raw: Any) -> Dict[str, Dict[str, str]]:
    """Pull usable {key: {subject, body}} out of the model's reply; drop anything malformed."""
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            m = re.search(r"\{.*\}", raw or "", re.S)
            try:
                data = json.loads(m.group(0)) if m else {}
            except ValueError:
                data = {}
    items = data.get("items", data) if isinstance(data, dict) else {}
    out: Dict[str, Dict[str, str]] = {}
    if not isinstance(items, dict):
        return out
    for key in KIT_KEYS:
        v = items.get(key)
        if not isinstance(v, dict):
            continue
        body = str(v.get("body") or "").strip()
        if len(body) < 20:
            continue
        out[key] = {"subject": str(v.get("subject") or "").strip()[:150], "body": body[:2000]}
    return out


def assemble(title: str, when: str, audience: str, start: Optional[datetime],
             generated: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
    """Merge generated copy over the fallback, in kit order, with each message's send time."""
    base = fallback_kit(title, when, audience)
    out = []
    for i in KIT_ITEMS:
        copy = generated.get(i["key"]) or base[i["key"]]
        subject = copy.get("subject", "") if i["subject"] else ""
        if i["subject"] and not subject:
            subject = base[i["key"]]["subject"]
        send_at = None
        if start is not None and i["offset"] is not None:
            send_at = (start + timedelta(minutes=i["offset"])).isoformat()
        out.append({"key": i["key"], "channel": i["channel"], "label": i["label"], "send_at": send_at,
                    "subject": subject, "body": copy["body"],
                    "ai": i["key"] in generated})
    return out


def email_html(name: str, title: str, when: str, items: List[Dict[str, Any]], site: str) -> str:
    """The kit as a plain, readable email."""
    e = html.escape
    first = e((name or "").split(" ")[0] or "there")
    parts = [f"<p>Hi {first},</p><p>Here are your reminder messages for <b>{e(title)}</b> ({e(when)}). "
             "Copy each one on its day. Replace the [join link] and {first_name} placeholders.</p>"]
    for n, i in enumerate(items, 1):
        parts.append(f"<h3 style='margin:24px 0 4px'>{n}. {e(i['label'])} &middot; {e(i['channel'])}</h3>")
        if i.get("subject"):
            parts.append(f"<p style='margin:0 0 6px'><b>Subject:</b> {e(i['subject'])}</p>")
        parts.append("<pre style='white-space:pre-wrap;font-family:inherit;background:#f6f6f6;padding:12px;"
                     f"border-radius:8px'>{e(i['body'])}</pre>")
    parts.append(f"<p style='margin-top:24px'>Don't want to send these by hand? "
                 f"<a href='{site}/register'>ShowUpAI sends them for you</a> on email, WhatsApp, SMS and LinkedIn, "
                 "at the right time for each registrant. 14-day free trial, no card.</p>"
                 "<p>Ashutosh, ShowUpAI</p>")
    return "<div style='font-family:Arial,sans-serif;font-size:15px;line-height:1.5;color:#111;max-width:640px'>" \
           + "".join(parts) + "</div>"
