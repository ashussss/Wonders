"""Agency mode: client workspaces are separate accounts the agency switches into."""
import asyncio
import os

import pytest

import _growth_helpers  # noqa: F401  (puts backend/ on sys.path)

os.environ.setdefault("JWT_SECRET", "test")
mm = pytest.importorskip("mongomock_motor")

import jwt  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials  # noqa: E402

import auth_utils  # noqa: E402
import billing  # noqa: E402
import routes_auth  # noqa: E402
import routes_clients  # noqa: E402


@pytest.fixture()
def db(monkeypatch):
    d = mm.AsyncMongoMockClient()["t"]
    for mod in (auth_utils, routes_auth, routes_clients):
        monkeypatch.setattr(mod, "db", d)
    return d


def run(c):
    return asyncio.run(c)


async def _user_from(token):
    return await auth_utils.get_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))


def test_agency_creates_switches_and_moves(db):
    async def go():
        agency = await routes_auth.create_user("a@agency.test", "Agency", "pw12345678")
        await db.users.update_one({"id": agency["id"]}, {"$set": {"role": "admin"}})
        me = await _user_from(auth_utils.make_token(agency["id"]))
        c = await routes_clients.create_client({"name": "SBM"}, user=me)
        assert c["email"] == ""                       # placeholder address is hidden
        assert await db.settings.find_one({"owner_id": c["id"]})

        sw = await routes_clients.switch_to_client(c["id"], user=me)
        as_client = await _user_from(sw["token"])
        assert as_client["id"] == c["id"]
        assert billing.entitlement(as_client)["plan"] == "agency"   # runs on the agency's plan
        listed = await routes_clients.list_clients(user=as_client)
        assert listed["current"] == c["id"] and listed["clients"][0]["name"] == "SBM"

        # A client token without the agency claim (or a forged one) is refused.
        with pytest.raises(HTTPException):
            await _user_from(auth_utils.make_token(c["id"]))
        with pytest.raises(HTTPException):
            await _user_from(auth_utils.make_token(c["id"], agency_id="someone-else"))

        # Move a webinar and its rows into the client.
        await db.webinars.insert_one({"id": "w1", "owner_id": agency["id"]})
        await db.touches.insert_one({"id": "t1", "webinar_id": "w1", "owner_id": agency["id"]})
        await db.invitees.insert_one({"id": "i1", "webinar_id": "w1", "owner_id": agency["id"]})
        r = await routes_clients.move_webinar({"webinar_id": "w1", "to": c["id"]}, user=me)
        assert r["moved"] == 3
        assert (await db.touches.find_one({"id": "t1"}))["owner_id"] == c["id"]

        back = await _user_from((await routes_clients.switch_back(user=as_client))["token"])
        assert back["id"] == agency["id"]
    asyncio.run(go())


def test_other_accounts_cannot_touch_clients(db):
    async def go():
        a = await routes_auth.create_user("a@agency.test", "Agency", "pw12345678")
        await db.users.update_one({"id": a["id"]}, {"$set": {"role": "admin"}})
        a_user = await _user_from(auth_utils.make_token(a["id"]))
        c = await routes_clients.create_client({"name": "SBM"}, user=a_user)
        other = await routes_auth.create_user("o@other.test", "Other", "pw12345678")
        o_user = await _user_from(auth_utils.make_token(other["id"]))
        with pytest.raises(HTTPException):
            await routes_clients.switch_to_client(c["id"], user=o_user)
        with pytest.raises(HTTPException) as e:                # trial accounts can't add clients
            await routes_clients.create_client({"name": "X"}, user=o_user)
        assert e.value.status_code == 402
        await db.webinars.insert_one({"id": "w2", "owner_id": other["id"]})
        with pytest.raises(HTTPException):
            await routes_clients.move_webinar({"webinar_id": "w2", "to": c["id"]}, user=a_user)
    asyncio.run(go())


def test_connect_link_saves_email_for_the_client(db, monkeypatch):
    import crypto_utils
    monkeypatch.setattr(crypto_utils, "encrypt_settings", lambda d: d)
    async def go():
        a = await routes_auth.create_user("a@agency.test", "Agency", "pw12345678")
        await db.users.update_one({"id": a["id"]}, {"$set": {"role": "admin"}})
        a_user = await _user_from(auth_utils.make_token(a["id"]))
        c = await routes_clients.create_client({"name": "SBM"}, user=a_user)
        link = await routes_clients.create_connect_link(c["id"], user=a_user)
        raw = link["url"].rsplit("/", 1)[-1]
        with pytest.raises(HTTPException):
            await routes_clients.connect_email(raw, {"api_key": "nope", "sender_email": "x@y.z"})
        await routes_clients.connect_email(raw, {"api_key": "xkeysib-" + "a" * 40,
                                                 "sender_email": "Admin@SBM.test", "sender_name": "SBM"})
        s = await db.settings.find_one({"owner_id": c["id"]})
        assert s["brevo_sender_email"] == "admin@sbm.test" and s["email_provider"] == "Brevo"
        assert not await db.settings.find_one({"owner_id": a["id"], "brevo_sender_email": "admin@sbm.test"})
        with pytest.raises(HTTPException):
            await routes_clients.connect_email("wrong-token", {})
    asyncio.run(go())
