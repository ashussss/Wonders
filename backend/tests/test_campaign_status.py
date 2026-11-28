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
            elif op == "$gt":
                if dv is None or dv <= x:
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
        if upsert:
            d = {k: v for k, v in q.items() if not isinstance(v, dict)}
            self.docs.append(d)
            return await self.update_one(q, upd)
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
        self.email_quota = _Coll()


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


def _sched(monkeypatch, settings_doc):
    async def settings(uid):
        return dict(settings_doc)
    monkeypatch.setattr(routes_delivery, "_user_settings_decrypted", settings)


def test_daily_limit_sends_in_batches_fewest_emails_first(monkeypatch):
    import email_quota
    db = _DB()
    _people(db, 5)
    db.invitees.docs[0]["sends"] = 3                      # already had emails: goes last
    sent = _setup(monkeypatch, db)
    _sched(monkeypatch, {"email_daily_limit": 2})
    db.webinars.docs[0]["starts_at"] = "2999-01-01T00:00:00Z"
    db.touches.docs.append(_touch(scheduled_at="2026-01-01T15:00:00+00:00",
                                  channels=["email", "linkedin_personal"]))
    asyncio.run(routes_delivery.scheduler_tick())
    t = db.touches.docs[0]
    assert sent == ["p1@s.org", "p2@s.org"]
    assert t["sent_status"] == "planned" and t["invite_backlog"] and t["retry_at"].endswith("15:00:00+00:00")
    assert any(d["channel"] == "linkedin_personal" for d in t["delivery_log"])
    assert asyncio.run(email_quota.used_today(db, "u1")) == 2
    # Status tab says it is waiting for tomorrow, with 3 still to go.
    out = asyncio.run(cs.build(db, W, {}, lambda t, s: True))
    row = out["touches"][0]
    assert row["state"] == "limit_wait" and row["email"]["invite_held"] == 3 and row["resume_at"]

    # Next day: the quota is fresh, the rest goes out, the post is not made again.
    sent.clear()
    db.email_quota.docs.clear()
    t["retry_at"] = "2026-01-02T15:00:00+00:00"
    asyncio.run(routes_delivery.scheduler_tick())
    assert sent == ["p3@s.org", "p4@s.org"]
    assert sum(1 for d in t["delivery_log"] if d["channel"] == "linkedin_personal") == 1
    inv = [d for d in t["delivery_log"] if "invite_total" in d]
    assert len(inv) == 1 and inv[0]["invite_sent"] == 4 and inv[0]["invite_held"] == 1
    sent.clear()
    db.email_quota.docs.clear()
    t["retry_at"] = "2026-01-03T15:00:00+00:00"
    asyncio.run(routes_delivery.scheduler_tick())
    assert sent == ["p0@s.org"] and t["sent_status"] == "sent" and not t["invite_backlog"]


def test_held_list_stops_when_next_touch_is_due(monkeypatch):
    db = _DB()
    _people(db, 3)
    sent = _setup(monkeypatch, db)
    _sched(monkeypatch, {"email_daily_limit": 1})
    db.webinars.docs[0]["starts_at"] = "2999-01-01T00:00:00Z"
    db.touches.docs.append(_touch(scheduled_at="2026-01-01T15:00:00+00:00", sent_status="planned",
                                  invite_backlog=True, retry_at="2026-01-02T15:00:00+00:00"))
    db.touches.docs.append(_touch(id="t4", touch_num=4, scheduled_at="2026-01-02T09:00:00+00:00"))
    asyncio.run(routes_delivery.scheduler_tick())
    old, new = db.touches.docs
    assert old["sent_status"] == "sent" and old["backlog_superseded"]
    assert len(sent) == 1 and new["invite_backlog"]


def test_no_limit_means_everyone_at_once(monkeypatch):
    db = _DB()
    _people(db, 4)
    sent = _setup(monkeypatch, db)
    _sched(monkeypatch, {})
    db.webinars.docs[0]["starts_at"] = "2999-01-01T00:00:00Z"
    db.touches.docs.append(_touch(scheduled_at="2026-01-01T15:00:00+00:00"))
    asyncio.run(routes_delivery.scheduler_tick())
    assert len(sent) == 4 and db.touches.docs[0]["sent_status"] == "sent"


def test_resume_time_is_next_day_at_touch_time():
    import email_quota
    from datetime import datetime, timezone
    now = datetime(2026, 11, 29, 15, 40, tzinfo=timezone.utc)
    assert email_quota.resume_at("2026-11-29T15:00:00+00:00", now) == "2026-11-30T15:00:00+00:00"
    late = datetime(2026, 11, 29, 23, 50, tzinfo=timezone.utc)
    assert email_quota.resume_at("2026-11-29T23:30:00+00:00", late) == "2026-11-30T23:30:00+00:00"
