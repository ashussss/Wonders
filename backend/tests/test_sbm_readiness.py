"""Offline: weekday warm-ups, live link fallback, the host's own case study."""
import asyncio
from datetime import datetime, timedelta

import ai
import files
from touch_render import values


W = {"id": "w1", "title": "Demo", "starts_at": "2026-12-08T15:00:00+00:00", "timezone": "Europe/London",
     "join_link": "", "after_signup_url": "https://example.org/event"}


def test_warmups_skip_weekends():
    now = datetime.fromisoformat("2026-11-23T16:00:00+00:00")
    start = datetime.fromisoformat(W["starts_at"])
    days = ai._weekday_warmups(ai._warmup_days((start - now).total_seconds() / 86400), start, now)
    assert len(set(days.values())) == len(days)
    for d in days.values():
        assert d >= 2
        assert (start - timedelta(days=d)).weekday() < 5


def test_registrant_link_falls_back_to_event_page():
    v = values(W)
    assert v["join_link"] == "https://example.org/event"
    assert values(W, invite=True)["join_link"].endswith("/r/w1")
    assert b"example.org/event" in files.build_ics(W)
    assert values({**W, "join_link": "https://zoom.us/j/1"})["join_link"] == "https://zoom.us/j/1"


def test_host_case_study_replaces_ai_story():
    story = {"before": "a", "change": "b", "after": "c", "lesson": "d"}
    mine = {"ai_content": {"case_study": "AI", "story": story}, "edited_content": {"case_study": "Real story"}}
    assert ai.kit_brief(ai.kit_from_lead_magnets(mine), 5) == "Case study:\nReal story"
    same = {"ai_content": {"case_study": "AI", "story": story}, "edited_content": {"case_study": "AI"}}
    assert "Before: a" in ai.kit_brief(ai.kit_from_lead_magnets(same), 5)
