"""Growth Engine design kit: the look of every social graphic.

Editorial, typographic brand graphics (no photos, no illustrations, no AI art):
Outfit type (the product's brand face, vendored in backend/assets/fonts), four
high-contrast brand themes, highlighted key words, geometric accents (rings, dot
grids, rules), soft card shadows, a carousel progress bar, and the ShowUpAI logo
plus showupai.live on every image.

Key words are marked in the AI's visual text with *asterisks*. They are drawn as a
marker highlight on light themes and in the accent colour on dark ones. With no
asterisks, numbers (40%, 3x, 15 minutes) are highlighted automatically.

Every renderer returns JPEG bytes (Instagram's Graph API only accepts JPEG); the
carousel returns a list of them. Portrait 1080x1350 everywhere: it takes the most
feed space on LinkedIn and Instagram.
"""

import hashlib
import io
import os
import re
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import blog_cover

W, H = 1080, 1350
PAD = 84
BRAND_URL = "showupai.live"

_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")
_WEIGHTS = {"reg": 400, "med": 500, "semi": 600, "bold": 700, "xbold": 800, "black": 900}
_FALLBACK = {"reg": "reg", "med": "reg", "semi": "semi", "bold": "bold", "xbold": "bold", "black": "bold"}
_font_cache: dict = {}


def font(weight: str, size: int):
    key = (weight, size)
    if key not in _font_cache:
        path = os.path.join(_FONT_DIR, f"outfit-latin-{_WEIGHTS[weight]}-normal.woff")
        try:
            _font_cache[key] = ImageFont.truetype(path, size)
        except Exception:                                        # noqa: BLE001
            _font_cache[key] = blog_cover._font(_FALLBACK[weight], size)
    return _font_cache[key]


def rgb(c: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha)


# em: "mark" = highlighter block behind the words, "color" = words in the accent colour.
THEMES = [
    {"name": "ink", "bg": "#0E0E11", "fg": "#FFFFFF", "muted": "#A6A6B0", "accent": "#FF6B1A",
     "on_accent": "#0E0E11", "card": "#1B1B22", "line": "#2C2C36", "em": "color",
     "em_fill": "#FF6B1A", "em_text": "#FF6B1A", "dark": True},
    {"name": "cream", "bg": "#F6F0E6", "fg": "#141414", "muted": "#5E584F", "accent": "#EA580C",
     "on_accent": "#FFFFFF", "card": "#FFFFFF", "line": "#E2D6C3", "em": "mark",
     "em_fill": "#FFC9A3", "em_text": "#141414", "dark": False},
    {"name": "navy", "bg": "#0A1630", "fg": "#FFFFFF", "muted": "#A9B7CE", "accent": "#FFB020",
     "on_accent": "#0A1630", "card": "#14264B", "line": "#22375F", "em": "color",
     "em_fill": "#FFB020", "em_text": "#FFB020", "dark": True},
    {"name": "orange", "bg": "#EA580C", "fg": "#FFFFFF", "muted": "#FFE2CF", "accent": "#141414",
     "on_accent": "#FFFFFF", "card": "#F07436", "line": "#F49A6A", "em": "mark",
     "em_fill": "#141414", "em_text": "#FFFFFF", "dark": True},
]
_BY_NAME = {t["name"]: t for t in THEMES}


def theme(seed: str, offset: int = 0) -> dict:
    h = int(hashlib.md5((seed or "x").encode()).hexdigest(), 16)
    return THEMES[(h + offset) % len(THEMES)]


def contrast_theme(t: dict) -> dict:
    """The theme a carousel's closing slide switches to, so it pops."""
    return _BY_NAME["ink"] if t["name"] == "orange" else _BY_NAME["orange"]


# ── rich text: *emphasis* ────────────────────────────────────────────────────

_NUM = re.compile(r"\d")


def tokens(text: str, auto: bool = True) -> List[Tuple[str, bool]]:
    """Split text into (word, emphasised) pairs. *a phrase* marks emphasis."""
    text = (text or "").strip()
    out: List[Tuple[str, bool]] = []
    marked = text.count("*") >= 2
    on = False
    for part in re.split(r"(\*)", text):
        if part == "*":
            on = not on if marked else on
            continue
        for w in part.split():
            out.append((w, on))
    if not marked and auto:
        out = [(w, bool(_NUM.search(w))) for w, _ in out]
    return out


