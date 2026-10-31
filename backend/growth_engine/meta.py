"""Meta (Facebook Page + Instagram Business) OAuth for the Growth Engine.

Flow: Facebook Login dialog -> code -> short-lived user token -> long-lived user token
-> /me/accounts gives each Page's own access token (does not expire when derived from a
long-lived user token) and its linked Instagram Business account.

The connection stores every Page the member manages (tokens encrypted at rest) and one
selected Page; the selected Page and its Instagram account are what the Growth Engine
publishes to. Same security rules as linkedin.py: state is single-use and stored hashed,
secrets come from the environment only, and no token is ever returned by an API route.

Permissions requested (the app needs Facebook Login for Business; an app in Development
mode works for its own admins without App Review):
    pages_show_list, pages_read_engagement, pages_manage_posts,
    instagram_basic, instagram_content_publish, business_management
"""

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx

from . import linkedin as li

logger = logging.getLogger("showup.growth.meta")

APP_ID = os.environ.get("META_APP_ID", "").strip()
APP_SECRET = os.environ.get("META_APP_SECRET", "").strip()
REDIRECT_URI = os.environ.get("META_REDIRECT_URI", "").strip()
# Optional: a "Facebook Login for Business" configuration ID. When set, the dialog uses
# config_id (permissions come from the configuration) instead of the scope list.
CONFIG_ID = os.environ.get("META_CONFIG_ID", "").strip()
GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v25.0").strip()
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
DIALOG_URL = f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth"

SCOPES = ["pages_show_list", "pages_read_engagement", "pages_manage_posts",
          "instagram_basic", "instagram_content_publish", "business_management"]

PLATFORM = "meta"

# Without these the Page token cannot post: Graph answers "(#200) ... must be granted
# before impersonating a user's page". Instagram needs its own two on top.
REQUIRED_PAGE_PERMS = ("pages_show_list", "pages_read_engagement", "pages_manage_posts")
REQUIRED_IG_PERMS = ("instagram_basic", "instagram_content_publish")


class MetaError(Exception):
    """OAuth/Graph failure with a message that is safe to show a user."""


def configured() -> bool:
    return bool(APP_ID and APP_SECRET and REDIRECT_URI)


def missing_config() -> list:
    return [n for n, v in (("META_APP_ID", APP_ID), ("META_APP_SECRET", APP_SECRET),
                           ("META_REDIRECT_URI", REDIRECT_URI)) if not v]


def build_authorization_url(state: str) -> str:
    from urllib.parse import urlencode
    params = {"client_id": APP_ID, "redirect_uri": REDIRECT_URI, "state": state, "response_type": "code"}
    if CONFIG_ID:
        params["config_id"] = CONFIG_ID
    else:
        params["scope"] = ",".join(SCOPES)
    return f"{DIALOG_URL}?" + urlencode(params)


def _err(r: httpx.Response, what: str) -> MetaError:
    try:
        msg = (r.json().get("error") or {}).get("message") or ""
    except Exception:                                                  # noqa: BLE001
        msg = ""
    logger.warning(f"meta {what} rejected: HTTP {r.status_code}")
    return MetaError(f"Facebook rejected the {what}. {li._redact(msg, 200)}".strip())


async def _get(c: httpx.AsyncClient, url: str, params: dict, what: str) -> dict:
    try:
        r = await c.get(url, params=params)
    except Exception:                                                  # noqa: BLE001
        raise MetaError("Could not reach Facebook. Please try again.") from None
    if r.status_code >= 400:
        raise _err(r, what)
    return r.json()


async def exchange_code(code: str) -> str:
    """code -> long-lived user access token."""
    if not code or not code.strip():
        raise MetaError("Facebook did not return an authorization code.")
    if not configured():
        raise MetaError("Facebook integration is not configured on this server.")
    async with httpx.AsyncClient(timeout=30) as c:
        short = await _get(c, f"{GRAPH_URL}/oauth/access_token", {
            "client_id": APP_ID, "client_secret": APP_SECRET,
            "redirect_uri": REDIRECT_URI, "code": code.strip()}, "authorization")
        token = short.get("access_token")
        if not token:
            raise MetaError("Facebook did not return an access token.")
        long = await _get(c, f"{GRAPH_URL}/oauth/access_token", {
            "grant_type": "fb_exchange_token", "client_id": APP_ID,
            "client_secret": APP_SECRET, "fb_exchange_token": token}, "token exchange")
    return long.get("access_token") or token


async def fetch_pages(user_token: str) -> List[Dict[str, Any]]:
    """Pages the member manages, each with its Page token and linked Instagram account."""
    async with httpx.AsyncClient(timeout=30) as c:
        me = await _get(c, f"{GRAPH_URL}/me", {"fields": "id,name", "access_token": user_token}, "profile request")
        data = await _get(c, f"{GRAPH_URL}/me/accounts", {
            "fields": "id,name,access_token,instagram_business_account{id,username}",
            "limit": 100, "access_token": user_token}, "page list request")
    pages = []
    for p in data.get("data") or []:
        if not p.get("id") or not p.get("access_token"):
            continue
        ig = p.get("instagram_business_account") or {}
        pages.append({"id": str(p["id"]), "name": str(p.get("name") or "")[:200],
                      "access_token": p["access_token"],
                      "ig_id": str(ig.get("id") or ""), "ig_username": str(ig.get("username") or "")[:100]})
    return [{"member_id": str(me.get("id") or ""), "member_name": str(me.get("name") or "")[:200]}] + pages


