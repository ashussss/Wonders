"""Webinar social images (carousel, infographic, quote card) wear the customer's Brand Kit."""
import asyncio
import io

from PIL import Image

import brand_kit as bk
import image_gen as ig

NAVY = {"primary_color": "#1B3A6B", "background_color": "#FFFFFF"}
BRAND = {"theme": bk.theme(NAVY), "name": "School Business Manager", "tagline": "By SBMs, for SBMs",
         "powered_by": True, "cta": "Book your place", "title": "Budget planning for 2027",
         "date_line": "Free live session · Tue 20 Nov, 4:00 PM GMT · with Richard Clarke"}


def _img(b):
    return Image.open(io.BytesIO(b)).convert("RGB")


def _has(img, rgb, tol=10):
    small = img.resize((108, 135 if img.height > img.width else 108))
    return any(all(abs(a - b) <= tol for a, b in zip(px, rgb)) for px in small.getdata())


def test_slides_use_brand_colour_not_orange():
    for kw in ({"is_cover": True}, {}, {"is_last": True}):
        img = _img(ig.make_slide(1, 6, "Heading here", "Body text here", brand=BRAND, **kw))
        assert _has(img, (0x1B, 0x3A, 0x6B))
        assert not _has(img, ig.ORANGE, tol=20)


def test_infographic_and_quote_use_brand():
    async def no_llm(*a, **k):
        return None
    info = _img(asyncio.run(ig.make_infographic("Budget planning", "SBMs", "", "case_study", BRAND)))
    assert info.getpixel((5, 5)) == (0x1B, 0x3A, 0x6B)          # brand header
    assert not _has(info, ig.ORANGE, tol=20)
    quote = _img(ig.make_quote_card("Is your budget ready for the pay award?", "SBMs", brand=BRAND))
    assert quote.getpixel((5, 5)) == (255, 255, 255)
    assert _has(quote, (0x1B, 0x3A, 0x6B)) and not _has(quote, ig.ORANGE, tol=20)


def test_logo_is_drawn():
    logo = Image.new("RGBA", (300, 100), (200, 30, 30, 255))
    buf = io.BytesIO(); logo.save(buf, "PNG")
    img = _img(ig.make_quote_card("Q?", brand={**BRAND, "logo_png": buf.getvalue()}))
    assert _has(img, (200, 30, 30))


def test_without_brand_keeps_showup_look():
    img = _img(ig.make_slide(1, 6, "H", "B"))
    assert _has(img, ig.ORANGE)


def test_no_fake_stats_in_fallbacks():
    import inspect
    src = inspect.getsource(ig)
    assert "70%" not in src and "62%" not in src
