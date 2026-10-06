"""Growth Engine — queue, approval and isolation tests against a real mongod."""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from _growth_helpers import require_mongo

require_mongo()

from growth_engine import COLLECTIONS, queue            # noqa: E402
from growth_engine.models import CampaignDraft, PlatformCopy, Strategy, VisualSpec  # noqa: E402

MONGO_URL = "mongodb://127.0.0.1:27019"
DB_NAME = "growth_queue_test"


def _draft(kind="blog", slug="test-slug", **kw):
    return CampaignDraft(
        kind=kind, source_type="blog", source_slug=slug, source_title=f"Test {kind}",
        strategy=Strategy(target_audience="Event hosts", pain_point="No-shows",
                          intent="Fix attendance", funnel_stage="awareness",
                          content_angle="angle", hook="hook line"),
        platform_copy={p: PlatformCopy(caption=f"{kind} copy for {p}", hashtags=["webinar"])
                       for p in ("linkedin", "facebook", "instagram")},
        platforms=["linkedin", "facebook", "instagram"],
        visual=VisualSpec(format="stat_card", number="51.3%", label="avg show-up rate",
                          source="Livestorm"), **kw)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db(growth_client):
    """Shared session client/loop — see tests/conftest.py for why."""
    database = growth_client[DB_NAME]
    await growth_client.drop_database(DB_NAME)
    await queue.ensure_indexes(database)
    yield database
    await growth_client.drop_database(DB_NAME)


@pytest.mark.asyncio(loop_scope="session")
async def test_enqueue_uses_growth_collections_not_social_posts(db):
    when = datetime.now(timezone.utc) - timedelta(minutes=5)
    doc = await queue.enqueue(db, _draft(), when, "2026-10-04")
    assert doc["status"] == "pending_review"
    assert doc["asset_ids"], "visual should render and store an asset"
    assert all("/api/growth/asset/" in u for u in doc["asset_urls"])
    colls = await db.list_collection_names()
    assert "growth_campaigns" in colls
    assert "social_posts" not in colls


@pytest.mark.asyncio(loop_scope="session")
async def test_asset_bytes_roundtrip(db):
    from growth_engine import visual_engine as ve
    when = datetime.now(timezone.utc)
    doc = await queue.enqueue(db, _draft(slug="roundtrip"), when, "2026-10-04")
    raw = await ve.read_asset(db, doc["asset_ids"][0])
    assert raw and raw[:2] == b"\xff\xd8"


@pytest.mark.asyncio(loop_scope="session")
async def test_dispatch_blocked_in_approval_mode(db):
    when = datetime.now(timezone.utc) - timedelta(minutes=5)
    doc = await queue.enqueue(db, _draft(slug="blocked"), when, "2026-10-04")
    await queue.approve(db, ids=[doc["id"]])
    res = await queue.dispatch_due(db)
    assert res.get("skipped") == "approval_mode"
    stored = await db[COLLECTIONS["campaigns"]].find_one({"id": doc["id"]})
    assert stored["status"] == "approved", "must stay unpublished in approval mode"
    assert not stored["results"]


@pytest.mark.asyncio(loop_scope="session")
async def test_approve_is_idempotent_and_only_from_pending(db):
    when = datetime.now(timezone.utc)
    doc = await queue.enqueue(db, _draft(slug="idem"), when, "2026-10-04")
    assert (await queue.approve(db, ids=[doc["id"]]))["approved"] == 1
    assert (await queue.approve(db, ids=[doc["id"]]))["approved"] == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_edit_whitelists_fields(db):
    when = datetime.now(timezone.utc)
    doc = await queue.enqueue(db, _draft(slug="edit"), when, "2026-10-04")
    assert (await queue.edit(db, doc["id"], {"_id": "x", "status": "approved"}))["ok"] is False
    assert (await queue.edit(db, doc["id"], {"scheduled_at": "2026-10-05T09:00:00+00:00"}))["ok"] is True


@pytest.mark.asyncio(loop_scope="session")
async def test_reject_sets_status(db):
    when = datetime.now(timezone.utc)
    doc = await queue.enqueue(db, _draft(slug="rej"), when, "2026-10-04")
    assert (await queue.reject(db, [doc["id"]], "off-topic"))["rejected"] == 1
    stored = await db[COLLECTIONS["campaigns"]].find_one({"id": doc["id"]})
    assert stored["status"] == "rejected"


@pytest.mark.asyncio(loop_scope="session")
async def test_blog_detection_dedupes_via_growth_queue_only(db):
    from growth_engine import blog_engine
    now = datetime.now(timezone.utc).isoformat()
    await db.blog_posts.insert_one({"slug": "dedupe-test", "title": "T", "content": "x" * 200,
                                    "published": True, "published_at": now, "word_count": 200})
    posts = await blog_engine.pick_todays_posts(db, want=4)
    assert "dedupe-test" in [p["slug"] for p in posts]
    # queue a campaign for it, then it should drop out of the eligible list
    when = datetime.now(timezone.utc)
    await queue.enqueue(db, _draft(slug="dedupe-test"), when, "2026-10-04")
    posts = await blog_engine.pick_todays_posts(db, want=4)
    assert "dedupe-test" not in [p["slug"] for p in posts]


