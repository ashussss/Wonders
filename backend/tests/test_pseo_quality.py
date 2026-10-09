"""Unit tests for the blog pipeline's quality controls (no server or Mongo needed):
banned-phrase detection, brand-mention count, topic dedup and spaced publish scheduling."""
import asyncio
import os
import sys
import types
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.modules.setdefault("database", types.SimpleNamespace(db=None))
import pseo  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, n):
        return self.rows[:n]


class _Coll:
    def __init__(self, rows):
        self.rows = rows

    def find(self, *a, **k):
        return _Cursor(self.rows)


def _with_posts(rows):
    pseo.db = types.SimpleNamespace(blog_posts=_Coll(rows))


def test_banned_phrases_detected_case_and_apostrophe_insensitive():
    found = pseo.banned_phrases_in("We Delve into it. Let’s dive in and unlock growth.")
    assert {"delve", "let's dive in", "unlock"} <= set(found)
    assert pseo.banned_phrases_in("Send the reminder 15 minutes before the start.") == []


def test_brand_mentions_ignore_domain():
    assert pseo.brand_mentions("[ShowUpAI](https://showupai.live) runs it. Visit showupai.live.") == 1


def test_quality_gate_holds_banned_phrases_and_brand_spam():
    base = {"fact_check_ok": True, "word_count": 1500, "title": "t", "meta_description": "m"}
    assert pseo.passes_quality_gate({**base, "content": "Plain, specific copy."})[0]
    assert not pseo.passes_quality_gate({**base, "content": "This is a game-changer."})[0]
    assert not pseo.passes_quality_gate({**base, "content": "ShowUpAI. ShowUpAI. ShowUpAI."})[0]
    assert not pseo.passes_quality_gate({**base, "word_count": 900, "content": "ok"})[0]


def test_topic_similarity_flags_live_duplicates_but_not_distinct_topics():
    sim = pseo.topic_similarity
    assert sim("best practices for post-webinar follow‑up", "best practices for webinar post‑event follow‑up") >= 0.75
    assert sim("using linkedin for b2b event promotion", "using linkedin to promote b2b webinars") >= 0.75
    assert sim("edtech webinar attendance", "webinar attendance for edtech companies") >= 0.6
    assert sim("webinar reminder sms examples", "webinar poll ideas to boost engagement") < 0.6
    assert sim("webinar statistics", "how to write compelling webinar titles") < 0.6


def test_find_overlap_lexical_without_llm(monkeypatch):
    monkeypatch.setattr(pseo, "GROQ_API_KEY", "")
    _with_posts([{"slug": "using-linkedin-to-promote-b2b-webinars", "keyword": "using linkedin to promote b2b webinars", "title": "x"}])
    hit = asyncio.run(pseo.find_overlap("leveraging linkedin for b2b event marketing"))
    assert hit and hit["slug"] == "using-linkedin-to-promote-b2b-webinars"
    assert asyncio.run(pseo.find_overlap("webinar poll ideas")) is None


def test_next_publish_slot_respects_daily_cap_and_varies_minutes(monkeypatch):
    monkeypatch.setattr(pseo, "PSEO_MAX_PUBLISH_PER_DAY", 1)
    rows, slots = [], []
    for _ in range(6):
        _with_posts(rows)
        slot = asyncio.run(pseo.next_publish_slot())
        assert slot
        slots.append(datetime.fromisoformat(slot).astimezone(IST))
        rows.append({"published": False, "publish_at": slot})
    days = Counter(s.date() for s in slots)
    assert max(days.values()) == 1
    assert len({(s.hour, s.minute) for s in slots}) > 1
    assert all(s > datetime.now(IST) for s in slots)


def test_seo_title_never_cut_mid_word():
    assert pseo.make_seo_title("Webinar Statistics") == "Webinar Statistics | ShowUpAI"
    long = "How to Write a Webinar Confirmation Email That Drives Attendance"
    assert pseo.make_seo_title(long) == long
    very = "Mastering Webinar Reminder Cadence for B2B SaaS: A Complete Playbook for Busy Teams"
    out = pseo.make_seo_title(very)
    assert len(out) <= 70 and very.startswith(out) and very[len(out)] == " "


