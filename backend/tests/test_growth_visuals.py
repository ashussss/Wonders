"""Growth Engine — visual rendering tests (all six formats).

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


def test_all_six_formats_registered():
    assert set(ve.RENDERERS) == {"carousel", "infographic", "stat_card",
                                 "checklist", "comparison", "quote"}