def plain(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("*", "")).strip()


def wrap(d, toks, f, max_w) -> List[List[Tuple[str, bool]]]:
    lines: List[List[Tuple[str, bool]]] = []
    cur: List[Tuple[str, bool]] = []
    for tok in toks:
        trial = " ".join(w for w, _ in cur + [tok])
        if cur and d.textlength(trial, font=f) > max_w:
            lines.append(cur)
            cur = [tok]
        else:
            cur.append(tok)
    if cur:
        lines.append(cur)
    return lines


def fit(d, text, weight, max_w, max_h, start, stop, max_lines=6, lh=1.12, auto=True):
    toks = tokens(text, auto)
    for size in range(start, stop - 1, -2):
        f = font(weight, size)
        lines = wrap(d, toks, f, max_w)
        if len(lines) <= max_lines and len(lines) * int(size * lh) <= max_h:
            return f, int(size * lh), lines
    f = font(weight, stop)
    lines = wrap(d, toks, f, max_w)[:max_lines]
    return f, int(stop * lh), lines


def draw_rich(img, lines, f, x, y, line_h, t, fill=None, center_w: Optional[int] = None) -> int:
    """Draw wrapped (word, emph) lines. Returns the y after the last line."""
    d = ImageDraw.Draw(img)
    space = d.textlength(" ", font=f)
    size = f.size
    base = rgb(fill or t["fg"])
    for line in lines:
        widths = [d.textlength(w, font=f) for w, _ in line]
        total = sum(widths) + space * (len(line) - 1)
        cx = x + ((center_w - total) / 2 if center_w else 0)
        # highlighter blocks first, one per run of emphasised words
        if t["em"] == "mark":
            px, run = cx, None
            for (w, em), wd in zip(line, widths):
                if em:
                    run = [px, px + wd] if run is None else [run[0], px + wd]
                elif run:
                    d.rounded_rectangle([run[0] - 10, y + size * 0.10, run[1] + 10, y + size * 1.08],
                                        radius=10, fill=rgb(t["em_fill"]))
                    run = None
                px += wd + space
            if run:
                d.rounded_rectangle([run[0] - 10, y + size * 0.10, run[1] + 10, y + size * 1.08],
                                    radius=10, fill=rgb(t["em_fill"]))
        px = cx
        for (w, em), wd in zip(line, widths):
            d.text((px, y), w, font=f, fill=rgb(t["em_text"]) if em else base)
            px += wd + space
        y += line_h
    return y


# ── decoration ───────────────────────────────────────────────────────────────

def canvas(t: dict, w: int = W, h: int = H):
    return Image.new("RGBA", (w, h), rgb(t["bg"]))


def ring(img, cx, cy, r, width, color, alpha=255):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx - r, cy - r, cx + r, cy + r], outline=rgb(color, alpha), width=width)
    img.alpha_composite(layer)


def accent_ring(img, t, cx, cy, r, width):
    """Geometric accent ring; on the orange theme it is a faint white line instead."""
    if t["name"] == "orange":
        ring(img, cx, cy, r, width, "#FFFFFF", 60)
    else:
        ring(img, cx, cy, r, width, t["accent"])


def dots(img, x0, y0, cols, rows, gap, r, color, alpha=255):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(cols):
        for j in range(rows):
            cx, cy = x0 + i * gap, y0 + j * gap
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgb(color, alpha))
    img.alpha_composite(layer)


def card(img, box, t, fill=None, radius=28, shadow=True):
    """Rounded card. Light themes get a soft drop shadow, dark ones a hairline border."""
    x0, y0, x1, y1 = [int(v) for v in box]
    if shadow and not t["dark"]:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([x0, y0 + 14, x1, y1 + 14], radius=radius, fill=(60, 35, 10, 46))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=rgb(fill or t["card"]),
                        outline=None if not t["dark"] or fill else rgb(t["line"]), width=2)


