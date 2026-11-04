"""Pure-logic checks for the Search Console autopilot (no server, Mongo or network)."""
import os
import sys
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.modules.setdefault("database", types.SimpleNamespace(db=None))
import seo_autopilot as sa  # noqa: E402

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def _row(page, query, imp, pos, clicks=0):
    return {"page": page, "query": query, "impressions": imp, "position": pos, "clicks": clicks}


def test_slug_of_handles_trailing_slash_and_non_blog_pages():
    assert sa.slug_of("https://showupai.live/blog/webinar-cta-examples") == "webinar-cta-examples"
    assert sa.slug_of("https://showupai.live/blog/webinar-cta-examples/") == "webinar-cta-examples"
    assert sa.slug_of("https://showupai.live/blog") is None
    assert sa.slug_of("https://showupai.live/") is None


def test_per_post_merges_slash_variants_and_weights_position():
    rows = [_row("https://showupai.live/blog/a", "q1", 3, 10),
            _row("https://showupai.live/blog/a/", "q2", 1, 30, clicks=1),
            _row("https://showupai.live/", "brand", 9, 2)]
    s = sa.per_post(rows)
    assert list(s) == ["a"]
    assert s["a"]["impressions"] == 4 and s["a"]["clicks"] == 1
    assert s["a"]["position"] == 15.0  # (3*10 + 1*30) / 4
    assert [q["query"] for q in s["a"]["queries"]] == ["q1", "q2"]


def _post(slug, imp, pos, published=True, refreshed=None):
    return {"slug": slug, "published": published, "autopilot_refreshed_at": refreshed,
            "gsc": {"impressions": imp, "position": pos}}


def test_pick_refresh_takes_striking_distance_and_respects_cooldown():
    recent = (NOW - timedelta(days=3)).isoformat()
    old = (NOW - timedelta(days=60)).isoformat()
    posts = [_post("page1", 50, 2),            # already top 5: leave it
             _post("deep", 50, 80),            # too deep to move
             _post("good", 3, 19),
             _post("better", 9, 23, refreshed=old),
             _post("cooling", 20, 12, refreshed=recent),
             _post("draft", 20, 12, published=False),
             _post("none", 0, 0)]
    assert [p["slug"] for p in sa.pick_refresh(posts, NOW, 5)] == ["better", "good"]
    assert [p["slug"] for p in sa.pick_refresh(posts, NOW, 1)] == ["better"]


def test_harvest_skips_brand_one_word_and_covered_topics():
    rows = [_row("u", "webinarjam alternatives", 1, 23),
            _row("u", "showupi3", 1, 5),
            _row("u", "webinar", 4, 50),
            _row("u", "webinarjam mailchimp integration", 1, 51),
            _row("u", "webinar cta examples", 1, 19)]
    existing = ["webinarjam alternatives", "Webinar CTA Examples That Convert"]
    assert sa.harvest_keywords(rows, existing, 10) == ["webinarjam mailchimp integration"]
    assert sa.harvest_keywords(rows, [], 1) == ["webinarjam alternatives"]
