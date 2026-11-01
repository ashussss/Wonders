"""
ShowUpAI Image Generator — Professional Social Media Images
- Multi-page Carousel (6 slides, 1080x1080 each, returned as ZIP or first slide)
- Topic Infographic (1080x1920 vertical)  
- Quote Card (1080x1080)
- ShowUp Score OG Image (1200x630)
"""
import os, io, asyncio, logging, textwrap, zipfile
from typing import Optional, Tuple

logger = logging.getLogger("showup.image_gen")

# ── Font setup ───────────────────────────────────────
FONT_CANDIDATES_BOLD = [
    "/tmp/showup_fonts/Poppins-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
FONT_CANDIDATES_REG = [
    "/tmp/showup_fonts/Poppins-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

def _find_font(candidates):
    for p in candidates:
        if os.path.exists(p):
            return p
    try:
        import urllib.request
        os.makedirs("/tmp/showup_fonts", exist_ok=True)
        for name, url in [
            ("Poppins-Bold.ttf", "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf"),
            ("Poppins-Regular.ttf", "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf"),
        ]:
            path = f"/tmp/showup_fonts/{name}"
            if not os.path.exists(path):
                urllib.request.urlretrieve(url, path)
        return f"/tmp/showup_fonts/{candidates[0].split('/')[-1]}"
    except:
        return None

FONT_BOLD = _find_font(FONT_CANDIDATES_BOLD)
FONT_REG  = _find_font(FONT_CANDIDATES_REG)

# ── Colors ───────────────────────────────────────────
ORANGE = (234, 88, 12)
WHITE  = (255, 255, 255)
BLACK  = (10, 10, 10)
DARK   = (18, 18, 28)
GRAY   = (80, 80, 100)
LIGHT  = (240, 240, 248)
PURPLE = (124, 58, 237)

def _font(path, size):
    from PIL import ImageFont
    if path and os.path.exists(path):
        try: return ImageFont.truetype(path, size)
        except: pass
    try: return ImageFont.load_default(size=size)
    except: return ImageFont.load_default()

def _wrap_text(draw, text, font, max_width, x, y, fill, line_gap=8):
    """Draw wrapped text, return bottom y."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textbbox((0,0), test, font=font)[2] <= max_width:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += draw.textbbox((0,0), line, font=font)[3] + line_gap
    return y

def _rr(draw, xy, r, fill, outline=None, ow=2):
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=ow)

# ── Customer brand ───────────────────────────────────
# Webinar images are the customer's, so they wear the customer's Brand Kit: their
# colours, their logo (or name), their webinar's date line, and only a small
# "Powered by ShowUp AI" line. Without a kit they keep the ShowUp look.

def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _palette(brand: Optional[dict]) -> dict:
    t = (brand or {}).get("theme")
    if t:
        return {"bg": _rgb(t["bg"]), "fg": _rgb(t["fg"]), "muted": _rgb(t["muted"]),
                "accent": _rgb(t["accent"]), "soft": _rgb(t["soft"]), "on_accent": _rgb(t["on_accent"]),
                "branded": True}
    return {"bg": DARK, "fg": WHITE, "muted": (180, 180, 200), "accent": ORANGE, "soft": (34, 34, 48),
            "on_accent": WHITE, "branded": False}


async def brand_context(db, w: dict) -> dict:
    """Brand Kit + webinar facts the image makers need. Never raises."""
    out: dict = {"date_line": "", "title": (w.get("title") or "").strip()}
    try:
        import brand_kit
        from touch_visuals import footer_lines
        b = await brand_kit.resolve(db, w.get("owner_id") or "")
        out.update(theme=b.get("theme"), name=b.get("name") or "", tagline=b.get("tagline") or "",
                   powered_by=b.get("powered_by", True), cta=b.get("cta_label") or "")
        if b.get("logo_hash"):
            out["logo_png"] = await brand_kit.logo_png(db, w.get("owner_id") or "")
        out["date_line"] = footer_lines(w, False)[1]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"brand context failed: {e}")
    return out


def _mark(img, draw, brand: Optional[dict], P: dict, x: int, y: int, h: int = 56, max_w: int = 360,
          color=None) -> int:
    """Customer logo or name at (x, y), top-left anchored. Returns the right edge."""
    from PIL import Image
    b = brand or {}
    if b.get("logo_png"):
        try:
            logo = Image.open(io.BytesIO(b["logo_png"])).convert("RGBA")
            logo.thumbnail((max_w, h))
            img.paste(logo, (x, y + (h - logo.height) // 2), logo)
            return x + logo.width
        except Exception as e:  # noqa: BLE001
            logger.warning(f"logo unusable: {e}")
    name = b.get("name") or ("ShowUp AI" if not P["branded"] else "")
    if name:
        f = _font(FONT_BOLD, int(h * 0.6))
        draw.text((x, y + h // 2), name, font=f, fill=color or P["fg"], anchor="lm")
        return x + int(draw.textlength(name, font=f))
    return x


def _fit_font(draw, text, max_w, size, min_size=18, bold=True):
    while size > min_size:
        f = _font(FONT_BOLD if bold else FONT_REG, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return _font(FONT_BOLD if bold else FONT_REG, min_size)


def _powered(draw, brand: Optional[dict], P: dict, W: int, y: int, color=None):
    b = brand or {}
    if not b.get("powered_by", True):
        return
    from brand_kit import POWERED_BY_LINE
    draw.text((W - 40, y), POWERED_BY_LINE, font=_font(FONT_REG, 20), fill=color or P["muted"], anchor="rm")


# ── CAROUSEL SLIDE ───────────────────────────────────
def make_slide(slide_num: int, total: int, heading: str, body: str,
               is_cover: bool = False, is_last: bool = False, brand: Optional[dict] = None) -> bytes:
    from PIL import Image, ImageDraw
    W = H = 1080
    P = _palette(brand)
    b = brand or {}
    img = Image.new("RGB", (W, H), P["accent"] if is_last else P["bg"])
    draw = ImageDraw.Draw(img)

    if is_cover:
        _rr(draw, [0, 0, 10, H], 0, P["accent"])
        _mark(img, draw, b, P, 40, 50)
        draw.text((W - 40, 78), "SWIPE →", font=_font(FONT_BOLD, 28), fill=P["accent"], anchor="rm")
        f_title = _font(FONT_BOLD, 72 if len(heading) < 40 else 56)
        y = _wrap_text(draw, heading, f_title, W - 120, 40, 200, P["fg"], 14)
        _wrap_text(draw, body, _font(FONT_REG, 36), W - 120, 40, max(y + 40, 640), P["muted"], 8)
        if b.get("date_line"):
            _wrap_text(draw, b["date_line"], _font(FONT_BOLD, 30), W - 120, 40, H - 170, P["accent"], 6)
        _powered(draw, b, P, W, H - 40)

    elif is_last:
        on = P["on_accent"]
        _mark(img, draw, b, P, 80, 80, color=on)
        if P["branded"] or b.get("title"):
            cta = b.get("cta") or "Save your spot"
            draw.text((80, 260), cta, font=_font(FONT_BOLD, 88), fill=on)
            y = _wrap_text(draw, b.get("title") or "", _font(FONT_BOLD, 44), W - 160, 80, 420, on, 10)
            if b.get("date_line"):
                _wrap_text(draw, b["date_line"], _font(FONT_REG, 36), W - 160, 80, y + 30, on, 8)
            draw.text((80, H - 200), "Link in the post", font=_font(FONT_BOLD, 40), fill=on)
        else:
            draw.text((80, 200), "Ready to double your\nattendance?", font=_font(FONT_BOLD, 88), fill=on)
            draw.text((80, 600), "ShowUpAI writes your entire pre-webinar sequence.", font=_font(FONT_REG, 40), fill=on)
            draw.text((80, 720), "showupai.live", font=_font(FONT_BOLD, 48), fill=on)
        _powered(draw, b, P, W, H - 40, color=on)

    else:
        _rr(draw, [0, 0, 10, H], 0, P["accent"])
        _rr(draw, [40, 40, 110, 100], 30, P["accent"])
        draw.text((75, 70), f"{slide_num:02d}", font=_font(FONT_BOLD, 40), fill=P["on_accent"], anchor="mm")
        draw.text((125, 52), f"/ {total-2:02d}", font=_font(FONT_REG, 28), fill=P["muted"])
        f_h = _font(FONT_BOLD, 58 if len(heading) < 35 else 46)
        y = _wrap_text(draw, heading, f_h, W-100, 40, 140, P["fg"], 12)
        draw.line([(40, y+20), (W-40, y+20)], fill=P["accent"], width=3)
        _wrap_text(draw, body, _font(FONT_REG, 38), W-100, 40, y+50, P["fg"], 10)
        _mark(img, draw, b, P, 40, H - 110, h=48, max_w=260)
        dot_y = H - 86
        dot_x = W - 60 - total * 20
        for i in range(total):
            color = P["accent"] if i == slide_num else P["soft"]
            draw.ellipse([dot_x+i*20-6, dot_y-6, dot_x+i*20+6, dot_y+6], fill=color)
        _powered(draw, b, P, W, H - 40)

    buf = io.BytesIO()
    img.save(buf, "PNG", quality=95)
    return buf.getvalue()


async def make_carousel(title: str, audience: str = "", starts_at: str = "",
                        touch_type: str = "insight", brand: Optional[dict] = None) -> bytes:
    """Generate 6-slide carousel using Groq for content, return as ZIP."""
    # Generate slide content with Groq
    from groq import Groq as GroqClient
    groq_key = os.environ.get("GROQ_API_KEY", "")
    
    slides_content = []
    if groq_key:
        try:
            def _gen():
                g = GroqClient(api_key=groq_key)
                resp = g.chat.completions.create(
                    model="openai/gpt-oss-20b", extra_body={"reasoning_effort": "low"},
                    messages=[{"role": "user", "content": f"""Create a 4-slide LinkedIn carousel about: {title}
Audience: {audience or "webinar hosts"}

Return ONLY this JSON:
{{
  "slides": [
    {{"heading": "short heading max 40 chars", "body": "2-3 sentences of value max 150 chars"}},
    {{"heading": "...", "body": "..."}},
    {{"heading": "...", "body": "..."}},
    {{"heading": "...", "body": "..."}}
  ]
}}"""}],
                    max_tokens=2000,
                    temperature=0.7,
                )
                return resp.choices[0].message.content
            
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(None, _gen)
            import json, re
            m = re.search(r'{.*}', raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                slides_content = data.get("slides", [])
        except Exception as e:
            logger.error(f"Carousel content gen failed: {e}")
    
    # Fallback slides
    if not slides_content:
        slides_content = [
            {"heading": "Why it matters", "body": "What changes for you once this is sorted."},
            {"heading": "Where it goes wrong", "body": "The mistake most people make, and how to spot it early."},
            {"heading": "What works instead", "body": "A simple approach you can use straight away."},
            {"heading": "Go further, live", "body": "We walk through it step by step in the session."},
        ]
    
    total = len(slides_content) + 2  # cover + content + CTA
    
    # Generate all slides
    all_slides = []
    loop = asyncio.get_event_loop()
    
    # Cover
    cover = await loop.run_in_executor(None, make_slide, 0, total, title,
                                        f"For {audience}" if audience else "Swipe to learn more", True, False, brand)
    all_slides.append(("slide_01_cover.png", cover))
    
    # Content slides
    for i, s in enumerate(slides_content):
        slide = await loop.run_in_executor(None, make_slide, i+1, total,
                                           s["heading"], s["body"], False, False, brand)
        all_slides.append((f"slide_{i+2:02d}.png", slide))

    # CTA
    cta = await loop.run_in_executor(None, make_slide, total-1, total, "", "", False, True, brand)
    all_slides.append((f"slide_{total:02d}_cta.png", cta))

    # Pack into ZIP
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        for name, data in all_slides:
            zf.writestr(name, data)
    
    logger.info(f"Carousel: {len(all_slides)} slides generated")
    return zip_buf.getvalue()


# ── INFOGRAPHIC (Topic-based, 1080x1920) ─────────────
async def make_infographic(title: str, audience: str = "", starts_at: str = "",
                           touch_type: str = "case_study", brand: Optional[dict] = None) -> bytes:
    """Generate topic infographic with AI-generated key points."""
    from PIL import Image, ImageDraw
    
    # Generate points with Groq
    points = []
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        try:
            def _gen():
                from groq import Groq as G
                g = G(api_key=groq_key)
                resp = g.chat.completions.create(
                    model="openai/gpt-oss-20b", extra_body={"reasoning_effort": "low"},
                    messages=[{"role": "user", "content": f"""Create 5 key insights about: {title}
Audience: {audience or "professionals"}
Each insight: short heading (5 words max) + one sentence explanation (max 100 chars)

Return ONLY JSON:
{{"points": [{{"heading": "...", "detail": "..."}}]}}"""}],
                    max_tokens=2000, temperature=0.7,
                )
                return resp.choices[0].message.content
            
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(None, _gen)
            import json, re
            m = re.search(r'{.*}', raw, re.DOTALL)
            if m:
                points = json.loads(m.group()).get("points", [])
        except Exception as e:
            logger.error(f"Infographic content gen: {e}")
    
    if not points:
        points = [
            {"heading": "Why it matters", "detail": "What changes for you once this is sorted."},
            {"heading": "The common mistake", "detail": "Where most people go wrong, and how to spot it early."},
            {"heading": "What works instead", "detail": "A simple approach you can use straight away."},
            {"heading": "Go further, live", "detail": "We walk through it step by step in the session."},
        ]
    
    W, H = 1080, 1920
    P = _palette(brand)
    b = brand or {}
    img = Image.new("RGB", (W, H), P["bg"])
    draw = ImageDraw.Draw(img)
    on = P["on_accent"]

    # Header in the brand colour
    _rr(draw, [0, 0, W, 460], 0, P["accent"])
    _mark(img, draw, b, P, 50, 40, h=60, color=on)
    label = touch_type.upper().replace("_", " ")
    lf = _font(FONT_BOLD, 26)
    lw = int(draw.textlength(label, font=lf))
    draw.rounded_rectangle([W - 50 - lw - 40, 50, W - 50, 94], radius=22, outline=on, width=2)
    draw.text((W - 50 - lw - 20, 72), label, font=lf, fill=on, anchor="lm")
    f_title = _font(FONT_BOLD, 64 if len(title) < 35 else 50)
    y = _wrap_text(draw, title, f_title, W-100, 50, 150, on, 12)
    if audience:
        draw.text((50, min(y + 20, 405)), f"For: {audience}", font=_font(FONT_REG, 32), fill=on)

    # Points
    py = 510
    for i, pt in enumerate(points[:5]):
        _rr(draw, [50, py, W-50, py+220], 20, P["soft"])
        draw.ellipse([70, py+20, 130, py+80], fill=P["accent"])
        draw.text((100, py+50), str(i+1), font=_font(FONT_BOLD, 40), fill=on, anchor="mm")
        draw.text((150, py+20), pt.get("heading", ""), font=_font(FONT_BOLD, 40), fill=P["fg"])
        _wrap_text(draw, pt.get("detail", ""), _font(FONT_REG, 32), W-200, 150, py+75, P["muted"], 6)
        py += 240

    # Footer: the webinar, then the small ShowUp line
    draw.line([(50, H-210), (W-50, H-210)], fill=P["muted"], width=2)
    _wrap_text(draw, b.get("title") or title, _font(FONT_BOLD, 34), W-100, 50, H-190, P["fg"], 6)
    if b.get("date_line"):
        draw.text((50, H-110), b["date_line"], font=_fit_font(draw, b["date_line"], W - 100, 28), fill=P["accent"])
    elif starts_at:
        draw.text((50, H-110), starts_at[:10], font=_font(FONT_BOLD, 28), fill=P["accent"])
    _powered(draw, b, P, W, H - 40)

    buf = io.BytesIO()
    img.save(buf, "PNG", quality=95)
    return buf.getvalue()


# ── QUOTE CARD ───────────────────────────────────────
def make_quote_card(title: str, audience: str = "", starts_at: str = "",
                    touch_type: str = "thought_provoking", brand: Optional[dict] = None) -> bytes:
    from PIL import Image, ImageDraw
    W = H = 1080
    P = _palette(brand)
    b = brand or {}
    img = Image.new("RGB", (W, H), P["bg"])
    draw = ImageDraw.Draw(img)
    _mark(img, draw, b, P, 80, 60)
    draw.text((60, 90), "“", font=_font(FONT_BOLD, 200), fill=P["accent"])
    f = _font(FONT_BOLD, 68 if len(title) < 60 else 52)
    y = _wrap_text(draw, title, f, W-160, 80, 260, P["fg"], 16)
    draw.line([(80, y+40), (380, y+40)], fill=P["accent"], width=4)
    if audience:
        draw.text((80, y+65), f"For {audience}", font=_font(FONT_REG, 34), fill=P["muted"])
    _rr(draw, [0, H-150, W, H], 0, P["accent"])
    line = b.get("date_line") or ("Webinar attendance, boosted" if not P["branded"] else "")
    if line:
        draw.text((60, H-105), line, font=_fit_font(draw, line, W - 120, 32), fill=P["on_accent"], anchor="lm")
    _powered(draw, b, P, W, H - 40, color=P["on_accent"])

    buf = io.BytesIO()
    img.save(buf, "PNG", quality=95)
    return buf.getvalue()


async def make_carousel_preview(title: str, audience: str = "", starts_at: str = "",
                              touch_type: str = "insight", brand: Optional[dict] = None) -> bytes:
    """Generate carousel and return first content slide as PNG preview."""
    # Generate content slides with Groq
    groq_key = os.environ.get("GROQ_API_KEY", "")
    slides_content = []
    
    if groq_key:
        try:
            def _gen():
                from groq import Groq as G
                g = G(api_key=groq_key)
                resp = g.chat.completions.create(
                    model="openai/gpt-oss-20b", extra_body={"reasoning_effort": "low"},
                    messages=[{"role": "user", "content": f"""Create 4 LinkedIn carousel slides about: {title}
Audience: {audience or "webinar hosts"}
Return ONLY JSON:
{{"slides": [{{"heading": "max 40 chars", "body": "max 120 chars"}}]}}"""}],
                    max_tokens=2000, temperature=0.7,
                )
                return resp.choices[0].message.content
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(None, _gen)
            import json, re
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                slides_content = json.loads(m.group()).get("slides", [])
        except Exception as e:
            logger.error(f"Carousel Groq: {e}")

    if not slides_content:
        slides_content = [
            {"heading": "Why it matters", "body": "What changes for you once this is sorted."},
            {"heading": "Where it goes wrong", "body": "The mistake most people make, and how to spot it early."},
            {"heading": "What works instead", "body": "A simple approach you can use straight away."},
            {"heading": "Go further, live", "body": "We walk through it step by step in the session."},
        ]

    loop = asyncio.get_event_loop()
    total = len(slides_content) + 2

    # Return cover slide as preview
    cover = await loop.run_in_executor(None, make_slide, 0, total, title,
                                        f"For {audience}" if audience else "Swipe to learn more →", True, False, brand)
    return cover


# ── MASTER FUNCTION ──────────────────────────────────
async def generate_webinar_social_image(
    webinar_id: str, title: str, audience: str = "",
    starts_at: str = "", touch_type: str = "carousel", extra: dict = None,
    brand: Optional[dict] = None,
) -> Optional[Tuple[bytes, str]]:
    try:
        image_type = (extra or {}).get("image_type", touch_type)
        loop = asyncio.get_event_loop()
        
        if image_type == "infographic":
            img_bytes = await make_infographic(title, audience, starts_at, touch_type, brand)
            mime = "image/png"
        elif image_type == "quote_card":
            quote = ((extra or {}).get("quote") or title).strip()
            img_bytes = await loop.run_in_executor(None, make_quote_card, quote, audience, starts_at, touch_type, brand)
            mime = "image/png"
        elif image_type == "carousel":
            # Return first slide as PNG preview (full ZIP available separately)
            img_bytes = await make_carousel_preview(title, audience, starts_at, touch_type, brand)
            mime = "image/png"
        else:
            img_bytes = await make_infographic(title, audience, starts_at, touch_type, brand)
            mime = "image/png"
        
        if not img_bytes:
            return None
        
        # Store in GridFS
        try:
            from database import social_images_fs
            async for doc in social_images_fs.find({"metadata.webinar_id": webinar_id}):
                await social_images_fs.delete(doc._id)
            await social_images_fs.upload_from_stream(
                f"social-{webinar_id}.{'zip' if mime=='application/zip' else 'png'}",
                img_bytes,
                metadata={"webinar_id": webinar_id, "image_type": image_type, "mime": mime}
            )
        except Exception as e:
            logger.warning(f"GridFS store failed: {e}")
        
        logger.info(f"Image generated: {image_type}, {len(img_bytes)} bytes")
        return img_bytes, mime
    except Exception as e:
        logger.error(f"Image generation failed: {e}", exc_info=True)
        return None


async def generate_showup_score_image(webinar_id: str, score: int, title: str) -> Optional[Tuple[bytes, str]]:
    try:
        from PIL import Image, ImageDraw
        W, H = 1200, 630
        img = Image.new("RGB", (W, H), DARK)
        draw = ImageDraw.Draw(img)
        for i in range(H):
            draw.line([(0,i),(W,i)], fill=(int(18+20*(i/H)), int(18+8*(i/H)), int(28+30*(i/H))))
        
        cx, cy, r = 280, 315, 200
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=ORANGE, width=8)
        score_str = str(score)
        f_s = _font(FONT_BOLD, 120)
        sw = draw.textbbox((0,0), score_str, font=f_s)[2]
        draw.text((cx-sw//2, cy-75), score_str, font=f_s, fill=ORANGE)
        draw.text((cx-28, cy+55), "/100", font=_font(FONT_REG, 40), fill=(180,180,200))
        draw.text((cx-80, cy+110), "ShowUp Score", font=_font(FONT_BOLD, 32), fill=(200,200,220))
        
        f_t = _font(FONT_BOLD, 52 if len(title) < 40 else 42)
        _wrap_text(draw, title, f_t, W-620, 560, 80, WHITE, 10)
        label = "Excellent" if score>=80 else "Good" if score>=60 else "Needs Work" if score>=40 else "At Risk"
        color = (16,185,129) if score>=80 else (245,158,11) if score>=60 else (239,68,68)
        draw.text((560, 420), label, font=_font(FONT_BOLD, 48), fill=color)
        draw.line([(560,500),(W-60,500)], fill=ORANGE, width=2)
        draw.text((560, 520), "⚡ ShowUpAI", font=_font(FONT_BOLD, 36), fill=ORANGE)
        
        buf = io.BytesIO()
        img.save(buf, "PNG", quality=95)
        return buf.getvalue(), "image/png"
    except Exception as e:
        logger.error(f"Score image: {e}")
        return None
