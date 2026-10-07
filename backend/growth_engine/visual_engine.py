"""Visual engine — renders the six Growth Engine formats with the existing brand kit.

Reuses ``social_images`` / ``blog_cover`` primitives (THEMES, fonts, logo, wrap)
so Growth Engine graphics match ShowUpAI's existing brand system exactly, without
duplicating any style code. Adds the three formats the social autopilot didn't have:
checklist, comparison and quote.

All output is JPEG — Instagram's Graph API only accepts JPEG.
"""

import io
import logging
import uuid

from bson import Binary
from PIL import Image, ImageDraw

import social_images as si

from . import ASSET_BUCKET, BRAND_NAME, COLLECTIONS
from .content_engine import is_renderable
from .models import VisualSpec

logger = logging.getLogger("showup.growth.visual")


# ── renderers ────────────────────────────────────────────────────────────────

def render_stat_card(spec: VisualSpec, seed: str = "") -> bytes:
    return si.render_stat_card(spec.number, spec.label, spec.source or BRAND_NAME,
                               seed=seed or spec.number)


def render_carousel(spec: VisualSpec, seed: str = "") -> list:
    slides = [{"title": s.get("title", ""), "body": s.get("body", "")} for s in spec.slides][:6]
    return si.render_carousel(spec.title or spec.slides[0]["title"], slides,
                              spec.cta or spec.title, seed=seed or spec.title)


def render_infographic(spec: VisualSpec, seed: str = "") -> bytes:
    return si.render_infographic(spec.title or spec.quote, spec.rows, seed=seed or spec.title)


def render_checklist(spec: VisualSpec, seed: str = "") -> bytes:
    """Checklist = the infographic grid with tick marks. Rows are prefixed so the
    renderer reads as a checklist rather than a numbered process."""
    rows = [f"✓  {r}".strip() for r in spec.rows][:6]
    return si.render_infographic(spec.title or "Checklist", rows, seed=(seed or spec.title) + "cl")


