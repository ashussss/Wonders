"""The event's own banner and the creatives made from it.

When a webinar comes in from a link (Circle, Luma, Eventbrite, Zoom...), the event's
cover image is downloaded and kept as the webinar banner. Its colours become the
webinar's `event_theme`, so every card and creative for that event looks like the
event, not like a generic template. The customer's own logo and font (Brand Kit)
stay on top; ShowUp AI is only the small "Powered by" line.

Creatives (all JPEG, which Instagram requires):
- promo      1080x1350  the 4:5 feed post: banner, title, date, host, "Save your seat"
- square     1080x1080  the same for places that crop to square
- story      1080x1920  Instagram/WhatsApp status
- youre_in   1080x1350  touch 1, sent with the registration confirmation
- tomorrow   1080x1350  "Tomorrow" countdown (day before)
- starting   1080x1350  touch 9, "Starts in 1 hour"
- live       1080x1350  touch 12, "We're live"
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
from typing import Any, Dict, Optional, Tuple

import brand_kit

logger = logging.getLogger("showup.event_art")

MAX_BANNER_BYTES = 8 * 1024 * 1024
BANNER_MAX_W = 1600

SIZES = {"promo": (1080, 1350), "square": (1080, 1080), "story": (1080, 1920),
         "youre_in": (1080, 1350), "tomorrow": (1080, 1350), "starting": (1080, 1350), "live": (1080, 1350)}

# Big line over the title. None = the plain promo layout.
HEADLINES = {
    "promo": "FREE LIVE WEBINAR", "square": "FREE LIVE WEBINAR", "story": "FREE LIVE WEBINAR",
    "youre_in": "YOU'RE IN", "tomorrow": "TOMORROW", "starting": "STARTS IN 1 HOUR", "live": "WE'RE LIVE",
}
CTAS = {
    "promo": "Save your seat", "square": "Save your seat", "story": "Save your seat",
    "youre_in": "Add it to your calendar", "tomorrow": "See you there", "starting": "Join here", "live": "Join now",
}
# Creatives shown on the webinar page for download, in this order.
DOWNLOADS = ["promo", "square", "story", "youre_in", "tomorrow", "starting", "live"]
LABELS = {"promo": "Feed post (4:5)", "square": "Square post", "story": "Story / status",
          "youre_in": "You're in (confirmation)", "tomorrow": "Tomorrow", "starting": "Starts in 1 hour",
          "live": "We're live"}
# Touches that had no card get the matching event creative.
TOUCH_CREATIVE = {1: "youre_in", 9: "starting", 12: "live"}


# ── banner: download, normalise, colours ─────────────────────────────────────

class BannerError(ValueError):
    """The image couldn't be used. The message is safe to show the customer."""


def normalise_banner(data: bytes) -> bytes:
    """Any image (PNG, WebP, JPEG, GIF first frame) -> RGB JPEG no wider than 1600px."""
    from PIL import Image, ImageOps
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise BannerError("That file isn't an image we can read")
    img = ImageOps.exif_transpose(img)
    if img.width < 200 or img.height < 100:
        raise BannerError("That image is too small to use as a banner")
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    if img.width > BANNER_MAX_W:
        img = img.resize((BANNER_MAX_W, round(img.height * BANNER_MAX_W / img.width)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue()


async def download_image(url: str) -> bytes:
    """Fetch an image from a public URL (no internal hosts, redirects checked)."""
    import httpx
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ShowUpAI/1.0; +https://showupai.live)",
               "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8"}
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, headers=headers) as client:
            _, body, ctype = await brand_kit._get(client, url, MAX_BANNER_BYTES + 1)
    except brand_kit.UnsafeURL as e:
        raise BannerError(str(e))
    except brand_kit.SiteError as e:
        raise BannerError(f"Couldn't download the image: {e}")
    except Exception as e:  # noqa: BLE001
        raise BannerError(f"Couldn't download the image ({type(e).__name__})")
    if len(body) > MAX_BANNER_BYTES:
        raise BannerError("That image is over 8MB")
    if ctype and not ctype.startswith("image/") and "octet-stream" not in ctype:
        raise BannerError("That link isn't an image")
    return body


