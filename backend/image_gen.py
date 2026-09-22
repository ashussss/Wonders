"""
ShowUp.ai Image Generator — Professional Social Media Images
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

# ── CAROUSEL SLIDE ───────────────────────────────────
def make_slide(slide_num: int, total: int, heading: str, body: str,
               is_cover: bool = False, is_last: bool = False) -> bytes:
    from PIL import Image, ImageDraw
    W = H = 1080
    img = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)

    # Background gradient
    for i in range(H):
        r2 = i / H
        draw.line([(0,i),(W,i)], fill=(
            int(18 + 30*r2), int(18 + 10*r2), int(28 + 40*r2)
        ))

    if is_cover:
        # Cover slide — big title
        _rr(draw, [0, 0, 10, H], 0, ORANGE)
        f_num = _font(FONT_BOLD, 28)
        draw.text((40, 60), "SWIPE →", font=f_num, fill=ORANGE)
        f_title = _font(FONT_BOLD, 72 if len(heading) < 40 else 56)
        _wrap_text(draw, heading, f_title, W-120, 40, 160, WHITE, 14)
        f_sub = _font(FONT_REG, 36)
        _wrap_text(draw, body, f_sub, W-120, 40, 700, (180,180,200), 8)
        # Logo
        _rr(draw, [40, H-110, 40+200, H-50], 30, ORANGE)
        draw.text((60, H-98), "⚡ ShowUp.ai", font=_font(FONT_BOLD, 32), fill=WHITE)

    elif is_last:
        # CTA slide
        _rr(draw, [0, 0, W, H], 0, ORANGE)
        f_big = _font(FONT_BOLD, 88)
        draw.text((80, 200), "Ready to double your\nattendance?", font=f_big, fill=WHITE)
        f_sub = _font(FONT_REG, 40)
        draw.text((80, 600), "ShowUp.ai writes your entire pre-webinar sequence.", font=f_sub, fill=(255,220,200))
        draw.text((80, 720), "showupai.app", font=_font(FONT_BOLD, 48), fill=WHITE)

    else:
        # Content slide
        _rr(draw, [0, 0, 10, H], 0, ORANGE)
        # Slide number
        _rr(draw, [40, 40, 110, 100], 30, ORANGE)
        draw.text((55, 50), f"{slide_num:02d}", font=_font(FONT_BOLD, 40), fill=WHITE)
        draw.text((125, 52), f"/ {total-2:02d}", font=_font(FONT_REG, 28), fill=(120,120,140))
        # Heading
        f_h = _font(FONT_BOLD, 58 if len(heading) < 35 else 46)
        y = _wrap_text(draw, heading, f_h, W-100, 40, 140, WHITE, 12)
        # Divider
        draw.line([(40, y+20), (W-40, y+20)], fill=ORANGE, width=3)
        # Body
        f_b = _font(FONT_REG, 38)
        _wrap_text(draw, body, f_b, W-100, 40, y+50, (210,210,230), 10)
        # Page indicator dots
        dot_y = H - 50
        dot_x = W//2 - (total*20)//2
        for i in range(total):
            color = ORANGE if i == slide_num else (60,60,80)
            draw.ellipse([dot_x+i*20-6, dot_y-6, dot_x+i*20+6, dot_y+6], fill=color)

    buf = io.BytesIO()
    img.save(buf, "PNG", quality=95)
    return buf.getvalue()


async def make_carousel(title: str, audience: str = "", starts_at: str = "",
                        touch_type: str = "insight") -> bytes:
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
                    model="llama-3.1-8b-instant",
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
                    max_tokens=600,
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
            {"heading": "The Problem", "body": "Most webinar hosts lose 70% of registrants before the event even starts."},
            {"heading": "The Root Cause", "body": "People aren't forgetting your webinar. They're losing the reason to care."},
            {"heading": "The Fix", "body": "Send value, not reminders. Insight → Poll → Case Study → Join link."},
            {"heading": "The Result", "body": "Attendance jumps from 31% to 62%+ with the right 8-touch sequence."},
        ]
    
    total = len(slides_content) + 2  # cover + content + CTA
    
    # Generate all slides
    all_slides = []
    loop = asyncio.get_event_loop()
    
    # Cover
    cover = await loop.run_in_executor(None, make_slide, 0, total, title, 
                                        f"For {audience}" if audience else "Swipe to learn more", True, False)
    all_slides.append(("slide_01_cover.png", cover))
    
    # Content slides
    for i, s in enumerate(slides_content):
        slide = await loop.run_in_executor(None, make_slide, i+1, total,
                                           s["heading"], s["body"], False, False)
        all_slides.append((f"slide_{i+2:02d}.png", slide))
    
    # CTA
    cta = await loop.run_in_executor(None, make_slide, total-1, total, "", "", False, True)
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
                           touch_type: str = "case_study") -> bytes:
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
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": f"""Create 5 key insights about: {title}
Audience: {audience or "professionals"}
Each insight: short heading (5 words max) + one sentence explanation (max 100 chars)

