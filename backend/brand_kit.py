"""The customer's brand kit: logo, colours, font and voice.

Everything a customer's audience sees (touch cards, emails, social copy) is the
customer's own brand. ShowUp AI only shows as a small "Powered by ShowUp AI" mark,
which Agency customers (sold as white-label) can switch off.

The kit is one document per owner in `brand_kits`. The logo is kept in the same
document as a small normalised PNG (bytes), so rendering needs no extra storage.
`extract_from_website` fills a kit from the customer's own site: name, logo,
colours, font and a sample of how they write.
"""
from __future__ import annotations

import asyncio
import colorsys
import hashlib
import io
import ipaddress
import json
import logging
import os
import re
import socket
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

logger = logging.getLogger("showup.brand_kit")

COLLECTION = "brand_kits"
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_MAX = 600                     # px, longest side, after normalising
POWERED_BY = "Powered by ShowUp AI"
POWERED_BY_URL = "https://showupai.live/?utm_source=powered_by"

# Fields the customer edits. Everything else in the document is managed here.
EDITABLE = ("business_name", "website", "primary_color", "background_color", "text_color", "font",
            "tone", "voice_sample", "audience", "cta_label", "hide_powered_by")


# ── colour helpers ───────────────────────────────────────────────────────────

def _rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: Tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, int(round(c)))):02X}" for c in rgb)


def _lum(h: str) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a: str, b: str, t: float) -> str:
    """a blended toward b by t (0 = a, 1 = b)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x + (y - x) * t for x, y in zip(ra, rb)))


def readable_on(bg: str) -> str:
    return "#111111" if contrast(bg, "#111111") >= contrast(bg, "#FFFFFF") else "#FFFFFF"


def _sat_light(h: str) -> Tuple[float, float]:
    r, g, b = (c / 255 for c in _rgb(h))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    return sat, light


def norm_color(v: Any) -> Optional[str]:
    """'#abc', '#aabbcc', '#aabbccdd', 'rgb(1,2,3)' -> '#AABBCC'; anything else -> None."""
    if not isinstance(v, str):
        return None
    s = v.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3})", s)
    if m:
        return "#" + "".join(c * 2 for c in m.group(1)).upper()
    m = re.fullmatch(r"#([0-9a-f]{6})(?:[0-9a-f]{2})?", s)
    if m:
        return "#" + m.group(1).upper()
    m = re.fullmatch(r"rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})(?:[\s,/]+[\d.%]+)?\s*\)", s)
    if m:
        return _hex(tuple(min(255, int(x)) for x in m.groups()))
    return None


def theme(kit: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Card colours from the kit, or None when the customer hasn't picked a brand colour.

    Text and accent are checked for contrast against the background, so a pale brand
    colour on white still gives readable cards.
    """
    primary = norm_color(kit.get("primary_color"))
    if not primary:
        return None
    bg = norm_color(kit.get("background_color")) or "#FFFFFF"
    fg = norm_color(kit.get("text_color"))
    if not fg or contrast(fg, bg) < 4.5:
        fg = readable_on(bg)
    accent = primary if contrast(primary, bg) >= 2.6 else fg
    soft = mix(bg, primary if accent == primary else fg, 0.08 if _lum(bg) > 0.4 else 0.16)
    return {"bg": bg, "fg": fg, "muted": mix(fg, bg, 0.42), "accent": accent, "soft": soft,
            "on_accent": readable_on(accent)}


def email_link_color(kit: Dict[str, Any]) -> str:
    p = norm_color(kit.get("primary_color"))
    return p if p and contrast(p, "#FFFFFF") >= 3 else "#2563EB"


# ── storage ──────────────────────────────────────────────────────────────────

