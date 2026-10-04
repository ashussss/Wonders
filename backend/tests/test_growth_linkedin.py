"""LinkedIn OAuth tests — state, CSRF, token exchange, userinfo, storage, isolation.

LinkedIn is mocked at the HTTP boundary; MongoDB is real. No test contacts
linkedin.com and no test needs a client secret.
"""
import os
import time
from datetime import datetime, timezone

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27019")
os.environ.setdefault("SUPERADMIN_SECRET", "testkey")
# Provide app credentials so the module-level config is "configured".
os.environ.setdefault("LINKEDIN_CLIENT_ID", "test_client_id")
os.environ.setdefault("LINKEDIN_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("LINKEDIN_REDIRECT_URI", "https://app.test/api/growth/integrations/linkedin/callback")

# A real Fernet key so the encryption path is genuinely exercised (plaintext
# storage is refused by the engine — see linkedin.save_connection).
if not os.environ.get("FERNET_KEY"):
    from cryptography.fernet import Fernet
    os.environ["FERNET_KEY"] = Fernet.generate_key().decode()

import pytest                                                    # noqa: E402
import pytest_asyncio                                            # noqa: E402

from _growth_helpers import BACKEND_DIR, require_mongo           # noqa: E402,F401

require_mongo()

from growth_engine import linkedin as li                         # noqa: E402

DB_NAME = "growth_linkedin_test"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db(growth_client):
    """Shared session client/loop — see tests/conftest.py for why."""
    database = growth_client[DB_NAME]
    await growth_client.drop_database(DB_NAME)
    await li.ensure_indexes(database)
    yield database
    await growth_client.drop_database(DB_NAME)


# ── 1. authorization URL generation ─────────────────────────────────────────

def test_authorization_url_has_required_params():
    from urllib.parse import parse_qs, urlparse
    url = li.build_authorization_url("state-abc")
    q = parse_qs(urlparse(url).query)
    assert url.startswith(li.AUTH_BASE_URL)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == [li.CLIENT_ID]
    assert q["state"] == ["state-abc"]
    assert q["redirect_uri"] == [li.REDIRECT_URI]
    granted = q["scope"][0].split()
    for scope in ("openid", "profile", "email", "w_member_social"):
        assert scope in granted


def test_authorization_url_never_contains_secret():
    url = li.build_authorization_url("s")
    assert li.CLIENT_SECRET not in url
    assert "client_secret" not in url


def test_authorization_url_uses_configured_redirect():
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(li.build_authorization_url("s")).query)
    assert q["redirect_uri"] == [li.REDIRECT_URI]


# ── 2. state generation ─────────────────────────────────────────────────────

def test_generate_state_is_random_and_long():
    a, b = li.generate_state(), li.generate_state()
    assert a != b
    assert len(a) >= 32, "state must be high entropy"


def test_config_reports_missing():
    assert li.configured() is True, "env credentials are set for this test run"
    assert li.missing_config() == []


# ── 3-5. state validation (invalid / expired / one-time) ────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_state_roundtrip_returns_owner(db):
    owner = "owner-123"
    state = await li.create_state(db, owner)
    assert await li.consume_state(db, state) == owner


@pytest.mark.asyncio(loop_scope="session")
async def test_invalid_state_rejected(db):
    with pytest.raises(li.StateError):
        await li.consume_state(db, "not-a-real-state")


@pytest.mark.asyncio(loop_scope="session")
async def test_missing_state_rejected(db):
    with pytest.raises(li.StateError):
        await li.consume_state(db, "")


@pytest.mark.asyncio(loop_scope="session")
async def test_state_cannot_be_reused(db):
    state = await li.create_state(db, "owner-reuse")
    assert await li.consume_state(db, state) == "owner-reuse"
    with pytest.raises(li.StateError):
        await li.consume_state(db, state)


@pytest.mark.asyncio(loop_scope="session")
async def test_expired_state_rejected(db):
    state = await li.create_state(db, "owner-expired")
    # Age the stored state past its TTL.
    await db[li.STATE_COLLECTION].update_one(
        {"state_hash": li.state_fingerprint(state)},
        {"$set": {"expires_at_ts": time.time() - 1}},
    )
    with pytest.raises(li.StateError):
        await li.consume_state(db, state)


