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


def test_default_plan_is_two_posts_a_day_on_every_platform():
    plan = queue.parse_weekly_plan(DEFAULT_WEEKLY_PLAN)
    assert sorted(plan) == list(range(7))
    assert all(len(items) == 2 for items in plan.values())
    assert all(not x["platforms"] for items in plan.values() for x in items)
    # the two posts on a day never share a format
    assert all(items[0]["format"] != items[1]["format"] for items in plan.values())
    kinds = [x["kind"] for items in plan.values() for x in items]
    assert {"pain_point", "blog", "news", "competitor", "engagement"} <= set(kinds)
    # a blog post every day, first slot
    assert all(items[0]["kind"] == "blog" for items in plan.values())
    assert sum(1 for items in plan.values() for x in items if x["format"] == "poll") == 2


def test_plan_skips_bad_entries_and_falls_back():
    plan = queue.parse_weekly_plan("mon=blog:carousel,xyz=blog:carousel,tue=nope:quote,wed=news:bad")
    assert list(plan) == [0]
    assert queue.parse_weekly_plan("garbage") == queue.parse_weekly_plan(DEFAULT_WEEKLY_PLAN)
    two = queue.parse_weekly_plan("mon=blog:carousel,mon=engagement:quote")
    assert [i["kind"] for i in two[0]] == ["blog", "engagement"]


def test_plan_for_a_date():
    assert len(queue.plan_for("2026-10-11")) == 2       # a Sunday
    assert queue.plan_for("2026-10-08")[1]["kind"] == "competitor"   # a Thursday


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


def test_every_caption_gets_the_site():
    assert ce.ensure_site("Hook.\n\nQuestion?\n\n#a #b #c").endswith("showupai.live\n\n#a #b #c")
    assert ce.ensure_site("Hook. Question?").endswith("\n\nshowupai.live")
    already = "See showupai.live\nQuestion?"
    assert ce.ensure_site(already) == already


def test_poll_spec_is_trimmed_to_linkedin_limits():
    from growth_engine.content_engine import _visual, is_renderable
    spec = _visual({"visual": {"format": "poll", "title": "Q" * 200,
                               "rows": ["a" * 50, "Two", "Three", "Four", "Five"]}},
                   "engagement", "s", "poll")
    assert spec.format == "poll" and is_renderable(spec)
    assert len(spec.title) <= 140 and len(spec.rows) == 4
    assert all(len(r) <= 30 for r in spec.rows)


def test_poll_renders_a_jpeg():
    from growth_engine import visual_engine as ve
    from growth_engine.models import VisualSpec
    b = ve.render_poll(VisualSpec(format="poll", title="When do you send the first reminder?",
                                  rows=["Right after signup", "A week before", "The day before"]))
    assert b[:2] == b"\xff\xd8"


@pytest.mark.asyncio
async def test_linkedin_poll_uses_posts_api(monkeypatch):
    import httpx
    sent = {}

    def handler(req):
        sent["url"], sent["headers"], sent["body"] = str(req.url), req.headers, req.content
        return httpx.Response(201, headers={"x-restli-id": "urn:li:share:1"})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k))
    res = await queue.post_linkedin_poll({"linkedin_marketing_token": "t",
                                          "linkedin_org_urn": "urn:li:person:x"},
                                         "Vote below?", "Which?", ["A", "B"])
    assert res == {"ok": True, "id": "urn:li:share:1"}
    assert sent["url"] == "https://api.linkedin.com/rest/posts"
    assert sent["headers"]["LinkedIn-Version"]
    assert b'"poll"' in sent["body"] and b'"question":"Which?"' in sent["body"]


def test_ensure_link_adds_blog_url_above_hashtags():
    from growth_engine.content_engine import ensure_link, is_blog_link
    url = "https://showupai.live/blog/webinar-no-shows"
    out = ensure_link("Hook.\n\nBody?\n\n#webinars #b2b", url)
    assert f"Read it here: {url}\n\n#webinars #b2b" in out
    assert ensure_link(out, url) == out
    assert is_blog_link(url)
    assert not is_blog_link("https://showupai.live/blog")
    assert not is_blog_link("https://marketingdive.com/news/x")


def test_meta_missing_permissions():
    from growth_engine import meta
    granted = ["pages_show_list", "pages_read_engagement", "instagram_basic"]
    assert meta.missing_permissions(granted, meta.REQUIRED_PAGE_PERMS) == ["pages_manage_posts"]
    assert meta.missing_permissions(granted) == ["pages_manage_posts", "instagram_content_publish"]
