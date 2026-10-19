"""Visual engine — renders the Growth Engine formats and stores the JPEGs.

The design itself (type, themes, layouts) lives in ``design.py``; this module maps a
VisualSpec onto it and persists the result. All output is JPEG — Instagram's Graph
API only accepts JPEG.
"""

import logging
import uuid

from bson import Binary
from . import ASSET_BUCKET, BRAND_NAME, COLLECTIONS, design
from .content_engine import is_renderable
from .models import VisualSpec

logger = logging.getLogger("showup.growth.visual")


# ── renderers ────────────────────────────────────────────────────────────────
# The look lives in design.py. These adapters map a VisualSpec onto it.

def render_stat_card(spec: VisualSpec, seed: str = "") -> bytes:
    return design.stat_card(spec.number, spec.label, spec.source or BRAND_NAME, seed=seed or spec.number)


def render_carousel(spec: VisualSpec, seed: str = "") -> list:
    slides = [{"title": s.get("title", ""), "body": s.get("body", "")} for s in spec.slides][:6]
    return design.carousel(spec.title or spec.slides[0]["title"], slides, spec.cta,
                           subtitle=spec.subtitle, seed=seed or spec.title)


def render_infographic(spec: VisualSpec, seed: str = "") -> bytes:
    return design.infographic(spec.title or spec.quote, spec.rows, seed=seed or spec.title)


def render_checklist(spec: VisualSpec, seed: str = "") -> bytes:
    return design.checklist(spec.title or "Checklist", spec.rows, seed=seed or spec.title)


def render_comparison(spec: VisualSpec, seed: str = "") -> bytes:
    return design.comparison(spec.title or "Comparison", spec.left or {}, spec.right or {},
                             seed=seed or spec.title)


def render_quote(spec: VisualSpec, seed: str = "") -> bytes:
    """No fabricated attribution: a role or team, never a made-up person."""
    return design.quote(spec.quote, spec.attribution, seed=seed or spec.quote)


def render_poll(spec: VisualSpec, seed: str = "") -> bytes:
    """Poll card: the question, then options A-D. On Facebook and Instagram (no poll
    API) people answer by commenting a letter; on LinkedIn the native poll is used."""
    return design.poll(spec.title, spec.rows[:4], seed=seed or spec.title)


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