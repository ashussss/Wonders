"""Checks for the one-off refresh plan of existing blog posts (no server or Mongo needed)."""
import os
import re
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.modules.setdefault("database", types.SimpleNamespace(db=None))
import blog_refresh as br  # noqa: E402
import pseo  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_plan_covers_each_post_once():
    slugs = [i["slug"] for i in br.REFRESH]
    assert len(slugs) == len(set(slugs)) == 35
    gone = set(br.MERGED) | set(br.REMOVED)
    assert not gone & set(slugs)
    assert len(br.MERGED) == 9 and len(br.REMOVED) == 1


def test_merge_targets_are_kept_posts_that_absorb_them():
    kept = {i["slug"]: i for i in br.REFRESH}
    for dup, target in br.MERGED.items():
        assert target in kept
        assert dup in kept[target].get("absorb", [])


def test_every_post_gets_its_own_example_and_valid_facts():
    scenarios = [i["scenario"] for i in br.REFRESH]
    assert len(set(scenarios)) == len(scenarios)
    assert not any(re.search(r"\b400 registrants\b", s) for s in scenarios)
    for i in br.REFRESH:
        assert all(0 <= f < len(pseo.FACTS) for f in i["facts"])
        assert i["brief"].strip()


def test_redirects_match_plan():
    text = open(os.path.join(ROOT, "frontend/public/_redirects")).read()
    rules = dict(re.findall(r"^/blog/(\S+)\s+/blog/(\S+)\s+301!", text, re.M))
    assert rules == {**br.MERGED, **br.REMOVED}
    assert text.index("/blog/") < text.index("/*")  # must come before the SPA catch-all


def test_exact_edit_matches_content_file():
    md = open(os.path.join(ROOT, "backend/content/webinar-statistics.md")).read()
    for find, repl in br.EXACT_EDITS["webinar-statistics"]:
        assert repl in md and find not in md
        assert "how-many-webinar-reminders-to-send" not in md


def test_retarget_links():
    c = ("See [replay](https://showupai.live/blog/webinar-replay-email-for-no-shows) and "
         "[stats](/blog/webinar-attendance-benchmarks-by-industry/) and [keep](https://showupai.live/blog/webinar-statistics).")
    out = br.retarget_links(c, {**br.MERGED, **br.REMOVED})
    assert "(https://showupai.live/blog/webinar-follow-up-email-for-no-shows)" in out
    assert "(/blog/webinar-statistics)" in out
    assert "replay-email" not in out and "by-industry" not in out


def test_problems_rejects_the_old_skeleton():
    fact = pseo.FACTS[0]["url"]
    good = " ".join(["word"] * 1300) + f"\n[ON24 reports]({fact}) 60%.\nExample: 620 x 38% = 235.6 attendees."
    assert br.problems(good, 1200) == []
    bad = good + "\nAI can cut churn by 15%.\nExample: 400 x 40% = 170 attendees from 400 registrants."
    found = " | ".join(br.problems(bad, 1200))
    assert "unsourced number" in found and "wrong arithmetic" in found and "400 registrants" in found
    assert any("too short" in p for p in br.problems("short text", 1200))
