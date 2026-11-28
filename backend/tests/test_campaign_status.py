"""Campaign status: per-contact email results, resumable invite-list sends, live
progress, post links and the Status tab's per-touch states."""
import asyncio
import os
import sys

import _growth_helpers  # noqa: F401  (puts backend/ on sys.path)

os.environ.setdefault("JWT_SECRET", "test")
if not hasattr(sys.modules.get("database"), "social_images_fs"):
    sys.modules.pop("database", None)

import campaign_status as cs  # noqa: E402
import invites  # noqa: E402
import routes_delivery  # noqa: E402

W = {"id": "w1", "owner_id": "u1", "title": "Supply staff budgets", "starts_at": "2026-12-08T15:00:00Z",
     "timezone": "Europe/London", "join_link": "https://example.org/live", "speaker": "Host"}


def _val_match(dv, v):
    if isinstance(v, dict):
        for op, x in v.items():
            if op == "$ne":
                if dv == x or (isinstance(dv, list) and x in dv):
                    return False
            elif op == "$in":
                if not (dv in x or (isinstance(dv, list) and set(dv) & set(x))):
                    return False
            elif op == "$lte":
                if dv is None or dv > x:
                    return False
            else:
                raise AssertionError(op)
        return True
    if isinstance(dv, list):
        return v in dv
    return dv == v


def _match(d, q):
    for k, v in q.items():
        if k == "$or":
            if not any(_match(d, sub) for sub in v):
                return False
        elif not _val_match(d.get(k), v):
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *a):
        return self

    async def to_list(self, n):
        return [dict(d) for d in self.docs]


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, q, proj=None):
        return _Cursor([d for d in self.docs if _match(d, q)])

    async def find_one(self, q, proj=None):
        return next((dict(d) for d in self.docs if _match(d, q)), None)

    async def insert_many(self, docs, ordered=True):
        self.docs.extend(dict(d) for d in docs)
        return type("R", (), {"inserted_ids": [d.get("id") for d in docs]})()

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if _match(d, q):
                d.update(upd.get("$set", {}))
                for k, v in upd.get("$inc", {}).items():
                    d[k] = d.get(k, 0) + v
                for k in upd.get("$unset", {}):
                    d.pop(k, None)
                for k, v in upd.get("$addToSet", {}).items():
                    d.setdefault(k, [])
                    if v not in d[k]:
                        d[k].append(v)
                return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()

    async def update_many(self, q, upd):
        for d in self.docs:
            if _match(d, q):
                d.update(upd.get("$set", {}))

    async def count_documents(self, q):
        return sum(1 for d in self.docs if _match(d, q))


class _DB:
    def __init__(self):
        self.webinars = _Coll([dict(W)])
        self.registrants = _Coll()
        self.invitees = _Coll()
        self.touches = _Coll()


def _setup(monkeypatch, db, fail=()):
    sent = []

    async def fake_dispatch(ch, settings, to_email, to_phone, subject, body, **kw):
        if ch != "email":
            return {"ok": True, "external_id": "urn:li:share:123"}
        sent.append(to_email)
        if to_email in fail:
            return {"ok": False, "detail": "Daily sending limit reached"}
        return {"ok": True}

    async def brand(*a, **k):
        return {"name": "SBM"}

    monkeypatch.setattr(routes_delivery, "db", db)
    monkeypatch.setattr(routes_delivery, "send_dispatch", fake_dispatch)
    monkeypatch.setattr(routes_delivery.brand_kit, "resolve", brand)
    monkeypatch.setattr(routes_delivery.touch_visuals, "has_visual", lambda n: False)
    return sent


def _touch(**kw):
    copy = {"subject": "s", "body": "Hi {{first_name}}"}
    t = {"id": "t2", "webinar_id": "w1", "owner_id": "u1", "touch_num": 2, "channels": ["email"],
         "approval_status": "approved", "auto_send": True, "sent_status": "planned",
         "scheduled_at": "2026-11-29T15:00:00+00:00",
         "ai_copy": {"channels": {"email": {"safe": copy}, "linkedin_personal": {"safe": copy}}}}
    t.update(kw)
    return t


def _people(db, n):
    asyncio.run(invites.import_invitees(db, "w1", "u1", [{"name": f"P{i}", "email": f"p{i}@s.org"} for i in range(n)]))


def test_each_contact_records_result_and_touch_shows_progress(monkeypatch):
    db = _DB()
    _people(db, 3)
    _setup(monkeypatch, db, fail={"p1@s.org"})
    t = _touch()
    db.touches.docs.append(dict(t))
    res = asyncio.run(routes_delivery._deliver_touch(t, {}, public_backend_url=""))
    line = res["log"][0]
    assert (line["invite_sent"], line["invite_failed"], line["invite_total"]) == (2, 1, 3)
    by = {d["email"]: d for d in db.invitees.docs}
    assert by["p0@s.org"]["sent_touches"] == ["t2"] and "last_error" not in by["p0@s.org"]
    assert by["p1@s.org"]["last_error"].startswith("Daily sending limit") and by["p1@s.org"]["fails"] == 1
    prog = db.touches.docs[0]["send_progress"]
    assert prog["done"] and (prog["sent"], prog["failed"], prog["total"]) == (2, 1, 3)