# ── 6-7. token exchange + userinfo parsing (LinkedIn mocked) ────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_exchange_code_success(monkeypatch):
    import httpx
    captured = {}

    def handler(request):
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={
            "access_token": "AQV-test-access-token",
            "expires_in": 5184000,
            "token_type": "Bearer",
            "scope": "openid profile email w_member_social",
        })

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    httpx.AsyncClient = lambda **kw: orig(transport=transport, **kw)
    try:
        out = await li.exchange_code_for_token(code="auth-code-123")
    finally:
        httpx.AsyncClient = orig

    assert out["access_token"] == "AQV-test-access-token"
    assert out["expires_in"] == 5184000
    assert out["expires_at"], "real expiry must be stored"
    assert "w_member_social" in out["scope"]
    assert "client_secret=test_client_secret" in captured["body"]


@pytest.mark.asyncio(loop_scope="session")
async def test_exchange_code_empty_rejected():
    with pytest.raises(li.LinkedInError):
        await li.exchange_code_for_token(code="")


@pytest.mark.asyncio(loop_scope="session")
async def test_exchange_code_error_surfaces_safely(monkeypatch):
    import httpx
    def handler(request):
        return httpx.Response(400, json={
            "error": "invalid_scope",
            "error_description": "unauthorized scope",
        })
    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    httpx.AsyncClient = lambda **kw: orig(transport=transport, **kw)
    try:
        with pytest.raises(li.LinkedInError) as e:
            await li.exchange_code_for_token(code="c")
    finally:
        httpx.AsyncClient = orig
    # safe message, no secret, no token
    assert "invalid_scope" in str(e.value) or "permission" in str(e.value)
    assert li.CLIENT_SECRET not in str(e.value)


@pytest.mark.asyncio(loop_scope="session")
async def test_plaintext_token_storage_is_refused(db, monkeypatch):
    """If encryption is unavailable the connect must fail, not store a raw token."""
    import crypto_utils
    monkeypatch.setattr(crypto_utils, "encrypt_value", lambda v: v)   # simulate no FERNET_KEY
    token = {"access_token": "AQV-plaintext-leak", "expires_in": 1,
             "expires_at": None, "scope": ["openid"]}
    profile = li.parse_userinfo({"sub": "mem-plain", "name": "N"})
    with pytest.raises(li.EncryptionUnavailable):
        await li.save_connection(db, "owner-plain", token, profile)
    stored = await db[li.CONNECTIONS_COLLECTION].find_one({"owner_id": "owner-plain"})
    if stored:
        assert "AQV-plaintext-leak" not in str(stored)


def test_parse_userinfo_extracts_identity():
    body = {
        "sub": "abc123", "name": "Ada Lovelace", "given_name": "Ada",
        "family_name": "Lovelace", "email": "ada@example.com",
        "email_verified": True,
        "picture": "https://media.licdn.com/pic.jpg",
        "locale": {"country": "gb", "language": "en"},
    }
    p = li.parse_userinfo(body)
    assert p["platform_user_id"] == "abc123"
    assert p["name"] == "Ada Lovelace"
    assert p["email"] == "ada@example.com"
    assert p["email_verified"] is True
    assert p["profile_picture"].startswith("https://")
    assert p["locale"] == "gb"


def test_parse_userinfo_requires_subject():
    with pytest.raises(li.LinkedInError):
        li.parse_userinfo({"name": "No Subject"})


def test_redact_strips_tokens():
    s = li._redact('{"access_token":"AQVsecretvalue123","error":"bad"}')
    assert "AQVsecretvalue123" not in s
    assert "redacted" in s


