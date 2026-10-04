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
    assert not pseo.passes_quality_gate({**base, "word_count": 1000, "content": "ok"})[0]


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
