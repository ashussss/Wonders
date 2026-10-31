"""Offline tests for PayPal billing: entitlement, plan limits, checkout, confirm,
cancel and webhooks. PayPal and Mongo are faked; no network, no mongod."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import _growth_helpers  # noqa: F401  (puts backend/ on sys.path)

os.environ.setdefault("JWT_SECRET", "test")
if not hasattr(sys.modules.get("database"), "social_images_fs"):
    sys.modules.pop("database", None)

import billing  # noqa: E402
from auth_utils import get_user  # noqa: E402


def _match(doc, q):
    for k, v in q.items():
        if isinstance(v, dict) and "$gte" in v:
            if not (doc.get(k) is not None and doc.get(k) >= v["$gte"]):
                return False
        elif doc.get(k) != v:
            return False
    return True


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if _match(d, q):
                return dict(d)
        return None

    async def count_documents(self, q):
        return sum(1 for d in self.docs if _match(d, q))

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if _match(d, q):
                d.update(upd.get("$set", {}))
                for k in upd.get("$unset", {}):
                    d.pop(k, None)
                return
        if upsert:
            self.docs.append({**q, **upd.get("$set", {})})


class _DB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, name):
        return self._c.setdefault(name, _Coll())

    __getattr__ = __getitem__


def _iso(delta=timedelta()):
    return (datetime.now(timezone.utc) + delta).isoformat()


PLAN_IDS = {"starter": "P-STARTER", "growth": "P-GROWTH", "agency": "P-AGENCY"}


class FakePayPal:
    def __init__(self):
        self.subs = {}
        self.calls = []
        self.verify = "SUCCESS"

    async def __call__(self, method, path, payload=None, content=None):
        self.calls.append((method, path, payload if content is None else json.loads(content)))
        if path == "/v1/billing/subscriptions" and method == "POST":
            sid = f"I-{len(self.subs) + 1}"
            self.subs[sid] = {"id": sid, "plan_id": payload["plan_id"], "custom_id": payload["custom_id"],
                              "status": "APPROVAL_PENDING", "billing_info": {}}
            return {"id": sid, "links": [{"rel": "approve", "href": f"https://paypal.test/approve/{sid}"}]}
        if path.startswith("/v1/billing/subscriptions/") and path.endswith("/cancel"):
            sid = path.split("/")[4]
            self.subs[sid]["status"] = "CANCELLED"
            self.subs[sid]["billing_info"].pop("next_billing_time", None)
            return {}
        if path.startswith("/v1/billing/subscriptions/") and method == "GET":
            return dict(self.subs[path.split("/")[-1]])
        if path == "/v1/notifications/verify-webhook-signature":
            return {"verification_status": self.verify}
        raise AssertionError(f"unexpected PayPal call {method} {path}")

    def activate(self, sid, days=30):
        self.subs[sid]["status"] = "ACTIVE"
        self.subs[sid]["billing_info"] = {"next_billing_time": _iso(timedelta(days=days)),
                                          "last_payment": {"time": _iso()}, "failed_payments_count": 0}


@pytest.fixture
def env(monkeypatch):
    fake_db, pp = _DB(), FakePayPal()
    monkeypatch.setattr(billing, "db", fake_db)
    monkeypatch.setattr(billing, "paypal", pp)
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "cid")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "secret")
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-1")
    for k, v in PLAN_IDS.items():
        monkeypatch.setenv(f"PAYPAL_PLAN_{k.upper()}", v)
    user = {"id": "u1", "email": "a@b.com", "name": "A", "role": "user", "created_at": _iso()}
    fake_db.users.docs.append(dict(user))

    app = FastAPI()
    app.include_router(billing.router)

    async def _current_user():
        return await fake_db.users.find_one({"id": "u1"})
    app.dependency_overrides[get_user] = _current_user
    return fake_db, pp, TestClient(app)


# ── entitlement ──────────────────────────────────────────────────────────────
def test_new_user_is_on_trial():
    ent = billing.entitlement({"created_at": _iso(-timedelta(days=3))})
    assert ent["active"] and ent["plan"] == "trial"


def test_trial_ends_after_14_days():
    ent = billing.entitlement({"created_at": _iso(-timedelta(days=15))})
    assert not ent["active"] and ent["reason"] == "trial_ended"


def test_admin_is_never_blocked():
    ent = billing.entitlement({"role": "superadmin", "created_at": _iso(-timedelta(days=400))})
    assert ent["active"] and ent["plan"] == "agency"


def test_cancelled_keeps_access_until_paid_through():
    old = _iso(-timedelta(days=60))
    paid = {"created_at": old, "billing": {"plan": "growth", "status": "CANCELLED",
                                           "paid_through": _iso(timedelta(days=5))}}
    lapsed = {"created_at": old, "billing": {"plan": "growth", "status": "CANCELLED",
                                             "paid_through": _iso(-timedelta(days=1))}}
    assert billing.entitlement(paid)["active"]
    assert not billing.entitlement(lapsed)["active"]


# ── plan limits ──────────────────────────────────────────────────────────────
async def test_quota_not_enforced_by_default(env, monkeypatch):
    monkeypatch.delenv("BILLING_ENFORCE", raising=False)
    await billing.require_webinar_quota({"id": "u1", "created_at": _iso(-timedelta(days=90))})


async def test_expired_trial_blocks_new_webinars(env, monkeypatch):
    monkeypatch.setenv("BILLING_ENFORCE", "true")
    with pytest.raises(HTTPException) as e:
        await billing.require_webinar_quota({"id": "u1", "created_at": _iso(-timedelta(days=90))})
    assert e.value.status_code == 402


async def test_starter_capped_at_five_webinars_a_month(env, monkeypatch):
    fake_db, _, _ = env
    monkeypatch.setenv("BILLING_ENFORCE", "true")
    user = {"id": "u1", "created_at": _iso(-timedelta(days=90)),
            "billing": {"plan": "starter", "status": "ACTIVE"}}
    for _ in range(4):
        fake_db.webinars.docs.append({"owner_id": "u1", "created_at": _iso()})
    await billing.require_webinar_quota(user)
    fake_db.webinars.docs.append({"owner_id": "u1", "created_at": _iso()})
    with pytest.raises(HTTPException) as e:
        await billing.require_webinar_quota(user)
    assert e.value.status_code == 402
    user["billing"]["plan"] = "growth"
    await billing.require_webinar_quota(user)


# ── checkout ─────────────────────────────────────────────────────────────────
def test_subscribe_then_confirm_activates_plan(env):
    fake_db, pp, client = env
    r = client.post("/api/billing/subscribe", json={"plan": "growth"})
    assert r.status_code == 200, r.text
    sid = r.json()["subscription_id"]
    assert r.json()["approve_url"].endswith(sid)
    body = pp.calls[0][2]
    assert body["plan_id"] == "P-GROWTH" and body["custom_id"] == "u1"
    assert body["application_context"]["return_url"].endswith("/app/billing?paypal=success")

    pp.activate(sid)
    r = client.post("/api/billing/confirm", json={"subscription_id": sid})
    assert r.status_code == 200, r.text
    assert r.json()["plan"] == "growth" and r.json()["reason"] == "subscribed"
    u = fake_db.users.docs[0]
    assert u["billing"]["status"] == "ACTIVE" and "billing_pending" not in u


def test_confirm_rejects_someone_elses_subscription(env):
    _, pp, client = env
    pp.subs["I-X"] = {"id": "I-X", "plan_id": "P-GROWTH", "custom_id": "other", "status": "ACTIVE",
                      "billing_info": {}}
    r = client.post("/api/billing/confirm", json={"subscription_id": "I-X"})
    assert r.status_code == 403


def test_unknown_plan_rejected(env):
    _, _, client = env
    assert client.post("/api/billing/subscribe", json={"plan": "gold"}).status_code == 400


def test_upgrade_cancels_old_subscription(env):
    fake_db, pp, client = env
    s1 = client.post("/api/billing/subscribe", json={"plan": "starter"}).json()["subscription_id"]
    pp.activate(s1)
    client.post("/api/billing/confirm", json={"subscription_id": s1})
    s2 = client.post("/api/billing/subscribe", json={"plan": "growth"}).json()["subscription_id"]
    pp.activate(s2)
    r = client.post("/api/billing/confirm", json={"subscription_id": s2})
    assert r.json()["plan"] == "growth"
    assert pp.subs[s1]["status"] == "CANCELLED"
    # The old subscription's late CANCELLED webhook must not downgrade the account.
    _webhook(client, "BILLING.SUBSCRIPTION.CANCELLED", {"id": s1}, "WH-EVT-OLD")
    assert fake_db.users.docs[0]["billing"]["subscription_id"] == s2
    assert fake_db.users.docs[0]["billing"]["status"] == "ACTIVE"


def test_cancel_keeps_access_to_end_of_period(env):
    fake_db, pp, client = env
    sid = client.post("/api/billing/subscribe", json={"plan": "growth"}).json()["subscription_id"]
    pp.activate(sid, days=20)
    client.post("/api/billing/confirm", json={"subscription_id": sid})
    r = client.post("/api/billing/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["active"] and r.json()["reason"] == "paid_period"
    assert fake_db.users.docs[0]["billing"]["status"] == "CANCELLED"


# ── webhooks ─────────────────────────────────────────────────────────────────
_HEADERS = {"paypal-auth-algo": "SHA256withRSA", "paypal-cert-url": "https://api.paypal.com/cert",
            "paypal-transmission-id": "t1", "paypal-transmission-sig": "sig",
            "paypal-transmission-time": "2026-10-22T00:00:00Z"}


def _webhook(client, kind, resource, event_id):
    raw = json.dumps({"id": event_id, "event_type": kind, "resource": resource})
    return client.post("/api/billing/webhook", content=raw, headers=_HEADERS)


def test_webhook_activation_and_renewal_payment(env):
    fake_db, pp, client = env
    sid = client.post("/api/billing/subscribe", json={"plan": "starter"}).json()["subscription_id"]
    pp.activate(sid)
    assert _webhook(client, "BILLING.SUBSCRIPTION.ACTIVATED", {"id": sid}, "E1").status_code == 200
    assert fake_db.users.docs[0]["billing"]["plan"] == "starter"
    r = _webhook(client, "PAYMENT.SALE.COMPLETED",
                 {"id": "SALE1", "billing_agreement_id": sid, "amount": {"total": "29.00", "currency": "USD"}}, "E2")
    assert r.status_code == 200
    assert fake_db.billing_payments.docs[0]["user_id"] == "u1"
    # Verify call carried the raw event and our webhook id.
    verify = [c for c in pp.calls if c[1] == "/v1/notifications/verify-webhook-signature"][0][2]
    assert verify["webhook_id"] == "WH-1" and verify["webhook_event"]["id"] == "E1"


def test_webhook_suspension_after_failed_payments(env):
    fake_db, pp, client = env
    sid = client.post("/api/billing/subscribe", json={"plan": "growth"}).json()["subscription_id"]
    pp.activate(sid)
    _webhook(client, "BILLING.SUBSCRIPTION.ACTIVATED", {"id": sid}, "E1")
    pp.subs[sid]["status"] = "SUSPENDED"
    pp.subs[sid]["billing_info"]["next_billing_time"] = _iso(-timedelta(days=1))
    _webhook(client, "BILLING.SUBSCRIPTION.SUSPENDED", {"id": sid}, "E3")
    u = fake_db.users.docs[0]
    assert u["billing"]["status"] == "SUSPENDED"
    u["created_at"] = _iso(-timedelta(days=60))
    assert not billing.entitlement(u)["active"]


def test_webhook_bad_signature_rejected(env):
    fake_db, pp, client = env
    pp.verify = "FAILURE"
    assert _webhook(client, "BILLING.SUBSCRIPTION.ACTIVATED", {"id": "I-1"}, "E9").status_code == 400
    assert not fake_db.billing_events.docs


def test_webhook_duplicate_is_ignored(env):
    fake_db, pp, client = env
    sid = client.post("/api/billing/subscribe", json={"plan": "growth"}).json()["subscription_id"]
    pp.activate(sid)
    _webhook(client, "BILLING.SUBSCRIPTION.ACTIVATED", {"id": sid}, "E1")
    r = _webhook(client, "BILLING.SUBSCRIPTION.ACTIVATED", {"id": sid}, "E1")
    assert r.json().get("duplicate") is True


def test_webhook_rejected_without_webhook_id(env, monkeypatch):
    _, _, client = env
    monkeypatch.delenv("PAYPAL_WEBHOOK_ID")
    assert _webhook(client, "BILLING.SUBSCRIPTION.ACTIVATED", {"id": "I-1"}, "E1").status_code == 400


# ── one-step checkout ────────────────────────────────────────────────────────
@pytest.fixture
def checkout_env(env, monkeypatch):
    fake_db, pp, client = env
    import routes_auth
    monkeypatch.setattr(routes_auth, "db", fake_db)
    monkeypatch.setattr(billing, "create_user", routes_auth.create_user)
    return fake_db, pp, client


def test_checkout_new_email_creates_account_and_paypal_link(checkout_env):
    fake_db, pp, client = checkout_env
    r = client.post("/api/billing/checkout", json={"plan": "growth", "email": "New@Host.com", "password": "longpass1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approve_url"].startswith("https://paypal.test/approve/") and body["token"]
    new = next(u for u in fake_db.users.docs if u["email"] == "new@host.com")
    assert new["name"] == "new" and new["password"] != "longpass1"
    assert pp.subs[body["subscription_id"]]["custom_id"] == new["id"]
    assert fake_db.settings.docs[0]["owner_id"] == new["id"]


def test_checkout_existing_email_needs_right_password(checkout_env):
    fake_db, _, client = checkout_env
    from auth_utils import hash_pw
    fake_db.users.docs[0]["password"] = hash_pw("rightpass")
    bad = client.post("/api/billing/checkout", json={"plan": "starter", "email": "a@b.com", "password": "wrong"})
    assert bad.status_code == 401
    ok = client.post("/api/billing/checkout", json={"plan": "starter", "email": "a@b.com", "password": "rightpass"})
    assert ok.status_code == 200, ok.text
    assert len(fake_db.users.docs) == 1


def test_checkout_validates_input(checkout_env):
    fake_db, _, client = checkout_env
    assert client.post("/api/billing/checkout", json={"plan": "gold", "email": "x@y.com", "password": "longpass1"}).status_code == 400
    assert client.post("/api/billing/checkout", json={"plan": "growth", "email": "nope", "password": "longpass1"}).status_code == 400
    assert client.post("/api/billing/checkout", json={"plan": "growth", "email": "x@y.com", "password": "short"}).status_code == 400
    assert len(fake_db.users.docs) == 1


def test_checkout_does_not_create_account_when_payments_off(checkout_env, monkeypatch):
    fake_db, _, client = checkout_env
    monkeypatch.delenv("PAYPAL_CLIENT_ID")
    r = client.post("/api/billing/checkout", json={"plan": "growth", "email": "x@y.com", "password": "longpass1"})
    assert r.status_code == 503
    assert len(fake_db.users.docs) == 1


def test_first_checkout_creates_paypal_plans(env, monkeypatch):
    fake_db, pp, client = env
    for k in PLAN_IDS:
        monkeypatch.delenv(f"PAYPAL_PLAN_{k.upper()}")
    created = []
    real = pp.__call__

    async def with_catalog(method, path, payload=None, content=None):
        if path == "/v1/catalogs/products":
            return {"id": "PROD-1"}
        if path == "/v1/billing/plans":
            created.append(payload["name"])
            return {"id": f"P-NEW-{len(created)}"}
        return await real(method, path, payload, content)
    monkeypatch.setattr(billing, "paypal", with_catalog)

    r = client.post("/api/billing/subscribe", json={"plan": "starter"})
    assert r.status_code == 200, r.text
    assert len(created) == 3
    assert fake_db.billing_config.docs[0]["plans"]["starter"] == "P-NEW-1"
    # Second checkout reuses the stored plans.
    client.post("/api/billing/subscribe", json={"plan": "growth"})
    assert len(created) == 3


def test_subscribe_without_keys_says_not_set_up(env, monkeypatch):
    _, _, client = env
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET")
    r = client.post("/api/billing/subscribe", json={"plan": "starter"})
    assert r.status_code == 503
