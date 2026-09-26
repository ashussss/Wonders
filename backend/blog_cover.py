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
    import re as _re
    k = " " + _re.sub(r"[^a-z0-9]+", " ", (keyword or "").lower()) + " "
    has = lambda *ws: any(f" {w} " in k or f" {w}s " in k for w in ws)
    if has("sms", "whatsapp", "text"):
        return "MESSAGING"
    if has("email", "newsletter", "inbox"):
        return "EMAIL REMINDERS"
    if has("linkedin", "social", "instagram", "facebook"):
        return "SOCIAL"
    if has("follow", "replay"):
        return "FOLLOW-UP"
    if has("strategy", "marketing", "promotion", "promote", "checklist", "funnel", "lead"):
        return "STRATEGY"
    if has("zoom", "video", "teams", "live"):
        return "LIVE EVENTS"
    if has("time", "when", "schedule", "advance", "calendar"):
        return "TIMING"
    if has("rate", "average", "benchmark", "ratio", "statistic", "tracking", "data"):
        return "ATTENDANCE DATA"
    if has("software", "tool", "automation", "automated", "features", "showupai"):
        return "TOOLS"
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


def _motif_phone(d, t, box):
    x0, y0, x1, y1 = box
    pw, ph = 210, 360
    px, py = (x0 + x1) // 2 - pw // 2, (y0 + y1) // 2 - ph // 2
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=34, fill=_hex(t["fg"]))
    d.rounded_rectangle([px + 12, py + 40, px + pw - 12, py + ph - 40], radius=18, fill=_hex(t["bg"]))
    d.rounded_rectangle([px + pw // 2 - 30, py + 16, px + pw // 2 + 30, py + 24], radius=4, fill=_hex(t["bg"]))
    bubbles = [(0, 60, 150, "a"), (1, 118, 120, "s"), (0, 176, 160, "a"), (1, 234, 100, "s")]
    for side, top, w, kind in bubbles:
        bx = px + 26 if side == 0 else px + pw - 26 - w
        col = _hex(t["accent"]) if kind == "a" else _hex(t["soft"])
        d.rounded_rectangle([bx, py + top, bx + w, py + top + 42], radius=16, fill=col)
    d.ellipse([px + pw - 20, py - 18, px + pw + 26, py + 28], fill=_hex(t["accent"]))


def _motif_envelope(d, t, box):
    x0, y0, x1, y1 = box
    ew, eh = 330, 220
    ex, ey = (x0 + x1) // 2 - ew // 2, (y0 + y1) // 2 - eh // 2 + 20
    # letter peeking out
    d.rounded_rectangle([ex + 30, ey - 70, ex + ew - 30, ey + 60], radius=12, fill=_hex(t["fg"]))
    for i in range(3):
        d.rounded_rectangle([ex + 60, ey - 44 + i * 26, ex + ew - 60 - (i * 40), ey - 32 + i * 26], radius=6, fill=_hex(t["soft"]))
    d.rounded_rectangle([ex, ey, ex + ew, ey + eh], radius=18, fill=_hex(t["accent"]))
    d.polygon([(ex, ey + 8), (ex + ew // 2, ey + eh // 2 + 10), (ex + ew, ey + 8)], fill=_hex(t["soft"]))
    d.ellipse([ex + ew - 34, ey - 34, ex + ew + 22, ey + 22], fill=_hex(t["fg"]))


def _motif_video(d, t, box):
    x0, y0, x1, y1 = box
    cols, rows, gap = 3, 3, 14
    cw = (x1 - x0 - gap * (cols - 1)) // cols
    ch = int(cw * 0.72)
    top = (y0 + y1) // 2 - (rows * ch + gap * (rows - 1)) // 2
    for r in range(rows):
        for c in range(cols):
            cx0, cy0 = x0 + c * (cw + gap), top + r * (ch + gap)
            live = (r, c) == (1, 1)
            d.rounded_rectangle([cx0, cy0, cx0 + cw, cy0 + ch], radius=14,
                                fill=_hex(t["accent"] if live else t["soft"]))
            hx, hy = cx0 + cw // 2, cy0 + ch // 2 - 6
            col = _hex("#FFFFFF") if live else _hex(t["muted"], 200)
            d.ellipse([hx - 14, hy - 14, hx + 14, hy + 14], fill=col)
            d.pieslice([hx - 26, hy + 12, hx + 26, hy + 52], 180, 360, fill=col)


def _motif_funnel(d, t, box):
    x0, y0, x1, y1 = box
    cx = (x0 + x1) // 2
    widths = [320, 250, 180, 110]
    y = y0 + 30
    for i, w in enumerate(widths):
        nxt = widths[i + 1] if i + 1 < len(widths) else w - 50
        col = _hex(t["accent"]) if i == len(widths) - 1 else _hex(t["soft"])
        d.polygon([(cx - w // 2, y), (cx + w // 2, y), (cx + nxt // 2, y + 70), (cx - nxt // 2, y + 70)], fill=col)
        y += 82
    for i in range(5):
        d.ellipse([cx - 90 + i * 40, y0 - 8, cx - 70 + i * 40, y0 + 12], fill=_hex(t["fg"]))


MOTIFS = [_motif_bars, _motif_rings, _motif_calendar, _motif_seats]
TOPIC_MOTIFS = [
    (("sms", "whatsapp", "text message"), _motif_phone),
    (("email", "newsletter", "inbox", "follow up", "follow-up"), _motif_envelope),
    (("zoom", "video", "live", "teams", "on demand", "on-demand"), _motif_video),
    (("strategy", "funnel", "registration", "promot", "marketing", "lead"), _motif_funnel),
    (("time", "when", "calendar", "advance", "schedule"), _motif_calendar),
    (("reminder", "notification", "how many"), _motif_rings),
    (("rate", "average", "benchmark", "statistic", "tracking", "ratio", "software"), _motif_bars),
    (("no-show", "no show", "attend", "drop off", "empty"), _motif_seats),
]


def motif_for(keyword: str, slug: str):
    k = f"{keyword} {slug}".lower().replace("-", " ")
    for words, fn in TOPIC_MOTIFS:
        if any(w.replace("-", " ") in k for w in words):
            return fn
    h = int(hashlib.md5((slug or keyword).encode()).hexdigest(), 16)
    return MOTIFS[(h // 7) % len(MOTIFS)]


def _paste_art(img, art_bytes, t, x0=640):
    """Right-hand AI illustration, cover-cropped, faded into the background on its left edge."""
    art = Image.open(io.BytesIO(art_bytes)).convert("RGBA")
    tw, th = W - x0, H
    scale = max(tw / art.width, th / art.height)
    art = art.resize((int(art.width * scale) + 1, int(art.height * scale) + 1), Image.LANCZOS)
    left = (art.width - tw) // 2
    top = (art.height - th) // 2
    art = art.crop((left, top, left + tw, top + th))
    mask = Image.new("L", (tw, th), 255)
    md = ImageDraw.Draw(mask)
    fade = 170
    for x in range(fade):
        md.line([(x, 0), (x, th)], fill=int(255 * (x / fade) ** 1.3))
    img.paste(art, (x0, 0), mask)
    return img


def render_cover(title: str, slug: str, keyword: str = "", art: bytes = None) -> bytes:
    h = int(hashlib.md5((slug or title).encode()).hexdigest(), 16)
    t = THEMES[h % len(THEMES)]
    motif = motif_for(keyword, slug)

    img = Image.new("RGBA", (W, H), _hex(t["bg"]))
    if art:
        try:
            img = _paste_art(img, art, t)
        except Exception:
            art = None

    if not art:
        # soft glow behind the illustration
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([700, 60, 1260, 620], fill=_hex(t["glow"], 70))
        img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(90)))

    d = ImageDraw.Draw(img)

    if not art:
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
    if art:
        d.text((ai_x + int(d.textlength("AI", font=wf)) + 22, fy + 21), "·  " + url, font=uf, fill=_hex(t["muted"]), anchor="lm")
    else:
        d.text((W - PAD, fy + 20), url, font=uf, fill=_hex(t["muted"]), anchor="rm")

    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()
