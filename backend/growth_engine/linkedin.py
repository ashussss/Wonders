"""LinkedIn OAuth 2.0 (Authorization Code flow) for the Growth Engine.

SCOPE / PERMISSION HONESTY
--------------------------
This module requests only member-level scopes that a LinkedIn app must have
approved in the Developer Portal before they will be granted:

    openid  profile  email  w_member_social

If the app has not been approved for ``w_member_social``, LinkedIn returns an
error at the authorize step and the connect flow surfaces that plainly. We never
pretend a scope is available.

NOT SUPPORTED without a separate, separately-approved application + organization
authorization (Community Management API):

    * posting to an Organization/company page as the member  -> needs org perms
    * reading another member's profile / activity feed       -> not in any API
    * sending connection requests / messaging               -> not in any API
    * scraping profile pages                                -> prohibited, never done

Those are recorded in CAPABILITY so the rest of the Growth Engine can tell the
difference between "available via API", "requires LinkedIn approval" and
"not supported", instead of guessing.

SECURITY
--------
* Client secret is read from the environment only, never logged, never returned.
* Access tokens are encrypted at rest with the app's existing Fernet helper.
* CSRF state is a 256-bit random token stored server-side with an expiry and
  single use. The owner is recovered from the stored state, never from the URL,
  so the callback can be trusted without a JWT.
* No token or secret is ever placed in a URL, a log line or an API response.
"""

import hashlib
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("showup.growth.linkedin")

# ── configuration (env only) ────────────────────────────────────────────────
CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.environ.get("LINKEDIN_REDIRECT_URI", "").strip()

AUTH_BASE_URL = os.environ.get(
    "LINKEDIN_AUTH_BASE_URL", "https://www.linkedin.com/oauth/v2/authorization"
).strip()
TOKEN_URL = os.environ.get(
    "LINKEDIN_TOKEN_URL", "https://www.linkedin.com/oauth/v2/accessToken"
).strip()
USERINFO_URL = os.environ.get(
    "LINKEDIN_USERINFO_URL", "https://api.linkedin.com/v2/userinfo"
).strip()

# Member-level scopes only. Requesting an unapproved scope makes the whole
# authorize call fail, so this list must stay minimal and must match the app.
SCOPES = ["openid", "profile", "email", "w_member_social"]

# LinkedIn does not issue refresh tokens for this flow. We store the expiry it
# reports and require a manual reconnect when it lapses. No invented refresh logic.
SUPPORTS_REFRESH_TOKEN = False

STATE_TTL_SECONDS = 600          # 10 minutes — long enough for a login detour
STATE_COLLECTION = "growth_oauth_states"

CONNECTIONS_COLLECTION = "growth_social_connections"

PLATFORM = "linkedin"
ACCOUNT_TYPE_MEMBER = "member"

# What the Growth Engine may and may not do through this integration.
CAPABILITY = {
    "available_via_api": [
        "read own member profile (openid/profile/email)",
        "publish posts as the connected member (w_member_social)",
        "read own post analytics (organizationalEntity permission, if approved)",
    ],
    "requires_linkedin_approval": [
        "posting to an Organization/company page (Community Management API)",
        "reading member analytics (r_organization_social)",
    ],
    "not_supported": [
        "search or read other members' profiles",
        "read another member's activity feed",
        "send or accept connection requests",
        "send LinkedIn messages",
        "automate likes/follows/comments",
        "scrape linkedin.com",
    ],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def configured() -> bool:
    """True when the LinkedIn app credentials are present in the environment."""
    return bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI)


def missing_config() -> list:
    return [n for n, v in (("LINKEDIN_CLIENT_ID", CLIENT_ID),
                           ("LINKEDIN_CLIENT_SECRET", CLIENT_SECRET),
                           ("LINKEDIN_REDIRECT_URI", REDIRECT_URI)) if not v]


# ── state (CSRF) ────────────────────────────────────────────────────────────

def generate_state() -> str:
    """256 bits of cryptographically secure randomness, URL-safe."""
    return secrets.token_urlsafe(32)


def state_fingerprint(state: str) -> str:
    """Store only a hash of the state, so a leaked DB cannot be replayed."""
    return hashlib.sha256(state.encode()).hexdigest()


async def create_state(db, owner_id: str, platform: str = PLATFORM) -> str:
    """Persist a one-time, expiring state bound to this owner. Returns the raw value.

    Only the SHA-256 fingerprint is stored — the raw token exists solely in the
    redirect URL we hand to the browser, so a database leak cannot be replayed.
    """
    state = generate_state()
    await db[STATE_COLLECTION].insert_one({
        "id": uuid.uuid4().hex,
        "state_hash": state_fingerprint(state),
        "owner_id": owner_id,
        "platform": platform,
        "created_at": now_iso(),
        "expires_at_ts": time.time() + STATE_TTL_SECONDS,
        "used": False,
    })
    return state


