"""Offline tests: webinar touches post with the user's own OAuth connections, and
the per-touch auto-post / reschedule rules. No mongod needed (tiny in-memory db)."""
import os
from datetime import datetime, timedelta, timezone

import pytest

import _growth_helpers  # noqa: F401  (puts backend/ on sys.path)

os.environ.setdefault("JWT_SECRET", "test")

import routes_delivery  # noqa: E402
import routes_webinars  # noqa: E402
import senders  # noqa: E402
from growth_engine import linkedin as li, meta  # noqa: E402


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None


class _DB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, name):
        return self._c.setdefault(name, _Coll())

    __getattr__ = __getitem__


def _iso(delta):
    return (datetime.now(timezone.utc) + delta).isoformat()


@pytest.fixture
def db(monkeypatch):
    fake = _DB()
    monkeypatch.setattr(routes_delivery, "db", fake)
    monkeypatch.setattr(routes_webinars, "db", fake)
    return fake


def _li_conn(db, owner="u1", expires=timedelta(days=30)):
    db[li.CONNECTIONS_COLLECTION].docs.append({
        "owner_id": owner, "platform": li.PLATFORM, "status": "connected",
        "platform_user_id": "abc123", "access_token_encrypted": "member-token",
        "expires_at": _iso(expires)})


def _meta_conn(db, owner="u1", ig=True):
    page = {"id": "p1", "name": "Page", "token_encrypted": "page-token"}
    db[li.CONNECTIONS_COLLECTION].docs.append({
        "owner_id": owner, "platform": meta.PLATFORM, "status": "connected",
        "page_id": "p1", "pages": [page], **({"ig_id": "ig1"} if ig else {})})


@pytest.mark.asyncio
async def test_member_settings_and_expiry(db):
    assert await li.member_publishing_settings(db, "u1") == {}
    _li_conn(db, expires=timedelta(days=-1))
    assert await li.member_publishing_settings(db, "u1") == {}
    db[li.CONNECTIONS_COLLECTION].docs.clear()
    _li_conn(db)
    assert await li.member_publishing_settings(db, "u1") == {
        "linkedin_member_token": "member-token", "linkedin_member_urn": "urn:li:person:abc123"}


@pytest.mark.asyncio
async def test_user_oauth_overrides_pasted_meta_tokens(db):
    _li_conn(db)
    _meta_conn(db, ig=False)
    s = await routes_delivery._with_user_oauth("u1", {
        "meta_graph_token": "pasted", "meta_page_id": "old", "instagram_business_id": "old-ig"})
    assert s["meta_graph_token"] == "page-token" and s["meta_page_id"] == "p1"
    assert "instagram_business_id" not in s          # Page has no IG: don't keep the pasted one
    assert s["linkedin_member_urn"] == "urn:li:person:abc123"
    # Another user's connection is never used.
    assert await routes_delivery._with_user_oauth("u2", {"x": 1}) == {"x": 1}


@pytest.mark.asyncio
async def test_dispatch_routes_linkedin_and_aliases(monkeypatch):
    calls = []

    async def fake_company(settings, message):
        calls.append(settings["linkedin_org_urn"])
        return senders.DeliveryResult(True, "linkedin")

    async def fake_fb(settings, message, **kw):
        calls.append("fb")
        return senders.DeliveryResult(True, "facebook")

    monkeypatch.setattr(senders, "post_linkedin_company", fake_company)
    monkeypatch.setattr(senders, "post_facebook_page", fake_fb)
    member = {"linkedin_member_token": "t", "linkedin_member_urn": "urn:li:person:abc"}

    r = await senders.dispatch("linkedin_personal", {}, None, None, "s", "b")
    assert not r["ok"] and "Connect LinkedIn" in r["detail"]
    assert (await senders.dispatch("linkedin_personal", member, None, None, "s", "b"))["ok"]
    # linkedin_page (the touch default) falls back to the member when no company token is set
    assert (await senders.dispatch("linkedin_page", member, None, None, "s", "b"))["ok"]
    # ...and uses the company Page when one is configured
    company = {**member, "linkedin_marketing_token": "c", "linkedin_org_urn": "urn:li:organization:9"}
    assert (await senders.dispatch("linkedin", company, None, None, "s", "b"))["ok"]
    assert (await senders.dispatch("facebook_page", {}, None, None, "s", "b"))["ok"]
    assert calls == ["urn:li:person:abc", "urn:li:person:abc", "urn:li:organization:9", "fb"]


def test_touch_auto_send_precedence():
    settings = {"per_touch_auto_send": {"3": True}}
    assert routes_delivery.touch_auto_send({"touch_num": 3}, settings)
    assert not routes_delivery.touch_auto_send({"touch_num": 4}, settings)
    assert not routes_delivery.touch_auto_send({"touch_num": 3, "auto_send": False}, settings)
    assert routes_delivery.touch_auto_send({"touch_num": 4, "auto_send": True}, settings)


@pytest.mark.asyncio
async def test_reschedule_rearms_queued_touch(db):
    db.touches.docs.append({"id": "t1", "owner_id": "u1", "sent_status": "queued",
                            "scheduled_at": _iso(timedelta(hours=-1))})
    future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    extra = await routes_webinars._schedule_update("t1", "u1", {"scheduled_at": future})
    assert extra["sent_status"] == "planned" and extra["scheduled_at"].endswith("+00:00")
    # Turning auto-post on for a touch whose time already passed doesn't fire it late.
    extra = await routes_webinars._schedule_update("t1", "u1", {"auto_send": True})
    assert "sent_status" not in extra
    with pytest.raises(Exception):
        await routes_webinars._schedule_update("t1", "u1", {"scheduled_at": "tomorrow"})
    with pytest.raises(Exception):
        await routes_webinars._schedule_update("t1", "someone-else", {"auto_send": True})
