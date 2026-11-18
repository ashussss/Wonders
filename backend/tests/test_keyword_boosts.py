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
