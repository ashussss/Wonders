"""Growth Engine — link engine: catalog, drafting, review flow, backlink checks.

Uses a real mongod when one is reachable, otherwise mongomock-motor if installed,
otherwise the DB tests skip. The pure-function tests always run.
"""
import inspect

import pytest
import pytest_asyncio

import _growth_helpers  # noqa: F401  (puts backend/ on sys.path)

from growth_engine import COLLECTIONS
from growth_engine import link_engine as le

DB_NAME = "growth_links_test"


# ── pure functions ───────────────────────────────────────────────────────────

def test_catalog_is_well_formed():
    keys = [c["key"] for c in le.CATALOG]
    assert len(keys) == len(set(keys))
    for c in le.CATALOG:
        assert c["asset"] in le.ASSET_SPECS, c["key"]
        assert c["cadence"] in ("once", "weekly", "on_demand")
        assert c["submit_url"].startswith("https://")
        assert c["priority"] in (1, 2, 3)
    assert {"product_hunt", "substack", "g2", "medium"} <= set(keys)


def test_engine_never_sends_anything():
    """The anti-spam contract: the module only GETs pages, it never POSTs anywhere."""
    src = inspect.getsource(le)
    for forbidden in (".post(", ".put(", "smtp", "send_mail", "selenium", "playwright"):
        assert forbidden not in src.lower(), forbidden


def test_find_backlink_detects_follow_and_nofollow():
    html = '<p>x</p><a rel="nofollow ugc" href="https://showupai.live/blog/a">ShowUpAI</a>'
    r = le.find_backlink(html, "showupai.live")
    assert r["found"] and not r["follow"] and "nofollow" in r["rel"]

    r = le.find_backlink('<a href="https://www.showupai.live/">site</a>', "showupai.live")
    assert r["found"] and r["follow"]

    r = le.find_backlink("We use ShowUpAI (showupai.live) for reminders.", "showupai.live")
    assert r["found"] and r["rel"] == "mention-only"

    assert not le.find_backlink('<a href="https://example.com">x</a>', "showupai.live")["found"]


# ── DB-backed ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db():
    if _growth_helpers.mongo_available():
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(_growth_helpers.DEFAULT_MONGO)
    else:
        mm = pytest.importorskip("mongomock_motor")
        client = mm.AsyncMongoMockClient()
    await client.drop_database(DB_NAME)
    yield client[DB_NAME]
    await client.drop_database(DB_NAME)


@pytest.fixture
def fake_ai(monkeypatch):
    prompts = []

    async def _fake(prompt):
        prompts.append(prompt)
        return {"tagline": f"Tagline {len(prompts)}", "short_description": "Reminders that get people to show up."}

    monkeypatch.setattr(le, "ai_json", _fake)
    return prompts


async def test_seed_is_idempotent_and_keeps_status(db):
    first = await le.seed_catalog(db)
    assert first["added"] == len(le.CATALOG)
    await db[COLLECTIONS["links"]].update_one({"key": "g2"}, {"$set": {"status": "live"}})
    again = await le.seed_catalog(db)
    assert again["added"] == 0
    assert (await db[COLLECTIONS["links"]].find_one({"key": "g2"}))["status"] == "live"
    await db[COLLECTIONS["links"]].update_one({"key": "g2"}, {"$set": {"status": "todo"}})


async def test_weekly_run_paces_one_time_items(db, fake_ai):
    res = await le.weekly_run(db, limit=2)
    weekly = [c["key"] for c in le.CATALOG if c["cadence"] == "weekly"]
    once = [k for k in res["drafted"] if k not in weekly]
    assert len(once) == 2
    # Highest-priority items go first.
    assert all(le.CATALOG_BY_KEY[k]["priority"] == 1 for k in once)
    assert set(weekly) <= set(res["drafted"])
    row = await db[COLLECTIONS["links"]].find_one({"key": once[0]})
    assert row["status"] == "pending_review" and row["draft"]["tagline"]
    # Prompt carries the rules and forbids upvote asks.
    assert "Never ask anyone for upvotes" in fake_ai[0]


async def test_later_drafts_are_told_to_avoid_earlier_taglines(db, fake_ai):
    await le.draft(db, "saashub")
    assert "Tagline" in fake_ai[-1].split("Do not reuse these earlier taglines")[1].split("\n")[0]


async def test_review_flow_and_illegal_moves(db, fake_ai):
    await le.draft(db, "alternativeto")
    with pytest.raises(ValueError):
        await le.set_status(db, "alternativeto", "live", "https://alternativeto.net/software/showupai/")
    await le.set_status(db, "alternativeto", "approved", draft_edit={"tagline": "Edited"})
    row = await le.set_status(db, "alternativeto", "submitted", "https://alternativeto.net/software/showupai/")
    assert row["status"] == "submitted" and row["draft"]["tagline"] == "Edited"
    with pytest.raises(ValueError):
        await le.set_status(db, "alternativeto", "submitted", "not-a-url")


async def test_on_demand_pr_answer(db, fake_ai):
    row = await le.draft_on_demand(db, "pr_answer", "Looking for event marketers: how do you cut webinar no-shows?",
                                   "https://www.qwoted.com/requests/123", "Qwoted")
    assert row["status"] == "pending_review" and row["category"] == "pr" and row["domain"] == "qwoted.com"
    assert "JOURNALIST QUERY" in fake_ai[-1]
    with pytest.raises(ValueError):
        await le.draft_on_demand(db, "spam_blast", "x")


async def test_verify_marks_live_then_lost(db, monkeypatch):
    pages = {"html": '<a href="https://showupai.live">ShowUpAI</a>'}

    class Resp:
        status_code = 200

        @property
        def text(self):
            return pages["html"]

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return Resp()

    monkeypatch.setattr(le.httpx, "AsyncClient", Client)
    coll = db[COLLECTIONS["links"]]
    await coll.update_one({"key": "crunchbase"}, {"$set": {"status": "submitted",
                                                           "live_url": "https://www.crunchbase.com/x"}})
    await le.verify_live(db, max_age_days=0)
    assert (await coll.find_one({"key": "crunchbase"}))["status"] == "live"
    pages["html"] = "<p>gone</p>"
    await le.verify_live(db, max_age_days=0)
    assert (await coll.find_one({"key": "crunchbase"}))["status"] == "lost"
