"""A second logo per webinar: the company running or co-hosting the session.

An agency or organiser (for example SBM) often runs a webinar presented by another
company. Their Brand Kit logo stays on every card and creative; this logo sits next
to it, split by a thin line, so both brands show on every visual.

Stored per webinar in `partner_logos` (PNG, trimmed). The webinar carries
`partner_logo_hash` and `partner_name`, which go into the card hash, so cards and
creatives are redrawn when the logo changes.
"""
from __future__ import annotations

import hashlib
import io
import logging
from typing import Any, Dict, List, Optional

import brand_kit

logger = logging.getLogger("showup.partner_logo")

COLLECTION = "partner_logos"
MAX_BYTES = 5 * 1024 * 1024


async def store(db, w: Dict[str, Any], data: bytes, name: str = "") -> Dict[str, Any]:
    """Normalise and save. Raises ValueError with a message safe to show."""
    if len(data) > MAX_BYTES:
        raise ValueError("Logo must be under 5MB")
    try:
        png = brand_kit.normalise_logo(data)
    except ValueError:
        raise
    except Exception:  # noqa: BLE001
        raise ValueError("That file isn't an image we can read (use PNG, JPG or WebP)") from None
    h = hashlib.md5(png).hexdigest()
    await db[COLLECTION].update_one({"webinar_id": w["id"]},
                                    {"$set": {"webinar_id": w["id"], "owner_id": w.get("owner_id"),
                                              "png": png, "hash": h}}, upsert=True)
    upd = {"partner_logo_hash": h}
    if name is not None:
        upd["partner_name"] = (name or "").strip()[:80]
    await db.webinars.update_one({"id": w["id"]}, {"$set": upd})
    return {"partner_logo_hash": h, "partner_logo_url": logo_path(w["id"], h),
            "partner_name": upd.get("partner_name", w.get("partner_name") or "")}


async def clear(db, wid: str) -> None:
    await db[COLLECTION].delete_one({"webinar_id": wid})
    await db.webinars.update_one({"id": wid}, {"$unset": {"partner_logo_hash": "", "partner_name": ""}})


async def png(db, wid: str) -> Optional[bytes]:
    row = await db[COLLECTION].find_one({"webinar_id": wid}, {"_id": 0, "png": 1})
    return bytes(row["png"]) if row and row.get("png") else None


def logo_path(wid: str, h: str) -> str:
    return f"/api/webinars/{wid}/partner-logo.png?v={h[:8]}" if h else ""


def card_fields(w: Dict[str, Any]) -> Dict[str, str]:
    """What goes into a card's brand (and so its hash). Empty for webinars without a
    partner, so their existing cards keep their hash and aren't redrawn."""
    out = {"partner_hash": w.get("partner_logo_hash") or "", "partner_name": (w.get("partner_name") or "").strip()}
    return {k: v for k, v in out.items() if v}


# ── drawing ──────────────────────────────────────────────────────────────────

def _text_logo(si, text: str, color, max_w: int, max_h: int):
    from PIL import Image, ImageDraw
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    f, _ = si._fit(probe, text, "bold", max_w, max_h, max(18, int(max_h * 0.62)), 16, max_lines=1)
    l, t, r, b = probe.textbbox((0, 0), text, font=f)
    img = Image.new("RGBA", (r - l + 4, max_h), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2 - l, max_h // 2), text, font=f, fill=color, anchor="lm")
    return img


def lockup(si, t: Dict[str, str], brand: Dict[str, Any], logo_png: Optional[bytes],
           partner_png: Optional[bytes], max_w: int, max_h: int):
    """Host logo | partner logo as one transparent image, or None when there's nothing
    to draw. Either side falls back to its name in text. Scaled to fit max_w x max_h."""
    from PIL import Image, ImageDraw
    parts: List[Any] = []
    for data, name in ((logo_png, brand.get("name")), (partner_png, brand.get("partner_name"))):
        img = None
        if data:
            try:
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                img.thumbnail((max_w, max_h))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"logo unusable in lockup: {e}")
                img = None
        if img is None and (name or "").strip():
            img = _text_logo(si, name.strip(), si._hex(t["fg"]), max_w, int(max_h * 0.8))
        if img is not None:
            parts.append(img)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    gap = max(14, max_h // 3)
    h = max(p.height for p in parts)
    w = sum(p.width for p in parts) + 2 * gap + 2
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x = 0
    for i, p in enumerate(parts):
        out.alpha_composite(p, (x, (h - p.height) // 2))
        x += p.width
        if i == 0:
            ImageDraw.Draw(out).line([(x + gap, int(h * 0.1)), (x + gap, int(h * 0.9))],
                                     fill=si._hex(t["muted"], 160), width=2)
            x += 2 * gap + 2
    if out.width > max_w:
        out = out.resize((max_w, max(1, round(out.height * max_w / out.width))), Image.LANCZOS)
    return out