class StateError(Exception):
    """Raised for missing, unknown, expired or already-used OAuth state."""


async def consume_state(db, state: str, platform: str = PLATFORM) -> str:
    """Validate + burn a state, returning its owner_id.

    Raises StateError for any invalid state. Uses a single atomic find_one_and_
    update so a state can never be redeemed twice even under concurrent requests.
    """
    if not state or not state.strip():
        raise StateError("missing state")

    now = time.time()
    doc = await db[STATE_COLLECTION].find_one_and_update(
        {"state_hash": state_fingerprint(state.strip()),
         "platform": platform,
         "used": False,
         "expires_at_ts": {"$gt": now}},
        {"$set": {"used": True, "used_at": now, "used_at_iso": now_iso()}},
        projection={"_id": 0},
    )
    if not doc:
        raise StateError("invalid, expired or already-used state")
    return str(doc.get("owner_id") or "")


async def purge_expired_states(db) -> int:
    r = await db[STATE_COLLECTION].delete_many({"expires_at_ts": {"$lt": time.time() - 86400}})
    return r.deleted_count


# ── authorization URL ───────────────────────────────────────────────────────

def build_authorization_url(state: str, redirect_uri: Optional[str] = None) -> str:
    """Build the LinkedIn authorize URL. Never contains a secret."""
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": (redirect_uri or REDIRECT_URI).strip(),
        "state": state,
        "scope": " ".join(SCOPES),
    }
    return f"{AUTH_BASE_URL}?{urlencode(params)}"


# ── token exchange + profile ────────────────────────────────────────────────

