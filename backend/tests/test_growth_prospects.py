"""Growth Engine — prospect scoring, import and compliance tests (real mongod)."""
import os

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from _growth_helpers import require_mongo

require_mongo()

from growth_engine import COLLECTIONS          # noqa: E402
from growth_engine import prospect_engine as pe   # noqa: E402

MONGO_URL = "mongodb://127.0.0.1:27019"
DB_NAME = "growth_prospect_test"

CSV = """name,title,company,linkedin_url
Sarah Jones,Demand Generation Manager,Acme SaaS,https://linkedin.com/in/sarahjones
Tom Bell,Head of Events,Big Events Co,linkedin.com/in/tombell
Priya Nair,Software Engineer,Acme SaaS,https://www.linkedin.com/in/priyanair
Rex Stone,Dentist,Smile Clinic,
"""


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db(growth_client):
    """Shared session client/loop — see tests/conftest.py for why."""
    database = growth_client[DB_NAME]
    await growth_client.drop_database(DB_NAME)
    yield database
    await growth_client.drop_database(DB_NAME)


# ── parsing ──────────────────────────────────────────────────────────────────

def test_csv_import_normalises_fields():
    rows = pe.parse_import(CSV)
    assert len(rows) == 4
    urls = {r["name"]: r["linkedin_url"] for r in rows}
    assert urls["Tom Bell"] == "https://www.linkedin.com/in/tombell"   # bare host normalised
    assert urls["Sarah Jones"] == "https://linkedin.com/in/sarahjones"
    assert urls["Rex Stone"] == ""                                     # kept without a link


def test_json_import():
    rows = pe.parse_import('[{"name":"Ann Lee","headline":"VP Marketing","company":"X"}]')
    assert len(rows) == 1 and rows[0]["company"] == "X"


def test_empty_input_returns_nothing():
    assert pe.parse_import("") == []


# ── scoring ──────────────────────────────────────────────────────────────────

def test_role_match_is_the_dominant_signal():
    s, breakdown, signals = pe.score_prospect(
        {"name": "Sarah", "headline": "Demand Generation Manager", "company": "Acme SaaS"})
    assert s >= 60, f"a core ICP title must read hot on its own, got {s} ({breakdown})"
    assert breakdown["role"] >= 30
    assert any("role:" in x for x in signals)


def test_non_icp_scores_low():
    s, _, _ = pe.score_prospect({"name": "Rex", "headline": "Dentist", "company": "Smile Clinic"})
    assert s < 40


def test_scoring_is_monotonic_with_fit():
    low, _, _ = pe.score_prospect({"headline": "Software Engineer", "company": "Acme SaaS"})
    high, _, _ = pe.score_prospect(
        {"headline": "Head of Events running a virtual summit", "company": "Marketing Agency"})
    assert high > low


def test_activity_raises_score():
    base = {"name": "A", "headline": "Marketing Manager", "company": "SaaS"}
    before, _, _ = pe.score_prospect(base)
    after, _, _ = pe.score_prospect({**base, "activity": [{"at": pe.now_iso(), "summary": "webinar"}]})
    assert after > before


def test_compliance_contract_is_hard_off():
    assert pe.PROVIDER_CONTRACT["no_browser_automation"] is True
    assert pe.PROVIDER_CONTRACT["no_login_scrape"] is True
    assert pe.PROVIDER_CONTRACT["no_auto_dm_or_connect"] is True
    assert pe.PROVIDER_CONTRACT["automated_engagement_enabled"] is False


# ── persistence ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_ingest_dedupes_on_reimport(db):
    rows = pe.parse_import(CSV)
    assert (await pe.ingest(db, rows))["added"] == 4
    again = await pe.ingest(db, rows)
    assert again["added"] == 0 and again["updated"] == 4
    assert await db[COLLECTIONS["prospects"]].count_documents({}) == 4


@pytest.mark.asyncio(loop_scope="session")
async def test_ingest_ranks_icp_first(db):
    await pe.ingest(db, pe.parse_import(CSV))
    top = await pe.top_prospects(db, limit=10)
    names = [p["name"] for p in top]
    assert names[0] == "Sarah Jones"
    assert names[-1] == "Rex Stone"
    assert top[0]["tier"] == "hot"


@pytest.mark.asyncio(loop_scope="session")
async def test_activity_is_stored_and_scored(db):
    await pe.ingest(db, pe.parse_import(CSV))
    p = await db[COLLECTIONS["prospects"]].find_one({"name": "Priya Nair"})
    before = p["score"]
    res = await pe.add_activity(db, p["id"], [
        {"type": "post", "summary": "Planning our first webinar series", "at": pe.now_iso()}])
    assert res["ok"] and res["added"] == 1
    after = await db[COLLECTIONS["prospects"]].find_one({"id": p["id"]})
    assert len(after["activity"]) == 1
    assert after["score"] > before
    assert any(h["event"] == "activity_added" for h in after["history"])


@pytest.mark.asyncio(loop_scope="session")
async def test_recommendations_are_advice_only(db):
    await pe.ingest(db, pe.parse_import(CSV))
    p = await db[COLLECTIONS["prospects"]].find_one({"name": "Sarah Jones"})
    rec = await pe.recommend_engagement(db, p["id"])
    assert rec["ok"] and rec["actions"]
    for a in rec["actions"]:
        assert "manual" in a["execute"], "engine must never execute engagement itself"


@pytest.mark.asyncio(loop_scope="session")
async def test_history_log_appends(db):
    await pe.ingest(db, pe.parse_import(CSV))
    p = await db[COLLECTIONS["prospects"]].find_one({"name": "Tom Bell"})
    await pe.log_history(db, p["id"], "note_sent", "operator replied")
    h = (await db[COLLECTIONS["prospects"]].find_one({"id": p["id"]}))["history"]
    assert any(x["event"] == "note_sent" for x in h)


@pytest.mark.asyncio(loop_scope="session")
async def test_unknown_prospect_errors_cleanly(db):
    assert (await pe.recommend_engagement(db, "nope"))["ok"] is False
    assert (await pe.connection_message(db, "nope"))["ok"] is False