def test_resumed_send_skips_people_already_emailed(monkeypatch):
    db = _DB()
    _people(db, 3)
    db.invitees.docs[0]["sent_touches"] = ["t2"]          # went out before a restart
    sent = _setup(monkeypatch, db)
    t = _touch()
    db.touches.docs.append(dict(t))
    res = asyncio.run(routes_delivery._deliver_touch(t, {}, public_backend_url=""))
    assert sent == ["p1@s.org", "p2@s.org"]
    assert res["log"][0]["invite_sent"] == 3 and res["log"][0]["invite_total"] == 3
    # Everyone done already: nothing is sent again, and the touch still counts as delivered.
    sent.clear()
    res = asyncio.run(routes_delivery._deliver_touch(t, {}, public_backend_url=""))
    assert sent == [] and res["ok"] and res["log"][0]["invite_sent"] == 3


def test_posts_keep_their_link(monkeypatch):
    db = _DB()
    _setup(monkeypatch, db)
    t = _touch(channels=["linkedin_personal"])
    res = asyncio.run(routes_delivery._deliver_touch(t, {}, public_backend_url=""))
    post = res["log"][0]
    assert post["external_id"] == "urn:li:share:123"
    assert post["url"] == "https://www.linkedin.com/feed/update/urn:li:share:123/"


def test_scheduler_claims_a_touch_before_sending(monkeypatch):
    db = _DB()
    _people(db, 2)
    sent = _setup(monkeypatch, db)

    async def settings(uid):
        return {}

    monkeypatch.setattr(routes_delivery, "_user_settings_decrypted", settings)
    due = "2026-01-01T15:00:00+00:00"
    db.touches.docs.append(_touch(scheduled_at=due))
    db.touches.docs.append(_touch(id="t3", scheduled_at=due, sent_status="sending",
                                  sending_started_at="2999-01-01T00:00:00+00:00"))
    db.webinars.docs[0]["starts_at"] = "2999-01-01T00:00:00Z"
    asyncio.run(routes_delivery.scheduler_tick())
    # t2 went out once; t3 is mid-send elsewhere (fresh claim) and is left alone.
    assert sent == ["p0@s.org", "p1@s.org"]
    assert db.touches.docs[0]["sent_status"] == "sent"
    assert db.touches.docs[1]["sent_status"] == "sending"


def test_status_view_states_and_counts():
    db = _DB()
    _people(db, 4)
    now_past, future = "2026-01-01T09:00:00+00:00", "2999-01-01T09:00:00+00:00"
    db.touches.docs = [
        _touch(id="a", touch_num=2, sent_status="sent", delivery_log=[
            {"channel": "email", "recipient": "invite list (4)", "ok": True, "detail": "x",
             "invite_sent": 3, "invite_failed": 1, "invite_total": 4},
            {"channel": "linkedin_personal", "ok": True, "external_id": "urn:li:share:9",
             "url": "https://www.linkedin.com/feed/update/urn:li:share:9/"},
            {"channel": "facebook", "ok": False, "detail": "Facebook not connected"}]),
        _touch(id="b", touch_num=3, approval_status="pending", scheduled_at=now_past),
        _touch(id="c", touch_num=4, scheduled_at=future),
        _touch(id="d", touch_num=5, scheduled_at=future, auto_send=False),
        _touch(id="e", touch_num=6, scheduled_at=future, sent_status="sending",
               send_progress={"sent": 2, "failed": 0, "total": 4, "done": False}),
    ]
    out = asyncio.run(cs.build(db, W, {"linkedin_member_token": "x"}, lambda t, s: bool(t.get("auto_send"))))
    st = {t["touch_num"]: t for t in out["touches"]}
    assert [st[n]["state"] for n in (2, 3, 4, 5, 6)] == ["sent", "missed", "scheduled", "manual", "sending"]
    assert st[2]["email"]["invite_sent"] == 3 and st[2]["email"]["invite_failed"] == 1
    assert st[6]["email"]["invite_sent"] == 2 and st[6]["email"]["invite_total"] == 4
    assert st[2]["posts"][0]["url"].endswith("urn:li:share:9/") and not st[2]["posts"][1]["ok"]
    assert any("Facebook not connected" in e for e in st[2]["errors"])
    assert out["next_send"]["touch_num"] == 4 and out["linkedin_connected"]
    assert out["contacts"]["total"] == 4 and out["totals"]["emails_sent"] == 5  # 3 done + 2 in flight


def test_older_invite_log_lines_still_count():
    c = cs.email_counts([{"channel": "email", "recipient": "invite list (5)", "ok": True,
                          "detail": "invite list: 4 sent, 1 failed"}], None)
    assert (c["invite_sent"], c["invite_failed"]) == (4, 1)
