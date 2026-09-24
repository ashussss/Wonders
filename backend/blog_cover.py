"""Branded 1200x630 cover images for blog posts (card thumbnail, post hero, og:image).

Pure Pillow, no AI call: fast, free, consistent brand. The theme and motif are picked from the
slug so every post keeps the same look each time it is regenerated.
"""

import hashlib
import io
import os
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 630
PAD = 72
FONT_DIR = "/tmp/showup_fonts"
FONTS = {
    "bold": "Poppins-Bold.ttf",
    "semi": "Poppins-SemiBold.ttf",
    "reg": "Poppins-Regular.ttf",
}
FALLBACKS = {
    "bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "semi": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "reg": ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}

THEMES = [
    {"bg": "#0F0F12", "fg": "#FFFFFF", "muted": "#A1A1AA", "accent": "#EA580C", "soft": "#27272A", "glow": "#EA580C"},
    {"bg": "#FAF6EF", "fg": "#111111", "muted": "#6B6B6B", "accent": "#EA580C", "soft": "#EDE6D8", "glow": "#FDBA74"},
    {"bg": "#0B1B34", "fg": "#FFFFFF", "muted": "#9FB0C8", "accent": "#F59E0B", "soft": "#1A2F52", "glow": "#3B82F6"},
    {"bg": "#EA580C", "fg": "#FFFFFF", "muted": "#FFE4D1", "accent": "#111111", "soft": "#F97316", "glow": "#FDBA74"},
]


def _ensure_fonts():
    os.makedirs(FONT_DIR, exist_ok=True)
    for name in FONTS.values():
        path = os.path.join(FONT_DIR, name)
        if not os.path.exists(path):
            try:
                url = f"https://github.com/google/fonts/raw/main/ofl/poppins/{name}"
                urllib.request.urlretrieve(url, path)
            except Exception:
                pass


def _font(kind: str, size: int):
    _ensure_fonts()
    for path in [os.path.join(FONT_DIR, FONTS[kind])] + FALLBACKS[kind]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _hex(c, alpha=255):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def _tag_for(keyword: str) -> str:
    k = (keyword or "").lower()
    if "email" in k:
        return "EMAIL REMINDERS"
    if "linkedin" in k:
        return "LINKEDIN"
    if "whatsapp" in k or "sms" in k:
        return "MESSAGING"
    if "time" in k or "when" in k:
        return "TIMING"
    if "rate" in k or "no-show" in k or "no show" in k or "average" in k or "ratio" in k:
        return "ATTENDANCE DATA"
    if "follow" in k:
        return "FOLLOW-UP"
    if "promot" in k or "marketing" in k or "checklist" in k:
        return "PROMOTION"
    return "WEBINAR ATTENDANCE"


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_title(draw, title, max_w, max_h):
    for size in range(66, 38, -2):
        f = _font("bold", size)
        lines = _wrap(draw, title, f, max_w)
        line_h = int(size * 1.18)
        if len(lines) <= 4 and len(lines) * line_h <= max_h:
            return f, lines, line_h
    f = _font("bold", 40)
    lines = _wrap(draw, title, f, max_w)[:4]
    if lines:
        lines[-1] = lines[-1].rstrip(".,") + "…"
    return f, lines, int(40 * 1.18)


_LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")


def _logo(size: int):
    try:
        return Image.open(_LOGO_PATH).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:  # fallback: orange tile with a bolt
        tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        g = ImageDraw.Draw(tile)
        g.rounded_rectangle([0, 0, size, size], radius=size // 4, fill=_hex("#EA580C"))
        g.polygon([(size * .56, size * .2), (size * .38, size * .52), (size * .5, size * .52), (size * .42, size * .8),
                   (size * .64, size * .44), (size * .52, size * .44)], fill=_hex("#FFFFFF"))
        return tile


def _logo_inverted(size: int):
    """White tile with the logo's bolt in orange."""
    src = _logo(size)
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 4, fill=_hex("#FFFFFF"))
    px_src, px = src.load(), tile.load()
    for y in range(size):
        for x in range(size):
            r, g, b, a = px_src[x, y]
            if a > 0 and r > 200 and g > 200 and b > 200:  # white bolt pixels -> orange
                px[x, y] = (234, 88, 12, 255)
    return tile


# ---------- motifs (right-hand illustration area) ----------

def _motif_bars(d, t, box):
    x0, y0, x1, y1 = box
    n, gap = 6, 18
    bw = (x1 - x0 - gap * (n - 1)) // n
    heights = [0.28, 0.4, 0.36, 0.55, 0.72, 0.95]
    for i, h in enumerate(heights):
        bx = x0 + i * (bw + gap)
        by = y1 - int((y1 - y0) * h)
        color = _hex(t["accent"]) if i == n - 1 else _hex(t["soft"])
        d.rounded_rectangle([bx, by, bx + bw, y1], radius=14, fill=color)
    # trend line
    pts = [(x0 + i * (bw + gap) + bw // 2, y1 - int((y1 - y0) * h) - 26) for i, h in enumerate(heights)]
    d.line(pts, fill=_hex(t["fg"], 200), width=5, joint="curve")
    for p in pts:
        d.ellipse([p[0] - 8, p[1] - 8, p[0] + 8, p[1] + 8], fill=_hex(t["bg"]), outline=_hex(t["fg"], 230), width=4)


def _motif_rings(d, t, box):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    for i, r in enumerate([165, 125, 88]):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=_hex(t["soft"] if i else t["muted"], 255), width=10 if i else 6)
    # bell
    d.rounded_rectangle([cx - 46, cy - 50, cx + 46, cy + 34], radius=40, fill=_hex(t["accent"]))
    d.rectangle([cx - 46, cy + 4, cx + 46, cy + 34], fill=_hex(t["accent"]))
    d.rounded_rectangle([cx - 62, cy + 26, cx + 62, cy + 44], radius=9, fill=_hex(t["accent"]))
    d.ellipse([cx - 14, cy + 46, cx + 14, cy + 70], fill=_hex(t["accent"]))
    d.ellipse([cx + 44, cy - 84, cx + 76, cy - 52], fill=_hex(t["accent"]))


def _motif_calendar(d, t, box):
    x0, y0, x1, y1 = box
    d.rounded_rectangle([x0, y0 + 20, x1, y1], radius=26, fill=_hex(t["soft"]))
    d.rounded_rectangle([x0, y0 + 20, x1, y0 + 92], radius=26, fill=_hex(t["accent"]))
    d.rectangle([x0, y0 + 66, x1, y0 + 92], fill=_hex(t["accent"]))
    for k in (0.28, 0.72):
        px = x0 + int((x1 - x0) * k)
        d.rounded_rectangle([px - 9, y0, px + 9, y0 + 48], radius=9, fill=_hex(t["fg"]))
    cols, rows = 5, 3
    cw = (x1 - x0 - 60) // cols
    ch = (y1 - y0 - 150) // rows
    for r in range(rows):
        for c in range(cols):
            cx = x0 + 30 + c * cw + cw // 2
            cy = y0 + 120 + r * ch + ch // 2
            if (r, c) == (1, 3):
                d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=_hex(t["accent"]))
                d.line([(cx - 13, cy), (cx - 3, cy + 11), (cx + 15, cy - 11)], fill=_hex("#FFFFFF"), width=6)
            else:
                d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=_hex(t["muted"], 150))


