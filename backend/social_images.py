"""Branded social images for ShowUpAI's own channels (LinkedIn, Facebook, Instagram).

- stat card      1080x1080  one sourced number + label + source
- carousel       1080x1350  hook slide, 3-6 tip slides, CTA slide (Instagram carousel / LinkedIn multi-image)
- infographic    1080x1350  title + 4-6 numbered rows
All JPEG (Instagram's Graph API only accepts JPEG).
"""

import hashlib
import io

from PIL import Image, ImageDraw, ImageFilter

from blog_cover import THEMES, _font, _hex, _logo, _logo_inverted, _wrap

BRAND_URL = "showupai.live"


def _theme(seed: str, offset: int = 0):
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    return THEMES[(h + offset) % len(THEMES)]


def _canvas(t, w, h, glow_box=None):
    img = Image.new("RGBA", (w, h), _hex(t["bg"]))
    if glow_box:
        g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse(glow_box, fill=_hex(t["glow"], 70))
        img = Image.alpha_composite(img, g.filter(ImageFilter.GaussianBlur(110)))
    return img


def _brand(img, t, x, y, size=44):
    orange = t["bg"].upper() == "#EA580C"
    img.alpha_composite(_logo_inverted(size) if orange else _logo(size), (x, y))
    d = ImageDraw.Draw(img)
    f = _font("bold", int(size * 0.66))
    d.text((x + size + 14, y + size // 2), "ShowUp", font=f, fill=_hex(t["fg"]), anchor="lm")
    ax = x + size + 14 + int(d.textlength("ShowUp", font=f))
    d.text((ax, y + size // 2), "AI", font=f, fill=_hex("#FFFFFF" if orange else (t["accent"] if t["accent"] != "#111111" else "#FFFFFF")), anchor="lm")
    return d


def _text_block(d, text, font, x, y, max_w, fill, line_h, max_lines=None):
    lines = _wrap(d, text, font, max_w)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;:") + "…"
    for ln in lines:
        d.text((x, y), ln, font=font, fill=fill)
        y += line_h
    return y


def _fit(d, text, kind, max_w, max_h, start, stop, max_lines=5, lh=1.15):
    for size in range(start, stop - 1, -2):
        f = _font(kind, size)
        lines = _wrap(d, text, f, max_w)
        if len(lines) <= max_lines and len(lines) * int(size * lh) <= max_h:
            return f, int(size * lh)
    return _font(kind, stop), int(stop * lh)


def _jpeg(img) -> bytes:
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=90, optimize=True, progressive=True)
    return out.getvalue()


def render_stat_card(number: str, label: str, source: str, seed: str = "") -> bytes:
    W = H = 1080
    t = _theme(seed or number + label)
    img = _canvas(t, W, H, (380, 120, 1180, 920))
    d = ImageDraw.Draw(img)
    pad = 90
    tf = _font("semi", 26)
    tag = "WEBINAR DATA"
    tw = int(d.textlength(tag, font=tf))
    d.rounded_rectangle([pad, pad, pad + tw + 44, pad + 50], radius=25, outline=_hex(t["accent"]), width=3)
    d.text((pad + 22, pad + 11), tag, font=tf, fill=_hex(t["accent"]))
    nf, _ = _fit(d, number, "bold", W - 2 * pad, 300, 260, 120, max_lines=1)
    d.text((pad, 250), number, font=nf, fill=_hex(t["accent"] if t["accent"] != "#111111" else t["fg"]))
    lf, lh = _fit(d, label, "semi", W - 2 * pad, 330, 52, 34, max_lines=5, lh=1.25)
    y = _text_block(d, label, lf, pad, 590, W - 2 * pad, _hex(t["fg"]), lh)
    d.text((pad, max(y + 24, 880)), f"Source: {source}", font=_font("reg", 24), fill=_hex(t["muted"]))
    _brand(img, t, pad, H - pad - 40, 44)
    d = ImageDraw.Draw(img)
    d.text((W - pad, H - pad - 18), BRAND_URL, font=_font("reg", 24), fill=_hex(t["muted"]), anchor="rm")
    return _jpeg(img)


def render_carousel(hook: str, slides: list, cta: str, seed: str = "") -> list:
    """slides: [{"title": str, "body": str}] (3-6). Returns list of JPEG bytes: hook, slides..., CTA."""
    W, H = 1080, 1350
    t = _theme(seed or hook)
    pad = 90
    total = len(slides) + 2
    pages = []

    # hook slide
    img = _canvas(t, W, H, (300, 200, 1250, 1150))
    d = ImageDraw.Draw(img)
    d.text((pad, pad + 10), f"1/{total}", font=_font("semi", 26), fill=_hex(t["muted"]))
    hf, hl = _fit(d, hook, "bold", W - 2 * pad, 700, 96, 56, max_lines=6, lh=1.12)
    lines = _wrap(d, hook, hf, W - 2 * pad)
    y = (H - hl * len(lines)) // 2 - 40
    _text_block(d, hook, hf, pad, y, W - 2 * pad, _hex(t["fg"]), hl)
    sc = _hex(t["accent"] if t["accent"] != "#111111" else t["fg"])
    sf = _font("semi", 34)
    d.text((pad, H - pad - 110), "Swipe", font=sf, fill=sc)
    ax = pad + int(d.textlength("Swipe", font=sf)) + 16
    ay = H - pad - 110 + 24
    d.line([(ax, ay), (ax + 44, ay)], fill=sc, width=5)
    d.polygon([(ax + 44, ay - 11), (ax + 60, ay), (ax + 44, ay + 11)], fill=sc)
    _brand(img, t, pad, H - pad - 44, 44)
    pages.append(_jpeg(img))

    # tip slides
    for i, s in enumerate(slides, start=2):
        img = _canvas(t, W, H)
        d = ImageDraw.Draw(img)
        d.text((pad, pad + 10), f"{i}/{total}", font=_font("semi", 26), fill=_hex(t["muted"]))
        num = str(i - 1).zfill(2)
        d.text((pad, 200), num, font=_font("bold", 150), fill=_hex(t["accent"] if t["accent"] != "#111111" else t["fg"]))
        tf, tl = _fit(d, s.get("title", ""), "bold", W - 2 * pad, 300, 64, 42, max_lines=4, lh=1.15)
        y = _text_block(d, s.get("title", ""), tf, pad, 420, W - 2 * pad, _hex(t["fg"]), tl)
        bf, bl = _fit(d, s.get("body", ""), "reg", W - 2 * pad, H - y - 300, 40, 28, max_lines=9, lh=1.4)
        _text_block(d, s.get("body", ""), bf, pad, y + 40, W - 2 * pad, _hex(t["muted"] if t["bg"] != "#FAF6EF" else "#333333"), bl)
        _brand(img, t, pad, H - pad - 44, 44)
        pages.append(_jpeg(img))

    # CTA slide
    img = _canvas(t, W, H, (200, 300, 1150, 1250))
    d = ImageDraw.Draw(img)
    d.text((pad, pad + 10), f"{total}/{total}", font=_font("semi", 26), fill=_hex(t["muted"]))
    cf, cl = _fit(d, cta, "bold", W - 2 * pad, 520, 76, 48, max_lines=6, lh=1.15)
    _text_block(d, cta, cf, pad, 420, W - 2 * pad, _hex(t["fg"]), cl)
    d.text((pad, 1000), BRAND_URL, font=_font("semi", 40), fill=_hex(t["accent"] if t["accent"] != "#111111" else t["fg"]))
    _brand(img, t, pad, H - pad - 44, 44)
    pages.append(_jpeg(img))
    return pages


def render_infographic(title: str, rows: list, seed: str = "") -> bytes:
    """rows: list of short strings (4-6)."""
    W, H = 1080, 1350
    t = _theme(seed or title, offset=1)
    img = _canvas(t, W, H, (500, -100, 1300, 700))
    d = ImageDraw.Draw(img)
    pad = 80
    tf, tl = _fit(d, title, "bold", W - 2 * pad, 260, 66, 44, max_lines=4, lh=1.12)
    y = _text_block(d, title, tf, pad, pad + 20, W - 2 * pad, _hex(t["fg"]), tl) + 40
    rows = rows[:6]
    avail = H - y - 170
    row_h = max(120, avail // max(1, len(rows)))
    for i, r in enumerate(rows, start=1):
        top = y + (i - 1) * row_h
        d.rounded_rectangle([pad, top, W - pad, top + row_h - 20], radius=24, fill=_hex(t["soft"]))
        cx, cy = pad + 60, top + (row_h - 20) // 2
        d.ellipse([cx - 34, cy - 34, cx + 34, cy + 34], fill=_hex(t["accent"]))
        d.text((cx, cy), str(i), font=_font("bold", 34), fill=_hex("#FFFFFF" if t["accent"] != "#FFFFFF" else "#EA580C"), anchor="mm")
        rf, rl = _fit(d, r, "semi", W - 2 * pad - 150, row_h - 50, 36, 24, max_lines=3, lh=1.25)
        lines = _wrap(d, r, rf, W - 2 * pad - 150)[:3]
        ty = cy - (rl * len(lines)) // 2
        for ln in lines:
            d.text((pad + 125, ty), ln, font=rf, fill=_hex(t["fg"]))
            ty += rl
    _brand(img, t, pad, H - pad - 44, 44)
    d = ImageDraw.Draw(img)
    d.text((W - pad, H - pad - 22), BRAND_URL, font=_font("reg", 24), fill=_hex(t["muted"]), anchor="rm")
    return _jpeg(img)


def cover_jpeg(png_bytes: bytes) -> bytes:
    return _jpeg(Image.open(io.BytesIO(png_bytes)).convert("RGBA"))
