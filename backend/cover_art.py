"""AI illustration for each blog post's cover, stored in Mongo.

Providers (tried in COVER_ART_PROVIDERS order): Cloudflare Workers AI FLUX.1 schnell (free daily allowance),
optionally Gemini image models (paid-only). The cover endpoint composites the illustration with the brand layout
(title, tag, logo). If generation fails, covers fall back to topic-matched drawn motifs.

Prompts are deliberately wordless (no title, no screens/charts/calendars/signs) because image models draw
garbled text when a scene invites it.
"""
import asyncio
import base64
import logging
import os
from datetime import datetime, timezone

from bson import Binary

from database import db

logger = logging.getLogger("showup.cover_art")

COVER_ART_ENABLED = os.environ.get("COVER_ART_ENABLED", "true").lower() == "true"
PROVIDERS = [p.strip() for p in os.environ.get("COVER_ART_PROVIDERS", "cloudflare").split(",") if p.strip()]
CLOUDFLARE_IMAGE_MODEL = os.environ.get("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
# Separate key allowed so only image generation sits on a billed Google project (optional, paid)
GEMINI_API_KEY = os.environ.get("GEMINI_IMAGE_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
IMAGE_MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_IMAGE_MODELS", "gemini-3.1-flash-lite-image,gemini-3.1-flash-image"
).split(",") if m.strip()]

PROMPT_VERSION = 2  # bump to regenerate existing art with {"upgrade": true}

SCENES = [
    (("sms", "whatsapp", "text message"), "a smartphone lying on a wooden desk beside a coffee cup, its screen glowing plain warm orange, a small ringing bell floating above it"),
    (("follow up", "follow-up", "replay", "no show", "no-show", "missed"), "a paper plane looping back towards a smiling person sitting at a desk"),
    (("email", "newsletter", "inbox"), "paper envelopes with orange wax seals flying like a flock of birds towards an open laptop with a plain glowing lid"),
    (("zoom", "video", "live", "teams", "on demand", "on-demand"), "a friendly group of diverse people waving from separate floating rounded window frames, faces and hands only"),
    (("linkedin", "social", "instagram", "facebook", "post"), "diverse professionals standing on floating platforms connected by glowing lines, heart and thumbs-up shaped bubbles rising between them"),
    (("calendar", "time", "when", "advance", "schedule", "timing"), "a large hourglass with glowing orange sand beside a small stage with a spotlight"),
    (("rate", "average", "benchmark", "statistic", "ratio", "tracking", "data"), "small figures climbing ascending stone steps towards a glowing trophy at the top"),
    (("strategy", "marketing", "funnel", "registration", "promot", "checklist", "lead"), "a giant funnel with many small people figures entering at the top and gathering into a happy crowd below"),
    (("reminder", "how many", "notification"), "a golden bell ringing with soft sound waves while small figures walk along a winding path towards a stage"),
    (("software", "tool", "automat", "features", "showupai"), "interlocking orange gears moving paper envelopes and small bells along a conveyor towards a stage with an audience"),
    (("edtech", "course", "student", "education"), "students with backpacks walking into a bright glowing doorway"),
    (("agency", "agencies", "client"), "a team of diverse people carrying glowing lanterns leading a crowd towards a stage"),
    (("title", "subject line", "write", "copy"), "a giant fountain pen drawing a glowing orange ribbon that pulls a crowd of people towards a stage"),
    (("drop off", "drop-off", "attendance", "attend"), "an auditorium where people are walking in and filling rows of orange seats, a speaker on stage"),
]

STYLE = ("Flat vector illustration, warm orange (#EA580C), charcoal and cream palette, soft gradients, simple rounded "
         "shapes, clean composition with generous empty space, subject centred. Wordless image: no text, no letters, "
         "no numbers, no writing, no labels, no signs, no logos.")