async def fetch_permissions(user_token: str) -> List[str]:
    """Permissions the member actually granted (Facebook lets them untick any of them)."""
    async with httpx.AsyncClient(timeout=30) as c:
        data = await _get(c, f"{GRAPH_URL}/me/permissions", {"access_token": user_token}, "permission check")
    return sorted({str(p.get("permission")) for p in data.get("data") or []
                   if p.get("status") == "granted" and p.get("permission")})


def missing_permissions(granted: List[str], perms=REQUIRED_PAGE_PERMS + REQUIRED_IG_PERMS) -> List[str]:
    return [p for p in perms if p not in set(granted or [])]


def _pick(pages: List[Dict[str, Any]], page_id: str = "") -> Optional[Dict[str, Any]]:
    if page_id:
        return next((p for p in pages if p["id"] == page_id), None)
    # Default: the first Page that has Instagram linked, else the first Page.
    return next((p for p in pages if p.get("ig_id")), pages[0] if pages else None)


async def save_connection(db, owner_id: str, member: Dict[str, Any], pages: List[Dict[str, Any]],
                          granted: Optional[List[str]] = None) -> None:
    from crypto_utils import encrypt_value

    stored = []
    for p in pages:
        enc = encrypt_value(p["access_token"])
        if not enc or enc == p["access_token"]:
            raise li.EncryptionUnavailable(
                "Token storage is unavailable: this server is missing FERNET_KEY, so Facebook "
                "tokens cannot be encrypted. The connection was not saved.")
        stored.append({k: v for k, v in p.items() if k != "access_token"} | {"token_encrypted": enc})
    sel = _pick(stored)
    doc = {
        "owner_id": owner_id, "platform": PLATFORM, "account_type": "page",
        "platform_user_id": member.get("member_id") or "", "name": member.get("member_name") or "",
        "pages": stored,
        "page_id": sel["id"] if sel else "", "page_name": sel["name"] if sel else "",
        "ig_id": sel.get("ig_id", "") if sel else "", "ig_username": sel.get("ig_username", "") if sel else "",
        "scopes": granted if granted is not None else SCOPES, "expires_at": None, "supports_refresh": False,
        "status": "connected" if sel else "no_pages", "updated_at": li.now_iso(),
    }
    existing = await db[li.CONNECTIONS_COLLECTION].find_one(
        {"owner_id": owner_id, "platform": PLATFORM}, {"_id": 0, "id": 1, "connected_at": 1})
    if existing:
        doc["id"], doc["connected_at"] = existing["id"], existing.get("connected_at") or li.now_iso()
        await db[li.CONNECTIONS_COLLECTION].update_one({"id": doc["id"]}, {"$set": doc})
    else:
        doc["id"], doc["connected_at"] = uuid.uuid4().hex, li.now_iso()
        await db[li.CONNECTIONS_COLLECTION].insert_one(doc)
    logger.info(f"meta connection saved for owner={owner_id}: {len(stored)} page(s), selected={doc['page_id']}")


async def select_page(db, owner_id: str, page_id: str) -> bool:
    conn = await li.get_connection(db, owner_id, PLATFORM)
    sel = _pick((conn or {}).get("pages") or [], page_id)
    if not sel:
        return False
    await db[li.CONNECTIONS_COLLECTION].update_one({"id": conn["id"]}, {"$set": {
        "page_id": sel["id"], "page_name": sel["name"], "ig_id": sel.get("ig_id", ""),
        "ig_username": sel.get("ig_username", ""), "status": "connected", "updated_at": li.now_iso()}})
    return True


async def publishing_settings(db, owner_id: str) -> Dict[str, str]:
    """Decrypted values in the shape social.py's publishers expect, or {} when not connected."""
    from crypto_utils import decrypt_value

    conn = await li.get_connection(db, owner_id, PLATFORM)
    if not conn or conn.get("status") != "connected" or not conn.get("page_id"):
        return {}
    page = next((p for p in conn.get("pages") or [] if p["id"] == conn["page_id"]), None)
    token = decrypt_value((page or {}).get("token_encrypted") or "")
    if not token or token.startswith("enc::"):
        return {}
    out = {"meta_graph_token": token, "meta_page_id": conn["page_id"]}
    if conn.get("ig_id"):
        out["instagram_business_id"] = conn["ig_id"]
    return out


def public_view(conn: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Safe shape for API responses: no tokens."""
    if not conn:
        return {"connected": False, "status": "not_connected"}
    return {
        "connected": conn.get("status") == "connected", "status": conn.get("status"),
        "name": conn.get("name") or "",
        "page_id": conn.get("page_id") or "", "page_name": conn.get("page_name") or "",
        "ig_id": conn.get("ig_id") or "", "ig_username": conn.get("ig_username") or "",
        "missing_permissions": missing_permissions(conn.get("scopes") or []),
        "pages": [{"id": p["id"], "name": p["name"], "ig_username": p.get("ig_username", ""),
                   "has_instagram": bool(p.get("ig_id"))} for p in conn.get("pages") or []],
        "connected_at": conn.get("connected_at"), "updated_at": conn.get("updated_at"),
    }


__all__ = ["SCOPES", "PLATFORM", "MetaError", "configured", "missing_config", "build_authorization_url",
           "exchange_code", "fetch_pages", "save_connection", "select_page", "publishing_settings", "public_view"]
