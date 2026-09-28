"""AI illustration for each blog post's cover, stored in Mongo.

Providers (tried in COVER_ART_PROVIDERS order): Cloudflare Workers AI FLUX.1 schnell (free daily allowance),
then Gemini image models (paid-only).

The cover endpoint composites it with the brand layout (title, tag, logo). If generation fails
(no billing on the Gemini key, model unavailable), covers fall back to topic-matched drawn motifs.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

from bson import Binary

from database import db

logger = logging.getLogger("showup.cover_art")

# Separate key allowed so only image generation sits on a billed Google project
GEMINI_API_KEY = os.environ.get("GEMINI_IMAGE_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
IMAGE_MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_IMAGE_MODELS", "gemini-3.1-flash-lite-image,gemini-3.1-flash-image,gemini-3.1-flash-image-preview"
).split(",") if m.strip()]
COVER_ART_ENABLED = os.environ.get("COVER_ART_ENABLED", "true").lower() == "true"
# Free option: Cloudflare Workers AI (10,000 Neurons/day on every plan, hard stop when used up, no card needed).
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
CLOUDFLARE_IMAGE_MODEL = os.environ.get("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
# Order to try; providers without credentials are skipped
PROVIDERS = [p.strip() for p in os.environ.get("COVER_ART_PROVIDERS", "cloudflare").split(",") if p.strip()]


def providers_available() -> list:
    out = []
    for p in PROVIDERS:
        if p == "cloudflare" and CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN:
            out.append(p)
        elif p == "gemini" and GEMINI_API_KEY:
            out.append(p)
    return out

SCENES = [
    (("sms", "whatsapp", "text message"), "a person glancing at a smartphone showing a friendly reminder message bubble, a laptop with a live webinar in the background"),
    (("email", "newsletter", "inbox"), "a tidy email inbox visualised as floating envelopes flowing towards a laptop that shows a live webinar"),
    (("follow up", "follow-up", "replay", "no show", "no-show"), "a webinar recording being sent to people who missed the live session, envelopes and a play button returning to them"),
    (("zoom", "video", "live", "teams"), "a grid of video call tiles with happy attendees joining a live webinar, the host waving"),
    (("linkedin", "social", "post"), "a professional social media feed with an event card, people engaging with likes and comments"),
    (("calendar", "time", "when", "advance", "schedule"), "a large desk calendar with one date circled, a clock and a laptop ready for a webinar"),
    (("rate", "average", "benchmark", "statistic", "tracking", "ratio"), "an analytics dashboard with rising bar charts and a filled webinar room"),
    (("strategy", "marketing", "funnel", "registration", "promot"), "a marketing funnel turning registrants into a full webinar audience"),
    (("reminder", "how many"), "a sequence of gentle notification bells lined up along a timeline leading to a webinar start"),
    (("software", "tool", "automat"), "a clean automation workflow of connected cards (email, chat, calendar) leading to a full virtual event"),
]


def build_prompt(title: str, keyword: str, excerpt: str = "") -> str:
    k = f"{keyword} {title}".lower()
    scene = next((s for words, s in SCENES if any(w in k for w in words)),
                 "a webinar host presenting on a laptop while a grid of attendees joins, calendar and notification icons floating")
    return (
        f"Editorial illustration for a B2B blog article titled \"{title}\". "
        f"Scene: {scene}. "
        f"{('Idea to convey: ' + excerpt[:220] + '. ') if excerpt else ''}"
        "Style: modern flat vector illustration with soft gradients and subtle grain, warm orange (#EA580C), charcoal "
        "and cream palette, clean composition, generous negative space, friendly diverse people where relevant. "
        "Portrait composition, main subject centred. Absolutely no text, letters, numbers, words, logos, UI labels or "
        "watermarks anywhere in the image."
    )


def _generate_cloudflare(prompt: str):
    import base64
    import httpx

    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{CLOUDFLARE_IMAGE_MODEL}"
    r = httpx.post(url, headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
                   json={"prompt": prompt[:2000], "steps": 8}, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"cloudflare {r.status_code}: {r.text[:200]}")
    ctype = r.headers.get("content-type", "")
    if ctype.startswith("image/"):
        return r.content, CLOUDFLARE_IMAGE_MODEL
    j = r.json()
    img = (j.get("result") or {}).get("image")
    if not img:
        raise RuntimeError(f"cloudflare: no image in response {str(j)[:200]}")
    return base64.b64decode(img), CLOUDFLARE_IMAGE_MODEL


def _generate(prompt: str):
    errors = []
    for p in providers_available():
        try:
            if p == "cloudflare":
                return _generate_cloudflare(prompt)
            if p == "gemini":
                return _generate_gemini(prompt)
        except Exception as e:
            errors.append(f"{p}: {str(e)[:160]}")
    raise RuntimeError("; ".join(errors) or "no image provider configured")


def _generate_gemini(prompt: str):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    last = None
    for model in IMAGE_MODELS:
        for with_ratio in (True, False):
            try:
                kw = {"response_modalities": ["IMAGE"]}
                if with_ratio:
                    kw["image_config"] = types.ImageConfig(aspect_ratio="4:5")
                r = client.models.generate_content(model=model, contents=[prompt],
                                                   config=types.GenerateContentConfig(**kw))
                for cand in r.candidates or []:
                    for part in (cand.content.parts if cand.content else []) or []:
                        if getattr(part, "inline_data", None) and part.inline_data.data:
                            return part.inline_data.data, model
                last = "no image in response"
            except Exception as e:
                last = str(e)
                if "not found" in last.lower() or "404" in last:
                    break  # try next model
    raise RuntimeError(f"image generation failed: {last}")


async def ensure_art(slug: str, force: bool = False) -> dict:
    """Generate (once) and store the illustration for a post. Returns status dict; never raises."""
    if not COVER_ART_ENABLED or not providers_available():
        return {"slug": slug, "ok": False,
                "detail": "no image provider: set CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN (free) on Render"}
    if not force and await db.blog_cover_art.find_one({"slug": slug}, {"_id": 1}):
        return {"slug": slug, "ok": True, "detail": "exists"}
    post = await db.blog_posts.find_one({"slug": slug}, {"_id": 0, "title": 1, "keyword": 1, "excerpt": 1})
    if not post:
        return {"slug": slug, "ok": False, "detail": "post not found"}
    prompt = build_prompt(post.get("title", ""), post.get("keyword", ""), post.get("excerpt", ""))
    try:
        data, model = await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(None, _generate, prompt), timeout=120)
    except Exception as e:
        logger.warning(f"cover art {slug}: {e}")
        return {"slug": slug, "ok": False, "detail": str(e)[:200]}
    await db.blog_cover_art.update_one({"slug": slug}, {"$set": {
        "slug": slug, "png": Binary(data), "model": model, "prompt": prompt,
        "created_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return {"slug": slug, "ok": True, "model": model}


async def get_art(slug: str):
    doc = await db.blog_cover_art.find_one({"slug": slug}, {"_id": 0, "png": 1, "created_at": 1})
    return (bytes(doc["png"]), doc.get("created_at", "")) if doc else (None, "")