class LinkedInError(Exception):
    """OAuth failure with a message that is safe to show a user.

    Never carries the client secret or a full access token.
    """

    def __init__(self, message: str, *, status_code: Optional[int] = None, error: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.error = error


class EncryptionUnavailable(Exception):
    """Raised when FERNET_KEY is missing so a token cannot be stored encrypted.

    Better to fail the connect than to persist a customer's access token in
    plaintext. The message is safe to show — it names no secret.
    """


def _redact(text: str, limit: int = 300) -> str:
    """Strip anything token-shaped out of an upstream error body."""
    import re
    text = text or ""
    text = re.sub(r"(?i)(access_token|refresh_token|id_token|client_secret)\"?\s*[:=]\s*\"?[^\"',\s}]+",
                  r"\1=[redacted]", text)
    text = re.sub(r"AQ[A-Za-z0-9_\-]{10,}", "[redacted]", text)      # LinkedIn token prefix
    return text[:limit]


async def exchange_code_for_token(db_unused=None, code: str = "",
                                  redirect_uri: Optional[str] = None) -> Dict[str, Any]:
    """Exchange an authorization code for an access token.

    Returns {"access_token", "expires_in", "expires_at", "scope", "token_type"}.
    Raises LinkedInError with a safe message on any failure.
    """
    if not code or not code.strip():
        raise LinkedInError("LinkedIn did not return an authorization code.")
    if not configured():
        raise LinkedInError("LinkedIn integration is not configured on this server.")

    payload = {
        "grant_type": "authorization_code",
        "code": code.strip(),
        "redirect_uri": (redirect_uri or REDIRECT_URI).strip(),
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(TOKEN_URL, data=payload,
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
    except Exception as e:                                            # noqa: BLE001
        logger.error(f"linkedin token request failed: {type(e).__name__}")
        raise LinkedInError("Could not reach LinkedIn. Please try again.") from None

    if r.status_code >= 400:
        detail = ""
        code_err = ""
        try:
            body = r.json()
            detail = _redact(body.get("error_description") or body.get("error") or "")
            code_err = str(body.get("error") or "")
        except Exception:                                             # noqa: BLE001
            detail = _redact(r.text)
        logger.warning(f"linkedin token exchange rejected: HTTP {r.status_code} error={code_err}")
        raise LinkedInError(
            "LinkedIn rejected the authorization. The app may be missing an approved "
            f"permission, or the redirect URI may not match. ({detail})",
            status_code=r.status_code, error=code_err)

    try:
        body = r.json()
    except Exception:                                                 # noqa: BLE001
        raise LinkedInError("LinkedIn returned an unreadable token response.") from None

    token = body.get("access_token")
    if not token:
        raise LinkedInError("LinkedIn did not return an access token.")

    expires_in = body.get("expires_in")
    try:
        expires_in = int(expires_in) if expires_in is not None else None
    except (TypeError, ValueError):
        expires_in = None

    # LinkedIn returns space-separated scopes in `scope` for OIDC apps.
    scope_raw = body.get("scope") or ""
    scopes = [s for s in str(scope_raw).replace(",", " ").split() if s] or list(SCOPES)

    out = {
        "access_token": token,
        "token_type": body.get("token_type") or "Bearer",
        "expires_in": expires_in,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
                      if expires_in else None,
        "scope": scopes,
    }
    logger.info("linkedin token exchange succeeded (scopes=%s, expires_in=%s)",
                ",".join(scopes), expires_in)
    return out


async def fetch_userinfo(access_token: str) -> Dict[str, Any]:
    """Fetch and normalise the member identity from the OIDC userinfo endpoint."""
    if not access_token:
        raise LinkedInError("No access token available for the userinfo request.")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(USERINFO_URL, headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            })
    except Exception:                                                 # noqa: BLE001
        logger.error("linkedin userinfo request failed at the transport layer")
        raise LinkedInError("Could not reach LinkedIn to read your profile.") from None

    if r.status_code >= 400:
        logger.warning(f"linkedin userinfo rejected: HTTP {r.status_code}")
        raise LinkedInError("LinkedIn would not return your profile for this token.",
                            status_code=r.status_code)

    try:
        body = r.json()
    except Exception:                                                 # noqa: BLE001
        raise LinkedInError("LinkedIn returned an unreadable profile response.") from None

    return parse_userinfo(body)


def parse_userinfo(body: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise LinkedIn's userinfo payload into our connection fields."""
    body = body if isinstance(body, dict) else {}
    sub = str(body.get("sub") or "").strip()
    if not sub:
        raise LinkedInError("LinkedIn did not include a member identifier.")

    picture = ""
    raw_pic = body.get("picture") or body.get("profilePicture")
    if isinstance(raw_pic, str) and raw_pic:
        picture = raw_pic
    elif isinstance(raw_pic, dict):
        picture = str(raw_pic.get("displayImage") or raw_pic.get("url") or "")

    return {
        "platform_user_id": sub,
        "name": str(body.get("name") or "").strip()[:200],
        "given_name": str(body.get("given_name") or "").strip()[:120],
        "family_name": str(body.get("family_name") or "").strip()[:120],
        "email": str(body.get("email") or "").strip()[:320],
        "email_verified": bool(body.get("email_verified")),
        "locale": str((body.get("locale") or {}).get("country")
                      if isinstance(body.get("locale"), dict) else body.get("locale") or "")[:20],
        "profile_picture": picture,
        "urn": str(body.get("urn") or "").strip()[:200],
    }


# ── connection storage ──────────────────────────────────────────────────────

async def ensure_indexes(db) -> None:
    """Indexes required for correct per-owner and per-account lookups."""
    await db[CONNECTIONS_COLLECTION].create_index([("owner_id", 1), ("platform", 1)])
    await db[CONNECTIONS_COLLECTION].create_index(
        [("owner_id", 1), ("platform", 1), ("platform_user_id", 1)])
    await db[CONNECTIONS_COLLECTION].create_index([("platform", 1), ("platform_user_id", 1)])
    await db[CONNECTIONS_COLLECTION].create_index("id")
    await db[STATE_COLLECTION].create_index("state_hash", unique=True)
    await db[STATE_COLLECTION].create_index("expires_at_ts")
    await db[STATE_COLLECTION].create_index([("owner_id", 1), ("platform", 1)])


async def save_connection(db, owner_id: str, token_data: Dict[str, Any],
                          profile: Dict[str, Any], account_type: str = ACCOUNT_TYPE_MEMBER) -> Dict[str, Any]:
    """Encrypt the token and upsert the connection. One connection per owner+platform.

    crypto_utils.encrypt_value() returns the input unchanged when FERNET_KEY is
    absent, which would leave a usable access token in plaintext. Because this
    store is per-customer credential material, we refuse rather than downgrade:
    a missing encryption key is a hard error here.
    """
    from crypto_utils import encrypt_value

    raw_token = token_data["access_token"]
    encrypted = encrypt_value(raw_token)
    if not encrypted or encrypted == raw_token:
        # Refuse to persist a plaintext token.
        await db[CONNECTIONS_COLLECTION].update_many(
            {"owner_id": owner_id, "platform": PLATFORM},
            {"$set": {"status": "encryption_unavailable", "updated_at": now_iso()}},
        )
        logger.error(
            "linkedin connection NOT saved: FERNET_KEY is missing or invalid, so the access "
            "token cannot be encrypted at rest. Set FERNET_KEY before connecting accounts."
        )
        raise EncryptionUnavailable(
            "Token storage is unavailable: this server is missing FERNET_KEY, so LinkedIn "
            "access tokens cannot be encrypted. The connection was not saved.")
    token_data = {**token_data, "access_token": encrypted}

    doc = {
        "id": uuid.uuid4().hex,
        "owner_id": owner_id,
        "platform": PLATFORM,
        "account_type": account_type,
        "platform_user_id": profile["platform_user_id"],
        "name": profile.get("name") or "",
        "given_name": profile.get("given_name") or "",
        "family_name": profile.get("family_name") or "",
        "email": profile.get("email") or "",
        "email_verified": profile.get("email_verified", False),
        "locale": profile.get("locale") or "",
        "profile_picture": profile.get("profile_picture") or "",
        "access_token_encrypted": encrypt_value(token_data["access_token"]),
        "token_type": token_data.get("token_type") or "Bearer",
        "scopes": token_data.get("scope") or list(SCOPES),
        "expires_at": token_data.get("expires_at"),
        "supports_refresh": SUPPORTS_REFRESH_TOKEN,
        "status": "connected",
        "updated_at": now_iso(),
    }

    # Re-connecting the same owner+platform replaces the previous connection so
    # a stale token can never linger. connected_at is preserved on reconnect.
    existing = await db[CONNECTIONS_COLLECTION].find_one(
        {"owner_id": owner_id, "platform": PLATFORM}, {"_id": 0, "id": 1, "connected_at": 1})
    if existing:
        doc["id"] = existing["id"]
        doc["connected_at"] = existing.get("connected_at") or now_iso()
        await db[CONNECTIONS_COLLECTION].update_one({"id": doc["id"]}, {"$set": doc})
    else:
        doc["connected_at"] = now_iso()
        await db[CONNECTIONS_COLLECTION].insert_one(doc)

    logger.info(f"linkedin connection saved for owner={owner_id} member={profile['platform_user_id']}")
    return {k: v for k, v in doc.items() if k != "access_token_encrypted"}


async def get_connection(db, owner_id: str, platform: str = PLATFORM) -> Optional[Dict[str, Any]]:
    return await db[CONNECTIONS_COLLECTION].find_one(
        {"owner_id": owner_id, "platform": platform}, {"_id": 0})


async def get_access_token(db, owner_id: str, platform: str = PLATFORM) -> Optional[str]:
    """Decrypt a stored token. ALWAYS requires owner_id — never a bare lookup.

    This is the only place the plaintext token is reconstructed, and it is
    never returned by an API route.
    """
    from crypto_utils import decrypt_value

    conn = await get_connection(db, owner_id, platform)
    if not conn:
        return None
    enc = conn.get("access_token_encrypted") or ""
    if not enc:
        return None
    return decrypt_value(enc)


async def disconnect(db, owner_id: str, platform: str = PLATFORM) -> bool:
    """Remove only THIS owner's connection for this platform. Other clients untouched."""
    r = await db[CONNECTIONS_COLLECTION].delete_one({"owner_id": owner_id, "platform": platform})
    await db[STATE_COLLECTION].delete_many({"owner_id": owner_id, "platform": platform})
    return bool(r.deleted_count)


def public_view(conn: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Safe shape for API responses. Contains no token, secret or OAuth code."""
    if not conn:
        return {"connected": False, "status": "not_connected"}
    return {
        "connected": True,
        "platform": conn.get("platform"),
        "account_type": conn.get("account_type"),
        "platform_user_id": conn.get("platform_user_id"),
        "name": conn.get("name") or "",
        "email": conn.get("email") or "",
        "locale": conn.get("locale") or "",
        "profile_picture": conn.get("profile_picture") or "",
        "scopes": conn.get("scopes") or [],
        "connected_at": conn.get("connected_at"),
        "updated_at": conn.get("updated_at"),
        "expires_at": conn.get("expires_at"),
        "supports_refresh": bool(conn.get("supports_refresh")),
        "status": conn.get("status") or "connected",
    }


__all__ = [
    "SCOPES", "CAPABILITY", "PLATFORM", "ACCOUNT_TYPE_MEMBER", "SUPPORTS_REFRESH_TOKEN",
    "configured", "missing_config", "generate_state", "create_state", "consume_state",
    "StateError", "purge_expired_states", "build_authorization_url",
    "exchange_code_for_token", "fetch_userinfo", "parse_userinfo", "LinkedInError",
    "EncryptionUnavailable",
    "ensure_indexes", "save_connection", "get_connection", "get_access_token",
    "disconnect", "public_view", "now_iso",
]