def render_comparison(spec: VisualSpec, seed: str = "") -> bytes:
    """Two-column side-by-side. Left column uses the soft panel colour, right the
    accent, so the 'recommended' side is visually distinct without extra colour logic."""
    W, H = 1080, 1350
    t = si._theme(seed or spec.title, offset=2)
    img = si._canvas(t, W, H)
    d = ImageDraw.Draw(img)
    pad, gap = 70, 30
    col_w = (W - 2 * pad - gap) // 2

    tf, tl = si._fit(d, spec.title or "Comparison", "bold", W - 2 * pad, 220, 60, 40, max_lines=3, lh=1.12)
    y = si._text_block(d, spec.title or "Comparison", tf, pad, pad, W - 2 * pad, si._hex(t["fg"]), tl) + 30

    top = y
    panel_h = H - top - 150
    for i, side in enumerate(("left", "right")):
        blk = getattr(spec, side, {}) or {}
        x0 = pad + i * (col_w + gap)
        d.rounded_rectangle([x0, top, x0 + col_w, top + panel_h], radius=26,
                            fill=si._hex(t["accent"] if i else t["soft"]))
        is_accent = i == 1
        head_fill = si._hex("#FFFFFF" if t["accent"] != "#FFFFFF" else "#EA580C") if is_accent else si._hex(t["fg"])
        body_fill = si._hex("#FFFFFF" if t["accent"] != "#FFFFFF" else "#EA580C") if is_accent else si._hex(t["fg"])
        mut_fill = si._hex("#FFFFFF" if t["accent"] != "#FFFFFF" else "#1F2937") if is_accent else si._hex(t["muted"])

        sf, sl = si._fit(d, blk.get("title") or "", "bold", col_w - 50, 120, 40, 26, max_lines=2)
        si._text_block(d, blk.get("title") or "", sf, x0 + 25, top + 28, col_w - 50, head_fill, sl)

        ry = top + 110
        rh = max(70, (panel_h - 140) // max(1, min(len(blk.get("rows") or []), 4)))
        for r in (blk.get("rows") or [])[:4]:
            rf, rl = si._fit(d, str(r), "semi", col_w - 60, rh - 16, 30, 20, max_lines=3, lh=1.25)
            lines = si._wrap(d, str(r), rf, col_w - 60)[:3]
            ty = ry + (rh - rl * len(lines)) // 2
            for ln in lines:
                d.text((x0 + 25, ty), ln, font=rf, fill=mut_fill)
                ty += rl
            ry += rh

    si._brand(img, t, pad, H - pad - 44, 44)
    d = ImageDraw.Draw(img)
    d.text((W - pad, H - pad - 22), si.BRAND_URL, font=si._font("reg", 24), fill=si._hex(t["muted"]), anchor="rm")
    return si._jpeg(img)


def render_quote(spec: VisualSpec, seed: str = "") -> bytes:
    """Large pull-quote with an oversized quote mark. No fabricated attribution —
    the card is credited to the brand, never to a made-up person."""
    W, H = 1080, 1080
    t = si._theme(seed or spec.quote, offset=3)
    img = si._canvas(t, W, H, (250, 150, 1200, 1000))
    d = ImageDraw.Draw(img)
    pad = 90
    accent = si._hex(t["accent"] if t["accent"] != "#111111" else t["fg"])

    d.text((pad - 10, pad - 40), "\u201C", font=si._font("bold", 220), fill=accent)

    qf, ql = si._fit(d, spec.quote, "bold", W - 2 * pad - 40, 560, 66, 40, max_lines=7, lh=1.2)
    lines = si._wrap(d, spec.quote, qf, W - 2 * pad - 40)[:7]
    total_h = ql * len(lines)
    y = max(pad + 130, (H - total_h) // 2 - 40)
    y = si._text_block(d, spec.quote, qf, pad, y, W - 2 * pad - 40, si._hex(t["fg"]), ql)

    if spec.attribution:
        d.text((pad, min(y + 40, H - 190)), f"— {spec.attribution}", font=si._font("semi", 30),
               fill=si._hex(t["muted"]))
    si._brand(img, t, pad, H - pad - 44, 44)
    d = ImageDraw.Draw(img)
    d.text((W - pad, H - pad - 22), si.BRAND_URL, font=si._font("reg", 24), fill=si._hex(t["muted"]), anchor="rm")
    return si._jpeg(img)


def render_poll(spec: VisualSpec, seed: str = "") -> bytes:
    """Poll card: the question, then options A-D. On Facebook and Instagram (no poll
    API) people answer by commenting a letter; on LinkedIn the native poll is used."""
    W, H = 1080, 1350
    t = si._theme(seed or spec.title, offset=1)
    img = si._canvas(t, W, H)
    d = ImageDraw.Draw(img)
    pad = 80
    accent = si._hex(t["accent"] if t["accent"] != "#111111" else t["fg"])

    tf_tag = si._font("semi", 26)
    tag = "QUICK POLL"
    tw = int(d.textlength(tag, font=tf_tag))
    d.rounded_rectangle([pad, pad, pad + tw + 44, pad + 50], radius=25, outline=accent, width=3)
    d.text((pad + 22, pad + 11), tag, font=tf_tag, fill=accent)

    qf, ql = si._fit(d, spec.title, "bold", W - 2 * pad, 360, 64, 40, max_lines=5, lh=1.15)
    y = si._text_block(d, spec.title, qf, pad, pad + 100, W - 2 * pad, si._hex(t["fg"]), ql) + 50

    opts = spec.rows[:4]
    avail = H - y - 230
    row_h = min(150, max(110, avail // max(1, len(opts))))
    for i, opt in enumerate(opts):
        top = y + i * row_h
        d.rounded_rectangle([pad, top, W - pad, top + row_h - 24], radius=22, fill=si._hex(t["soft"]))
        cx, cy = pad + 58, top + (row_h - 24) // 2
        d.ellipse([cx - 32, cy - 32, cx + 32, cy + 32], fill=accent)
        d.text((cx, cy), "ABCD"[i], font=si._font("bold", 32),
               fill=si._hex("#FFFFFF" if t["accent"] != "#FFFFFF" else "#EA580C"), anchor="mm")
        of, _ = si._fit(d, opt, "semi", W - 2 * pad - 150, row_h - 40, 38, 26, max_lines=1)
        d.text((pad + 120, cy), opt, font=of, fill=si._hex(t["fg"]), anchor="lm")

    d.text((pad, H - pad - 120), "Comment your letter below", font=si._font("semi", 34), fill=accent)
    si._brand(img, t, pad, H - pad - 44, 44)
    d = ImageDraw.Draw(img)
    d.text((W - pad, H - pad - 22), si.BRAND_URL, font=si._font("semi", 26), fill=si._hex(t["muted"]), anchor="rm")
    return si._jpeg(img)


RENDERERS = {
    "stat_card": render_stat_card,
    "carousel": render_carousel,
    "infographic": render_infographic,
    "checklist": render_checklist,
    "comparison": render_comparison,
    "quote": render_quote,
    "poll": render_poll,
}

MULTI_IMAGE = {"carousel"}


# ── storage (own collection + own GridFS bucket) ─────────────────────────────

def asset_url(asset_id: str) -> str:
    from config import PUBLIC_BACKEND_URL
    return f"{PUBLIC_BACKEND_URL.rstrip('/')}/api/growth/asset/{asset_id}.jpg"


async def store_assets(db, spec: VisualSpec, seed: str = "") -> dict:
    """Render + persist a spec into growth_assets / growth_assets_fs.

    Returns {"asset_ids": [...], "asset_urls": [...]}. Never raises on a single
    format failure — it returns what it managed to render so a campaign can still
    be reviewed as text-only.
    """
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket
    from bson import Binary

    if not is_renderable(spec):
        logger.error(f"visual_engine: refusing to render unrenderable spec ({spec.format})")
        return {"asset_ids": [], "asset_urls": [], "error": "unrenderable_spec"}

    fn = RENDERERS[spec.format]
    try:
        out = fn(spec, seed)
    except Exception as e:                                       # noqa: BLE001
        logger.error(f"visual_engine: render failed for {spec.format}: {e}")
        return {"asset_ids": [], "asset_urls": [], "error": str(e)[:200]}

    pages = out if isinstance(out, list) else [out]
    ids: list = []
    for b in pages:
        # Store bytes in the Growth Engine's own collection, mirroring how
        # social.py stores social images (Binary in a document, not GridFS).
        # database.py declares GridFS buckets but the codebase never uploads via
        # them, and motor's GridIn needs a raw pymongo Collection — so this is
        # both the working pattern and the one that actually runs here.
        aid = uuid.uuid4().hex
        await db[COLLECTIONS["assets"]].insert_one({
            "id": aid, "jpg": Binary(b), "bytes": len(b),
            "format": spec.format, "created_at": _now(),
        })
        ids.append(aid)
    return {"asset_ids": ids, "asset_urls": [asset_url(i) for i in ids]}


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


async def read_asset(db, asset_id: str) -> bytes | None:
    doc = await db[COLLECTIONS["assets"]].find_one({"id": asset_id})
    return bytes(doc["jpg"]) if doc and doc.get("jpg") is not None else None


__all__ = [
    "RENDERERS",
    "MULTI_IMAGE",
    "render_stat_card",
    "render_carousel",
    "render_infographic",
    "render_checklist",
    "render_comparison",
    "render_quote",
    "store_assets",
    "read_asset",
    "asset_url",
]