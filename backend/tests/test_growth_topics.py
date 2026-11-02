"""Growth Engine topic library: pillars, sourced facts, rotation."""
import asyncio

from _growth_helpers import BACKEND_DIR  # noqa: F401  (fixes sys.path)
from growth_engine import queue
from growth_engine import topic_library as tl


def test_every_fact_key_resolves_and_has_a_source():
    for t in tl.TOPICS + tl.ENGAGEMENT_TOPICS:
        for k in t["facts"]:
            assert k in tl.FACTS, k
    for claim, src in tl.FACTS.values():
        assert claim and src


def test_all_five_pillars_are_covered_and_interleaved():
    pillars = [t["pillar"] for t in tl.TOPICS]
    assert set(pillars) == set(tl.PILLAR_HINTS)
    assert all(a != b for a, b in zip(pillars, pillars[1:]))
    assert len(tl.TOPICS) >= 40


def test_rotation_changes_topic_and_pillar_day_to_day():
    days = [f"2026-11-{d:02d}-0" for d in range(2, 16)]
    picks = [tl.pick_topic(s) for s in days]
    assert len({p["brief"] for p in picks}) == len(picks)
    assert all(a["pillar"] != b["pillar"] for a, b in zip(picks, picks[1:]))


def test_stat_card_always_gets_a_fact():
    for d in range(1, 29):
        assert tl.pick_topic(f"2026-11-{d:02d}-1", need_fact=True)["facts"]
        assert tl.pick_engagement(f"2026-11-{d:02d}-1", need_fact=True)["facts"]


def test_fact_block():
    assert "none" in tl.fact_block([])
    block = tl.fact_block(["showup_avg"])
    assert "47.7%" in block and "Livestorm 2026" in block


def test_hook_without_facts_never_asks_for_a_number():
    for d in range(1, 29):
        assert "number" not in tl.pick_hook(f"2026-11-{d:02d}-0", has_facts=False)


def test_original_campaign_passes_brief_facts_and_hook(monkeypatch):
    seen = {}

    async def fake_build(kind, **kw):
        seen.update(kw, kind=kind)
        return None

    monkeypatch.setattr(queue, "build_campaign", fake_build)
    asyncio.get_event_loop().run_until_complete(
        queue.build_original_campaign("pain_point", seed="2026-11-03-1", visual_format="stat_card"))
    assert seen["kind"] == "pain_point"
    assert "PILLAR:" in seen["angle_hint"] and "HOOK STYLE:" in seen["angle_hint"]
    assert "SOURCED FACTS (" in seen["fact_block"]