def test_clean_post_fields_repairs_auto_cut_title_but_keeps_custom():
    t = "How to Write a Webinar Confirmation Email That Drives Attendance"
    d = pseo.clean_post_fields({"title": t, "seo_title": f"{t} | ShowUpAI"[:70], "content": "x"})
    assert d["seo_title"] == t
    d = pseo.clean_post_fields({"title": t, "seo_title": "Custom SEO Title", "content": "x"})
    assert d["seo_title"] == "Custom SEO Title"


def test_unknown_blog_links_are_unwrapped():
    c = ("See [follow-up emails](https://showupai.live/blog/best-practices-for-post-webinar-followup-emails) "
         "and [stats](https://showupai.live/blog/webinar-statistics) and [home](https://showupai.live).")
    out = pseo.strip_unknown_blog_links(c, {"webinar-statistics"})
    assert "post-webinar-followup-emails" not in out and "See follow-up emails and" in out
    assert "(https://showupai.live/blog/webinar-statistics)" in out and "(https://showupai.live)" in out


def test_unsourced_numbers_and_empty_tables():
    fact = pseo.FACTS[0]["url"]
    c = "\n".join([
        f"[ON24 reports]({fact}) a 60% conversion.",
        "Example: 400 x 40% = 160 attendees.",
        "62% of firms experience a data breach.",
        "```", "Open rate 45%", "```",
    ])
    assert pseo.unsourced_numbers(c) == ["62% of firms experience a data breach."]
    hollow = "| Industry | Rate |\n|---|---|\n| SaaS | - |\n| EdTech | — |\n"
    full = "| Channel | When |\n|---|---|\n| Email | T-24h |\n| SMS | T-1h |\n"
    assert pseo.empty_tables(hollow) == 1 and pseo.empty_tables(full) == 0
    base = {"fact_check_ok": True, "word_count": 1500, "title": "t", "meta_description": "m"}
    assert not pseo.passes_quality_gate({**base, "content": "62% of firms churn."})[0]
    assert not pseo.passes_quality_gate({**base, "content": hollow})[0]


def test_bad_math_flags_wrong_sums_only():
    ok = "Example: 250 registrants x 36% = 90 attendees. 90 + 15 = 105. 1,000 x 8% = 80. 45 / 300 = 15%."
    assert pseo.bad_math(ok) == []
    assert pseo.bad_math("Example: 400 x 55% = 220 opens, then 220 x 30% = 80 clicks.") == ["220 x 30% = 80"]
    assert pseo.bad_math("45 + 36 = 61") == ["45 + 36 = 61"]
    base = {"fact_check_ok": True, "word_count": 1500, "title": "t", "meta_description": "m"}
    assert not pseo.passes_quality_gate({**base, "content": "Example: 300 x 40% = 150 attendees."})[0]


def test_next_publish_slot_four_a_day_uses_different_times(monkeypatch):
    monkeypatch.setattr(pseo, "PSEO_MAX_PUBLISH_PER_DAY", 4)
    rows, slots = [], []
    for _ in range(12):
        _with_posts(rows)
        slot = asyncio.run(pseo.next_publish_slot())
        assert slot
        slots.append(datetime.fromisoformat(slot).astimezone(IST))
        rows.append({"published": False, "publish_at": slot})
    days = Counter(s.date() for s in slots)
    assert max(days.values()) <= 4
    for d in days:
        hours = sorted(s.hour for s in slots if s.date() == d)
        assert all(b - a >= 2 for a, b in zip(hours, hours[1:]))


class _CountColl:
    def __init__(self, n):
        self.n = n

    async def count_documents(self, q):
        return self.n

    def find(self, *a, **k):
        return types.SimpleNamespace(sort=lambda *a, **k: _Cursor([]))


def _catch_up(monkeypatch, have, runs):
    monkeypatch.setattr(pseo, "PSEO_MAX_PUBLISH_PER_DAY", 4)
    pseo.db = types.SimpleNamespace(blog_posts=_CountColl(have))
    calls = []

    async def fake_run(n):
        calls.append(n)
        return {"results": runs.pop(0) if runs else []}
    monkeypatch.setattr(pseo, "run_pipeline", fake_run)
    return asyncio.run(pseo.catch_up()), calls


