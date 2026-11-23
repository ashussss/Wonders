"""Forgot / reset password: one-time expiring link, sent by email, old sessions signed out."""
import asyncio
import os
import re
from datetime import datetime, timedelta, timezone

import _growth_helpers  # noqa: F401  (puts backend/ on sys.path)

os.environ.setdefault("JWT_SECRET", "test")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402

import auth_utils  # noqa: E402
import password_reset  # noqa: E402
import routes_auth  # noqa: E402
import senders  # noqa: E402


def _match(d, q):
    return all(d.get(k) == v for k, v in q.items())


class _Res:
    def __init__(self, n):
        self.modified_count = n


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, q, proj=None):
        return next((dict(d) for d in self.docs if _match(d, q)), None)

    async def insert_one(self, doc):
        self.docs.append({"_id": len(self.docs) + 1, **doc})

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if _match(d, q):
                d.update(upd.get("$set", {}))
                return _Res(1)
        return _Res(0)

    async def delete_many(self, q):
        self.docs = [d for d in self.docs if not _match(d, q)]


class _DB:
    def __init__(self):
        self.users, self.password_resets, self.settings = _Coll(), _Coll(), _Coll()


@pytest.fixture
def env(monkeypatch):
    db = _DB()
    for mod in (routes_auth, password_reset, auth_utils):
        monkeypatch.setattr(mod, "db", db)
    monkeypatch.setenv("SYSTEM_BREVO_API_KEY", "k")
    monkeypatch.setenv("SYSTEM_SENDER_EMAIL", "hello@showupai.live")
    sent = []

    async def fake_send(settings, to, subject, html, ics_bytes=None):
        sent.append({"settings": settings, "to": to, "subject": subject, "html": html})
        return senders.DeliveryResult(True, "brevo")
    monkeypatch.setattr(senders, "send_email", fake_send)
    monkeypatch.setattr(routes_auth.limiter, "enabled", False)
    app = FastAPI()
    app.state.limiter = routes_auth.limiter
    app.include_router(routes_auth.router)
    old_pw = auth_utils.hash_pw("oldpassword1")
    asyncio.run(db.users.insert_one({"id": "u1", "email": "ashu@x.io", "name": "Ashu", "password": old_pw}))
    return db, app, sent


def _call(app, method, path, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.request(method, path, **kw)
    return asyncio.run(go())


def _token_from(sent):
    return re.search(r"reset-password\?token=([\w-]+)", sent[-1]["html"]).group(1)


def test_forgot_sends_link_and_reset_works_once(env):
    db, app, sent = env
    r = _call(app, "POST", "/api/auth/forgot-password", json={"email": "ASHU@x.io"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert sent[-1]["to"] == "ashu@x.io"
    assert sent[-1]["settings"]["brevo_sender_email"] == "hello@showupai.live"
    token = _token_from(sent)
    assert "https://showupai.live/reset-password?token=" in sent[-1]["html"]
    # only the hash is stored
    assert db.password_resets.docs[0]["token_hash"] != token

    assert _call(app, "GET", "/api/auth/reset-password/check", params={"token": token}).json() == {"valid": True}
    assert _call(app, "POST", "/api/auth/reset-password", json={"token": token, "password": "short"}).status_code == 400

    r = _call(app, "POST", "/api/auth/reset-password", json={"token": token, "password": "newpassword9"})
    assert r.status_code == 200 and r.json()["token"]
    assert auth_utils.verify_pw("newpassword9", db.users.docs[0]["password"])

    # the link is dead after one use
    assert _call(app, "POST", "/api/auth/reset-password", json={"token": token, "password": "another123"}).status_code == 400
    assert _call(app, "GET", "/api/auth/reset-password/check", params={"token": token}).json() == {"valid": False}


def test_unknown_email_gets_same_answer_and_no_mail(env):
    _, app, sent = env
    r = _call(app, "POST", "/api/auth/forgot-password", json={"email": "nobody@x.io"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert sent == []


def test_expired_link_is_refused(env):
    db, app, sent = env
    _call(app, "POST", "/api/auth/forgot-password", json={"email": "ashu@x.io"})
    token = _token_from(sent)
    db.password_resets.docs[0]["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    r = _call(app, "POST", "/api/auth/reset-password", json={"token": token, "password": "newpassword9"})
    assert r.status_code == 400


def test_new_request_kills_older_link(env):
    _, app, sent = env
    _call(app, "POST", "/api/auth/forgot-password", json={"email": "ashu@x.io"})
    first = _token_from(sent)
    _call(app, "POST", "/api/auth/forgot-password", json={"email": "ashu@x.io"})
    assert _call(app, "GET", "/api/auth/reset-password/check", params={"token": first}).json() == {"valid": False}


def test_reset_signs_out_old_sessions_but_not_the_new_one(env):
    db, app, sent = env
    old = auth_utils.make_token("u1")
    me = lambda t: _call(app, "GET", "/api/auth/me", headers={"Authorization": f"Bearer {t}"})  # noqa: E731
    assert me(old).status_code == 200
    # pretend the old session started an hour ago
    import jwt
    payload = jwt.decode(old, auth_utils.JWT_SECRET, algorithms=[auth_utils.JWT_ALG])
    payload["exp"] -= 3600
    old = jwt.encode(payload, auth_utils.JWT_SECRET, algorithm=auth_utils.JWT_ALG)

    _call(app, "POST", "/api/auth/forgot-password", json={"email": "ashu@x.io"})
    new = _call(app, "POST", "/api/auth/reset-password",
                json={"token": _token_from(sent), "password": "newpassword9"}).json()["token"]
    assert me(old).status_code == 401
    assert me(new).status_code == 200


def test_superadmin_settings_used_when_no_env(env, monkeypatch):
    db, app, sent = env
    monkeypatch.delenv("SYSTEM_BREVO_API_KEY")
    asyncio.run(db.users.insert_one({"id": "sa", "email": "owner@x.io", "name": "Owner", "role": "superadmin", "password": "x"}))
    asyncio.run(db.settings.insert_one({"owner_id": "sa", "email_provider": "Brevo",
                                        "brevo_api_key": "abc", "brevo_sender_email": "team@showupai.live"}))
    _call(app, "POST", "/api/auth/forgot-password", json={"email": "ashu@x.io"})
    assert sent[-1]["settings"]["brevo_sender_email"] == "team@showupai.live"
    assert sent[-1]["settings"]["brevo_sender_name"] == "ShowUp AI"


def test_change_password_needs_current_and_keeps_this_session(env):
    db, app, _ = env
    tok = auth_utils.make_token("u1")
    h = {"Authorization": f"Bearer {tok}"}
    r = _call(app, "POST", "/api/auth/change-password", headers=h,
              json={"current_password": "wrong", "new_password": "newpassword9"})
    assert r.status_code == 400
    r = _call(app, "POST", "/api/auth/change-password", headers=h,
              json={"current_password": "oldpassword1", "new_password": "short"})
    assert r.status_code == 400
    r = _call(app, "POST", "/api/auth/change-password", headers=h,
              json={"current_password": "oldpassword1", "new_password": "newpassword9"})
    assert r.status_code == 200
    assert auth_utils.verify_pw("newpassword9", db.users.docs[0]["password"])
    new_h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert _call(app, "GET", "/api/auth/me", headers=new_h).status_code == 200


def test_register_needs_8_char_password(env):
    _, app, _ = env
    r = _call(app, "POST", "/api/auth/register", json={"email": "n@x.io", "name": "N", "password": "short"})
    assert r.status_code == 400
