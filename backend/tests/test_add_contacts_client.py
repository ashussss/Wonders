"""Add contacts in a client workspace: one bad address must not block the rest."""
import asyncio
import os

import pytest

import _growth_helpers  # noqa: F401

os.environ.setdefault("JWT_SECRET", "test")
mm = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import auth_utils  # noqa: E402
import routes_auth  # noqa: E402
import routes_clients  # noqa: E402
import routes_webinars  # noqa: E402


@pytest.fixture()
def env(monkeypatch):
    d = mm.AsyncMongoMockClient()["t"]
    for mod in (auth_utils, routes_auth, routes_clients, routes_webinars):
        monkeypatch.setattr(mod, "db", d)
    app = FastAPI()
    app.state.limiter = routes_webinars.limiter
    app.include_router(routes_webinars.router)
    app.include_router(routes_clients.router)

    async def setup():
        a = await routes_auth.create_user("a@agency.com", "Agency", "pw12345678")
        await d.users.update_one({"id": a["id"]}, {"$set": {"role": "admin"}})
        me = await auth_utils.get_user(auth_utils.HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=auth_utils.make_token(a["id"])))
        c = await routes_clients.create_client({"name": "SBM"}, user=me)
        await d.webinars.insert_one({"id": "w1", "owner_id": c["id"], "title": "x"})
        return {"Authorization": "Bearer " + auth_utils.make_token(c["id"], agency_id=a["id"])}
    return d, TestClient(app), asyncio.run(setup())


ROWS = [{"name": "Jane", "email": "jane@example.com", "phone": None, "source": "invite"},
        {"name": "Typo", "email": "a..b@gmail.com"},
        {"name": "Reserved", "email": "x@school.local"},
        {"name": "Outlook", "email": "<ravi@example.com>"}]


@pytest.mark.parametrize("path", ["invitees", "registrants"])
def test_bad_rows_are_skipped_not_fatal(env, path):
    d, client, h = env
    r = client.post(f"/api/webinars/w1/{path}/import", json=ROWS, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inserted"] == 2
    assert sorted(body["invalid"]) == ["a..b@gmail.com", "x@school.local"]
    listed = client.get(f"/api/webinars/w1/{path}", headers=h).json()
    rows = listed["items"] if path == "invitees" else listed
    assert {x["email"] for x in rows} == {"jane@example.com", "ravi@example.com"}


def test_single_contact_in_client_workspace(env):
    d, client, h = env
    r = client.post("/api/webinars/w1/registrants/import", json=[{"name": "", "email": "one@example.com"}], headers=h)
    assert r.status_code == 200 and r.json()["inserted"] == 1


@pytest.mark.parametrize("path", ["invitees", "registrants"])
def test_big_csv_is_one_bulk_insert(env, path):
    """1,800 rows: every row lands, re-sending dedupes, and it's done in bulk."""
    d, client, h = env
    rows = [{"name": f"P{i}", "email": f"p{i}@example.com"} for i in range(1800)]
    rows.append({"name": "dup", "email": "p1@example.com"})
    r = client.post(f"/api/webinars/w1/{path}/import", json=rows, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] == 1800
    coll = getattr(d, path)
    assert asyncio.run(coll.count_documents({"webinar_id": "w1"})) == 1800
    again = client.post(f"/api/webinars/w1/{path}/import", json=rows[:10], headers=h).json()
    assert again["inserted"] == 0 and again["deduped"] == 10


def test_imported_registrant_leaves_invite_list(env):
    d, client, h = env
    client.post("/api/webinars/w1/invitees/import", json=[{"name": "A", "email": "a@example.com"}], headers=h)
    client.post("/api/webinars/w1/registrants/import", json=[{"name": "A", "email": "a@example.com"}], headers=h)
    inv = asyncio.run(d.invitees.find_one({"email": "a@example.com"}))
    assert inv["registered_at"]