def test_catch_up_skips_when_day_is_full(monkeypatch):
    res, calls = _catch_up(monkeypatch, 4, [])
    assert "skipped" in res and calls == []


def test_catch_up_fills_missing_posts_and_retries_failed_drafts(monkeypatch):
    sched, draft = [{"status": "scheduled"}], [{"status": "draft"}]
    _, calls = _catch_up(monkeypatch, 2, [draft, sched, draft, sched, sched])
    assert len(calls) == 4  # 2 missing: one failed draft, one scheduled, one failed, one scheduled


def test_catch_up_gives_up_and_stops_on_empty_queue(monkeypatch):
    _, calls = _catch_up(monkeypatch, 3, [[{"status": "draft"}]] * 10)
    assert len(calls) == 3  # 1 missing -> at most 3 attempts
    _, calls = _catch_up(monkeypatch, 0, [])
    assert len(calls) == 1  # empty queue ends it at once


def test_drop_failing_sentences_keeps_sourced_and_example_numbers():
    url = pseo.FACTS[0]["url"]
    content = "\n".join([
        "## Why it matters",
        "Most teams see 73% no-shows. That hurts.",
        f"ON24 reports a figure [here]({url}) of 60%.",
        "- Around 40% of people forget. Send a reminder.",
        "For example, 20% of 100 is 20.",
        "| Channel | Lift |", "|---|---|", "| SMS | 30% |",
        "Doubling 50 x 2 = 120 is wrong.",
        "Keep this line.",
    ])
    out = pseo.drop_failing_sentences(content)
    assert "73%" not in out and "That hurts." in out and url in out
    assert "40%" not in out and "- Send a reminder." in out
    assert "For example, 20% of 100 is 20." in out
    assert "| SMS | 30% |" not in out and "| Channel | Lift |" in out
    assert "50 x 2 = 120" not in out and "Keep this line." in out
    assert not pseo.unsourced_numbers(out) and not pseo.bad_math(out)


def test_trim_brand_mentions_to_gate_limit():
    b = pseo.BRAND
    out = pseo.trim_brand_mentions(f"{b} helps. Use {b} now. {b} also does X.")
    assert pseo.brand_mentions(out) == 2 and out.endswith("The tool also does X.")


class _UpdColl:
    def __init__(self):
        self.updates = []

    async def update_one(self, q, u):
        self.updates.append((q, u))


def test_auto_schedule_repairs_held_draft_then_schedules(monkeypatch):
    coll = _UpdColl()
    pseo.db = types.SimpleNamespace(blog_posts=coll)

    async def no_style(c):
        return c

    async def slot():
        return "2026-10-08T05:00:00+00:00"
    monkeypatch.setattr(pseo, "style_fix", no_style)
    monkeypatch.setattr(pseo, "next_publish_slot", slot)
    monkeypatch.setattr(pseo, "PSEO_AUTO_SCHEDULE", True)
    body = " ".join(["Plain specific advice about reminders."] * 250)
    post = {"slug": "s", "title": "t", "meta_description": "m", "fact_check_ok": True,
            "content": body + "\nTeams lose 73% of signups.", "word_count": 1300}
    assert not pseo.passes_quality_gate(post)[0]
    res = asyncio.run(pseo.auto_schedule(post))
    assert res["status"] == "scheduled"
    saved = [u["$set"] for _, u in coll.updates if "content" in u.get("$set", {})][0]
    assert "73%" not in saved["content"]


def test_auto_schedule_records_held_reason(monkeypatch):
    coll = _UpdColl()
    pseo.db = types.SimpleNamespace(blog_posts=coll)

    async def no_style(c):
        return c
    monkeypatch.setattr(pseo, "style_fix", no_style)
    monkeypatch.setattr(pseo, "PSEO_AUTO_SCHEDULE", True)
    post = {"slug": "s", "title": "t", "meta_description": "m", "fact_check_ok": True, "content": "short", "word_count": 1}
    res = asyncio.run(pseo.auto_schedule(post))
    assert res["held"].startswith("too short")
    assert any(u.get("$set", {}).get("held_reason", "").startswith("too short") for _, u in coll.updates)


