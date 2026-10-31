"""Offline tests for the show-up sequence: placeholder rendering, send times,
post-event audiences, confirmation on registration and copy fallbacks."""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

import _growth_helpers  # noqa: F401  (puts backend/ on sys.path)

os.environ.setdefault("JWT_SECRET", "test")
# Other suites stub `database` with a bare namespace at import time; these tests need the real module.
if not hasattr(sys.modules.get("database"), "social_images_fs"):
    sys.modules.pop("database", None)

import ai  # noqa: E402
import routes_delivery  # noqa: E402
import senders  # noqa: E402
import touch_render  # noqa: E402
from config import TOUCH_DEFS  # noqa: E402

W = {"id": "w1", "owner_id": "u1", "title": "Fix your onboarding", "starts_at": "2026-10-20T12:30:00Z",
     "timezone": "Asia/Kolkata", "join_link": "https://zoom.us/j/123", "speaker": "Ashu Pratap",
     "description": "How to stop losing users in week one."}


def test_email_render_is_personal_and_complete():
    out = touch_render.render("Hi {{first_name}},\n\n{{webinar_title}} is {{webinar_date}} at {{webinar_time}} — "
                              "join: {{join_link}}\n\n{{speaker}}", W, "email", {"name": "riya sharma"})
    assert out.startswith("Hi Riya,")
    assert "Tuesday, 20 October at 6:00 PM IST" in out
    assert "https://zoom.us/j/123" in out and "—" not in out and "{{" not in out
    assert out.endswith("Ashu Pratap")


def test_social_render_uses_registration_page_and_no_greeting():
    out = touch_render.render("Hi {{first_name}}, big news \U0001F680\n\nSave your spot: {{join_link}}", W, "linkedin")
    assert out.startswith("big news")
    assert "zoom.us" not in out and "/r/w1" in out
    assert "\U0001F680" not in out


def test_unknown_name_falls_back_to_there():
    assert touch_render.render("Hi {{first_name}},", W, "email", {"name": "a@b.com"}) == "Hi there,"


def test_email_html_links_are_clickable_and_escaped():
    html = senders.text_to_email_html("a <b> & https://x.io/a?b=1&c=2.\nhttps://calendar.google.com/calendar/render?x=1")
    assert "&lt;b&gt;" in html
    assert '<a href="https://x.io/a?b=1&amp;c=2"' in html
    assert ">Add it to your calendar</a>" in html


def _sched(touch, start, tz="Asia/Kolkata"):
    return asyncio.run(ai.compute_dynamic_schedule(start.isoformat(), touch, tz=tz))


def test_schedule_long_lead_time():
    start = (datetime.now(timezone.utc) + timedelta(days=30)).replace(hour=12, minute=30, second=0, microsecond=0)
    t2 = datetime.fromisoformat(_sched(2, start))
    assert (start.date() - t2.date()).days in (21, 22)
    assert t2.astimezone(touch_render.webinar_tz({"timezone": "Asia/Kolkata"})).hour == 9
    assert datetime.fromisoformat(_sched(8, start)) == start - timedelta(hours=24)
    assert datetime.fromisoformat(_sched(9, start)) == start - timedelta(hours=1)
    assert datetime.fromisoformat(_sched(12, start)) == start
    warm = [datetime.fromisoformat(_sched(n, start)) for n in range(2, 8)]
    assert warm == sorted(warm) and len({w.date() for w in warm}) == 6


def test_schedule_short_lead_time_never_bursts():
    start = datetime.now(timezone.utc) + timedelta(days=3, hours=6)
    times = [_sched(n, start) for n in range(2, 10)]
    sent = [t for t in times if t]
    assert all(datetime.fromisoformat(t) > datetime.now(timezone.utc) for t in sent)
    assert len(sent) == len(set(sent))                      # no two touches at the same moment
    assert times[6] and times[7]                             # 24h and 1h reminders always kept


def test_post_event_audiences():
    assert routes_delivery._touch_audience({"webinar_id": "w", "touch_num": 10, "trigger": "After event"})["attended"] is True
    assert routes_delivery._touch_audience({"webinar_id": "w", "touch_num": 11, "trigger": "2 days after"})["attended"] == {"$ne": True}
    assert "attended" not in routes_delivery._touch_audience({"webinar_id": "w", "touch_num": 8, "trigger": "x"})


def test_every_touch_has_a_job():
    for t in TOUCH_DEFS:
        assert t["num"] in ai.TOUCH_CONTEXT and t["num"] in ai.TOUCH_TYPE


def test_fallback_and_banned_retry(monkeypatch):
    calls = []

    async def fake_llm(prompt, max_tokens=0):
        calls.append(prompt)
        if len(calls) == 1:
            return '{"safe": {"body": "Let\'s dive in — now"}, "casual": {"body": "ok"}}'
        return '{"safe": {"body": "Here is the fix.\\n\\n{{join_link}}"}, "casual": {"body": "Quick one."}}'

    monkeypatch.setattr(ai, "_call_llm", fake_llm)
    ch, copy = asyncio.run(ai._generate_single_channel(W, 3, "linkedin", "ctx", "insight"))
    assert len(calls) == 2 and "dive in" in calls[1]
    assert copy["safe"]["body"].startswith("Here is the fix.")

    async def broken(prompt, max_tokens=0):
        return "{}"

    monkeypatch.setattr(ai, "_call_llm", broken)
    _, copy = asyncio.run(ai._generate_single_channel(W, 9, "email", "ctx", "one_hour"))
    assert copy["safe"]["subject"] == "we start in an hour"
    assert "{{join_link}}" in copy["safe"]["body"]


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(upd.get("$set", {}))


class _DB:
    def __init__(self):
        self.webinars = _Coll([dict(W)])
        self.registrants = _Coll([{"id": "r1", "webinar_id": "w1", "name": "Riya", "email": "riya@x.io", "phone": None}])
        self.touches = _Coll([{"id": "t1", "webinar_id": "w1", "touch_num": 1, "channels": ["email", "whatsapp"],
                               "approval_status": "pending",
                               "ai_copy": {"channels": {"email": {"safe": {"subject": "AI", "body": "AI body"}}}}}])
        self.settings = _Coll()


def test_confirmation_sent_on_registration(monkeypatch):
    fake = _DB()
    sent = []

    async def fake_dispatch(ch, settings, to_email, to_phone, subject, body, ics_bytes=None, image_url=None):
        sent.append((ch, to_email, subject, body, bool(ics_bytes)))
        return {"ok": True}

    async def no_oauth(user_id, settings):
        return settings

    monkeypatch.setattr(routes_delivery, "db", fake)
    monkeypatch.setattr(routes_delivery, "send_dispatch", fake_dispatch)
    monkeypatch.setattr(routes_delivery, "_with_user_oauth", no_oauth)
    res = asyncio.run(routes_delivery.send_confirmation("w1", "r1"))
    assert res["ok"] and len(sent) == 1                      # no phone, so no WhatsApp
    ch, to, subject, body, has_ics = sent[0]
    # Touch 1 isn't approved, so the built-in confirmation goes, not the unreviewed AI copy.
    assert subject == "You're in: Fix your onboarding" and body.startswith("Hi Riya,")
    assert "https://zoom.us/j/123" in body and "calendar.google.com" in body and has_ics
    assert fake.registrants.docs[0]["confirmation_sent_at"]
    # A second call does nothing.
    assert not asyncio.run(routes_delivery.send_confirmation("w1", "r1"))["ok"] and len(sent) == 1