def public_view(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The kit as the API returns it: no logo bytes, plus where the logo is served."""
    doc = dict(doc or {})
    doc.pop("_id", None)
    doc.pop("logo_png", None)
    doc["logo_url"] = logo_path(doc)
    return doc


def logo_path(doc: Dict[str, Any]) -> Optional[str]:
    if not doc.get("logo_hash") or not doc.get("id"):
        return None
    return f"/api/brand/{doc['id']}/logo.png?v={doc['logo_hash'][:8]}"


async def load(db, owner_id: str, with_logo: bool = False) -> Dict[str, Any]:
    proj = {"_id": 0} if with_logo else {"_id": 0, "logo_png": 0}
    try:
        return await db[COLLECTION].find_one({"owner_id": owner_id}, proj) or {}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"brand kit load failed for {owner_id}: {e}")
        return {}


async def save(db, owner_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    from auth_utils import now_iso
    fields = {**fields, "owner_id": owner_id, "updated_at": now_iso()}
    await db[COLLECTION].update_one({"owner_id": owner_id},
                                    {"$set": fields, "$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)
    return await load(db, owner_id)


def clean_fields(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Validate what the customer typed. Empty strings clear a field."""
    out: Dict[str, Any] = {}
    for k in EDITABLE:
        if k not in raw or raw[k] is None:
            continue
        v = raw[k]
        if k.endswith("_color"):
            v = norm_color(v) if v else ""
            if v is None:
                raise ValueError(f"{k.replace('_', ' ')} must be a colour like #1A2B3C")
        elif k == "hide_powered_by":
            v = bool(v)
        elif k == "website":
            v = str(v).strip()
            if v and not re.match(r"^https?://", v, re.I):
                v = "https://" + v
        else:
            limit = {"voice_sample": 3000, "tone": 600, "audience": 300}.get(k, 80)
            v = re.sub(r"[ \t]+", " ", str(v)).strip()[:limit]
        out[k] = v
    return out


def normalise_logo(data: bytes) -> bytes:
    """Any raster image -> RGBA PNG, transparent margins trimmed, at most LOGO_MAX px."""
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    img.load()
    img = img.convert("RGBA")
    box = img.getchannel("A").getbbox()
    if box:
        img = img.crop(box)
    if min(img.size) < 16:
        raise ValueError("That logo is too small")
    img.thumbnail((LOGO_MAX, LOGO_MAX))
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


async def set_logo(db, owner_id: str, data: bytes) -> Dict[str, Any]:
    png = normalise_logo(data)
    return await save(db, owner_id, {"logo_png": png, "logo_hash": hashlib.md5(png).hexdigest()})


async def clear_logo(db, owner_id: str) -> Dict[str, Any]:
    await db[COLLECTION].update_one({"owner_id": owner_id}, {"$unset": {"logo_png": "", "logo_hash": ""}})
    return await load(db, owner_id)


# ── what the renderers use ───────────────────────────────────────────────────

async def _can_hide_mark(db, owner_id: str) -> bool:
    """Only the Agency plan (sold as white-label) may hide the Powered by mark."""
    try:
        from billing import entitlement
        user = await db.users.find_one({"id": owner_id}, {"_id": 0})
        return bool(user) and entitlement(user).get("plan") == "agency"
    except Exception as e:  # noqa: BLE001
        logger.warning(f"plan lookup failed for {owner_id}: {e}")
        return False


async def resolve(db, owner_id: str, base_url: str = "") -> Dict[str, Any]:
    """Everything needed to brand one customer's output.

    Always returns a dict: a customer with no kit gets the defaults (current card
    themes, plain email) plus the Powered by mark.
    """
    kit = await load(db, owner_id or "")
    base = (base_url or os.environ.get("PUBLIC_BACKEND_URL") or "").rstrip("/")
    path = logo_path(kit)
    hide = bool(kit.get("hide_powered_by")) and await _can_hide_mark(db, owner_id)
    return {
        "id": kit.get("id"),
        "name": kit.get("business_name") or "",
        "website": kit.get("website") or "",
        "theme": theme(kit),
        "font": (kit.get("font") or "").strip(),
        "logo_hash": kit.get("logo_hash") or "",
        "logo_url": f"{base}{path}" if path and base else "",
        "cta_label": kit.get("cta_label") or "",
        "link_color": email_link_color(kit),
        "button_color": (theme(kit) or {}).get("accent") if theme(kit) else "",
        "powered_by": not hide,
        "owner_id": owner_id,
    }


def card_brand(brand: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The part of the brand that changes how a card looks (goes into the card's hash)."""
    b = brand or {}
    return {"theme": b.get("theme"), "font": b.get("font") or "", "logo_hash": b.get("logo_hash") or "",
            "name": b.get("name") or "", "powered_by": b.get("powered_by", True)}


async def logo_png(db, owner_id: str) -> Optional[bytes]:
    kit = await load(db, owner_id, with_logo=True)
    data = kit.get("logo_png")
    return bytes(data) if data else None


async def voice_brief(db, owner_id: str) -> str:
    """The customer's voice, for the copy prompt. Old Settings brand fields still count."""
    kit = await load(db, owner_id or "")
    try:
        s = await db.settings.find_one({"owner_id": owner_id}, {"_id": 0}) or {}
    except Exception:  # noqa: BLE001
        s = {}
    return build_voice_brief(kit, s)


def build_voice_brief(kit: Dict[str, Any], s: Optional[Dict[str, Any]] = None) -> str:
    s = s or {}
    name = kit.get("business_name") or ""
    tone = kit.get("tone") or s.get("brand_tone") or ""
    audience = kit.get("audience") or s.get("brand_audience") or ""
    lines = []
    if name:
        site = f" ({kit['website']})" if kit.get("website") else ""
        lines.append(f"- The host speaks for {name}{site}. Every message must sound like it came from {name}, "
                     f"never from a software tool. Never mention ShowUp AI.")
    if tone:
        lines.append(f"- How they sound: {tone}")
    if audience:
        lines.append(f"- Who they talk to: {audience}")
    if s.get("brand_language"):
        lines.append(f"- Spelling and language: {s['brand_language']}")
    if kit.get("cta_label"):
        lines.append(f"- When pointing to the link, they say things like: \"{kit['cta_label']}\"")
    if s.get("brand_always_include"):
        lines.append(f"- Always include: {s['brand_always_include']}")
    if s.get("brand_banned_phrases"):
        lines.append(f"- Never use: {s['brand_banned_phrases']}")
    sample = (kit.get("voice_sample") or "").strip()
    if sample:
        lines.append("- This is how they actually write. Match its rhythm, word choice and formality. "
                     "Do not copy its sentences or its facts:\n\"\"\"\n" + sample[:1500] + "\n\"\"\"")
    if not lines:
        return ""
    return ("BRAND VOICE (this business's own voice; where it differs from the defaults above, follow it, "
            "but the banned words and the no-invented-facts rule still apply):\n" + "\n".join(lines))


# ── fonts ────────────────────────────────────────────────────────────────────

FONT_DIR = "/tmp/showup_fonts/brand"
_WEIGHTS = {"bold": (700, 800, 600, 900, 500), "semi": (600, 500, 700, 400), "reg": (400, 300, 500)}
_font_cache: Dict[str, Optional[Dict[str, str]]] = {}
# An old browser user agent makes Google Fonts serve plain TTF, which Pillow reads.
_TTF_UA = "Mozilla/4.0"


def _font_slug(family: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")


def _download_weight(family: str, weight: int) -> Optional[str]:
    import httpx
    path = os.path.join(FONT_DIR, f"{_font_slug(family)}-{weight}.ttf")
    if os.path.exists(path):
        return path
    try:
        css = httpx.get("https://fonts.googleapis.com/css2",
                        params={"family": f"{family}:wght@{weight}"},
                        headers={"User-Agent": _TTF_UA}, timeout=10)
        if css.status_code != 200:
            return None
        m = re.search(r"url\((https://fonts\.gstatic\.com/[^)]+\.ttf)\)", css.text)
        if not m:
            return None
        r = httpx.get(m.group(1), timeout=20)
        if r.status_code != 200 or len(r.content) < 1000:
            return None
        os.makedirs(FONT_DIR, exist_ok=True)
        with open(path, "wb") as f:
            f.write(r.content)
        return path
    except Exception as e:  # noqa: BLE001
        logger.info(f"font {family} {weight} unavailable: {e}")
        return None


def font_paths(family: str) -> Optional[Dict[str, str]]:
    """{'bold','semi','reg'} -> local TTF paths for a Google Fonts family, or None.

    Blocking (downloads once, then cached on disk and in memory); call from a thread.
    """
    family = (family or "").strip()
    if not family or not re.fullmatch(r"[A-Za-z0-9 ]{2,40}", family):
        return None
    if family in _font_cache:
        return _font_cache[family]
    out: Dict[str, str] = {}
    for kind, weights in _WEIGHTS.items():
        for wt in weights:
            p = _download_weight(family, wt)
            if p:
                out[kind] = p
                break
    result = out if "reg" in out or "bold" in out else None
    if result:
        for kind in ("bold", "semi", "reg"):
            result.setdefault(kind, result.get("semi") or result.get("bold") or result.get("reg"))
    _font_cache[family] = result
    return result


async def font_paths_async(family: str) -> Optional[Dict[str, str]]:
    if not family:
        return None
    return await asyncio.get_running_loop().run_in_executor(None, font_paths, family)


# ── reading a brand off the customer's website ──────────────────────────────

class UnsafeURL(ValueError):
    pass


def _check_public(url: str) -> None:
    """Refuse anything that isn't a public http(s) host (no internal network requests)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise UnsafeURL("Use a full website address, like https://yourbrand.com")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror:
        raise UnsafeURL("That website couldn't be found")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL("That address isn't a public website")


async def _get(client, url: str, limit: int) -> Tuple[str, bytes, str]:
    """GET with a public-host check on every redirect hop. Returns (final_url, body, content_type)."""
    for _ in range(5):
        await asyncio.get_running_loop().run_in_executor(None, _check_public, url)
        async with client.stream("GET", url) as r:
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = urljoin(url, r.headers["location"])
                continue
            if r.status_code >= 400:
                raise ValueError(f"{url} answered {r.status_code}")
            body = b""
            async for chunk in r.aiter_bytes():
                body += chunk
                if len(body) > limit:
                    break
            return str(r.url), body[:limit], r.headers.get("content-type", "")
    raise ValueError("Too many redirects")


_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\b|#[0-9a-fA-F]{3}\b|rgba?\([^)]{5,40}\)")
_BRAND_VAR = re.compile(r"--[\w-]*(?:primary|brand|accent|main|theme)[\w-]*\s*:\s*([^;}{]+)", re.I)
_GENERIC_FONTS = {"sans-serif", "serif", "monospace", "system-ui", "-apple-system", "blinkmacsystemfont",
                  "segoe ui", "helvetica", "helvetica neue", "arial", "inherit", "initial", "ui-sans-serif",
                  "apple color emoji", "segoe ui emoji", "segoe ui symbol", "noto color emoji", "times new roman",
                  "georgia", "cursive", "var", "unset", "emoji", "ui-serif", "ui-monospace", "menlo", "monaco",
                  "consolas", "courier new", "tahoma", "verdana", "sans", "fontawesome", "font awesome"}


def pick_colors(theme_color: str, css: str, inline_styles: str = "") -> Dict[str, str]:
    """Brand colours from a site: theme-color and --brand/--primary variables count most,
    then how often each saturated colour appears. Greys never count as the brand colour."""
    scores: Dict[str, float] = {}

    def add(raw, w):
        c = norm_color(raw)
        if not c:
            return
        sat, light = _sat_light(c)
        if sat < 0.25 or light < 0.12 or light > 0.9:
            return
        scores[c] = scores.get(c, 0) + w

    add(theme_color, 40)
    for m in _BRAND_VAR.finditer(css):
        add(m.group(1).strip(), 25)
    for raw in _COLOR_RE.findall(css + "\n" + inline_styles):
        add(raw, 1)
    out: Dict[str, str] = {}
    if scores:
        out["primary_color"] = max(scores, key=scores.get)
    m = re.search(r"(?:^|[},\s])(?:body|html)\s*(?:,[^{]*)?\{[^}]*background(?:-color)?\s*:\s*([^;}]+)", css, re.I)
    bg = norm_color(m.group(1).strip().split()[0]) if m else None
    if bg:
        out["background_color"] = bg
    m = re.search(r"(?:^|[},\s])body\s*(?:,[^{]*)?\{[^}]*?(?<![-\w])color\s*:\s*([^;}]+)", css, re.I)
    fg = norm_color(m.group(1).strip()) if m else None
    if fg and contrast(fg, bg or "#FFFFFF") >= 4.5:
        out["text_color"] = fg
    return out


def pick_font(font_links: List[str], css: str) -> str:
    for href in font_links:
        q = parse_qs(urlparse(href).query)
        for fam in q.get("family", []):
            name = fam.split(":")[0].split("|")[0].replace("+", " ").strip()
            if name:
                return name
    for m in re.finditer(r"font-family\s*:\s*([^;}]+)", css, re.I):
        for part in m.group(1).split(","):
            name = part.strip().strip("'\"").strip()
            if name and name.lower() not in _GENERIC_FONTS and not name.lower().startswith(("var(", "__")):
                return name[:40]
    return ""


def _logo_candidates(soup, base: str) -> List[str]:
    found: List[Tuple[int, str]] = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        hint = " ".join([src, " ".join(img.get("class") or []), img.get("id") or "", img.get("alt") or ""]).lower()
        if "logo" in hint and src and not src.startswith("data:"):
            in_header = bool(img.find_parent(["header", "nav"]))
            found.append((0 if in_header else 1, urljoin(base, src)))
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel") or []).lower()
        href = link.get("href")
        if not href:
            continue
        if "apple-touch-icon" in rel:
            found.append((2, urljoin(base, href)))
        elif "icon" in rel:
            found.append((3, urljoin(base, href)))
    found.sort(key=lambda x: x[0])
    seen, out = set(), []
    for _, u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:6]


def voice_excerpt(soup, description: str = "") -> str:
    """A few real sentences from the site, as a starting voice sample."""
    parts = [description.strip()] if description else []
    for tag in soup.find_all(["h1", "h2", "p"]):
        text = re.sub(r"\s+", " ", tag.get_text(" ", strip=True))
        if (tag.name == "p" and len(text) >= 60) or (tag.name != "p" and 12 <= len(text) <= 120):
            if text not in parts:
                parts.append(text)
        if sum(len(p) for p in parts) > 900:
            break
    return "\n\n".join(p for p in parts if p)[:1200]


async def _describe_voice(name: str, excerpt: str) -> Dict[str, str]:
    """Ask the model for a usable description of how this business writes. Optional."""
    if not excerpt:
        return {}
    try:
        from ai import _call_llm
        raw = await _call_llm(
            "Here is text from a business's own website.\n\n"
            f"BUSINESS: {name}\nTEXT:\n{excerpt[:2500]}\n\n"
            "Return ONLY JSON with three keys:\n"
            '"tone": two short sentences a copywriter could follow to sound like this business '
            "(formality, energy, typical words, sentence length). Plain words.\n"
            '"audience": who they sell to, in under 15 words.\n'
            '"cta_label": the 2 to 5 word button text this business would use to get someone to sign up '
            "for their free live session, in their style.", max_tokens=400)
        data = json.loads(raw)
        return {k: str(data.get(k) or "").strip()[:300] for k in ("tone", "audience", "cta_label") if data.get(k)}
    except Exception as e:  # noqa: BLE001
        logger.info(f"voice description skipped: {e}")
        return {}


async def extract_from_website(url: str) -> Dict[str, Any]:
    """Read name, logo, colours, font and voice from a website. Missing pieces are left out."""
    import httpx
    from bs4 import BeautifulSoup

    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ShowUpAI-BrandKit/1.0; +https://showupai.live)"}
    async with httpx.AsyncClient(timeout=12, headers=headers, follow_redirects=False) as client:
        final, body, _ = await _get(client, url, 2_000_000)
        soup = BeautifulSoup(body.decode("utf-8", "ignore"), "html.parser")

        def meta(*names):
            for n in names:
                tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
                if tag and tag.get("content"):
                    return tag["content"].strip()
            return ""

        name = meta("og:site_name", "application-name")
        if not name and soup.title and soup.title.string:
            name = re.split(r"\s[|\-–—:·]\s", soup.title.string.strip())[0]
        description = meta("description", "og:description")

        css = "\n".join(s.get_text() for s in soup.find_all("style"))
        inline = " ".join(t.get("style", "") for t in soup.find_all(style=True))
        font_links = []
        sheets = []
        for link in soup.find_all("link", href=True):
            rel = " ".join(link.get("rel") or []).lower()
            href = urljoin(final, link["href"])
            if "fonts.googleapis.com" in href:
                font_links.append(href)
            elif "stylesheet" in rel:
                sheets.append(href)
        for href in sheets[:4]:
            try:
                _, data, _ = await _get(client, href, 1_500_000)
                css += "\n" + data.decode("utf-8", "ignore")
            except Exception as e:  # noqa: BLE001
                logger.info(f"stylesheet {href} skipped: {e}")
        for m in re.finditer(r"@import\s+url\(['\"]?(https://fonts\.googleapis\.com/[^'\")]+)", css):
            font_links.append(m.group(1))

        logo = None
        for cand in _logo_candidates(soup, final):
            if cand.lower().split("?")[0].endswith(".svg"):
                continue                       # Pillow can't draw SVG; a PNG/icon comes next
            try:
                _, data, ctype = await _get(client, cand, 3_000_000)
                if "svg" in ctype:
                    continue
                png = await asyncio.get_running_loop().run_in_executor(None, normalise_logo, data)
                from PIL import Image
                if min(Image.open(io.BytesIO(png)).size) >= 48:
                    logo = png
                    break
            except Exception as e:  # noqa: BLE001
                logger.info(f"logo candidate {cand} skipped: {e}")

    out: Dict[str, Any] = {"website": final.split("?")[0].rstrip("/")}
    if name:
        out["business_name"] = name.strip()[:80]
    out.update(pick_colors(meta("theme-color", "msapplication-TileColor"), css, inline))
    font = pick_font(font_links, css)
    if font:
        out["font"] = font
    excerpt = voice_excerpt(soup, description)
    if excerpt:
        out["voice_sample"] = excerpt
    out.update(await _describe_voice(out.get("business_name", ""), excerpt))
    if logo:
        out["logo_png"] = logo
    return out