@pytest.mark.asyncio(loop_scope="session")
async def test_generate_day_follows_weekly_plan(db, monkeypatch):
    import growth_engine.content_engine as content_engine
    import growth_engine.news_engine as news_engine
    import growth_engine.queue as q

    async def _no_ai(*a, **kw):
        raise AssertionError("test reached the live AI — stub build_campaign")

    seen = []

    async def fake_build(_db, item, day, n):
        seen.append(item)
        return CampaignDraft(
            kind=item["kind"], source_type="original", source_slug=f"{item['kind']}-{day}-{n}",
            strategy=Strategy(target_audience="Event hosts", pain_point="No-shows",
                              intent="Fix attendance", funnel_stage="awareness",
                              content_angle="angle", hook="hook line"),
            platform_copy={"linkedin": PlatformCopy(caption="copy?")},
            platforms=["linkedin"],
            visual=VisualSpec(format="stat_card", number="1%", label="l"))

    monkeypatch.setattr(content_engine, "ai_json", _no_ai)
    monkeypatch.setattr(news_engine, "ai_json", _no_ai)
    monkeypatch.setattr(q, "_build_planned", fake_build)

    # 2031-02-03 is a Monday: one pain-point carousel.
    res = await queue.generate_day(db, day="2031-02-03", render=False, force=True)
    assert res["count"] == 1, res["created"]
    assert seen[-1]["kind"] == "pain_point" and seen[-1]["format"] == "carousel"
    # 2031-02-09 is a Sunday: nothing planned.
    res = await queue.generate_day(db, day="2031-02-09", render=False, force=True)
    assert res["count"] == 0 and "nothing planned" in res["note"]


@pytest.mark.asyncio(loop_scope="session")
async def test_engagement_campaign_has_a_valid_funnel_stage(db, monkeypatch):
    """Regression: 'engagement' is a campaign KIND, not a funnel stage. Using it as
    one raised KeyError and silently lost 1 of the 9 daily campaigns."""
    import growth_engine.queue as q
    from growth_engine.content_engine import stage_hint_for, KIND_STAGE
    from growth_engine import FUNNEL_STAGES

    assert stage_hint_for("engagement")
    for kind, stage in KIND_STAGE.items():
        assert stage in FUNNEL_STAGES, f"{kind} maps to invalid stage {stage}"


@pytest.mark.asyncio(loop_scope="session")
async def test_generate_day_is_idempotent(db, monkeypatch):
    import growth_engine.content_engine as content_engine
    import growth_engine.news_engine as news_engine
    import growth_engine.queue as q
    from growth_engine.models import CampaignDraft, PlatformCopy, Strategy, VisualSpec

    async def fake_news(_self, want=2, exclude_ids=None):
        return [{"id": f"n{i}", "title": f"News {i}", "url": "https://e.test/i",
                 "summary": "B2B event benchmark.", "source": "Pub", "relevance": 5}
                for i in range(want)]

    async def _no_ai(*a, **kw):
        raise AssertionError("test reached the live AI — stub build_campaign")

    async def fake_campaign(kind, **kw):
        # Originals have no source of their own, so derive a UNIQUE slug from the
        # seed — otherwise pain_point #0 and #1 collide and one is deduped away.
        slug = kw.get("source_slug") or kw.get("seed") or f"{kind}-unique"
        return CampaignDraft(
            kind=kind, source_type="original", source_slug=slug,
            strategy=Strategy(target_audience="Event hosts", pain_point="No-shows",
                              intent="Fix attendance", funnel_stage="awareness",
                              content_angle="angle", hook="hook line"),
            platform_copy={"linkedin": PlatformCopy(caption="copy")},
            platforms=["linkedin"],
            visual=VisualSpec(format="stat_card", number="1%", label="l"))

    monkeypatch.setattr(content_engine, "ai_json", _no_ai)
    # news_engine imports ai_json into its own namespace (used by triage).
    monkeypatch.setattr(news_engine, "ai_json", _no_ai)
    monkeypatch.setattr(news_engine, "pick_news", fake_news)
    async def fake_build(_db, item, day, n):
        return await fake_campaign(item["kind"], seed=f"{day}-{n}")

    monkeypatch.setattr(q, "_build_planned", fake_build)

    # Own plan_day: the session-scoped DB may already hold today's plan from an
    # earlier test, and generate_day is idempotent per day.
    res = await queue.generate_day(db, day="2031-02-04", render=False, force=True)
    assert res["count"] >= 1
    res2 = await queue.generate_day(db, day="2031-02-04", render=False)
    assert res2.get("note") == "already generated for this day"