def palette(jpeg: bytes) -> Dict[str, str]:
    """The banner's main colours: `bg` (what most of it is) and `accent` (its strongest
    brand colour, or None for a black-and-white banner)."""
    from PIL import Image
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    img.thumbnail((160, 160))
    q = img.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:24]
    counts = sorted(q.getcolors() or [], reverse=True)
    total = sum(c for c, _ in counts) or 1
    colours = [(c / total, brand_kit._hex(tuple(pal[i * 3:i * 3 + 3]))) for c, i in counts]
    bg = colours[0][1]
    accent, best = None, 0.0
    for share, hexv in colours:
        sat, light = brand_kit._sat_light(hexv)
        if share < 0.03 or sat < 0.35 or light < 0.18 or light > 0.85:
            continue
        score = sat * (share ** 0.5)
        if score > best:
            accent, best = hexv, score
    return {"bg": bg, "accent": accent}


def event_theme(jpeg: bytes) -> Optional[Dict[str, str]]:
    """Card colours in the banner's look. Dark banners give dark cards; light or busy
    ones give light cards tinted with the banner's colour. Contrast is checked by
    brand_kit.theme, so text always reads."""
    p = palette(jpeg)
    bg, accent = p["bg"], p["accent"]
    if brand_kit._lum(bg) < 0.12:
        card_bg = brand_kit.mix(bg, "#000000", 0.25)         # keep a dark banner's mood
    else:
        card_bg = brand_kit.mix("#FFFFFF", accent or bg, 0.06)  # near-white, tinted
    primary = accent or brand_kit.readable_on(card_bg)
    return brand_kit.theme({"primary_color": primary, "background_color": card_bg})


async def store_banner(db, fs, webinar: Dict[str, Any], data: bytes, source: str = "upload",
                       filename: str = "banner.jpg") -> Dict[str, Any]:
    """Save `data` as the webinar's banner and its colours as the webinar's event theme.
    Replaces an older banner. Returns {"url", "event_theme"}."""
    wid, owner = webinar["id"], webinar["owner_id"]
    loop = asyncio.get_running_loop()
    jpeg = await loop.run_in_executor(None, normalise_banner, data)
    try:
        theme = await loop.run_in_executor(None, event_theme, jpeg)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"banner colours for {wid} failed: {e}")
        theme = None
    old = await db.banners.find_one({"webinar_id": wid}, {"_id": 0})
    file_id = await fs.upload_from_stream(f"banner-{wid}.jpg", jpeg,
                                          metadata={"webinar_id": wid, "owner_id": owner, "mime": "image/jpeg"})
    digest = hashlib.md5(jpeg).hexdigest()
    await db.banners.update_one(
        {"webinar_id": wid},
        {"$set": {"webinar_id": wid, "owner_id": owner, "file_id": file_id, "mime": "image/jpeg",
                  "filename": filename, "size": len(jpeg), "hash": digest, "source": source,
                  "uploaded_at": _now()}},
        upsert=True)
    if old and old.get("file_id"):
        try:
            await fs.delete(old["file_id"])
        except Exception:  # noqa: BLE001
            pass
    url = f"/api/webinars/{wid}/banner.img?v={digest[:8]}"
    await db.webinars.update_one({"id": wid, "owner_id": owner},
                                 {"$set": {"banner_url": url, "banner_hash": digest, "event_theme": theme}})
    return {"url": url, "event_theme": theme}