def pill(d, x, y, text, t, solid=False, size=26, color=None) -> int:
    f = font("semi", size)
    tw = d.textlength(text, font=f)
    h = int(size * 1.9)
    c = color or t["accent"]
    if solid:
        d.rounded_rectangle([x, y, x + tw + 2 * size, y + h], radius=h // 2, fill=rgb(c))
        d.text((x + size, y + h / 2), text, font=f, fill=rgb(t["on_accent"] if not color else t["bg"]), anchor="lm")
    else:
        d.rounded_rectangle([x, y, x + tw + 2 * size, y + h], radius=h // 2, outline=rgb(c), width=3)
        d.text((x + size, y + h / 2), text, font=f, fill=rgb(c), anchor="lm")
    return int(tw + 2 * size)


def arrow(d, x, y, length, color, width=5):
    d.line([(x, y), (x + length, y)], fill=rgb(color), width=width)
    d.polygon([(x + length - 2, y - 11), (x + length + 14, y), (x + length - 2, y + 11)], fill=rgb(color))


def check(d, cx, cy, s, color, width=7):
    d.line([(cx - s * 0.45, cy), (cx - s * 0.12, cy + s * 0.32), (cx + s * 0.48, cy - s * 0.34)],
           fill=rgb(color), width=width, joint="curve")


def cross(d, cx, cy, s, color, width=6):
    k = s * 0.32
    d.line([(cx - k, cy - k), (cx + k, cy + k)], fill=rgb(color), width=width)
    d.line([(cx - k, cy + k), (cx + k, cy - k)], fill=rgb(color), width=width)


def footer(img, t, w=W, h=H, pad=PAD, site=True):
    """Logo + wordmark bottom-left, showupai.live bottom-right."""
    size = 48
    y = h - pad - size
    orange = t["name"] == "orange"
    img.alpha_composite(blog_cover._logo_inverted(size) if orange else blog_cover._logo(size), (pad, y))
    d = ImageDraw.Draw(img)
    f = font("bold", 32)
    d.text((pad + size + 14, y + size / 2), "ShowUp", font=f, fill=rgb(t["fg"]), anchor="lm")
    ax = pad + size + 14 + d.textlength("ShowUp", font=f)
    d.text((ax, y + size / 2), "AI", font=f, fill=rgb("#FFFFFF" if orange else (t["accent"] if t["dark"] or t["name"] == "cream" else t["fg"])), anchor="lm")
    if site:
        d.text((w - pad, y + size / 2), BRAND_URL, font=font("semi", 28), fill=rgb(t["muted"]), anchor="rm")


def progress(d, t, i, total, y, pad=PAD, w=W):
    """Segmented progress bar for carousels."""
    gap = 10
    seg = (w - 2 * pad - gap * (total - 1)) / total
    for k in range(total):
        x0 = pad + k * (seg + gap)
        d.rounded_rectangle([x0, y, x0 + seg, y + 8], radius=4,
                            fill=rgb(t["accent"] if k <= i else t["line"]))


def jpeg(img) -> bytes:
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=92, optimize=True, progressive=True, subsampling=0)
    return out.getvalue()


# ── formats ──────────────────────────────────────────────────────────────────

def carousel(hook: str, slides: Sequence[dict], cta: str, subtitle: str = "", tag: str = "",
             seed: str = "") -> List[bytes]:
    t = theme(seed or hook)
    slides = list(slides)[:6]
    total = len(slides) + 2
    pages: List[bytes] = []
    inner = W - 2 * PAD

    # cover
    img = canvas(t)
    accent_ring(img, t, W - 10, 40, 230, 32)
    d = ImageDraw.Draw(img)
    pill(d, PAD, PAD, (tag or "WEBINAR PLAYBOOK").upper(), t)
    top, limit = 300, H - PAD - 240          # headline + subtitle must end above the swipe button
    sub_h = 150 if subtitle else 0
    hf, hl, lines = fit(d, hook, "black", inner, limit - top - sub_h - 40, 124, 60, max_lines=6, lh=1.04)
    block = hl * len(lines) + (sub_h + 40 if subtitle else 0)
    y = top + max(0, (limit - top - block) // 2)
    y = draw_rich(img, lines, hf, PAD, y, hl, t)
    if subtitle:
        sf, sl, sl_lines = fit(d, subtitle, "med", inner - 40, sub_h, 42, 30, max_lines=3, lh=1.3, auto=False)
        draw_rich(img, sl_lines, sf, PAD, y + 36, sl, t, fill=t["muted"])
    d = ImageDraw.Draw(img)
    sw = pill(d, PAD, H - PAD - 200, "Swipe to read", t, solid=True, size=30)
    arrow(d, PAD + sw + 26, H - PAD - 200 + 28, 46, t["accent"], 6)
    progress(d, t, 0, total, H - PAD - 96)
    footer(img, t)
    pages.append(jpeg(img))

    # tips
    for i, s in enumerate(slides, start=1):
        img = canvas(t)
        d = ImageDraw.Draw(img)
        d.text((W - PAD, PAD + 24), f"{i + 1:02d} / {total:02d}", font=font("semi", 28),
               fill=rgb(t["muted"]), anchor="rm")
        nf = font("black", 230)
        d.text((PAD - 8, PAD - 40), f"{i:02d}", font=nf, fill=rgb(t["bg"]),
               stroke_width=4, stroke_fill=rgb(t["accent"]))
        tf, tl, tlines = fit(d, s.get("title", ""), "xbold", inner, 330, 78, 46, max_lines=4, lh=1.08)
        y = draw_rich(img, tlines, tf, PAD, 360, tl, t)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([PAD, y + 26, PAD + 96, y + 36], radius=5, fill=rgb(t["accent"]))
        body = s.get("body", "")
        if body:
            box_top = y + 80
            bf, bl, blines = fit(d, body, "reg", inner - 80, H - box_top - 330, 44, 30, max_lines=8, lh=1.38,
                                 auto=False)
            box_h = bl * len(blines) + 80
            card(img, [PAD, box_top, W - PAD, box_top + box_h], t)
            draw_rich(img, blines, bf, PAD + 40, box_top + 40, bl, t,
                      fill=t["fg"] if not t["dark"] else "#E8E8EE" if t["name"] != "orange" else "#FFFFFF")
        d = ImageDraw.Draw(img)
        if i < len(slides):
            sf = font("semi", 28)
            label = "Keep swiping"
            lw = d.textlength(label, font=sf)
            d.text((W - PAD - 70 - lw, H - PAD - 170), label, font=sf, fill=rgb(t["accent"]))
            arrow(d, W - PAD - 56, H - PAD - 152, 36, t["accent"], 5)
        progress(d, t, i, total, H - PAD - 96)
        footer(img, t)
        pages.append(jpeg(img))

    # closing slide, contrast theme
    c = contrast_theme(t)
    img = canvas(c)
    ring(img, W + 40, 60, 260, 36, c["fg"], 50)
    d = ImageDraw.Draw(img)
    pill(d, PAD, PAD, "YOUR TURN", c, color=c["fg"])
    cf, cl, clines = fit(d, cta or "Which of these will you try first? Tell me in the comments.",
                         "black", inner, 520, 96, 54, max_lines=6, lh=1.06)
    y = draw_rich(img, clines, cf, PAD, 300, cl, c)
    d = ImageDraw.Draw(img)
    x = PAD
    for word in ("Save", "Share", "Comment"):
        x += pill(d, x, y + 60, word, c, solid=True, size=30, color=c["fg"]) + 16
    d.text((PAD, H - PAD - 300), "More playbooks at", font=font("med", 34), fill=rgb(c["muted"]))
    d.text((PAD, H - PAD - 255), BRAND_URL, font=font("black", 76), fill=rgb(c["fg"]))
    progress(d, c, total - 1, total, H - PAD - 96)
    footer(img, c, site=False)
    pages.append(jpeg(img))
    return pages


def _list_page(title: str, rows: Sequence[str], seed: str, offset: int, tag: str, badge: str) -> bytes:
    t = theme(seed or title, offset)
    img = canvas(t)
    dots(img, W - PAD - 4 * 30, PAD + 10, 5, 3, 30, 4, t["muted"], 120)
    d = ImageDraw.Draw(img)
    pill(d, PAD, PAD, tag, t)
    tf, tl, tlines = fit(d, title, "black", W - 2 * PAD, 300, 84, 50, max_lines=4, lh=1.06)
    y = draw_rich(img, tlines, tf, PAD, PAD + 100, tl, t) + 44
    rows = [r for r in rows if r][:6]
    gap = 22
    avail = H - y - PAD - 120
    row_h = min(190, (avail - gap * (len(rows) - 1)) // max(1, len(rows)))
    for i, r in enumerate(rows, start=1):
        top = y + (i - 1) * (row_h + gap)
        card(img, [PAD, top, W - PAD, top + row_h], t, radius=24)
        d = ImageDraw.Draw(img)
        bx, by, bs = PAD + 28, top + (row_h - 72) // 2, 72
        d.rounded_rectangle([bx, by, bx + bs, by + bs], radius=20, fill=rgb(t["accent"]))
        if badge == "check":
            check(d, bx + bs / 2, by + bs / 2 + 2, 44, t["on_accent"], 8)
        else:
            d.text((bx + bs / 2, by + bs / 2), str(i), font=font("black", 40), fill=rgb(t["on_accent"]), anchor="mm")
        rf, rl, rlines = fit(d, r, "semi", W - 2 * PAD - 160, row_h - 30, 38, 26, max_lines=3, lh=1.2, auto=False)
        ty = top + (row_h - rl * len(rlines)) // 2 - 4
        draw_rich(img, rlines, rf, PAD + 130, ty, rl, t)
    footer(img, t)
    return jpeg(img)


def infographic(title: str, rows: Sequence[str], seed: str = "") -> bytes:
    return _list_page(title, rows, seed, 1, "THE PLAYBOOK", "number")


def checklist(title: str, rows: Sequence[str], seed: str = "") -> bytes:
    return _list_page(title, rows, seed + "cl", 2, "SAVE THIS CHECKLIST", "check")


def stat_card(number: str, label: str, source: str, seed: str = "") -> bytes:
    t = theme(seed or number + label)
    img = canvas(t)
    accent_ring(img, t, W + 20, 100, 220, 34)
    d = ImageDraw.Draw(img)
    pill(d, PAD, PAD, "WEBINAR DATA", t)
    nf = font("black", 300)
    for size in range(300, 120, -10):
        nf = font("black", size)
        if d.textlength(plain(number), font=nf) <= W - 2 * PAD:
            break
    d.text((PAD - 6, 330), plain(number), font=nf, fill=rgb(t["accent"] if t["name"] != "orange" else t["fg"]))
    lf, ll, llines = fit(d, label, "bold", W - 2 * PAD, 360, 62, 38, max_lines=5, lh=1.15, auto=False)
    y = draw_rich(img, llines, lf, PAD, 330 + int(nf.size * 1.12), ll, t)
    d = ImageDraw.Draw(img)
    if source:
        d.text((PAD, y + 36), f"Source: {plain(source)}", font=font("med", 28), fill=rgb(t["muted"]))
    footer(img, t)
    return jpeg(img)


def quote(text: str, attribution: str = "", seed: str = "") -> bytes:
    t = theme(seed or text, 3)
    img = canvas(t)
    dots(img, W - PAD - 6 * 32, H - PAD - 330, 7, 6, 32, 5, t["muted"], 100)
    d = ImageDraw.Draw(img)
    d.text((PAD - 14, PAD - 120), "“", font=font("black", 420), fill=rgb(t["accent"] if t["name"] != "orange" else t["fg"]))
    qf, ql, qlines = fit(d, text, "xbold", W - 2 * PAD, 640, 88, 50, max_lines=8, lh=1.12)
    y = max(PAD + 300, (H - ql * len(qlines)) // 2 - 10)
    y = draw_rich(img, qlines, qf, PAD, y, ql, t)
    d = ImageDraw.Draw(img)
    if attribution:
        d.rounded_rectangle([PAD, y + 50, PAD + 60, y + 58], radius=4, fill=rgb(t["accent"] if t["name"] != "orange" else t["fg"]))
        d.text((PAD + 80, y + 54), plain(attribution), font=font("semi", 32), fill=rgb(t["muted"]), anchor="lm")
    footer(img, t)
    return jpeg(img)


def comparison(title: str, left: dict, right: dict, seed: str = "") -> bytes:
    t = theme(seed or title, 2)
    img = canvas(t)
    d = ImageDraw.Draw(img)
    pill(d, PAD, PAD, "OLD WAY VS BETTER WAY", t)
    tf, tl, tlines = fit(d, title, "black", W - 2 * PAD, 260, 80, 48, max_lines=3, lh=1.06)
    y = draw_rich(img, tlines, tf, PAD, PAD + 100, tl, t) + 50
    gap = 24
    col_w = (W - 2 * PAD - gap) // 2
    bottom = H - PAD - 110
    for i, side in enumerate((left or {}, right or {})):
        x0 = PAD + i * (col_w + gap)
        better = i == 1
        st = dict(t)
        if better:
            st.update(fg=t["on_accent"], muted=t["on_accent"], em="color", em_text=t["on_accent"])
        card(img, [x0, y, x0 + col_w, bottom], t, fill=t["accent"] if better else None, radius=30)
        d = ImageDraw.Draw(img)
        head = plain(side.get("title") or ("Better way" if better else "Usual way"))
        hf, hl, hlines = fit(d, head, "xbold", col_w - 60, 110, 40, 28, max_lines=2, lh=1.1, auto=False)
        hy = draw_rich(img, hlines, hf, x0 + 30, y + 34, hl, st)
        d = ImageDraw.Draw(img)
        d.line([(x0 + 30, hy + 20), (x0 + col_w - 30, hy + 20)],
               fill=rgb(t["on_accent"] if better else t["line"], 120 if better else 255), width=2)
        rows = [r for r in (side.get("rows") or []) if r][:4]
        ry = hy + 50
        rh = (bottom - ry - 30) // max(1, len(rows))
        for r in rows:
            mx, my = x0 + 52, ry + 26
            d.ellipse([mx - 22, my - 22, mx + 22, my + 22],
                      fill=rgb(t["on_accent"] if better else t["line"]))
            if better:
                check(d, mx, my + 1, 26, t["accent"], 5)
            else:
                cross(d, mx, my, 26, t["muted"], 5)
            rf, rl, rlines = fit(d, r, "med", col_w - 120, rh - 20, 32, 22, max_lines=4, lh=1.22, auto=False)
            draw_rich(img, rlines, rf, x0 + 92, ry + 4, rl, st if better else dict(t, fg=t["fg"]))
            d = ImageDraw.Draw(img)
            ry += rh
    footer(img, t)
    return jpeg(img)


def poll(question: str, options: Sequence[str], seed: str = "") -> bytes:
    t = theme(seed or question, 1)
    img = canvas(t)
    accent_ring(img, t, W + 30, -40, 190, 28)
    d = ImageDraw.Draw(img)
    pill(d, PAD, PAD, "QUICK POLL", t, solid=True)
    qf, ql, qlines = fit(d, question, "black", W - 2 * PAD, 360, 80, 46, max_lines=5, lh=1.08)
    y = draw_rich(img, qlines, qf, PAD, PAD + 110, ql, t) + 50
    opts = [plain(o) for o in options if o][:4]
    gap = 22
    avail = H - y - PAD - 220
    row_h = min(150, (avail - gap * (len(opts) - 1)) // max(1, len(opts)))
    for i, o in enumerate(opts):
        top = y + i * (row_h + gap)
        card(img, [PAD, top, W - PAD, top + row_h], t, radius=row_h // 2)
        d = ImageDraw.Draw(img)
        cx, cy = PAD + row_h // 2, top + row_h // 2
        r = row_h // 2 - 16
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgb(t["accent"]))
        d.text((cx, cy), "ABCD"[i], font=font("black", int(r * 1.1)), fill=rgb(t["on_accent"]), anchor="mm")
        of, ol, olines = fit(d, o, "semi", W - 2 * PAD - row_h - 60, row_h - 30, 40, 26, max_lines=2, lh=1.15, auto=False)
        draw_rich(img, olines, of, PAD + row_h + 10, cy - ol * len(olines) / 2 - 4, ol, t)
    d = ImageDraw.Draw(img)
    letters = "ABCD"[:len(opts)]
    pill(d, PAD, H - PAD - 190, "Vote in the comments: " + ", ".join(letters[:-1]) + " or " + letters[-1:], t, size=30)
    footer(img, t)
    return jpeg(img)


__all__ = ["carousel", "infographic", "checklist", "stat_card", "quote", "comparison", "poll",
           "tokens", "plain", "THEMES", "theme", "font"]
