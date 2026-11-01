"""Link-to-webinar matching: a Circle link must resolve to that exact event."""
from integrations import match_circle_record, _circle_url_parts

EVENTS = [
    {"id": 101, "name": "Budget Planning Webinar for School Leaders", "slug": "budget-planning-webinar-for-school-leaders"},
    {"id": 102, "name": "Safeguarding Webinar for School Business Managers", "slug": "safeguarding-webinar-for-school-business-managers"},
    {"id": 103, "name": "Budget Planning Webinar for School Leaders", "slug": "budget-planning-webinar-for-school-leaders-4f2a1"},
]


def test_url_parts_ignore_query_and_fragment():
    assert _circle_url_parts("https://x.circle.so/c/events/my-talk?utm_source=li#top") == ("", "my-talk")
    assert _circle_url_parts("https://schoolbusinessmanager.uk/c/webinars/my-talk/") == ("webinars", "my-talk")


def test_exact_slug_wins_over_lookalike():
    url = "https://schoolbusinessmanager.uk/c/events/budget-planning-webinar-for-school-leaders-4f2a1"
    assert match_circle_record(EVENTS, url)["id"] == 103
    url = "https://schoolbusinessmanager.uk/c/events/budget-planning-webinar-for-school-leaders"
    assert match_circle_record(EVENTS, url)["id"] == 101


def test_one_shared_word_is_not_a_match():
    # Old matcher picked any event sharing a single word like "webinar" or "school".
    url = "https://schoolbusinessmanager.uk/c/events/ofsted-readiness-webinar-school"
    assert match_circle_record(EVENTS, url) is None


def test_fuzzy_title_match_when_slug_differs():
    url = "https://x.circle.so/c/events/safeguarding-webinar-school-business-managers"
    assert match_circle_record(EVENTS, url)["id"] == 102


def test_ambiguous_fuzzy_match_returns_none():
    url = "https://x.circle.so/c/events/budget-planning-school-leaders"
    assert match_circle_record(EVENTS, url) is None


def test_match_by_record_url():
    recs = [{"id": 7, "name": "Other", "slug": "x", "url": "https://c.circle.so/c/live/spring-kickoff"}]
    assert match_circle_record(recs, "https://c.circle.so/c/live/spring-kickoff")["id"] == 7


# ── Circle "Pick Event" list ─────────────────────────────────────────────
from integrations import upcoming_circle_events

NOW = "2026-10-31T12:00:00"


def test_picker_drops_news_posts_and_past_events():
    recs = [
        {"id": 1, "name": "DfE pondered launching in-house MIS", "slug": "dfe-mis"},  # news post, no start
        {"id": 2, "name": "Old webinar", "starts_at": "2026-10-01T17:00:00Z"},
        {"id": 3, "name": "School Business Manager (UK) Portal Walkthrough & Live Demo",
         "slug": "portal-walkthrough", "starts_at": "2026-11-07T17:00:00.000Z", "space_id": 9},
        {"id": 4, "name": "HR clinic", "event_setting": {"starts_at": "2026-11-03T10:00:00Z"}, "url": "https://x/c/e/hr"},
    ]
    spaces = {9: {"name": "Events & Webinars", "url": "https://schoolbusinessmanager.uk/c/events-webinar-calendar"}}
    out = upcoming_circle_events(recs, NOW, spaces)
    assert [e["id"] for e in out] == [4, 3]
    assert out[1]["url"] == "https://schoolbusinessmanager.uk/c/events-webinar-calendar/portal-walkthrough"
    assert out[1]["space_name"] == "Events & Webinars"


# ── Fetching one event from a Circle link ────────────────────────────────────
import asyncio
import integrations
from integrations import fill_from_circle_event, is_circle_space_page, _clean_text


def test_clean_text_decodes_entities_and_tags():
    assert _clean_text("Events &amp; Webinars") == "Events & Webinars"
    assert _clean_text("<p>Hi&nbsp;<b>there</b></p>") == "Hi there"


def test_space_page_is_detected():
    assert is_circle_space_page({"description": "Explore Events &amp; Webinars space in School Business Manager (UK)"})
    assert not is_circle_space_page({"description": "Join Richard for a budget session"})


def test_fill_from_v2_event_record():
    ev = {"name": "Budget &amp; Planning", "body": "<p>Plan the year</p>", "starts_at": "2026-11-20T10:00:00Z",
          "ends_at": "2026-11-20T11:00:00Z", "cover_image_url": "https://img/c.png",
          "virtual_location_url": "https://zoom.us/j/1", "host": {"name": "Richard Clarke"}}
    r = fill_from_circle_event({}, ev, "https://x/c/events-webinars/budget")
    assert r["title"] == "Budget & Planning"
    assert r["description"] == "Plan the year"
    assert r["starts_at"] == "2026-11-20T10:00:00Z"
    assert r["cover_image_url"] == "https://img/c.png"
    assert r["join_link"] == "https://zoom.us/j/1"
    assert r["speaker"] == "Richard Clarke"


class _Resp:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


class _FakeCircle:
    """Admin v2 only: one event space with two events; v1 is gone (404)."""
    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, params=None):
        params = params or {}
        if params.get("page", 1) > 1:
            return _Resp(200, {"records": []})
        if url.endswith("/api/admin/v2/spaces"):
            return _Resp(200, {"records": [{"id": 9, "slug": "events-webinars", "name": "Events & Webinars", "space_type": "event"},
                                           {"id": 8, "slug": "news", "space_type": "basic"}]})
        if url.endswith("/api/admin/v2/events"):
            return _Resp(200, {"records": [
                {"id": 1, "name": "Ofsted Prep", "slug": "ofsted-prep", "starts_at": "2026-12-01T09:00:00Z"},
                {"id": 2, "name": "Budget Planning", "slug": "budget-planning", "starts_at": "2026-11-20T10:00:00Z",
                 "cover_image_url": "https://img/budget.png"},
            ]})
        return _Resp(404, {})


def test_fetch_uses_admin_v2_events(monkeypatch):
    monkeypatch.setattr(integrations.httpx, "AsyncClient", _FakeCircle)
    r = asyncio.run(integrations.fetch_circle_event(
        "https://schoolbusinessmanager.uk/c/events-webinars/budget-planning", "tok"))
    assert not r.get("error")
    assert r["title"] == "Budget Planning"
    assert r["starts_at"] == "2026-11-20T10:00:00Z"
    assert r["cover_image_url"] == "https://img/budget.png"


def test_space_page_scrape_does_not_fill_title_or_banner(monkeypatch):
    async def no_event(url, key, settings=None):
        return {"title": "", "description": "", "starts_at": "", "cover_image_url": "",
                "error": "Couldn't find this exact event in your Circle community."}

    async def space_page(url):
        return {"title": "Events & Webinars", "description": "Explore Events & Webinars space in SBM (UK)",
                "cover_image_url": "https://img/calendar.jpg", "starts_at": ""}

    monkeypatch.setattr(integrations, "fetch_circle_event", no_event)
    monkeypatch.setattr(integrations, "scrape_and_extract", space_page)
    r = asyncio.run(integrations.fetch_webinar_from_url("https://x.circle.so/c/events-webinars/foo",
                                                        {"circle_api_key": "k"}))
    assert r["title"] == "" and r["cover_image_url"] == ""
    assert r["error"]