def build_prompt(title: str, keyword: str, excerpt: str = "") -> str:
    """Scene chosen from the topic; the title/excerpt are NOT included (they make models draw text)."""
    import re as _re
    k = " " + _re.sub(r"[^a-z0-9]+", " ", f"{keyword} {title}".lower()) + " "
    # match at word starts only ("rate" must not match "strategy"; "promot" matches "promote")
    hit = lambda w: (" " + _re.sub(r"[^a-z0-9]+", " ", w.lower()).strip()) in k
    scene = next((sc for words, sc in SCENES if any(hit(w) for w in words)),
                 "a speaker on a small stage presenting to an audience of diverse people seated in rows")
    return f"{scene}. {STYLE}"


def _cf():
    """Read Cloudflare settings at call time (tolerates stray spaces/quotes/'Bearer ' pasted into Render)."""
    acc = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip().strip('"').strip("'")
    tok = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip().strip('"').strip("'")
    if tok.lower().startswith("bearer "):
        tok = tok[7:].strip()
    return acc, tok


def providers_available() -> list:
    acc, tok = _cf()
    out = []
    for p in PROVIDERS:
        if p == "cloudflare" and acc and tok:
            out.append(p)
        elif p == "gemini" and GEMINI_API_KEY:
            out.append(p)
    return out


def _generate_cloudflare(prompt: str):
    import httpx

    acc, tok = _cf()
    url = f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{CLOUDFLARE_IMAGE_MODEL}"
    r = httpx.post(url, headers={"Authorization": f"Bearer {tok}"}, json={"prompt": prompt[:2000], "steps": 8}, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"cloudflare {r.status_code}: {r.text[:200]}")
    if r.headers.get("content-type", "").startswith("image/"):
        return r.content, CLOUDFLARE_IMAGE_MODEL
    img = (r.json().get("result") or {}).get("image")
    if not img:
        raise RuntimeError(f"cloudflare: no image in response {r.text[:200]}")
    return base64.b64decode(img), CLOUDFLARE_IMAGE_MODEL


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
                r = client.models.generate_content(model=model, contents=[prompt], config=types.GenerateContentConfig(**kw))
                for cand in r.candidates or []:
                    for part in (cand.content.parts if cand.content else []) or []:
                        if getattr(part, "inline_data", None) and part.inline_data.data:
                            return part.inline_data.data, model
                last = "no image in response"
            except Exception as e:
                last = str(e)
                if "not found" in last.lower() or "404" in last:
                    break
    raise RuntimeError(f"gemini: {last}")


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


async def ensure_art(slug: str, force: bool = False) -> dict:
    """Generate (once) and store the illustration for a post. Returns a status dict; never raises."""
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
        data, model = await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(None, _generate, prompt), timeout=150)
    except Exception as e:
        logger.warning(f"cover art {slug}: {e}")
        return {"slug": slug, "ok": False, "detail": str(e)[:200]}
    await db.blog_cover_art.update_one({"slug": slug}, {"$set": {
        "slug": slug, "png": Binary(data), "model": model, "prompt": prompt, "version": PROMPT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return {"slug": slug, "ok": True, "model": model}


async def get_art(slug: str):
    doc = await db.blog_cover_art.find_one({"slug": slug}, {"_id": 0, "png": 1, "created_at": 1})
    return (bytes(doc["png"]), doc.get("created_at", "")) if doc else (None, "")


def status() -> dict:
    """Safe diagnostics: never returns secrets."""
    acc, tok = _cf()
    return {
        "providers_configured": PROVIDERS,
        "providers_ready": providers_available(),
        "cloudflare_account_id_length": len(acc),
        "cloudflare_account_id_looks_ok": len(acc) == 32 and all(c in "0123456789abcdef" for c in acc.lower()),
        "cloudflare_token_length": len(tok),
        "cloudflare_token_starts_with": tok[:5] + "..." if tok else "",
        "env_var_names_seen": sorted(k for k in os.environ if "CLOUDFLARE" in k.upper()),
        "image_model": CLOUDFLARE_IMAGE_MODEL,
        "prompt_version": PROMPT_VERSION,
    }