# ── 8-9. encrypted storage + status view ────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_token_stored_encrypted(db):
    owner = "owner-store"
    token = {"access_token": "AQV-super-secret-token", "expires_in": 5184000,
             "expires_at": "2030-01-01T00:00:00+00:00", "scope": ["openid"]}
    profile = li.parse_userinfo({"sub": "mem-1", "name": "N", "email": "n@e.com"})
    await li.save_connection(db, owner, token, profile)

    raw = await db[li.CONNECTIONS_COLLECTION].find_one({"owner_id": owner})
    assert raw["access_token_encrypted"] != token["access_token"]
    assert "AQV-super-secret-token" not in str(raw), "plaintext token must not be stored"
    assert (await li.get_access_token(db, owner)) == token["access_token"], "round-trips via decrypt"


@pytest.mark.asyncio(loop_scope="session")
async def test_connection_status_has_no_secrets(db):
    owner = "owner-status"
    token = {"access_token": "AQV-leak-me", "expires_in": 5184000,
             "expires_at": "2030-01-01T00:00:00+00:00", "scope": ["openid", "profile"]}
    profile = li.parse_userinfo({"sub": "mem-2", "name": "Status User", "email": "s@e.com"})
    await li.save_connection(db, owner, token, profile)

    conn = await li.get_connection(db, owner)
    view = li.public_view(conn)
    assert view["connected"] is True
    assert view["name"] == "Status User"
    assert view["email"] == "s@e.com"
    # absolutely no credential material
    assert "access_token" not in view
    assert "access_token_encrypted" not in view
    assert "AQV-leak-me" not in str(view)


def test_public_view_when_not_connected():
    assert li.public_view(None) == {"connected": False, "status": "not_connected"}


# ── 10. disconnect ──────────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_disconnect_removes_only_that_owner(db):
    tok = {"access_token": "AQV-x", "expires_in": 1, "expires_at": None, "scope": ["openid"]}
    prof = li.parse_userinfo({"sub": "m1", "name": "A"})
    prof2 = li.parse_userinfo({"sub": "m2", "name": "B"})
    await li.save_connection(db, "own-A", tok, prof)
    await li.save_connection(db, "own-B", tok, prof2)

    assert await li.disconnect(db, "own-A") is True
    assert await li.get_connection(db, "own-A") is None
    # other client untouched
    assert await li.get_connection(db, "own-B") is not None


# ── 11. owner isolation ─────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_tokens_isolated_per_owner(db):
    tok_a = {"access_token": "AQV-owner-a", "expires_in": 1, "expires_at": None, "scope": ["openid"]}
    tok_b = {"access_token": "AQV-owner-b", "expires_in": 1, "expires_at": None, "scope": ["openid"]}
    await li.save_connection(db, "own-1", tok_a, li.parse_userinfo({"sub": "s1", "name": "N1"}))
    await li.save_connection(db, "own-2", tok_b, li.parse_userinfo({"sub": "s2", "name": "N2"}))
    assert await li.get_access_token(db, "own-1") == "AQV-owner-a"
    assert await li.get_access_token(db, "own-2") == "AQV-owner-b"


@pytest.mark.asyncio(loop_scope="session")
async def test_reconnect_replaces_token(db):
    owner = "owner-recon"
    await li.save_connection(db, owner,
        {"access_token": "AQV-old", "expires_in": 1, "expires_at": None, "scope": ["openid"]},
        li.parse_userinfo({"sub": "same", "name": "N"}))
    await li.save_connection(db, owner,
        {"access_token": "AQV-new", "expires_in": 1, "expires_at": None, "scope": ["openid"]},
        li.parse_userinfo({"sub": "same", "name": "N"}))
    # only one connection for this owner, holding the fresh token
    count = await db[li.CONNECTIONS_COLLECTION].count_documents({"owner_id": owner})
    assert count == 1
    assert await li.get_access_token(db, owner) == "AQV-new"


# ── capability honesty ──────────────────────────────────────────────────────

def test_capability_declares_limits():
    assert li.CAPABILITY["not_supported"], "must explicitly declare unsupported capabilities"
    joined = " ".join(li.CAPABILITY["not_supported"]).lower()
    assert "scrap" in joined
    assert "connection request" in joined
    assert li.SUPPORTS_REFRESH_TOKEN is False, "LinkedIn issues no refresh token for this flow"