async def import_cover(db, fs, webinar: Dict[str, Any], url: str, force: bool = False) -> Optional[Dict[str, Any]]:
    """Use the event page's cover image as the banner (unless the host already has one)."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    if not force and await db.banners.find_one({"webinar_id": webinar["id"]}, {"_id": 1}):
        return None
    try:
        data = await download_image(url)
        out = await store_banner(db, fs, webinar, data, source=url)
        await db.webinars.update_one({"id": webinar["id"], "owner_id": webinar["owner_id"]},
                                     {"$set": {"cover_image_url": url}, "$unset": {"banner_error": ""}})
        logger.info(f"banner imported for {webinar['id']} from {url}")
        return out
    except BannerError as e:
        logger.warning(f"banner import for {webinar['id']} from {url} failed: {e}")
        await db.webinars.update_one({"id": webinar["id"], "owner_id": webinar["owner_id"]},
                                     {"$set": {"banner_error": str(e)[:200], "cover_image_url": url}})
    except Exception as e:  # noqa: BLE001
        logger.exception(f"banner import for {webinar['id']} crashed: {e}")
    return None


async def banner_bytes(db, fs, webinar_id: str) -> Optional[bytes]:
    meta = await db.banners.find_one({"webinar_id": webinar_id}, {"_id": 0})
    if not meta or not meta.get("file_id"):
        return None
    try:
        stream = await fs.open_download_stream(meta["file_id"])
        return await stream.read()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"banner read for {webinar_id} failed: {e}")
        return None


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── creatives ────────────────────────────────────────────────────────────────

def creative_spec(kind: str, w: Dict[str, Any], brand: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from touch_render import values
    v = values(w, public=True)
    title = (w.get("title") or "").strip()
    when = " · ".join(x for x in (v["webinar_date"], v["webinar_time"]) if x)
    host = v.get("speaker") or ""
    link = v.get("registration_link") or ""
    import partner_logo
    cb = {**brand_kit.card_brand(brand), **partner_logo.card_fields(w)}
    if w.get("event_theme"):
        cb = {**cb, "theme": w["event_theme"]}
    return {"kind": kind, "size": list(SIZES[kind]), "headline": HEADLINES[kind], "cta": CTAS[kind],
            "title": title, "when": when, "host": host, "link": _short_link(link),
            "banner": w.get("banner_hash") or "", "seed": w.get("id") or title, "brand": cb}


def spec_hash(spec: Dict[str, Any]) -> str:
    return hashlib.md5(json.dumps(spec, sort_keys=True).encode()).hexdigest()


def _short_link(url: str) -> str:
    from urllib.parse import urlparse
    if not url:
        return ""
    p = urlparse(url if "://" in url else "https://" + url)
    s = (p.netloc + p.path).removeprefix("www.").rstrip("/")
    return s if len(s) <= 42 else p.netloc.removeprefix("www.")


def render_creative(spec: Dict[str, Any], banner: Optional[bytes] = None, logo_png: Optional[bytes] = None,
                    fonts: Optional[Dict[str, str]] = None, partner_png: Optional[bytes] = None) -> bytes:
    from blog_cover import FONT_OVERRIDE
    token = FONT_OVERRIDE.set(fonts or None)
    try:
        return _render(spec, banner, logo_png, partner_png)
    finally:
        FONT_OVERRIDE.reset(token)


def _cover(img, box_w: int, box_h: int):
    """Scale and centre-crop to fill box_w x box_h (CSS object-fit: cover)."""
    from PIL import Image
    scale = max(box_w / img.width, box_h / img.height)
    r = img.resize((max(box_w, round(img.width * scale)), max(box_h, round(img.height * scale))), Image.LANCZOS)
    x, y = (r.width - box_w) // 2, (r.height - box_h) // 2
    return r.crop((x, y, x + box_w, y + box_h))


def _render(spec: Dict[str, Any], banner: Optional[bytes], logo_png: Optional[bytes],
            partner_png: Optional[bytes] = None) -> bytes:
    from PIL import Image, ImageDraw
    import social_images as si
    from touch_visuals import _colors

    Wd, Ht = spec["size"]
    pad = 72 if Wd == Ht else 80
    brand = spec.get("brand") or {}
    t, accent, on_accent = _colors(spec["seed"], brand.get("theme"))
    img = Image.new("RGBA", (Wd, Ht), si._hex(t["bg"]))
    d = ImageDraw.Draw(img)

    # Banner on top, full bleed. Its height follows the format: the story is tall,
    # the square needs room for text.
    top = 0
    if banner:
        try:
            b = Image.open(io.BytesIO(banner)).convert("RGB")
            # Full width, never cropped at the sides: event banners carry their name
            # and date as text. A tall banner is trimmed top and bottom instead.
            bh = min({1080: 470, 1350: 610, 1920: 860}.get(Ht, int(Ht * 0.44)), round(Wd * b.height / b.width))
            img.paste(_cover(b, Wd, bh), (0, 0))
            top = bh
        except Exception as e:  # noqa: BLE001
            logger.warning(f"banner unusable in creative: {e}")
    if not top:
        # No banner: a solid band in the event colour with the host's mark keeps it designed.
        bh = {1080: 300, 1350: 380, 1920: 560}.get(Ht, 360)
        d.rectangle([0, 0, Wd, bh], fill=si._hex(accent))
        f, lh = si._fit(d, spec["headline"], "bold", Wd - 2 * pad, bh - 120, 92, 48, max_lines=2, lh=1.05)
        si._text_block(d, spec["headline"], f, pad, bh - 40 - lh * len(si._wrap(d, spec["headline"], f, Wd - 2 * pad)[:2]),
                       Wd - 2 * pad, si._hex(on_accent), lh, max_lines=2)
        top = bh

    # Bottom bar: logo / name on the left, Powered by on the right.
    foot_h = 96
    bottom = Ht - foot_h
    d.line([(pad, bottom), (Wd - pad, bottom)], fill=si._hex(t["muted"], 90), width=2)
    room = Wd - 2 * pad
    if brand.get("powered_by", True):
        room -= int(d.textlength(brand_kit.POWERED_BY_LINE, font=si._font("semi", 20))) + 36
    _foot_brand(img, d, si, t, brand, logo_png, pad, bottom + foot_h // 2, partner_png, max_w=max(200, room))
    if brand.get("powered_by", True):
        f = si._font("semi", 20)
        d.text((Wd - pad, bottom + foot_h // 2), brand_kit.POWERED_BY_LINE, font=f, fill=si._hex(t["muted"]), anchor="rm")

    # Text block between banner and footer.
    y = top + {1920: 110, 1350: 56}.get(Ht, 40)
    avail = bottom - y - 40
    if banner:  # headline chip only when the banner carries the picture
        hf = si._font("bold", 28 if Ht > 1080 else 24)
        tw = int(d.textlength(spec["headline"], font=hf))
        d.rounded_rectangle([pad, y, pad + tw + 44, y + 54], radius=27, fill=si._hex(accent))
        d.text((pad + 22, y + 27), spec["headline"], font=hf, fill=si._hex(on_accent), anchor="lm")
        y += 54 + 30
        avail -= 84
    cta_h = 84
    title_max = max(120, avail - cta_h - 150)
    tf, tl = si._fit(d, spec["title"], "bold", Wd - 2 * pad, title_max, {1920: 84, 1350: 70}.get(Ht, 58), 34,
                     max_lines=4, lh=1.12)
    y = si._text_block(d, spec["title"], tf, pad, y, Wd - 2 * pad, si._hex(t["fg"]), tl, max_lines=4) + 18
    for line, kind in ((spec["when"], "semi"), (f"with {spec['host']}" if spec["host"] else "", "reg")):
        if not line:
            continue
        f, lh = si._fit(d, line, kind, Wd - 2 * pad, 60, {1920: 44, 1350: 36}.get(Ht, 30), 22, max_lines=1)
        d.text((pad, y), line, font=f, fill=si._hex(accent if kind == "semi" else t["muted"]))
        y += lh + 8
    # CTA button pinned above the footer.
    cy = bottom - 40 - cta_h
    if cy > y + 10:
        cf = si._font("bold", 34 if Ht > 1080 else 30)
        cw = int(d.textlength(spec["cta"], font=cf)) + 80
        d.rounded_rectangle([pad, cy, pad + cw, cy + cta_h], radius=cta_h // 2, fill=si._hex(accent))
        d.text((pad + cw // 2, cy + cta_h // 2), spec["cta"], font=cf, fill=si._hex(on_accent), anchor="mm")
        if spec["link"] and pad + cw + 30 < Wd - pad:
            lf, _ = si._fit(d, spec["link"], "semi", Wd - 2 * pad - cw - 30, 40, 26, 18, max_lines=1)
            d.text((pad + cw + 28, cy + cta_h // 2), spec["link"], font=lf, fill=si._hex(t["muted"]), anchor="lm")
    return si._jpeg(img)


def _foot_brand(img, d, si, t, brand, logo_png, x, cy, partner_png=None, max_w=460):
    from PIL import Image
    if partner_png or brand.get("partner_name"):
        import partner_logo
        lock = partner_logo.lockup(si, t, brand, logo_png, partner_png, max_w, 52)
        if lock is not None:
            img.alpha_composite(lock, (x, cy - lock.height // 2))
            return
    if logo_png:
        try:
            logo = Image.open(io.BytesIO(logo_png)).convert("RGBA")
            logo.thumbnail((260, 52))
            img.alpha_composite(logo, (x, cy - logo.height // 2))
            return
        except Exception as e:  # noqa: BLE001
            logger.warning(f"brand logo unusable: {e}")
    name = (brand.get("name") or "").strip()
    if name:
        f, _ = si._fit(d, name, "bold", 420, 40, 28, 18, max_lines=1)
        d.text((x, cy), name, font=f, fill=si._hex(t["fg"]), anchor="lm")


# ── storage ──────────────────────────────────────────────────────────────────

COLLECTION = "event_creatives"


async def ensure_creative(db, fs, w: Dict[str, Any], kind: str,
                          brand: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """The stored creative, rendered on first use and again when the banner, colours,
    title, date or brand change."""
    if kind not in SIZES:
        return None
    owner = w.get("owner_id") or ""
    if brand is None:
        brand = await brand_kit.resolve(db, owner)
    spec = creative_spec(kind, w, brand)
    h = spec_hash(spec)
    key = {"webinar_id": w["id"], "kind": kind}
    row = await db[COLLECTION].find_one(key, {"_id": 0})
    if row and row.get("hash") == h:
        return row
    try:
        banner = await banner_bytes(db, fs, w["id"]) if spec["banner"] else None
        logo = await brand_kit.logo_png(db, owner) if spec["brand"].get("logo_hash") else None
        fonts = await brand_kit.font_paths_async(spec["brand"].get("font") or "")
        import partner_logo
        partner = await partner_logo.png(db, w["id"]) if spec["brand"].get("partner_hash") else None
        jpeg = await asyncio.get_running_loop().run_in_executor(None, render_creative, spec, banner, logo,
                                                                fonts, partner)
    except Exception as e:  # noqa: BLE001
        logger.error(f"creative {kind} for {w['id']} failed: {e}", exc_info=True)
        return row
    file_id = await fs.upload_from_stream(f"creative-{w['id']}-{kind}.jpg", jpeg,
                                          metadata={"webinar_id": w["id"], "mime_type": "image/jpeg"})
    if row and row.get("file_id"):
        try:
            await fs.delete(row["file_id"])
        except Exception:  # noqa: BLE001
            pass
    new = {**key, "owner_id": owner, "hash": h, "file_id": file_id, "size": spec["size"]}
    await db[COLLECTION].update_one(key, {"$set": new}, upsert=True)
    return new


def creative_url(base: str, row: Optional[Dict[str, Any]]) -> Optional[str]:
    if not row:
        return None
    return f"{(base or '').rstrip('/')}/api/webinars/{row['webinar_id']}/creatives/{row['kind']}.jpg?v={row['hash'][:8]}"