def _motif_seats(d, t, box):
    x0, y0, x1, y1 = box
    cols, rows = 7, 6
    step = min((x1 - x0) // cols, (y1 - y0) // rows)
    filled = {(r, c) for r in range(rows) for c in range(cols) if (r * 3 + c * 5) % 7 < 5}
    for r in range(rows):
        for c in range(cols):
            cx = x0 + c * step + step // 2
            cy = y0 + r * step + step // 2
            rad = step // 2 - 8
            if (r, c) in filled:
                d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=_hex(t["accent"] if (r + c) % 4 else t["fg"]))
            else:
                d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=_hex(t["muted"], 170), width=4)


MOTIFS = [_motif_bars, _motif_rings, _motif_calendar, _motif_seats]


def render_cover(title: str, slug: str, keyword: str = "") -> bytes:
    h = int(hashlib.md5((slug or title).encode()).hexdigest(), 16)
    t = THEMES[h % len(THEMES)]
    motif = MOTIFS[(h // 7) % len(MOTIFS)]

    img = Image.new("RGBA", (W, H), _hex(t["bg"]))

    # soft glow behind the illustration
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([700, 60, 1260, 620], fill=_hex(t["glow"], 70))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(90)))

    d = ImageDraw.Draw(img)

    # illustration
    motif(d, t, (790, 150, 1130, 500))

    # tag pill
    tag = _tag_for(keyword or title)
    tf = _font("semi", 18)
    tw = int(d.textlength(tag, font=tf))
    d.rounded_rectangle([PAD, PAD, PAD + tw + 40, PAD + 42], radius=21, outline=_hex(t["accent"]), width=2)
    d.text((PAD + 20, PAD + 9), tag, font=tf, fill=_hex(t["accent"]))

    # title
    top, bottom = PAD + 80, H - PAD - 70
    f, lines, lh = _fit_title(d, title.strip(), 660, bottom - top)
    y = top + max(0, (bottom - top - lh * len(lines)) // 2) - 10
    for line in lines:
        d.text((PAD, y), line, font=f, fill=_hex(t["fg"]))
        y += lh

    # footer: real ShowUpAI logo + "ShowUp" + accent "AI" wordmark, url
    fy = H - PAD - 40
    if t["bg"].upper() == "#EA580C":  # orange theme: inverted logo (white tile, orange bolt) so it stays visible
        img.alpha_composite(_logo_inverted(40), (PAD, fy))
    else:
        img.alpha_composite(_logo(40), (PAD, fy))
    d = ImageDraw.Draw(img)
    wf = _font("bold", 26)
    d.text((PAD + 54, fy + 20), "ShowUp", font=wf, fill=_hex(t["fg"]), anchor="lm")
    ai_x = PAD + 54 + int(d.textlength("ShowUp", font=wf))
    ai_col = "#FFFFFF" if t["bg"].upper() == "#EA580C" else t["accent"]
    d.text((ai_x, fy + 20), "AI", font=wf, fill=_hex(ai_col if ai_col != "#111111" else "#FFFFFF"), anchor="lm")
    uf = _font("reg", 20)
    url = "showupai.live/blog"
    d.text((W - PAD, fy + 20), url, font=uf, fill=_hex(t["muted"]), anchor="rm")

    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()
