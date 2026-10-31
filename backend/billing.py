"""PayPal subscriptions: plans, checkout, webhooks and plan limits.

Flow: the user picks a plan on /app/billing -> POST /api/billing/subscribe creates a
PayPal subscription (custom_id = our user id) and returns PayPal's approve link ->
PayPal sends the user back to /app/billing?paypal=success&subscription_id=... ->
POST /api/billing/confirm reads the subscription from PayPal and activates the plan.
Webhooks keep it in sync afterwards (renewals, cancels, failed payments).

PayPal is always the source of truth: confirm and every webhook re-read the
subscription from the PayPal API instead of trusting the request body.

Env (Render):
  PAYPAL_ENV            sandbox | live (default sandbox)
  PAYPAL_CLIENT_ID      REST app client id
  PAYPAL_CLIENT_SECRET  REST app secret
  PAYPAL_WEBHOOK_ID     id of the webhook pointing at /api/billing/webhook
  PAYPAL_PLAN_STARTER / _GROWTH / _AGENCY   optional; otherwise created by
                        POST /api/billing/admin/setup-plans and stored in Mongo
  PUBLIC_APP_URL        frontend base (default https://showupai.live)
  BILLING_ENFORCE       true -> block new webinars once the trial ends without a plan
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import re

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from auth_utils import get_user, make_token, now_iso, verify_pw
from database import db
from routes_auth import create_user

logger = logging.getLogger("showup.billing")
router = APIRouter(prefix="/api/billing")
limiter = Limiter(key_func=get_remote_address)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TRIAL_DAYS = 14
PLANS: Dict[str, Dict[str, Any]] = {
    "starter": {"name": "Starter", "price": "29.00", "webinars_per_month": 5},
    "growth": {"name": "Growth", "price": "79.00", "webinars_per_month": None},
    "agency": {"name": "Agency", "price": "199.00", "webinars_per_month": None},
}
# Statuses PayPal reports for a subscription that is billing normally.
LIVE_STATUSES = {"ACTIVE"}
ADMIN_ROLES = {"admin", "superadmin"}


def _env() -> str:
    return "live" if os.environ.get("PAYPAL_ENV", "sandbox").lower() == "live" else "sandbox"


def _api_base() -> str:
    return "https://api-m.paypal.com" if _env() == "live" else "https://api-m.sandbox.paypal.com"


def _app_url() -> str:
    return os.environ.get("PUBLIC_APP_URL", "https://showupai.live").rstrip("/")


def configured() -> bool:
    return bool(os.environ.get("PAYPAL_CLIENT_ID") and os.environ.get("PAYPAL_CLIENT_SECRET"))


def enforcing() -> bool:
    return os.environ.get("BILLING_ENFORCE", "false").lower() in ("1", "true", "yes")


def _parse_ts(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── PayPal API ───────────────────────────────────────────────────────────────
_token_cache: Dict[str, Any] = {"token": None, "exp": 0.0, "env": None}


async def _access_token() -> str:
    if not configured():
        raise HTTPException(503, "Payments are not set up yet. Please contact support.")
    if _token_cache["token"] and _token_cache["env"] == _env() and _token_cache["exp"] > time.time() + 60:
        return _token_cache["token"]
    # Keys pasted into a dashboard often pick up spaces or quotes.
    client_id = os.environ["PAYPAL_CLIENT_ID"].strip().strip('"\'')
    secret = os.environ["PAYPAL_CLIENT_SECRET"].strip().strip('"\'')
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{_api_base()}/v1/oauth2/token", auth=(client_id, secret),
                             data={"grant_type": "client_credentials"})
    except httpx.HTTPError as e:
        logger.error("paypal token request failed: %s", e)
        raise HTTPException(502, "Could not reach PayPal. Please try again.")
    if r.status_code in (401, 403):
        logger.error("paypal rejected the %s keys: %s %s", _env(), r.status_code, r.text[:300])
        raise HTTPException(503, "Payments are not set up correctly yet. Please contact support.")
    if r.status_code != 200:
        logger.error("paypal token failed: %s %s", r.status_code, r.text[:300])
        raise HTTPException(502, "Could not reach PayPal. Please try again.")
    body = r.json()
    _token_cache.update(token=body["access_token"], exp=time.time() + int(body.get("expires_in", 3000)),
                        env=_env())
    return body["access_token"]


async def paypal(method: str, path: str, payload: Optional[Dict[str, Any]] = None,
                 content: Optional[str] = None) -> Dict[str, Any]:
    token = await _access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
               "Prefer": "return=representation"}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request(method, f"{_api_base()}{path}", headers=headers,
                            json=payload if content is None else None, content=content)
    if r.status_code >= 400:
        logger.error("paypal %s %s failed: %s %s", method, path, r.status_code, r.text[:500])
        raise HTTPException(502, f"PayPal error ({r.status_code}). Please try again.")
    return r.json() if r.content else {}


# ── Plans ────────────────────────────────────────────────────────────────────
def _config_id() -> str:
    return f"paypal_plans_{_env()}"


async def plan_ids() -> Dict[str, str]:
    """{plan_key: paypal_plan_id}. Env vars win over the ids stored by setup-plans."""
    stored = await db.billing_config.find_one({"_id": _config_id()}) or {}
    ids = dict(stored.get("plans") or {})
    for key in PLANS:
        env_id = os.environ.get(f"PAYPAL_PLAN_{key.upper()}")
        if env_id:
            ids[key] = env_id
    return ids


async def plan_key_for(paypal_plan_id: str) -> Optional[str]:
    for key, pid in (await plan_ids()).items():
        if pid == paypal_plan_id:
            return key
    return None


async def setup_plans() -> Dict[str, str]:
    """Create the ShowUp AI product and the three monthly plans in PayPal, once per env."""
    ids = await plan_ids()
    if all(k in ids for k in PLANS):
        return ids
    stored = await db.billing_config.find_one({"_id": _config_id()}) or {}
    product_id = stored.get("product_id")
    if not product_id:
        product = await paypal("POST", "/v1/catalogs/products", {
            "name": "ShowUp AI", "description": "Webinar attendance booster",
            "type": "SERVICE", "category": "SOFTWARE", "home_url": _app_url()})
        product_id = product["id"]
    for key, p in PLANS.items():
        if key in ids:
            continue
        plan = await paypal("POST", "/v1/billing/plans", {
            "product_id": product_id, "name": f"ShowUp AI {p['name']}", "status": "ACTIVE",
            "description": f"ShowUp AI {p['name']} plan, billed monthly",
            "billing_cycles": [{
                "frequency": {"interval_unit": "MONTH", "interval_count": 1},
                "tenure_type": "REGULAR", "sequence": 1, "total_cycles": 0,
                "pricing_scheme": {"fixed_price": {"value": p["price"], "currency_code": "USD"}},
            }],
            "payment_preferences": {"auto_bill_outstanding": True, "payment_failure_threshold": 3},
        })
        ids[key] = plan["id"]
    await db.billing_config.update_one(
        {"_id": _config_id()},
        {"$set": {"product_id": product_id, "plans": ids, "updated_at": now_iso()}}, upsert=True)
    return ids


# ── Entitlement ──────────────────────────────────────────────────────────────
def entitlement(user: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """What the user may do right now: {active, plan, reason, trial_ends_at, paid_through}."""
    now = now or datetime.now(timezone.utc)
    b = user.get("billing") or {}
    created = _parse_ts(user.get("created_at")) or now
    trial_ends = created + timedelta(days=TRIAL_DAYS)
    paid_through = _parse_ts(b.get("paid_through"))
    base = {"trial_ends_at": trial_ends.isoformat(),
            "paid_through": paid_through.isoformat() if paid_through else None,
            "subscription_status": b.get("status")}
    if user.get("role") in ADMIN_ROLES:
        return {**base, "active": True, "plan": "agency", "reason": "admin"}
    if b.get("plan") in PLANS and b.get("status") in LIVE_STATUSES:
        return {**base, "active": True, "plan": b["plan"], "reason": "subscribed"}
    # Cancelled / suspended: keep access until the end of the period already paid for.
    if b.get("plan") in PLANS and paid_through and paid_through > now:
        return {**base, "active": True, "plan": b["plan"], "reason": "paid_period"}
    if trial_ends > now:
        return {**base, "active": True, "plan": "trial", "reason": "trial"}
    return {**base, "active": False, "plan": None, "reason": "trial_ended"}


def _month_start(now: datetime) -> str:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


async def webinars_this_month(user_id: str) -> int:
    start = _month_start(datetime.now(timezone.utc))
    return await db.webinars.count_documents({"owner_id": user_id, "created_at": {"$gte": start}})


async def require_webinar_quota(user: Dict[str, Any]) -> None:
    """Raise 402 when the user may not create another webinar. No-op unless BILLING_ENFORCE."""
    if not enforcing():
        return
    ent = entitlement(user)
    if not ent["active"]:
        raise HTTPException(402, "Your 14-day free trial has ended. Pick a plan in Billing to keep creating webinars.")
    limit = (PLANS.get(ent["plan"]) or {}).get("webinars_per_month")
    if limit is not None and await webinars_this_month(user["id"]) >= limit:
        raise HTTPException(402, f"The {PLANS[ent['plan']]['name']} plan includes {limit} webinars a month. "
                                 "Upgrade to Growth for unlimited webinars.")


# ── Applying PayPal state ────────────────────────────────────────────────────
async def apply_subscription(sub: Dict[str, Any], expected_user_id: Optional[str] = None) -> Optional[str]:
    """Copy a PayPal subscription onto the user named in its custom_id. Returns that user id."""
    user_id = sub.get("custom_id")
    if not user_id:
        logger.warning("paypal subscription %s has no custom_id", sub.get("id"))
        return None
    if expected_user_id and user_id != expected_user_id:
        raise HTTPException(403, "This subscription belongs to another account.")
    plan = await plan_key_for(sub.get("plan_id", ""))
    if not plan:
        logger.warning("paypal subscription %s uses unknown plan %s", sub.get("id"), sub.get("plan_id"))
        return None
    info = sub.get("billing_info") or {}
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "billing": 1})
    if user is None:
        logger.warning("paypal subscription %s points at missing user %s", sub.get("id"), user_id)
        return None
    prev = (user or {}).get("billing") or {}
    # A newer subscription on the account wins; ignore late events for an old one.
    if prev.get("subscription_id") and prev["subscription_id"] != sub.get("id") \
            and prev.get("status") in LIVE_STATUSES and sub.get("status") not in LIVE_STATUSES:
        return user_id
    paid_through = info.get("next_billing_time") or prev.get("paid_through")
    await db.users.update_one({"id": user_id}, {"$set": {"billing": {
        "provider": "paypal", "env": _env(), "plan": plan,
        "subscription_id": sub.get("id"), "status": sub.get("status"),
        "paid_through": paid_through,
        "last_payment_at": (info.get("last_payment") or {}).get("time") or prev.get("last_payment_at"),
        "failed_payments": info.get("failed_payments_count", 0),
        "payer_email": (sub.get("subscriber") or {}).get("email_address") or prev.get("payer_email"),
        "updated_at": now_iso(),
    }}})
    logger.info("billing: user=%s plan=%s status=%s", user_id, plan, sub.get("status"))
    return user_id


async def verify_webhook(request: Request, raw: bytes) -> bool:
    webhook_id = os.environ.get("PAYPAL_WEBHOOK_ID")
    if not webhook_id:
        logger.error("PAYPAL_WEBHOOK_ID is not set; rejecting webhook")
        return False
    h = request.headers
    # The event must go back byte-for-byte, so splice the raw body in instead of re-serialising it.
    meta = {"auth_algo": h.get("paypal-auth-algo"), "cert_url": h.get("paypal-cert-url"),
            "transmission_id": h.get("paypal-transmission-id"),
            "transmission_sig": h.get("paypal-transmission-sig"),
            "transmission_time": h.get("paypal-transmission-time"), "webhook_id": webhook_id}
    if not all(meta.values()):
        return False
    content = json.dumps(meta)[:-1] + ', "webhook_event": ' + raw.decode("utf-8") + "}"
    try:
        r = await paypal("POST", "/v1/notifications/verify-webhook-signature", content=content)
    except HTTPException:
        return False
    return r.get("verification_status") == "SUCCESS"


# ── Routes ───────────────────────────────────────────────────────────────────
@router.get("/plans")
async def list_plans():
    return {"plans": [{"key": k, **v} for k, v in PLANS.items()],
            "trial_days": TRIAL_DAYS, "configured": configured(), "env": _env()}


@router.get("/status")
async def status(user=Depends(get_user)):
    ent = entitlement(user)
    limit = (PLANS.get(ent["plan"]) or {}).get("webinars_per_month")
    return {**ent, "plans": PLANS, "configured": configured(), "enforcing": enforcing(),
            "env": _env(), "webinars_this_month": await webinars_this_month(user["id"]),
            "webinar_limit": limit,
            "subscription_id": (user.get("billing") or {}).get("subscription_id")}


async def start_subscription(user: Dict[str, Any], plan: str) -> Dict[str, Any]:
    """Create a PayPal subscription for the user and return {approve_url, subscription_id}."""
    if plan not in PLANS:
        raise HTTPException(400, "Unknown plan")
    b = user.get("billing") or {}
    if b.get("status") in LIVE_STATUSES and b.get("plan") == plan:
        raise HTTPException(400, f"You are already on the {PLANS[plan]['name']} plan.")
    if not configured():
        raise HTTPException(503, "Payments are not set up yet. Please contact support.")
    ids = await plan_ids()
    if plan not in ids:
        # First checkout after the keys are set: create the PayPal plans now.
        ids = await setup_plans()
    sub = await paypal("POST", "/v1/billing/subscriptions", {
        "plan_id": ids[plan], "custom_id": user["id"],
        "subscriber": {"email_address": user["email"]},
        "application_context": {
            "brand_name": "ShowUp AI", "user_action": "SUBSCRIBE_NOW",
            "shipping_preference": "NO_SHIPPING",
            "return_url": f"{_app_url()}/app/billing?paypal=success",
            "cancel_url": f"{_app_url()}/app/billing?paypal=cancel",
        },
    })
    approve = next((l["href"] for l in sub.get("links", []) if l.get("rel") == "approve"), None)
    if not approve:
        raise HTTPException(502, "PayPal did not return a checkout link. Please try again.")
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "billing_pending": {"subscription_id": sub["id"], "plan": plan, "created_at": now_iso()}}})
    return {"approve_url": approve, "subscription_id": sub["id"]}


@router.post("/subscribe")
async def subscribe(payload: Dict[str, Any] = Body(...), user=Depends(get_user)):
    return await start_subscription(user, (payload.get("plan") or "").lower())


@router.post("/checkout")
@limiter.limit("10/minute")
async def checkout(request: Request, payload: Dict[str, Any] = Body(...)):
    """One-step checkout from the pricing page: email + password -> account -> PayPal.

    A new email gets an account on the spot. An existing email must give its
    password, so nobody can start a subscription on someone else's account.
    """
    plan = (payload.get("plan") or "").lower()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if plan not in PLANS:
        raise HTTPException(400, "Unknown plan")
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address.")
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        if not verify_pw(password, existing["password"]):
            raise HTTPException(401, "This email already has an account. Enter its password, or log in first.")
        user = existing
    else:
        if len(password) < 8:
            raise HTTPException(400, "Choose a password of at least 8 characters.")
        if not configured():
            raise HTTPException(503, "Payments are not set up yet. Please contact support.")
        name = (payload.get("name") or "").strip() or email.split("@")[0]
        user = await create_user(email, name, password)
    started = await start_subscription(user, plan)
    return {**started, "token": make_token(user["id"]),
            "user": {"id": user["id"], "email": user["email"], "name": user.get("name", ""),
                     "role": user.get("role", "user")}}


@router.post("/confirm")
async def confirm(payload: Dict[str, Any] = Body(...), user=Depends(get_user)):
    sub_id = payload.get("subscription_id") or ((user.get("billing_pending") or {}).get("subscription_id"))
    if not sub_id:
        raise HTTPException(400, "subscription_id required")
    sub = await paypal("GET", f"/v1/billing/subscriptions/{sub_id}")
    await apply_subscription(sub, expected_user_id=user["id"])
    old = (user.get("billing") or {}).get("subscription_id")
    if sub.get("status") in LIVE_STATUSES and old and old != sub_id:
        # Plan change: the new subscription is live, stop billing the old one.
        try:
            await paypal("POST", f"/v1/billing/subscriptions/{old}/cancel",
                         {"reason": "Switched to another ShowUp AI plan"})
        except HTTPException:
            logger.error("billing: could not cancel old subscription %s for user %s", old, user["id"])
    await db.users.update_one({"id": user["id"]}, {"$unset": {"billing_pending": ""}})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password": 0})
    return {"status": sub.get("status"), **entitlement(fresh)}


@router.post("/cancel")
async def cancel(user=Depends(get_user)):
    b = user.get("billing") or {}
    if not b.get("subscription_id") or b.get("status") not in LIVE_STATUSES:
        raise HTTPException(400, "No active subscription to cancel.")
    await paypal("POST", f"/v1/billing/subscriptions/{b['subscription_id']}/cancel",
                 {"reason": "Cancelled by the customer in ShowUp AI"})
    sub = await paypal("GET", f"/v1/billing/subscriptions/{b['subscription_id']}")
    await apply_subscription(sub, expected_user_id=user["id"])
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password": 0})
    return entitlement(fresh)


@router.post("/webhook")
async def webhook(request: Request):
    raw = await request.body()
    if not await verify_webhook(request, raw):
        raise HTTPException(400, "Invalid webhook signature")
    event = json.loads(raw)
    event_id, kind = event.get("id"), event.get("event_type", "")
    if event_id and await db.billing_events.find_one({"_id": event_id}):
        return {"ok": True, "duplicate": True}
    resource = event.get("resource") or {}
    sub_id = None
    if kind.startswith("BILLING.SUBSCRIPTION."):
        sub_id = resource.get("id")
    elif kind.startswith("PAYMENT.SALE."):
        sub_id = resource.get("billing_agreement_id")
    user_id = None
    if sub_id:
        sub = await paypal("GET", f"/v1/billing/subscriptions/{sub_id}")
        user_id = await apply_subscription(sub)
    if kind == "PAYMENT.SALE.COMPLETED":
        await db.billing_payments.update_one({"_id": resource.get("id")}, {"$set": {
            "user_id": user_id, "subscription_id": sub_id,
            "amount": (resource.get("amount") or {}).get("total"),
            "currency": (resource.get("amount") or {}).get("currency"),
            "created_at": resource.get("create_time") or now_iso()}}, upsert=True)
    if event_id:
        await db.billing_events.insert_one({"_id": event_id, "type": kind, "subscription_id": sub_id,
                                            "user_id": user_id, "received_at": now_iso()})
    return {"ok": True}


@router.post("/admin/setup-plans")
async def admin_setup_plans(user=Depends(get_user)):
    if user.get("role") not in ADMIN_ROLES:
        raise HTTPException(403, "Admin only")
    return {"env": _env(), "plans": await setup_plans(),
            "webhook_url": os.environ.get("PUBLIC_BACKEND_URL", "").rstrip("/") + "/api/billing/webhook"}