def test_catch_up_schedules_held_drafts_before_writing_new(monkeypatch):
    held = [{"slug": "a"}, {"slug": "b"}]
    coll = _CountColl(2)
    coll.find = lambda *a, **k: types.SimpleNamespace(sort=lambda *a, **k: _Cursor(held))
    monkeypatch.setattr(pseo, "PSEO_MAX_PUBLISH_PER_DAY", 4)
    pseo.db = types.SimpleNamespace(blog_posts=coll)

    async def sched(post, when=None, **kw):
        return {"status": "scheduled"}
    calls = []

    async def fake_run(n):
        calls.append(n)
        return {"results": []}
    monkeypatch.setattr(pseo, "auto_schedule", sched)
    monkeypatch.setattr(pseo, "run_pipeline", fake_run)
    assert asyncio.run(pseo.catch_up()) == {"ok": True, "rescheduled": 2}
    assert calls == []


def test_held_draft_from_earlier_day_publishes_now(monkeypatch):
    old = {"slug": "old", "created_at": "2026-01-01T03:30:00+00:00"}
    new = {"slug": "new", "created_at": "2999-01-01T03:30:00+00:00"}
    coll = _CountColl(0)
    coll.find = lambda *a, **k: types.SimpleNamespace(sort=lambda *a, **k: _Cursor([old, new]))
    pseo.db = types.SimpleNamespace(blog_posts=coll)
    seen = {}

    async def sched(post, when=None, **kw):
        seen[post["slug"]] = when
        return {"status": "scheduled"}
    monkeypatch.setattr(pseo, "auto_schedule", sched)
    assert asyncio.run(pseo.schedule_held_drafts(5)) == 2
    assert seen["old"] and seen["new"] is None


def test_last_resort_publishes_when_fact_check_cannot_run(monkeypatch):
    coll = _UpdColl()
    pseo.db = types.SimpleNamespace(blog_posts=coll)

    async def no_ai(c):
        return c, None  # Groq down: fact-check never runs

    async def no_style(c):
        return c

    async def slot():
        return "2026-10-09T05:00:00+00:00"
    monkeypatch.setattr(pseo, "fact_check", no_ai)
    monkeypatch.setattr(pseo, "style_fix", no_style)
    monkeypatch.setattr(pseo, "next_publish_slot", slot)
    monkeypatch.setattr(pseo, "PSEO_AUTO_SCHEDULE", True)
    body = " ".join(["Plain specific advice about reminders."] * 200)
    post = {"slug": "s", "title": "t", "meta_description": "m", "word_count": 1000,
            "content": body + "\nThis is a game-changer for teams.\nTeams lose 73% of signups."}
    assert asyncio.run(pseo.auto_schedule(dict(post)))["held"] == "fact-check did not run"
    res = asyncio.run(pseo.auto_schedule(dict(post), last_resort=True))
    assert res["status"] == "scheduled"
    saved = [u["$set"] for _, u in coll.updates if u.get("$set", {}).get("last_resort_fix")][0]
    assert "73%" not in saved["content"] and "game-changer" not in saved["content"]


def test_last_resort_still_holds_thin_drafts(monkeypatch):
    coll = _UpdColl()
    pseo.db = types.SimpleNamespace(blog_posts=coll)

    async def no_ai(c):
        return c, None

    async def no_style(c):
        return c
    monkeypatch.setattr(pseo, "fact_check", no_ai)
    monkeypatch.setattr(pseo, "style_fix", no_style)
    monkeypatch.setattr(pseo, "PSEO_AUTO_SCHEDULE", True)
    post = {"slug": "s", "title": "t", "meta_description": "m", "content": "short", "word_count": 1}
    assert asyncio.run(pseo.auto_schedule(post, last_resort=True))["held"].startswith("too short")


def test_drop_banned_sentences():
    out = pseo.drop_banned_sentences("## Unlock growth\nKeep me. Let's dive in now.\n- A game changer. Real tip.\nFine.")
    assert out == "Keep me.\n- Real tip.\nFine."
