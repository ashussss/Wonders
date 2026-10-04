"""Growth Engine integrations — LinkedIn OAuth connect/status/disconnect.

Mounted at /api/growth. Uses the ShowUp JWT for every endpoint EXCEPT the OAuth
callback, which cannot have a JWT (LinkedIn redirects the browser straight to it).
The callback therefore recovers the owner from the server-side OAuth state, which
is single-use and expiring — never from anything the caller supplied.

No endpoint here ever returns an access token, the client secret, an encrypted
token, or an OAuth code.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from auth_utils import get_user
from database import db

from . import linkedin as li

logger = logging.getLogger("showup.growth.integrations")

# No prefix here: this router is included into growth_engine.routes, whose own
# router already carries prefix="/api/growth". Setting it here too would produce
# /api/growth/api/growth/... because include_router re-applies a child prefix.
router = APIRouter()

# Where the browser lands after a successful connect / failed connect.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://showupai.live").rstrip("/")

# The OAuth callback is a server-side redirect, so it must return the browser to
# the actual protected React route (/app/integrations) — not a bare /integrations,
# which is not a registered route and would 404.
INTEGRATIONS_PATH = "/app/integrations"


def _redirect(**params: str) -> RedirectResponse:
    """Redirect back to the Integrations page with a query string (no secrets, ever)."""
    from urllib.parse import urlencode
    qs = urlencode({k: v for k, v in params.items() if v})
    return RedirectResponse(f"{FRONTEND_URL}{INTEGRATIONS_PATH}{'?' + qs if qs else ''}",
                            status_code=302)


# ── capability discovery ────────────────────────────────────────────────────

@router.get("/integrations")
async def integrations_status(request: Request, user=Depends(get_user)):
    """Connection state for the authenticated owner. Never returns credentials."""
    conn = await li.get_connection(db, user["id"], li.PLATFORM)
    return {
        "linkedin": li.public_view(conn),
        "configured": li.configured(),
        "capabilities": li.CAPABILITY,
    }


@router.get("/integrations/linkedin/status")
async def linkedin_status(request: Request, user=Depends(get_user)):
    """Safe internal/debug view of this owner's LinkedIn connection."""
    conn = await li.get_connection(db, user["id"], li.PLATFORM)
    return {
        "configured": li.configured(),
        "missing_config": li.missing_config(),
        "redirect_uri_configured": bool(li.REDIRECT_URI),
        "connection": li.public_view(conn),
    }


# ── connect ─────────────────────────────────────────────────────────────────

@router.get("/integrations/linkedin/connect")
async def linkedin_connect(request: Request, user=Depends(get_user), redirect: bool = True):
    """Start the Authorization Code flow.

    Creates a one-time state bound to the authenticated owner and returns the
    LinkedIn authorization URL (or redirects to it). The client secret is never
    involved on this leg.
    """
    if not li.configured():
        missing = ", ".join(li.missing_config())
        raise HTTPException(503, f"LinkedIn integration is not configured (missing: {missing})")

    await li.ensure_indexes(db)
    state = await li.create_state(db, user["id"])
    url = li.build_authorization_url(state)

    if not redirect:
        return {"authorization_url": url, "state": state,
                "expires_in": li.STATE_TTL_SECONDS, "scopes": li.SCOPES}

    return RedirectResponse(url, status_code=302)


# ── callback (no JWT — identity comes from the stored state) ────────────────

@router.get("/integrations/linkedin/callback")
async def linkedin_callback(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    error_description: str = Query(default=""),
):
    """LinkedIn redirect target.

    Order matters: validate state FIRST so a hostile callback cannot make us
    exchange an attacker-supplied code before we know whose owner it belongs to.
    """
    if error:
        # LinkedIn refused (e.g. a scope is not approved for this app).
        logger.warning(f"linkedin oauth denied by user/app: {error}")
        return _redirect(
                         li_status="error",
                         li_error=error,
                         li_detail=error_description or "")

    try:
        owner_id = await li.consume_state(db, state)
    except li.StateError as e:
        logger.warning(f"linkedin callback rejected: {e}")
        raise HTTPException(400, "Invalid or expired authorization state. "
                                 "Please start the connect flow again.") from None

    if not owner_id:
        raise HTTPException(400, "Authorization state did not resolve to an account.")

    # The owner came from our own store; confirm the account still exists.
    owner = await db.users.find_one({"id": owner_id}, {"_id": 0, "id": 1})
    if not owner:
        raise HTTPException(400, "The account that started this connection no longer exists.")

    try:
        token_data = await li.exchange_code_for_token(code=code)
        access_token = token_data["access_token"]
        profile = await li.fetch_userinfo(access_token)
    except li.LinkedInError as e:
        logger.warning(f"linkedin connect failed for owner={owner_id}: {e}")
        return _redirect(li_status="error", li_error=str(e)[:300])

    try:
        await li.save_connection(db, owner_id, token_data, profile)
    except li.EncryptionUnavailable as e:
        # Token cannot be stored encrypted — refuse rather than persist plaintext.
        logger.error(f"linkedin connect aborted for owner={owner_id}: {e}")
        return _redirect(li_status="error",
                         li_error="LinkedIn connected, but this server cannot store credentials "
                                  "securely (FERNET_KEY missing). Please contact support.")

    # Give the frontend a short-lived hand-off so it can show the identity
    # without the callback URL itself ever carrying the member's email.
    return _redirect(li_status="connected",
                     li_name=profile.get("name") or "",
                     li_sub=profile.get("platform_user_id") or "")


# ── disconnect ──────────────────────────────────────────────────────────────

@router.delete("/integrations/linkedin")
async def linkedin_disconnect(request: Request, user=Depends(get_user)):
    """Remove only this owner's LinkedIn connection. Other clients are untouched."""
    removed = await li.disconnect(db, user["id"], li.PLATFORM)
    return {"ok": True, "disconnected": removed, "platform": li.PLATFORM}


# ── housekeeping ────────────────────────────────────────────────────────────

@router.post("/integrations/linkedin/purge-states")
async def purge_states(request: Request, user=Depends(get_user)):
    """Delete this owner's expired/redeemed OAuth states."""
    n = await db[li.STATE_COLLECTION].delete_many({"owner_id": user["id"]})
    return {"ok": True, "deleted": n.deleted_count}


__all__ = ["router"]