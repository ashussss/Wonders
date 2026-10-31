"""The card that goes with each value touch: tips, a case study, a poll, a checklist.

Each card shows the touch's piece of the webinar's content kit (ai.TOUCH_ASSET) and,
in the footer, the webinar title, date and host, so the reminder rides on something
people would save or share. Cards are the host's content, so they carry no ShowUpAI
branding. 1080x1350 JPEG: the 4:5 shape LinkedIn, Facebook and Instagram all show in
full, and Instagram only accepts JPEG.

Cards are rendered on first use and re-rendered only when what they show changes
(kit edits, a new date), keyed by a hash of the card's content.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from ai import TOUCH_ASSET
from touch_render import parse_start, values, webinar_tz

logger = logging.getLogger("showup.touch_visuals")

W, H, PAD = 1080, 1350, 80
POST_EVENT = {10, 11}

TAGS = {
    "problem": "THE PROBLEM",
    "insights": "TRY THIS TODAY",
    "poll": "QUICK POLL",
    "story": "CASE STUDY",
    "agenda": "WHAT WE'LL COVER",
    "myth": "MYTH VS TRUTH",
    "checklist": "BEFORE THE SESSION",
    "takeaways": "KEY TAKEAWAYS",
}


def card_spec(touch_num: int, kit: Optional[Dict[str, Any]], w: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """What the card for this touch shows, or None when the touch has no card (or no content)."""
    kind = TOUCH_ASSET.get(touch_num)
    if touch_num == 9 or not kind:          # one-hour reminder stays a short text
        return None
    data = (kit or {}).get(kind)
    if not data:
        return None
    if kind == "checklist" and touch_num == 8:
        tag = "BEFORE TOMORROW"
    else:
        tag = TAGS[kind]
    return {"kind": kind, "tag": tag, "data": data, "footer": footer_lines(w, touch_num in POST_EVENT),
            "seed": w.get("id") or w.get("title") or ""}


def footer_lines(w: Dict[str, Any], post_event: bool) -> Tuple[str, str]:
    v = values(w)
    host = f"with {v['speaker']}" if v["speaker"] else ""
    if post_event:
        sub = ", ".join(x for x in ("Recording available", host) if x)
    else:
        start = parse_start(w)
        when = ""
        if start:
            local = start.astimezone(webinar_tz(w))
            when = f"{local:%a} {local.day} {local:%b}, " + f"{local:%I:%M %p}".lstrip("0") + f" {local.tzname()}"
        sub = " · ".join(x for x in ("Free live session", when, host) if x)
    return (w.get("title") or "").strip(), sub


def spec_hash(spec: Dict[str, Any]) -> str:
    return hashlib.md5(json.dumps(spec, sort_keys=True).encode()).hexdigest()


# ── drawing ──────────────────────────────────────────────────────────────────

def _colors(seed: str):
    import social_images as si
    t = si._theme(seed)
    accent = t["accent"] if t["accent"] != "#111111" else t["fg"]
    on_accent = "#FFFFFF" if t["accent"] not in ("#FFFFFF",) else "#111111"
    if t["bg"].upper() == "#EA580C":     # orange theme: accent is black, numbers read white on it
        on_accent = "#FFFFFF"
    return t, accent, on_accent


def _tag(d, si, text, accent):
    f = si._font("semi", 26)
    tw = int(d.textlength(text, font=f))
    d.rounded_rectangle([PAD, PAD, PAD + tw + 44, PAD + 50], radius=25, outline=si._hex(accent), width=3)
    d.text((PAD + 22, PAD + 11), text, font=f, fill=si._hex(accent))
    return PAD + 50


def _footer(d, si, t, accent, lines) -> int:
    """Draws the webinar line at the bottom and returns the y where content must stop."""
    title, sub = lines
    top = H - PAD - 120
    d.line([(PAD, top), (W - PAD, top)], fill=si._hex(t["muted"], 120), width=2)
    tf, tl = si._fit(d, title, "bold", W - 2 * PAD, 80, 34, 24, max_lines=2, lh=1.2)
    y = si._text_block(d, title, tf, PAD, top + 22, W - 2 * PAD, si._hex(t["fg"]), tl, max_lines=2)
    sf, _ = si._fit(d, sub, "semi", W - 2 * PAD, 34, 26, 18, max_lines=1)
    d.text((PAD, y + 6), sub, font=sf, fill=si._hex(accent))
    return top - 30


def _rows(d, si, t, accent, on_accent, rows: List[Tuple[str, str]], y0: int, y1: int, marker: str = "num"):
    """Numbered or checkbox rows, each a heading with an optional detail line."""
    rows = rows[:5]
    gap = 22
    row_h = max(110, min(230, (y1 - y0 - gap * (len(rows) - 1)) // max(1, len(rows))))
    text_x, text_w = PAD + 120, W - 2 * PAD - 150
    for i, (head, detail) in enumerate(rows):
        top = y0 + i * (row_h + gap)
        d.rounded_rectangle([PAD, top, W - PAD, top + row_h], radius=22, fill=si._hex(t["soft"]))
        cx, cy = PAD + 58, top + row_h // 2
        if marker == "check":
            d.rounded_rectangle([cx - 26, cy - 26, cx + 26, cy + 26], radius=8, outline=si._hex(accent), width=5)
        else:
            d.ellipse([cx - 32, cy - 32, cx + 32, cy + 32], fill=si._hex(accent))
            d.text((cx, cy), marker[i] if marker != "num" else str(i + 1), font=si._font("bold", 32),
                   fill=si._hex(on_accent), anchor="mm")
        if detail:
            hf, hl = si._fit(d, head, "bold", text_w, row_h * 0.45, 36, 26, max_lines=2, lh=1.15)
            hlines = si._wrap(d, head, hf, text_w)[:2]
            df, dl = si._fit(d, detail, "reg", text_w, row_h - 36 - hl * len(hlines), 28, 20, max_lines=3, lh=1.25)
            dlines = si._wrap(d, detail, df, text_w)[:3]
            ty = cy - (hl * len(hlines) + 6 + dl * len(dlines)) // 2
            ty = si._text_block(d, head, hf, text_x, ty, text_w, si._hex(t["fg"]), hl, max_lines=2) + 6
            si._text_block(d, detail, df, text_x, ty, text_w, si._hex(t["muted"]), dl, max_lines=3)
        else:
            hf, hl = si._fit(d, head, "semi", text_w, row_h - 40, 38, 24, max_lines=3, lh=1.22)
            lines = si._wrap(d, head, hf, text_w)[:3]
            si._text_block(d, head, hf, text_x, cy - hl * len(lines) // 2, text_w, si._hex(t["fg"]), hl, max_lines=3)


def _headline(d, si, t, text, y, max_h, start=60, stop=38, lines=4):
    f, lh = si._fit(d, text, "bold", W - 2 * PAD, max_h, start, stop, max_lines=lines, lh=1.15)
    return si._text_block(d, text, f, PAD, y, W - 2 * PAD, si._hex(t["fg"]), lh, max_lines=lines)


def _panel(d, si, t, label, text, top, bottom, label_color, fill, text_kind="semi", start=40):
    d.rounded_rectangle([PAD, top, W - PAD, bottom], radius=24, fill=fill)
    d.text((PAD + 40, top + 32), label, font=si._font("bold", 26), fill=label_color)
    f, lh = si._fit(d, text, text_kind, W - 2 * PAD - 80, bottom - top - 110, start, 24, max_lines=5, lh=1.25)
    si._text_block(d, text, f, PAD + 40, top + 82, W - 2 * PAD - 80, si._hex(t["fg"]), lh, max_lines=5)


def render_card(spec: Dict[str, Any]) -> bytes:
    from PIL import Image, ImageDraw
    import social_images as si

    t, accent, on_accent = _colors(spec["seed"])
    img = Image.new("RGBA", (W, H), si._hex(t["bg"]))
    d = ImageDraw.Draw(img)
    y = _tag(d, si, spec["tag"], accent) + 50
    bottom = _footer(d, si, t, accent, spec["footer"])
    kind, data = spec["kind"], spec["data"]

    if kind == "problem":
        y = _headline(d, si, t, data["hook"], y, 520, 72, 44, 6) + 40
        if data.get("example"):
            d.line([(PAD, y), (PAD + 120, y)], fill=si._hex(accent), width=6)
            f, lh = si._fit(d, data["example"], "reg", W - 2 * PAD, bottom - y - 40, 42, 24, max_lines=6, lh=1.3)
            si._text_block(d, data["example"], f, PAD, y + 36, W - 2 * PAD, si._hex(t["muted"]), lh, max_lines=6)
    elif kind == "insights":
        n = len(data[:4])
        y = _headline(d, si, t, f"{n} things you can try today", y, 90, 56, 40, 1) + 36
        _rows(d, si, t, accent, on_accent, [(i["heading"], i.get("detail", "")) for i in data[:4]], y, bottom)
    elif kind == "poll":
        y = _headline(d, si, t, data["question"], y, 340, 60, 38, 5) + 40
        opts = data["options"][:4]
        _rows(d, si, t, accent, on_accent, [(o, "") for o in opts], y, min(bottom - 70, y + 150 * len(opts)), marker="ABCD")
        d.text((PAD, bottom - 40), "Comment or reply with your letter", font=si._font("semi", 32),
               fill=si._hex(accent), anchor="lm")
    elif kind == "story":
        parts = [("WHERE THEY STARTED", data["before"]), ("WHAT CHANGED", data["change"]), ("THE RESULT", data["after"])]
        lesson_h = 120 if data.get("lesson") else 0
        gap = 24
        ph = (bottom - y - lesson_h - gap * 3) // 3
        for i, (label, text) in enumerate(parts):
            top = y + i * (ph + gap)
            _panel(d, si, t, label, text, top, top + ph, si._hex(accent), si._hex(t["soft"]))
        if lesson_h:
            ly = y + 3 * (ph + gap)
            f, lh = si._fit(d, data["lesson"], "bold", W - 2 * PAD, lesson_h, 40, 26, max_lines=2, lh=1.2)
            si._text_block(d, data["lesson"], f, PAD, ly + 10, W - 2 * PAD, si._hex(accent), lh, max_lines=2)
    elif kind == "myth":
        mid = y + (bottom - y) // 2 - 12
        _panel(d, si, t, "MYTH", data["myth"], y, mid, si._hex(t["muted"]), si._hex(t["soft"]), start=54)
        d2 = ImageDraw.Draw(img)
        d2.rounded_rectangle([PAD, mid + 24, W - PAD, bottom], radius=24, outline=si._hex(accent), width=4)
        d2.text((PAD + 40, mid + 56), "TRUTH", font=si._font("bold", 26), fill=si._hex(accent))
        f, lh = si._fit(d2, data["truth"], "bold", W - 2 * PAD - 80, bottom - mid - 140, 54, 26, max_lines=6, lh=1.25)
        si._text_block(d2, data["truth"], f, PAD + 40, mid + 106, W - 2 * PAD - 80, si._hex(t["fg"]), lh, max_lines=6)
    else:   # agenda, checklist, takeaways
        heads = {"agenda": "In this session", "checklist": "Have these ready", "takeaways": "Do these this week"}
        y = _headline(d, si, t, heads[kind], y, 90, 56, 40, 1) + 36
        _rows(d, si, t, accent, on_accent, [(x, "") for x in data[:5]], y, bottom,
              marker="check" if kind == "checklist" else "num")
    return si._jpeg(img)


# ── storage ──────────────────────────────────────────────────────────────────

COLLECTION = "touch_visuals"


async def ensure_visual(db, bucket, t: Dict[str, Any], w: Dict[str, Any],
                        kit: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """The stored card for this touch, rendering it if it's missing or out of date."""
    if TOUCH_ASSET.get(t.get("touch_num")) is None:
        return None
    if kit is None:
        from ai import load_kit
        kit = await load_kit(w["id"])
    spec = card_spec(t["touch_num"], kit, w)
    if not spec:
        return None
    h = spec_hash(spec)
    row = await db[COLLECTION].find_one({"touch_id": t["id"]}, {"_id": 0})
    if row and row.get("hash") == h:
        return row
    try:
        jpeg = await asyncio.get_running_loop().run_in_executor(None, render_card, spec)
    except Exception as e:  # noqa: BLE001
        logger.error(f"touch card {t['id']} ({spec['kind']}) failed: {e}", exc_info=True)
        return row
    file_id = await bucket.upload_from_stream(f"touch-{t['id']}.jpg", jpeg,
                                              metadata={"touch_id": t["id"], "mime_type": "image/jpeg"})
    if row and row.get("file_id"):
        try:
            await bucket.delete(row["file_id"])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"old touch card delete failed: {e}")
    new = {"touch_id": t["id"], "webinar_id": t["webinar_id"], "owner_id": t.get("owner_id") or w.get("owner_id"),
           "kind": spec["kind"], "hash": h, "file_id": file_id}
    await db[COLLECTION].update_one({"touch_id": t["id"]}, {"$set": new}, upsert=True)
    return new


def visual_url(base: str, row: Optional[Dict[str, Any]]) -> Optional[str]:
    if not row or not base:
        return None
    return f"{base.rstrip('/')}/api/touches/{row['touch_id']}/visual.jpg?v={row['hash'][:8]}"


def has_visual(touch_num: int) -> bool:
    return touch_num in TOUCH_ASSET and touch_num != 9
