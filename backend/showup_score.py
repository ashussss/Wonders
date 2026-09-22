"""ShowUp Score share image generator (PIL/Pillow).

Produces a 1080x1080 brand-styled PNG summarising a completed webinar's attendance rate
versus the industry baseline (~30%). Designed to be shared on LinkedIn from touch #7.
"""
from __future__ import annotations
import io
import os
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

INDUSTRY_BASELINE = 30  # %
BRAND_ORANGE = (234, 88, 12)
BRAND_DARK = (17, 24, 39)
BRAND_LIGHT = (249, 250, 251)
BRAND_AMBER = (245, 158, 11)
BRAND_GREEN = (22, 163, 74)

# Try several common system fonts so deployment works without bundled fonts.
_FONT_BOLD = [
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_FONT_REG = [
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = _FONT_BOLD if bold else _FONT_REG
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:  # noqa: BLE001
                continue
    # Final fallback: default bitmap font (tiny but renders)
    return ImageFont.load_default()


def _measure(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def render_showup_score(webinar_title: str, attendance_rate: float,
                        registrants: int, attendees: int) -> bytes:
    """Render a 1080x1080 PNG. Returns bytes."""
    W = H = 1080
    img = Image.new("RGB", (W, H), BRAND_LIGHT)
    d = ImageDraw.Draw(img)

    rate_int = int(round(attendance_rate))
    multiplier = (attendance_rate / INDUSTRY_BASELINE) if INDUSTRY_BASELINE else 0
    is_great = attendance_rate >= 50

    # Diagonal orange accent band (top-right)
    d.polygon([(W, 0), (W, 340), (W - 480, 0)], fill=BRAND_ORANGE)
    # Subtle bottom accent
    d.rectangle([(0, H - 24), (W, H)], fill=BRAND_ORANGE)

    # Eyebrow label
    label_font = _font(28, bold=True)
    d.text((80, 80), "SHOWUP SCORE", fill=BRAND_ORANGE, font=label_font)

    # Webinar title (wrap at ~28 chars)
    title_font = _font(48, bold=True)
    title = webinar_title if len(webinar_title) <= 60 else webinar_title[:57] + "…"
    # naive wrap by words
    words = title.split()
    lines = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > 26:
            lines.append(cur.strip())
            cur = w + " "
        else:
            cur += w + " "
    if cur.strip():
        lines.append(cur.strip())
    y = 130
    for ln in lines[:3]:
        d.text((80, y), ln, fill=BRAND_DARK, font=title_font)
        y += 60

    # Hero stat
    hero_font = _font(280, bold=True)
    pct_text = f"{rate_int}%"
    pw, ph = _measure(d, pct_text, hero_font)
    d.text(((W - pw) / 2, 360), pct_text, fill=BRAND_ORANGE, font=hero_font)

    # Hero subtitle
    sub_font = _font(40, bold=True)
    sub_text = "of registrants showed up live"
    sw, _ = _measure(d, sub_text, sub_font)
    d.text(((W - sw) / 2, 680), sub_text, fill=BRAND_DARK, font=sub_font)

    # Comparison strip
    cmp_font = _font(32, bold=True)
    if multiplier >= 1.2:
        cmp_text = f"that's {multiplier:.1f}× the industry baseline of {INDUSTRY_BASELINE}%"
        cmp_color = BRAND_GREEN if is_great else BRAND_AMBER
    elif multiplier >= 1.0:
        cmp_text = f"in line with the industry baseline of {INDUSTRY_BASELINE}%"
        cmp_color = BRAND_AMBER
    else:
        cmp_text = f"industry baseline is {INDUSTRY_BASELINE}% — room to grow"
        cmp_color = BRAND_DARK
    cw, _ = _measure(d, cmp_text, cmp_font)
    d.text(((W - cw) / 2, 750), cmp_text, fill=cmp_color, font=cmp_font)

    # Reg / att breakdown
    detail_font = _font(28, bold=False)
    detail = f"{attendees} attended of {registrants} registered"
    dw, _ = _measure(d, detail, detail_font)
    d.text(((W - dw) / 2, 815), detail, fill=(75, 85, 99), font=detail_font)

    # Footer brand
    brand_font = _font(36, bold=True)
    d.text((80, H - 110), "ShowUp", fill=BRAND_DARK, font=brand_font)
    d.text((215, H - 110), ".ai", fill=BRAND_ORANGE, font=brand_font)
    foot_font = _font(22, bold=False)
    d.text((80, H - 70), "AI-orchestrated webinar attendance booster", fill=(107, 114, 128), font=foot_font)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
