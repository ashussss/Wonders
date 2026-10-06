#!/usr/bin/env python
"""LinkedIn OAuth end-to-end verification against the real app + real mongod.

LinkedIn's token and userinfo endpoints are mocked at the HTTP boundary; ShowUp's
own auth, state store, encryption and routes are all real. No test contacts
linkedin.com and no real LinkedIn credentials are used.

    MONGO_URL=mongodb://127.0.0.1:27019 python tests/verify_growth_linkedin_flow.py

Run standalone (see test_growth_linkedin.py for why).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27019")
os.environ.setdefault("DB_NAME", "growth_linkedin_flow_test")
os.environ.setdefault("SUPERADMIN_SECRET", "testkey")
os.environ.setdefault("LINKEDIN_CLIENT_ID", "test_client_id")
os.environ.setdefault("LINKEDIN_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("LINKEDIN_REDIRECT_URI",
                      "https://app.test/api/growth/integrations/linkedin/callback")
os.environ.setdefault("FRONTEND_URL", "https://showupai.live")
if not os.environ.get("FERNET_KEY"):
    from cryptography.fernet import Fernet
    os.environ["FERNET_KEY"] = Fernet.generate_key().decode()

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + str(detail)[:150] if detail and not cond else ''}")
    if not cond:
        FAILS.append(name)


def install_linkedin_mock():
    """Route only linkedin.py's own HTTP calls to a local mock transport.

    Patches httpx.AsyncClient globally? No — google-genai subclasses it, so a
    global swap breaks unrelated imports. Instead we patch the two call sites
    inside growth_engine.linkedin with a client bound to a mock transport.
    """
    import httpx
    from growth_engine import linkedin as li

    state = {"token_calls": 0, "userinfo_calls": 0, "fail_token": False}

    def handler(request):
        url = str(request.url)
        if url.startswith(li.TOKEN_URL):
            state["token_calls"] += 1
            if state["fail_token"]:
                return httpx.Response(400, json={"error": "invalid_scope",
                                                "error_description": "unauthorized scope"})
            return httpx.Response(200, json={
                "access_token": "AQV-mock-access-token-123",
                "expires_in": 5184000, "token_type": "Bearer",
                "scope": "openid profile email w_member_social"})
        if url.startswith(li.USERINFO_URL):
            state["userinfo_calls"] += 1
            return httpx.Response(200, json={
                "sub": "linkedin-member-42", "name": "Ada Lovelace",
                "given_name": "Ada", "family_name": "Lovelace",
                "email": "ada@example.com", "email_verified": True,
                "picture": "https://media.licdn.com/pic.jpg",
                "locale": {"country": "gb", "language": "en"}})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def _client(**kw):
        """Client bound to the LinkedIn mock transport."""
        return real_async_client(transport=transport, **kw)

    # Patch ONLY this module's httpx reference, not httpx globally — the ASGI test
    # client and google-genai also use httpx.AsyncClient and must be untouched.
    import types
    li_stub = types.SimpleNamespace(AsyncClient=_client, Response=httpx.Response)
    li.httpx = li_stub
    return state


async def main():
    import httpx
    from motor.motor_asyncio import AsyncIOMotorClient

    mock_state = install_linkedin_mock()

    from auth_utils import make_token, hash_pw
    from database import db as app_db
    import database as database_mod
    from growth_engine import linkedin as li

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])

    # Import the app FIRST so every router binds the original database.client,
    # then rebind those references onto a client owned by this loop.
    import server

    from auth_utils import make_token, hash_pw
    from growth_engine import linkedin as li
    import database as database_mod
    import growth_engine.routes as grows
    import growth_engine.integrations as gint

    live_db = client[os.environ["DB_NAME"]]
    database_mod.client = client
    database_mod.db = live_db
    grows.db = live_db
    gint.db = live_db
    await client.drop_database(os.environ["DB_NAME"])
    await li.ensure_indexes(live_db)

    # Two ShowUp customers, each with their own JWT.
    for email, name in (("c1@example.com", "Customer One"), ("c2@example.com", "Customer Two")):
        await live_db.users.insert_one({"id": email, "email": email, "name": name,
                                        "password": hash_pw("x")})
    tok1, tok2 = make_token("c1@example.com"), make_token("c2@example.com")
    H1 = {"Authorization": f"Bearer {tok1}"}
    H2 = {"Authorization": f"Bearer {tok2}"}

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                 follow_redirects=False) as c:
        print("\n=== 1. auth required ===")
        r0 = await c.get("/api/growth/integrations")
        print(f"      DEBUG no-auth integrations -> {r0.status_code} {r0.text[:120]}")
        r0b = await c.get("/api/growth/status", headers={"X-API-KEY": "testkey"})
        print(f"      DEBUG /api/growth/status -> {r0b.status_code}")
        check("integrations without JWT -> 401/403", r0.status_code in (401, 403), r0.status_code)
        check("connect without JWT -> 401/403",
              (await c.get("/api/growth/integrations/linkedin/connect")).status_code in (401, 403))

        print("\n=== 2. status when not connected ===")
        r = await c.get("/api/growth/integrations", headers=H1)
        check("status 200", r.status_code == 200, r.text[:200])
        body = r.json()
        check("linkedin.connected is False", body["linkedin"]["connected"] is False, body["linkedin"])
        check("capabilities advertised", "not_supported" in body["capabilities"])

        print("\n=== 3. connect creates state + redirects to LinkedIn ===")
        r = await c.get("/api/growth/integrations/linkedin/connect", headers=H1)
        check("connect 302", r.status_code == 302, r.status_code)
        loc = r.headers.get("location", "")
        check("redirects to LinkedIn authorize", loc.startswith(li.AUTH_BASE_URL), loc[:80])
        check("no secret in redirect", li.CLIENT_SECRET not in loc and "client_secret" not in loc)
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(loc).query)
        check("state present", bool(qs.get("state", [""])[0]))
        state = qs["state"][0]

        print("\n=== 4. callback rejects bad state ===")
        r = await c.get("/api/growth/integrations/linkedin/callback",
                        params={"code": "x", "state": "bogus-state"})
        check("bad state -> 400", r.status_code == 400, r.status_code)
        check("no token was exchanged", mock_state["token_calls"] == 0, mock_state["token_calls"])

        print("\n=== 5. callback rejects reused state ===")
        r = await c.get("/api/growth/integrations/linkedin/callback",
                        params={"code": "auth-code-xyz", "state": state})
        check("first callback redirects to frontend", r.status_code in (302, 307), r.status_code)
        loc = r.headers.get("location", "")
        check("frontend redirect", loc.startswith("https://showupai.live"), loc)
        # Must land on the real protected React route, not a bare /integrations
        # (which is not registered and would 404).
        check("redirect path is /app/integrations", "/app/integrations" in loc, loc)
        check("redirect carries success status", "li_status=connected" in loc, loc)
        check("token exchanged once", mock_state["token_calls"] == 1, mock_state["token_calls"])
        r2 = await c.get("/api/growth/integrations/linkedin/callback",
                         params={"code": "auth-code-xyz", "state": state})
        check("replayed state -> 400", r2.status_code == 400, r2.status_code)
        check("replay exchanged nothing", mock_state["token_calls"] == 1, mock_state["token_calls"])

        print("\n=== 6. connection stored encrypted + owner-scoped ===")
        r = await c.get("/api/growth/integrations", headers=H1)
        li1 = r.json()["linkedin"]
        check("customer 1 connected", li1["connected"] is True, li1)
        check("name from userinfo", li1["name"] == "Ada Lovelace", li1.get("name"))
        check("email from userinfo", li1["email"] == "ada@example.com", li1.get("email"))
        check("scopes recorded", "w_member_social" in li1["scopes"], li1.get("scopes"))
        check("expiry recorded", bool(li1["expires_at"]), li1.get("expires_at"))
        check("no token in response", "access_token" not in li1 and "AQV-" not in str(li1))

        r = await c.get("/api/growth/integrations", headers=H2)
        check("customer 2 NOT connected (isolation)", r.json()["linkedin"]["connected"] is False,
              r.json()["linkedin"])

        raw = await live_db[li.CONNECTIONS_COLLECTION].find_one({"owner_id": "c1@example.com"})
        check("token encrypted at rest", raw["access_token_encrypted"] != "AQV-mock-access-token-123")
        check("no plaintext token in doc", "AQV-mock-access-token-123" not in str(raw))
        check("account_type member", raw["account_type"] == "member", raw.get("account_type"))

        print("\n=== 7. customer 2 connects independently ===")
        r = await c.get("/api/growth/integrations/linkedin/connect", headers=H2)
        loc2 = r.headers["location"]
        state2 = parse_qs(urlparse(loc2).query)["state"][0]
        await c.get("/api/growth/integrations/linkedin/callback",
                    params={"code": "code2", "state": state2})
        r = await c.get("/api/growth/integrations", headers=H2)
        check("customer 2 now connected", r.json()["linkedin"]["connected"] is True)
        docs = await live_db[li.CONNECTIONS_COLLECTION].find({}).to_list(10)
        check("two separate connection rows", len(docs) == 2, len(docs))
        check("distinct owner_ids", len({d["owner_id"] for d in docs}) == 2)

        print("\n=== 8. token fetch always owner-scoped ===")
        t1 = await li.get_access_token(live_db, "c1@example.com")
        check("owner 1 token decrypts", t1 == "AQV-mock-access-token-123", bool(t1))
        check("unknown owner gets None", (await li.get_access_token(live_db, "nobody@x.com")) is None)

        print("\n=== 9. disconnect affects only that owner ===")
        r = await c.delete("/api/growth/integrations/linkedin", headers=H1)
        check("disconnect 200", r.status_code == 200, r.text[:150])
        check("customer 1 disconnected", (await c.get("/api/growth/integrations", headers=H1))
              .json()["linkedin"]["connected"] is False)
        check("customer 2 still connected", (await c.get("/api/growth/integrations", headers=H2))
              .json()["linkedin"]["connected"] is True)

        print("\n=== 10. OAuth error from LinkedIn handled ===")
        mock_state["fail_token"] = True
        r = await c.get("/api/growth/integrations/linkedin/connect", headers=H2)
        state3 = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
        r = await c.get("/api/growth/integrations/linkedin/callback",
                        params={"code": "bad", "state": state3})
        check("upstream error -> frontend redirect", r.status_code in (302, 307), r.status_code)
        check("error surfaced safely", "li_status=error" in r.headers.get("location", ""),
              r.headers.get("location", "")[:120])
        check("no secret in error redirect", li.CLIENT_SECRET not in r.headers.get("location", ""))

        print("\n=== 11. user-denied OAuth ===")
        r = await c.get("/api/growth/integrations/linkedin/callback",
                        params={"error": "user_cancelled_login", "error_description": "cancelled"})
        check("denied -> redirect with error", r.status_code in (302, 307)
              and "li_error=user_cancelled_login" in r.headers.get("location", ""),
              r.headers.get("location", "")[:120])

        print("\n=== 12. debug status endpoint is safe ===")
        r = await c.get("/api/growth/integrations/linkedin/status", headers=H2)
        check("status 200", r.status_code == 200)
        body = r.json()
        check("reports configured", body["configured"] is True)
        check("no credentials in body", "access_token" not in str(body)
              and li.CLIENT_SECRET not in str(body))

    await client.drop_database(os.environ["DB_NAME"])
    client.close()
    print(f"\n{'ALL LINKEDIN FLOW CHECKS PASSED' if not FAILS else 'FAILURES: ' + str(FAILS)}")
    sys.exit(0 if not FAILS else 1)


if __name__ == "__main__":
    asyncio.run(main())