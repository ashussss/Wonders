"""Growth Engine — RSS news discovery tests (offline, no MongoDB)."""
from datetime import datetime, timedelta, timezone

import pytest

from _growth_helpers import BACKEND_DIR  # noqa: F401  (fixes sys.path)
from growth_engine import news_engine as ne


def _rss(items) -> bytes:
    body = "".join(f"""<item>
      <title>{i['title']}</title>
      <link>{i['url']}</link>
      <description>{i['desc']}</description>
      <pubDate>{i['date']}</pubDate>
      <source url="https://example.com">{i.get('source', 'Test Pub')}</source>
    </item>""" for i in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'.encode()


NOW = datetime.now(timezone.utc)
RECENT = NOW.strftime("%a, %d %b %Y %H:%M:%S +0000")
OLD = (NOW - timedelta(days=900)).strftime("%a, %d %b %Y %H:%M:%S +0000")


def test_parses_relevant_items_and_filters_the_rest():
    xml = _rss([
        {"title": "Webinar attendance rates drop as registrants get busier",
         "url": "https://e.test/a", "desc": "Average show-up rate fell to 58%.",
         "date": RECENT, "source": "Marketing Dive"},
        {"title": "Bitcoin price surges past record high", "url": "https://e.test/b",
         "desc": "Crypto rally.", "date": RECENT},
        {"title": "Old story about webinars from three years ago", "url": "https://e.test/c",
         "desc": "Webinar engagement engagement engagement.", "date": OLD},
    ])
    items = ne._parse_feed(xml, "https://feed.test/rss", NOW - timedelta(hours=48))
    titles = [i["title"] for i in items]
    assert len(items) == 1
    assert "attendance rates drop" in titles[0]
    assert items[0]["source"] == "Marketing Dive"


def test_cleans_html_and_entities():
    # Numeric references are valid XML; named HTML entities are not, so the parser
    # must survive real feeds that emit them un-escaped.
    xml = _rss([{"title": "B2B demand generation benchmarks for 2026",
                 "url": "https://e.test/x",
                 "desc": "&lt;p&gt;Lead &amp; conversion &#8212; data&lt;/p&gt;",
                 "date": RECENT}])
    item = ne._parse_feed(xml, "https://feed.test/rss", NOW - timedelta(hours=48))[0]
    assert "<p>" not in item["summary"]
    assert "&amp;" not in item["summary"]
    assert "Lead & conversion" in item["summary"]
    assert "—" in item["summary"]


def test_survives_undeclared_named_entities():
    # Google News and some publishers emit &mdash; raw, which is not well-formed XML.
    xml = _rss([{"title": "Webinar attendance rates fall", "url": "https://e.test/y",
                 "desc": "show-up rate &mdash; down", "date": RECENT}])
    assert ne._parse_feed(xml, "https://feed.test/rss", NOW) == [], \
        "must not raise on a malformed feed"


def test_malformed_feed_returns_empty():
    assert ne._parse_feed(b"<<<not xml", "https://feed.test/bad", NOW) == []


def test_relevance_scoring():
    assert ne.relevance_score("Webinar attendance rate falls", "show-up rate") >= 3
    assert ne.relevance_score("Bitcoin rally continues", "crypto price") == 0
    assert ne.relevance_score("Marketing Dive covers Nike brand spend", "brand campaign") < 3


@pytest.mark.asyncio(loop_scope="session")
async def test_triage_falls_back_when_no_candidates():
    # relevance below threshold -> nothing to triage
    assert await ne.triage([], want=2) == []


@pytest.mark.asyncio(loop_scope="session")
async def test_triage_returns_shortlist_when_few_candidates(monkeypatch):
    items = [{"title": "webinar attendance benchmarks", "summary": "x", "source": "p", "relevance": 5}]
    # len(candidates) <= want -> returned without an AI call
    assert await ne.triage(items, want=2) == items