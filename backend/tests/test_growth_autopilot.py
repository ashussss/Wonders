"""Growth Engine — auto mode: varied plan, theme rotation, auto-approval, retries.

The pure tests run anywhere. The queue tests use mongomock_motor when it is
installed and skip otherwise.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from _growth_helpers import BACKEND_DIR  # noqa: F401  (fixes sys.path)
from growth_engine import DEFAULT_WEEKLY_PLAN, VISUAL_FORMATS, queue
from growth_engine.models import CampaignDraft, PlatformCopy, Strategy, VisualSpec


def test_week_uses_many_templates_and_never_repeats_back_to_back():
    plan = queue.parse_weekly_plan(DEFAULT_WEEKLY_PLAN)
    order = [x["format"] for d in range(7) for x in plan[d]]
    assert len(order) == 14
    assert len(set(order)) >= 8
    assert all(a != b for a, b in zip(order, order[1:] + order[:1]))
    assert set(order) <= set(VISUAL_FORMATS)


def test_theme_rotates_between_consecutive_posts():
    seq = []
    for i in range(10):
        day = (datetime(2026, 10, 12) + timedelta(days=i)).date().isoformat()
        seq += [queue.theme_index(day, 0) % 4, queue.theme_index(day, 1) % 4]
    assert all(a != b for a, b in zip(seq, seq[1:]))
    assert set(seq) == {0, 1, 2, 3}


def _doc(**kw):
    d = {"platforms": ["linkedin", "instagram"], "asset_ids": ["a"], "review": {},
         "visual": {"format": "carousel", "title": "t", "rows": []},
         "platform_copy": {"linkedin": {"caption": "hi"}, "instagram": {"caption": "hi"}}}
    d.update(kw)
    return d


def test_hold_reason():
    assert queue.hold_reason(_doc()) == ""
    assert "render" in queue.hold_reason(_doc(review={"visual_error": "boom"}))
    assert queue.hold_reason(_doc(asset_ids=[])) == "no image"
    assert "incomplete" in queue.hold_reason(_doc(visual={"format": "checklist", "title": "Review needed"}))
    assert "instagram" in queue.hold_reason(_doc(platform_copy={"linkedin": {"caption": "x"}}))


# ── queue behaviour on an in-memory Mongo ────────────────────────────────────

mm = pytest.importorskip("mongomock_motor")


def _draft(slug):
    return CampaignDraft(
        kind="blog", source_type="blog", source_slug=slug,
        strategy=Strategy(target_audience="Event hosts", pain_point="No-shows",
                          intent="Fix attendance", funnel_stage="awareness",
                          content_angle="angle", hook="hook line"),
        platform_copy={p: PlatformCopy(caption=f"copy {p}?") for p in ("linkedin", "facebook")},
        platforms=["linkedin", "facebook"],
        visual=VisualSpec(format="hot_take", title="A *clear* opinion", subtitle="why"))


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def mdb():
    return mm.AsyncMongoMockClient()["autopilot"]


def test_auto_mode_approves_good_posts(mdb, monkeypatch):
    import growth_engine as ge
    monkeypatch.setattr(ge, "APPROVAL_MODE", False)
    monkeypatch.setattr(ge, "GROWTH_AUTO_PUBLISH", True)
    doc = _run(queue.enqueue(mdb, _draft("a"), datetime.now(timezone.utc), "2026-10-12"))
    assert doc["status"] == "approved" and doc["review"]["mode"] == "auto"

    monkeypatch.setattr(ge, "GROWTH_AUTO_PUBLISH", False)
    doc = _run(queue.enqueue(mdb, _draft("b"), datetime.now(timezone.utc), "2026-10-12"))
    assert doc["status"] == "pending_review"


def test_failed_posts_are_retried_and_stuck_ones_recovered(mdb, monkeypatch):
    import growth_engine as ge
    monkeypatch.setattr(ge, "GROWTH_AUTO_PUBLISH", True)
    monkeypatch.setattr(queue, "APPROVAL_MODE", False)
    calls = []

    async def fake_publish(_db, d):
        calls.append(d["id"])
        await _db[ge.COLLECTIONS["campaigns"]].update_one(
            {"id": d["id"]}, {"$set": {"status": "posted"}, "$inc": {"attempts": 1}})
        return {"id": d["id"], "status": "posted"}

    monkeypatch.setattr(queue, "publish_campaign", fake_publish)
    col = mdb[ge.COLLECTIONS["campaigns"]]
    now = datetime.now(timezone.utc)
    old = (now - timedelta(hours=1)).isoformat()
    _run(col.insert_many([
        {"id": "failed", "status": "failed", "attempts": 1, "updated_at": old, "scheduled_at": old},
        {"id": "gave_up", "status": "failed", "attempts": 3, "updated_at": old, "scheduled_at": old},
        {"id": "too_old", "status": "failed", "attempts": 1, "updated_at": old,
         "scheduled_at": (now - timedelta(days=2)).isoformat()},
        {"id": "fresh_fail", "status": "partial", "attempts": 1, "updated_at": now.isoformat(),
         "scheduled_at": old},
        {"id": "stuck", "status": "publishing", "updated_at": old, "scheduled_at": old},
        {"id": "future", "status": "approved", "updated_at": old,
         "scheduled_at": (now + timedelta(hours=3)).isoformat()},
    ]))
    res = _run(queue.dispatch_due(mdb))
    assert sorted(calls) == ["failed", "stuck"], res


def test_generation_lock_blocks_a_second_run(mdb):
    assert _run(queue._claim_generation(mdb, "2026-10-12")) is True
    assert _run(queue._claim_generation(mdb, "2026-10-12")) is False
    stale = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    _run(mdb["growth_locks"].update_one({"_id": "generate:2026-10-12"}, {"$set": {"at": stale}}))
    assert _run(queue._claim_generation(mdb, "2026-10-12")) is True
