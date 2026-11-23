"""Invite list: warm-up emails reach people who haven't registered, with the
registration link and an unsubscribe link, and stop once they register."""
import asyncio
import os
import re
import sys

import _growth_helpers  # noqa: F401  (puts backend/ on sys.path)

os.environ.setdefault("JWT_SECRET", "test")
if not hasattr(sys.modules.get("database"), "social_images_fs"):
    sys.modules.pop("database", None)

import invites  # noqa: E402
import routes_delivery  # noqa: E402
import senders  # noqa: E402
import touch_render  # noqa: E402

W = {"id": "w1", "owner_id": "u1", "title": "Budget season for schools", "starts_at": "2026-12-08T10:00:00Z",
     "timezone": "Europe/London", "join_link": "https://zoom.us/j/999", "speaker": "Host"}


def _match(d, q):
    for k, v in q.items():
        if isinstance(v, dict) and "$ne" in v:
            if d.get(k) == v["$ne"]:
                return False
        elif d.get(k) != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, n):
        return [dict(d) for d in self.docs[:n]]


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, q, proj=None):
        return _Cursor([d for d in self.docs if _match(d, q)])

    async def find_one(self, q, proj=None):
        return next((dict(d) for d in self.docs if _match(d, q)), None)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if _match(d, q):
                d.update(upd.get("$set", {}))
                for k, v in upd.get("$inc", {}).items():
                    d[k] = d.get(k, 0) + v
                return

    async def update_many(self, q, upd):
        for d in self.docs:
            if _match(d, q):
                d.update(upd.get("$set", {}))

    async def count_documents(self, q):
        return sum(1 for d in self.docs if _match(d, q))


class _DB:
    def __init__(self):
        self.webinars = _Coll([dict(W)])
        self.registrants = _Coll([{"id": "r1", "webinar_id": "w1", "name": "Riya", "email": "riya@x.io"}])
        self.invitees = _Coll()
        self.touches = _Coll()


def test_import_skips_registered_duplicates_and_past_unsubscribes():
    db = _DB()
    db.invitees.docs.append({**invites.new_invitee("w0", "u1", "Old", "gone@x.io"), "unsubscribed": True})
    out = asyncio.run(invites.import_invitees(db, "w1", "u1", [
        {"name": "Sam", "email": "Sam@School.org"}, {"name": "Sam again", "email": "sam@school.org"},
        {"name": "Riya", "email": "riya@x.io"}, {"name": "Gone", "email": "gone@x.io"}]))
    assert out == {"inserted": 1, "deduped": 1, "already_registered": 1, "unsubscribed_before": 1}
    assert asyncio.run(invites.summary(db, "w1"))["reachable"] == 1


def test_invite_render_points_join_link_at_registration():
    body = "Hi {{first_name}},\n\nSave a seat: {{join_link}}"
    out = touch_render.render(body, W, "email", {"name": "sam lee"}, invite=True)
    assert out.startswith("Hi Sam,") and "/r/w1" in out and "zoom.us" not in out
    # Registrants still get the live room link.
    assert "zoom.us/j/999" in touch_render.render(body, W, "email", {"name": "Riya"})


def test_email_touches_reach_invitees_except_confirmation_and_thanks():
    db = _DB()
    asyncio.run(invites.import_invitees(db, "w1", "u1", [{"name": "Sam", "email": "sam@school.org"}]))
    assert len(asyncio.run(invites.invite_targets(db, {"webinar_id": "w1", "touch_num": 5, "channels": ["email"]}))) == 1
    for n in (2, 3, 4, 5, 6, 7, 8, 9, 11, 12):
        assert asyncio.run(invites.invite_targets(db, {"webinar_id": "w1", "touch_num": n, "channels": ["email"]}))
    for t in ({"touch_num": 1, "channels": ["email"]}, {"touch_num": 10, "channels": ["email"]},
              {"touch_num": 5, "channels": ["linkedin_page"]}):
        assert asyncio.run(invites.invite_targets(db, {"webinar_id": "w1", **t})) == []
    asyncio.run(invites.mark_registered(db, "w1", "SAM@school.org"))
    assert asyncio.run(invites.invite_targets(db, {"webinar_id": "w1", "touch_num": 5, "channels": ["email"]})) == []


def test_deliver_touch_emails_invitees_with_unsubscribe(monkeypatch):
    db = _DB()
    db.registrants.docs = []          # no registrants yet: invitees must still get it
    asyncio.run(invites.import_invitees(db, "w1", "u1", [{"name": "Sam", "email": "sam@school.org"}]))
    sent = []

    async def fake_dispatch(ch, settings, to_email, to_phone, subject, body, ics_bytes=None, image_url=None,
                            link_labels=None, unsubscribe_url="", unsubscribe_reason=""):
        sent.append((ch, to_email, body, unsubscribe_url, unsubscribe_reason))
        return {"ok": True}

    async def brand(*a, **k):
        return {"name": "School Business Manager"}

    monkeypatch.setenv("PUBLIC_BACKEND_URL", "https://api.example")
    monkeypatch.setattr(routes_delivery, "db", db)
    monkeypatch.setattr(routes_delivery, "send_dispatch", fake_dispatch)
    monkeypatch.setattr(routes_delivery.brand_kit, "resolve", brand)
    monkeypatch.setattr(routes_delivery.touch_visuals, "has_visual", lambda n: False)
    t = {"id": "t5", "webinar_id": "w1", "owner_id": "u1", "touch_num": 5, "channels": ["email"],
         "ai_copy": {"channels": {"email": {"safe": {"subject": "a story", "body": "Hi {{first_name}},\n\n{{join_link}}"}}}}}
    res = asyncio.run(routes_delivery._deliver_touch(t, {}, public_backend_url=""))
    assert res["ok"] and len(sent) == 1
    ch, to, body, unsub, reason = sent[0]
    assert to == "sam@school.org" and "/r/w1" in body and "zoom.us" not in body
    assert re.fullmatch(r"https://api\.example/api/unsubscribe/[0-9a-f-]{36}", unsub)
    assert "School Business Manager" in reason
    assert db.invitees.docs[0]["sends"] == 1
    assert "invite list: 1 sent" in res["log"][0]["detail"]


def test_unsubscribe_covers_all_lists_of_that_host():
    db = _DB()
    asyncio.run(invites.import_invitees(db, "w1", "u1", [{"name": "Sam", "email": "sam@school.org"}]))
    db.invitees.docs.append(invites.new_invitee("w2", "u1", "Sam", "sam@school.org"))
    db.invitees.docs.append(invites.new_invitee("w3", "other", "Sam", "sam@school.org"))
    assert asyncio.run(invites.unsubscribe(db, db.invitees.docs[0]["id"]))
    assert [d["unsubscribed"] for d in db.invitees.docs] == [True, True, False]
    assert asyncio.run(invites.unsubscribe(db, "nope")) is None


def test_invite_email_footer_says_why():
    html = senders.build_email_html("hi", unsubscribe_url="https://u", unsubscribe_reason="On the SBM list.")
    assert "On the SBM list." in html and "registered for this session" not in html
    assert "registered for this session" in senders.build_email_html("hi", unsubscribe_url="https://u")