Return ONLY JSON:
{{"points": [{{"heading": "...", "detail": "..."}}]}}"""}],
                    max_tokens=400, temperature=0.7,
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
            {"heading": "The Challenge", "detail": "70% of webinar registrants never show up to the live event."},
            {"heading": "Root Cause", "detail": "Reminders don't re-engage — you need reasons, not repetition."},
            {"heading": "The Solution", "detail": "8-touch value sequence from registration to post-event."},
            {"heading": "Key Channels", "detail": "Email, LinkedIn, WhatsApp, Circle.so — all coordinated."},
            {"heading": "The Result", "detail": "Average attendance jumps from 31% to 62%+ consistently."},
        ]
    
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    
    # Orange header
    _rr(draw, [0, 0, W, 420], 0, ORANGE)
    draw.text((50, 40), "⚡ ShowUp.ai", font=_font(FONT_BOLD, 36), fill=(255,220,200))
    _rr(draw, [50, 85, 280, 125], 20, (180,60,5))
    draw.text((65, 90), touch_type.upper().replace("_"," "), font=_font(FONT_BOLD, 28), fill=WHITE)
    f_title = _font(FONT_BOLD, 64 if len(title) < 35 else 50)
    _wrap_text(draw, title, f_title, W-100, 50, 150, WHITE, 12)
    if audience:
        draw.text((50, 375), f"For: {audience}", font=_font(FONT_REG, 32), fill=(255,200,160))
    
    # Stats bar
    stats = [("62%+", "Attendance"), ("8", "Touches"), ("6", "Channels")]
    for i, (val, lbl) in enumerate(stats):
        x = 50 + i*340
        _rr(draw, [x, 440, x+310, 560], 16, LIGHT)
        draw.text((x+20, 450), val, font=_font(FONT_BOLD, 64), fill=ORANGE)
        draw.text((x+20, 525), lbl, font=_font(FONT_REG, 28), fill=GRAY)
    
    # Points
    py = 590
    colors = [ORANGE, PURPLE, (16,185,129), (245,158,11), (239,68,68)]
    for i, pt in enumerate(points[:5]):
        _rr(draw, [50, py, W-50, py+220], 20, LIGHT)
        # Number circle
        c = colors[i % len(colors)]
        draw.ellipse([70, py+20, 130, py+80], fill=c)
        draw.text((85, py+28), str(i+1), font=_font(FONT_BOLD, 44), fill=WHITE)
        # Text
        draw.text((150, py+20), pt["heading"], font=_font(FONT_BOLD, 40), fill=BLACK)
        _wrap_text(draw, pt["detail"], _font(FONT_REG, 32), W-200, 150, py+75, GRAY, 6)
        # Color bar on left
        _rr(draw, [50, py, 58, py+220], 4, c)
        py += 240
    
    # Footer
    _rr(draw, [0, H-120, W, H], 0, DARK)
    draw.text((50, H-95), "⚡ showupai.app", font=_font(FONT_BOLD, 44), fill=ORANGE)
    if starts_at:
        draw.text((W-200, H-85), starts_at[:10], font=_font(FONT_REG, 28), fill=(140,140,160))
    
    buf = io.BytesIO()
    img.save(buf, "PNG", quality=95)
    return buf.getvalue()


# ── QUOTE CARD ───────────────────────────────────────
def make_quote_card(title: str, audience: str = "", starts_at: str = "",
                    touch_type: str = "thought_provoking") -> bytes:
    from PIL import Image, ImageDraw
    W = H = 1080
    img = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)
    for i in range(H):
        r2 = i/H
        draw.line([(0,i),(W,i)], fill=(int(18+30*r2), int(18+8*r2), int(28+15*r2)))
    
    draw.text((50, -30), "“", font=_font(FONT_BOLD, 200), fill=ORANGE)
    f = _font(FONT_BOLD, 68 if len(title) < 60 else 52)
    y = _wrap_text(draw, title, f, W-140, 80, 180, WHITE, 16)
    draw.text((W-160, y-20), "”", font=_font(FONT_BOLD, 160), fill=ORANGE)
    draw.line([(80, y+50), (380, y+50)], fill=ORANGE, width=4)
    if audience:
        draw.text((80, y+75), f"For {audience}", font=_font(FONT_REG, 34), fill=(200,150,100))
    _rr(draw, [0, H-110, W, H], 0, ORANGE)
    draw.text((50, H-95), "⚡ ShowUp.ai — webinar attendance, boosted", font=_font(FONT_BOLD, 38), fill=WHITE)
    
    buf = io.BytesIO()
    img.save(buf, "PNG", quality=95)
    return buf.getvalue()


async def make_carousel_preview(title: str, audience: str = "", starts_at: str = "",
                              touch_type: str = "insight") -> bytes:
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
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": f"""Create 4 LinkedIn carousel slides about: {title}
Audience: {audience or "webinar hosts"}
Return ONLY JSON:
{{"slides": [{{"heading": "max 40 chars", "body": "max 120 chars"}}]}}"""}],
                    max_tokens=500, temperature=0.7,
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
            {"heading": "The Problem", "body": "70% of webinar registrants never show up to the live event."},
            {"heading": "Root Cause", "body": "People lose the reason to care between registration and the event."},
            {"heading": "The Fix", "body": "Send value not reminders — insight, poll, case study, join link."},
            {"heading": "The Result", "body": "Attendance jumps from 31% to 62%+ with right 8-touch sequence."},
        ]

    loop = asyncio.get_event_loop()
    total = len(slides_content) + 2

    # Return cover slide as preview
    cover = await loop.run_in_executor(None, make_slide, 0, total, title,
                                        f"For {audience}" if audience else "Swipe to learn more →", True, False)
    return cover


# ── MASTER FUNCTION ──────────────────────────────────
async def generate_webinar_social_image(
    webinar_id: str, title: str, audience: str = "",
    starts_at: str = "", touch_type: str = "carousel", extra: dict = None
) -> Optional[Tuple[bytes, str]]:
    try:
        image_type = (extra or {}).get("image_type", touch_type)
        loop = asyncio.get_event_loop()
        
        if image_type == "infographic":
            img_bytes = await make_infographic(title, audience, starts_at, touch_type)
            mime = "image/png"
        elif image_type == "quote_card":
            img_bytes = await loop.run_in_executor(None, make_quote_card, title, audience, starts_at, touch_type)
            mime = "image/png"
        elif image_type == "carousel":
            # Return first slide as PNG preview (full ZIP available separately)
            img_bytes = await make_carousel_preview(title, audience, starts_at, touch_type)
            mime = "image/png"
        else:
            img_bytes = await make_infographic(title, audience, starts_at, touch_type)
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
        draw.text((560, 520), "⚡ ShowUp.ai", font=_font(FONT_BOLD, 36), fill=ORANGE)
        
        buf = io.BytesIO()
        img.save(buf, "PNG", quality=95)
        return buf.getvalue(), "image/png"
    except Exception as e:
        logger.error(f"Score image: {e}")
        return None
