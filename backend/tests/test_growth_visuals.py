"""Growth Engine — visual rendering tests (every format).

Pure-render tests: no MongoDB, no AI. Each renderer must produce real JPEG bytes
at the brand's expected dimensions.
"""
import io

import pytest
from PIL import Image

from _growth_helpers import BACKEND_DIR  # noqa: F401  (fixes sys.path)
from growth_engine import visual_engine as ve
from growth_engine.content_engine import is_renderable
from growth_engine.models import VisualSpec


def _specs():
    return {
        "carousel": VisualSpec(
            format="carousel", title="Your registrants aren't busy. They forgot.",
            slides=[{"title": "The reminder never landed", "body": "One email is not a sequence."},
                    {"title": "Timing beats volume", "body": "One nudge beats five blasts."},
                    {"title": "Give them one job", "body": "Calendar invite + join link."},
                    {"title": "Make it easy to say no", "body": "Record the session."}],
            cta="Read the attendance playbook"),
        "infographic": VisualSpec(
            format="infographic", title="Fixing webinar attendance in 5 steps",
            rows=["Audit no-show rate", "Build a touch sequence", "Send calendar invites",
                  "Nudge 3 days out", "Track show-up rate"]),
        "stat_card": VisualSpec(
            format="stat_card", number="51.3%", label="Average webinar show-up rate",
            source="Livestorm"),
        "checklist": VisualSpec(
            format="checklist", title="Pre-webinar checklist",
            rows=["Confirm join link", "Send calendar invite", "Schedule nudge",
                  "Test copy", "Assign a host"]),
        "comparison": VisualSpec(
            format="comparison", title="One broadcast vs a sequence",
            left={"title": "One broadcast", "rows": ["Sent once", "Generic", "No tracking"]},
            right={"title": "A sequence", "rows": ["11 touches", "Timed to intent", "Measured"]}),
        "quote": VisualSpec(
            format="quote", quote="Attendance is earned. Nobody shows up for a broadcast.",
            attribution="ShowUpAI"),
        "myth_fact": VisualSpec(
            format="myth_fact", title="Webinar reminder *myths*",
            items=[{"label": "One reminder email is enough", "value": "People need 3-5 nudges across channels"},
                   {"label": "No-shows weren't interested", "value": "Most no-shows simply *forgot*"}]),
        "timeline": VisualSpec(
            format="timeline", title="The reminder *timeline*",
            items=[{"label": "7 days before", "value": "Announce the agenda"},
                   {"label": "1 day before", "value": "Send the calendar invite again"},
                   {"label": "15 min before", "value": "Join link on WhatsApp"}]),
        "hot_take": VisualSpec(
            format="hot_take", title="Your registration page is not the *problem*",
            subtitle="The week before the event is where attendance is lost."),
    }


@pytest.mark.parametrize("fmt", sorted(_specs()))
def test_renderer_produces_real_jpeg(fmt):
    spec = _specs()[fmt]
    assert is_renderable(spec), f"{fmt} spec should be renderable"
    out = ve.RENDERERS[fmt](spec, seed=f"test-{fmt}")
    pages = out if isinstance(out, list) else [out]
    assert pages, f"{fmt} produced no pages"
    for b in pages:
        assert len(b) > 1000, f"{fmt} page too small ({len(b)}B)"
        im = Image.open(io.BytesIO(b))
        assert im.format == "JPEG"
        assert im.size[0] == 1080


def test_carousel_is_multi_page():
    spec = _specs()["carousel"]
    pages = ve.render_carousel(spec, seed="carousel-multi")
    # 4 slides + hook slide + CTA slide
    assert len(pages) == 6
    assert all(p[:2] == b"\xff\xd8" for p in pages)


@pytest.mark.parametrize("spec", [
    VisualSpec(format="stat_card", title="t"),                       # no number
    VisualSpec(format="carousel", slides=[{"title": "a"}]),          # too few slides
    VisualSpec(format="comparison", left={"rows": ["a"]}),           # missing right side
    VisualSpec(format="infographic"),                                # no rows
    VisualSpec(format="quote"),                                      # no quote
])
def test_unrenderable_specs_are_refused(spec):
    assert not is_renderable(spec)


def test_comparison_with_both_sides_is_renderable():
    # Both sides present => a complete comparison, which the comparison renderer draws.
    spec = VisualSpec(format="comparison", title="A vs B",
                      left={"title": "A", "rows": ["x", "y"]},
                      right={"title": "B", "rows": ["p", "q"]})
    assert is_renderable(spec)


def test_all_formats_registered():
    from growth_engine import VISUAL_FORMATS
    assert set(ve.RENDERERS) == set(VISUAL_FORMATS) == {
        "carousel", "infographic", "stat_card", "checklist", "comparison", "quote", "poll",
        "myth_fact", "timeline", "hot_take"}


def test_forced_theme_changes_the_look():
    from growth_engine import design
    spec = _specs()["hot_take"]
    with design.use_theme(0):
        a = ve.render_hot_take(spec, seed="same")
    with design.use_theme(1):
        b = ve.render_hot_take(spec, seed="same")
    corner = lambda raw: Image.open(io.BytesIO(raw)).convert("RGB").getpixel((5, 5))  # noqa: E731
    assert corner(a) != corner(b)
    assert design.theme("x") in design.THEMES          # back to seeded themes outside the block

def test_design_highlight_tokens():
    from growth_engine import design
    toks = design.tokens("One email is *not a sequence*")
    assert [w for w, em in toks if em] == ["not", "a", "sequence"]
    assert all(not em for w, em in toks if w in ("One", "email", "is"))
    # no asterisks: numbers are highlighted automatically
    assert dict(design.tokens("Send the 1-hour reminder"))["1-hour"] is True
    assert design.plain("*Bold* claim") == "Bold claim"


def test_design_uses_vendored_brand_font():
    from growth_engine import design
    assert design.font("black", 40).getname()[0].startswith("Outfit")


@pytest.mark.parametrize("fmt", sorted(_specs()))
def test_every_format_is_portrait(fmt):
    out = ve.RENDERERS[fmt](_specs()[fmt], seed=f"p-{fmt}")
    for b in (out if isinstance(out, list) else [out]):
        assert Image.open(io.BytesIO(b)).size == (1080, 1350)
