"""keyword_boosts: exact, idempotent on-page additions for striking-distance queries (no server or Mongo needed)."""
import os
import re
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.modules.setdefault("database", types.SimpleNamespace(db=None))
import keyword_boosts as kb  # noqa: E402
import pseo  # noqa: E402

POST = {"slug": "x", "title": "Old", "content": "Quick answer here.\n\n## Body\n\nText.\n\n## FAQ\n\nQ?", "faq_items": []}


def test_section_goes_before_faq_and_is_added_once():
    boost = {"slug": "x", "section": ("What is a webinar series?", "A series is ...")}
    ch = kb.apply_boost(POST, boost)
    c = ch["content"]
    assert c.index("## What is a webinar series?") < c.index("## FAQ")
    assert kb.apply_boost({**POST, "content": c}, boost) == {}


def test_lead_section_goes_after_quick_answer():
    ch = kb.apply_boost(POST, {"slug": "x", "lead_section": ("Quick verdict", "- A\n- B")})
    assert ch["content"].startswith("Quick answer here.\n\n## Quick verdict")


def test_faq_and_title_are_idempotent():
    boost = {"slug": "x", "title": "New title", "faq": [("What is a webinar CTA?", "The next step.")]}
    ch = kb.apply_boost(POST, boost)
    assert ch["title"] == "New title" and ch["faq_items"][-1]["question"] == "What is a webinar CTA?"
    assert kb.apply_boost({**POST, **ch}, boost) == {}


def test_boost_copy_follows_pipeline_rules():
    for b in kb.BOOSTS:
        texts = [a for _, a in b.get("faq", [])] + [q for q, _ in b.get("faq", [])]
        for key in ("section", "lead_section"):
            if b.get(key):
                texts += list(b[key])
        texts.append(b.get("title", ""))
        for t in texts:
            assert "%" not in t, (b["slug"], t)
            assert not pseo.banned_phrases_in(t), (b["slug"], pseo.banned_phrases_in(t))
            assert "—" not in t
            for url in re.findall(r"\]\((https://showupai\.live[^)]*)\)", t):
                path = url.replace("https://showupai.live", "")
                assert path in pseo.SEO_PAGES or path.startswith("/blog/"), url


def test_priority_keywords_are_on_topic_and_first():
    assert all(pseo.is_on_topic(k) for k, _, _ in kb.PRIORITY_KEYWORDS)
    assert kb._FIRST_AT < pseo._PRIORITY_AT


def test_index_status_drops_redirects_and_off_topic_posts():
    assert pseo.index_status({"slug": "best-practices-for-webinar-followup-emails", "title": "x"}) == "redirect"
    assert pseo.index_status({"slug": "a", "redirect_to": "b"}) == "redirect"
    assert pseo.index_status({"slug": "integrating-nfc-badge-data-with-abm-platforms",
                              "keyword": "integrating nfc badge data with abm platforms"}) == "noindex"
    assert pseo.index_status({"slug": "webinar-cta-examples", "keyword": "webinar cta examples"}) == ""
    assert pseo.index_status({"slug": "hybrid-event-reminder-strategies", "title": "Hybrid event reminder strategies"}) == ""


def test_compare_links_first_plain_mention_only_and_idempotent():
    c = ("We used Zoom and Demio.\n\n## Zoom vs Demio\n| Zoom | x |\n"
         "Try [Livestorm](https://livestorm.co) or Livestorm. WebinarJam too.\n```\nZoom\n```")
    out = kb.link_compare_pages(c)
    assert "[Zoom](https://showupai.live/compare/zoom) and [Demio](https://showupai.live/compare/demio)" in out
    assert "## Zoom vs Demio" in out and "| Zoom | x |" in out
    assert "[Livestorm](https://livestorm.co) or [Livestorm](https://showupai.live/compare/livestorm)" in out
    assert "compare/webinarjam" not in out  # max 3 per post
    assert kb.link_compare_pages(out) == out


def test_cleanup_noindex_and_duplicate_redirects():
    assert pseo.index_status({"slug": "zero-knowledge-proof-certificates-for-webinars", "title": "Webinar certificates"}) == "noindex"
    assert pseo.index_status({"slug": "building-a-webinar-content-hub-for-lead-nurturing", "title": "x"}) == "redirect"
    assert pseo.index_status({"slug": "webinar-content-hubs-for-lead-nurturing", "title": "Webinar content hubs"}) == ""
    for dup, kept in kb.DUPLICATE_REDIRECTS.items():
        assert kept not in kb.DUPLICATE_REDIRECTS and dup not in kb.NOINDEX_SLUGS


def test_cleanup_title_fix_and_links_are_idempotent():
    post = {"slug": "international-webinar-localization-tactics", "keyword": "webinar localization tactics",
            "title": "International Webinar Localization Tactics That Actually Boost",
            "seo_title": "International Webinar Localization Tactics That Actually Boost", "content": "Plain."}
    ch = kb.cleanup_changes(post)
    assert ch["title"].endswith("Boost Attendance") and len(ch["seo_title"]) <= 60
    assert kb.cleanup_changes({**post, **ch}) == {}

    body = ("We moved from Hopin and Crowdcast to BigMarker.\n\n## Hopin pricing\n| Hopin | x |\n"
            "See [old](https://showupai.live/blog/building-a-webinar-content-hub-for-lead-nurturing).")
    p = {"slug": "demio-alternatives", "keyword": "demio alternatives", "title": "Demio alternatives", "content": body}
    new = kb.cleanup_changes(p)["content"]
    assert "[Hopin](https://showupai.live/blog/airmeet-vs-hopin) and [Crowdcast](https://showupai.live/blog/crowdcast-alternatives)" in new
    assert "[BigMarker]" not in new.split("\n")[0]  # max 2 in-text links per post
    assert "## Hopin pricing" in new and "| Hopin | x |" in new
    assert "/blog/webinar-content-hubs-for-lead-nurturing)" in new
    assert new.count(kb._RELATED_MARK) == 1 and "/blog/demio-vs-webinarjam)" in new
    assert kb.cleanup_changes({**p, "content": new}) == {}
    # the target post does not link to itself; noindexed posts get no new links
    own = kb.cleanup_changes({"slug": "crowdcast-alternatives", "keyword": "crowdcast alternatives", "title": "t",
                              "content": "Crowdcast is fine."})
    assert "crowdcast-alternatives)" not in own.get("content", "").split("**Related")[0]
    assert kb.cleanup_changes({"slug": "leveraging-webinar-polls-for-seo", "title": "t", "content": "Hopin."}) == {}
