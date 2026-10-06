"""Growth Engine — weekly plan, voice rules and competitor detection.

No MongoDB and no live AI: the model is stubbed so these run anywhere.
"""
import pytest

from _growth_helpers import BACKEND_DIR  # noqa: F401  (fixes sys.path)
from growth_engine import DEFAULT_WEEKLY_PLAN
from growth_engine import content_engine as ce
from growth_engine import queue
from growth_engine.blog_engine import is_competitor_post
from growth_engine.models import PlatformCopy


def test_default_plan_is_one_post_a_day_mon_to_sat():
    plan = queue.parse_weekly_plan(DEFAULT_WEEKLY_PLAN)
    assert sorted(plan) == [0, 1, 2, 3, 4, 5]
    assert all(len(items) == 1 for items in plan.values())
    kinds = [plan[d][0]["kind"] for d in range(6)]
    assert kinds == ["pain_point", "blog", "news", "competitor", "engagement", "blog"]
    assert plan[1][0]["format"] == "carousel"
    assert plan[5][0]["platforms"] == ["facebook"]
    # Instagram and LinkedIn: 5 a week. Facebook: 6.
    per = {p: sum(1 for i in plan.values() for x in i if not x["platforms"] or p in x["platforms"])
           for p in ("linkedin", "facebook", "instagram")}
    assert per == {"linkedin": 5, "facebook": 6, "instagram": 5}


def test_plan_skips_bad_entries_and_falls_back():
    plan = queue.parse_weekly_plan("mon=blog:carousel,xyz=blog:carousel,tue=nope:quote,wed=news:bad")
    assert list(plan) == [0]
    assert queue.parse_weekly_plan("garbage") == queue.parse_weekly_plan(DEFAULT_WEEKLY_PLAN)
    two = queue.parse_weekly_plan("mon=blog:carousel,mon=engagement:quote")
    assert [i["kind"] for i in two[0]] == ["blog", "engagement"]


def test_plan_for_sunday_is_empty():
    assert queue.plan_for("2026-10-11") == []           # a Sunday
    assert queue.plan_for("2026-10-08")[0]["kind"] == "competitor"   # a Thursday


def test_humanize_strips_ai_tells():
    out = ce.humanize("Stop guessing 🚀 — start measuring → now\n\n\n\nDone ✨")
    assert "🚀" not in out and "✨" not in out and "—" not in out and "→" not in out
    assert "\n\n\n" not in out


def test_copy_issues_flags_banned_words_and_missing_question():
    bad = {"linkedin": PlatformCopy(caption="In today's fast-paced world, unlock attendance.")}
    issues = ce.copy_issues(bad)
    assert any("in today's" in i for i in issues)
    assert any("question" in i for i in issues)
    good = {"linkedin": PlatformCopy(caption="Your reminders are too late.\n\nWhen do you send the first one? Tell me below.")}
    assert ce.copy_issues(good) == []


def test_competitor_detection():
    assert is_competitor_post({"slug": "best-livestorm-alternatives"})
    assert is_competitor_post({"slug": "showupai-vs-zoom-reminders"})
    assert not is_competitor_post({"slug": "live-vs-on-demand-webinar-attendance"})


@pytest.mark.asyncio
async def test_build_campaign_rewrites_once_when_rules_broken(monkeypatch):
    calls = []

    async def fake_ai(prompt):
        calls.append(prompt)
        cap = ("Unlock better attendance — today 🚀" if len(calls) == 1
               else "Your no-shows are a timing problem.\n\nWhat day do you send reminders? Tell me in the comments.")
        return {"strategy": {}, "platform_copy": {"linkedin": {"caption": cap}},
                "visual": {"format": "carousel", "title": "Fix it",
                           "slides": [{"title": f"S{i}", "body": "b"} for i in range(4)], "cta": "c"}}

    monkeypatch.setattr(ce, "ai_json", fake_ai)
    draft = await ce.build_campaign("pain_point", seed="t", platforms=["linkedin"],
                                    visual_format="carousel")
    assert len(calls) == 2
    assert "BROKE THESE RULES" in calls[1]
    assert 'VISUAL FORMAT: use "carousel"' in calls[0]
    assert draft.platform_copy["linkedin"].caption.startswith("Your no-shows")
    assert draft.visual.format == "carousel"
