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
