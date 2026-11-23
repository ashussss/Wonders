"""Forgot / reset password.

A reset link carries a random token that is good for RESET_TTL_MINUTES and only once.
Only its SHA-256 hash is stored, so a leaked database can't be used to reset anyone.

The email goes out through the platform's own sender, in this order:
  1. SYSTEM_BREVO_API_KEY + SYSTEM_SENDER_EMAIL (or SYSTEM_SENDGRID_API_KEY + SYSTEM_SENDER_EMAIL) on Render
  2. the email provider saved in the superadmin's Settings (the ShowUp account's own Brevo/SendGrid)
"""
from __future__ import annotations

import hashlib
import html
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from database import db

logger = logging.getLogger("showup.password_reset")

RESET_TTL_MINUTES = 60
MIN_PASSWORD_LEN = 8


def app_url() -> str:
    return os.environ.get("PUBLIC_APP_URL", "https://showupai.live").rstrip("/")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_reset(user_id: str) -> str:
    """New one-time token for this user; any older unused link stops working."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await db.password_resets.delete_many({"user_id": user_id})
    await db.password_resets.insert_one({
        "user_id": user_id,
        "token_hash": hash_token(token),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=RESET_TTL_MINUTES)).isoformat(),
        "used": False,
    })
    return token


async def find_valid_reset(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    doc = await db.password_resets.find_one({"token_hash": hash_token(token), "used": False})
    if not doc:
        return None
    if datetime.fromisoformat(doc["expires_at"]) < datetime.now(timezone.utc):
        return None
    return doc


async def _system_email_settings() -> Optional[Dict[str, Any]]:
    sender = os.environ.get("SYSTEM_SENDER_EMAIL", "").strip()
    name = os.environ.get("SYSTEM_SENDER_NAME", "ShowUp AI").strip() or "ShowUp AI"
    if sender and os.environ.get("SYSTEM_BREVO_API_KEY"):
        return {"email_provider": "brevo", "brevo_api_key": os.environ["SYSTEM_BREVO_API_KEY"],
                "brevo_sender_email": sender, "brevo_sender_name": name}
    if sender and os.environ.get("SYSTEM_SENDGRID_API_KEY"):
        return {"email_provider": "sendgrid", "sendgrid_api_key": os.environ["SYSTEM_SENDGRID_API_KEY"],
                "sendgrid_sender_email": sender, "sendgrid_sender_name": name}
    # Fallback: the provider saved on the superadmin (ShowUp's own) account.
    admin = await db.users.find_one({"role": "superadmin"}, {"_id": 0, "id": 1})
    if not admin:
        return None
    from crypto_utils import decrypt_settings
    s = decrypt_settings(await db.settings.find_one({"owner_id": admin["id"]}, {"_id": 0}) or {})
    provider = (s.get("email_provider") or "Brevo").strip().lower()
    key = {"sendgrid": "sendgrid_api_key", "mailchimp": "mailchimp_api_key",
           "buzzai": "buzzai_api_key"}.get(provider, "brevo_api_key")
    if not s.get(key):
        return None
    for p in ("brevo", "sendgrid", "mailchimp"):
        s[f"{p}_sender_name"] = "ShowUp AI"
    return s


def reset_email_html(name: str, link: str) -> str:
    from senders import build_email_html
    hi = f"Hi {html.escape(name)}," if name else "Hi,"
    body = (
        f"{hi}<br><br>"
        "Someone asked to reset the password for your ShowUp AI account. "
        "Click the button below to choose a new one.<br><br>"
        f'<a href="{html.escape(link)}" style="display:inline-block;background:#EA580C;color:#ffffff;'
        'padding:12px 22px;border-radius:8px;font-weight:600;text-decoration:none;">Reset password</a><br><br>'
        f"This link works once and expires in {RESET_TTL_MINUTES} minutes.<br>"
        "If you didn't ask for this, you can ignore this email. Your password stays the same.<br><br>"
        "ShowUp AI"
    )
    return build_email_html(body, subject="Reset your ShowUp AI password")


async def send_reset_email(user: Dict[str, Any], token: str) -> bool:
    settings = await _system_email_settings()
    if not settings:
        logger.error("Password reset: no system email sender configured "
                     "(set SYSTEM_BREVO_API_KEY + SYSTEM_SENDER_EMAIL on Render)")
        return False
    from senders import send_email
    link = f"{app_url()}/reset-password?token={token}"
    res = await send_email(settings, user["email"], "Reset your ShowUp AI password",
                           reset_email_html(user.get("name", ""), link))
    if not res.get("ok"):
        logger.error("Password reset email failed via %s: %s", res.get("provider"), res.get("detail"))
    return bool(res.get("ok"))


def token_issued_before_password_change(payload: Dict[str, Any], changed_at: Optional[str]) -> bool:
    """True if this JWT was issued before the password was last changed (old session).

    Tokens carry no iat, but every token lives exactly 14 days, so issued = exp - 14 days."""
    if not changed_at or "exp" not in payload:
        return False
    issued = float(payload["exp"]) - 14 * 24 * 3600
    return issued < datetime.fromisoformat(changed_at).timestamp() - 1
