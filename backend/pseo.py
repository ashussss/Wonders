"""Programmatic SEO pipeline for ShowUp.ai.

Flow:  keyword queue (seo_candidates) -> AI long-form draft (blog_posts, published=False)
       -> human review -> publish -> appears on /blog and in /api/sitemap.xml

Everything lives in MongoDB (same MONGO_URL / DB_NAME as the rest of the app).
"""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

from database import db

logger = logging.getLogger("showup.pseo")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
PSEO_MODEL = os.environ.get("PSEO_MODEL", "openai/gpt-oss-120b")
PSEO_FALLBACK_MODEL = os.environ.get("PSEO_FALLBACK_MODEL", "openai/gpt-oss-20b")
PSEO_POSTS_PER_DAY = int(os.environ.get("PSEO_POSTS_PER_DAY", "1"))
PSEO_AUTO_PUBLISH = os.environ.get("PSEO_AUTO_PUBLISH", "false").lower() == "true"
SITE_URL = "https://showupai.live"

# Starter keyword bank. Seeded once; add more via POST /api/seo/research.
SEED_KEYWORDS = [
    ("how to increase webinar attendance", "informational"),
    ("average webinar attendance rate", "informational"),
    ("webinar reminder email sequence", "informational"),
    ("why people register for webinars but don't attend", "informational"),
    ("best time to send webinar reminder emails", "informational"),
    ("webinar no-show rate", "informational"),
    ("webinar reminder sms", "informational"),
    ("how many webinar reminders to send", "informational"),
    ("webinar attendance software", "commercial"),
    ("zoom webinar attendance tips", "informational"),
    ("linkedin posts to promote a webinar", "informational"),
    ("webinar follow up email for no shows", "informational"),
    ("b2b webinar marketing strategy", "informational"),
    ("webinar registration to attendance ratio", "informational"),
    ("how to reduce webinar drop off", "informational"),
    ("automated webinar reminders", "commercial"),
    ("webinar promotion checklist", "informational"),
    ("edtech webinar attendance", "informational"),
    ("webinar reminder whatsapp message", "informational"),
    ("calendar invite for webinar attendance", "informational"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:80] or "post"


async def _unique_slug(base: str) -> str:
    slug, n = base, 2
    while await db.blog_posts.find_one({"slug": slug}, {"_id": 1}):
        slug = f"{base}-{n}"
        n += 1
    return slug


async def ensure_indexes():
    await db.blog_posts.create_index("slug", unique=True)
    await db.blog_posts.create_index([("published", 1), ("published_at", -1)])
    await db.seo_candidates.create_index("keyword", unique=True)


async def seed_keywords() -> int:
    added = 0
    for kw, intent in SEED_KEYWORDS:
        added += await add_keyword(kw, intent)
    return added


async def add_keyword(keyword: str, intent: str = "informational") -> int:
    keyword = keyword.strip().lower()
    if not keyword:
        return 0
    res = await db.seo_candidates.update_one(
        {"keyword": keyword},
        {"$setOnInsert": {"keyword": keyword, "intent": intent, "status": "pending", "created_at": now_iso()}},
        upsert=True,
    )
    return 1 if res.upserted_id else 0


PROMPT = """You are a senior B2B marketer who has run hundreds of webinars. Write an in-depth blog article.

Target keyword: "{keyword}"
Search intent: {intent}
Product context: ShowUp.ai (showupai.live) helps webinar hosts get more registrants to actually attend, using an
AI-written, multi-channel reminder sequence (email, LinkedIn, WhatsApp/SMS, calendar) timed around the event.
Mention ShowUp.ai naturally at most twice, near the end. The article must be genuinely useful without the product.

Rules:
- 1300 to 1800 words. Markdown only: "## " and "### " headings, "- " bullets, "1. " numbered lists, plain paragraphs.
- No H1 (the title is shown separately). No links, no tables, no images, no emojis.
- Open with a 2-3 sentence direct answer to the keyword (featured-snippet style).
- Do NOT invent statistics, percentages, studies, quotes or customer names. If you give numbers, frame them as
  ranges or rules of thumb, not as cited facts.
- Tone: direct, practical, skeptical of hype. Avoid: "unlock", "revolutionary", "game-changer", "in today's fast-paced".
- Include concrete steps, examples of message timing, and common mistakes.

Return ONLY a JSON object with these keys:
{{
  "title": "compelling title, max 65 chars, includes the keyword naturally",
  "meta_description": "max 155 chars",
  "excerpt": "1-2 sentence summary, max 200 chars",
  "content": "the full markdown article",
  "faq_items": [{{"question": "...", "answer": "2-3 sentence answer"}}],   // 4 to 6 items
  "entities": ["key concepts/tools mentioned"],
  "related_topics": ["3-5 related topics to write about next"]
}}"""


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("No JSON object in model output")
        return json.loads(text[start:end + 1])


def _groq_json(prompt: str) -> dict:
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    last_err = None
    for model in (PSEO_MODEL, PSEO_FALLBACK_MODEL):
        # Try strict JSON mode first, then plain mode with JSON extraction.
        for json_mode in (True, False):
            try:
                kwargs = dict(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=16000,  # gpt-oss spends part of this on reasoning
                    temperature=0.6,
                    extra_body={"reasoning_effort": "low"},
                )
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                r = client.chat.completions.create(**kwargs)
                return _parse_json(r.choices[0].message.content)
            except Exception as e:
                last_err = e
                logger.warning(f"pSEO model {model} (json_mode={json_mode}) failed: {e}")
                if "model_not_found" in str(e) or "does not exist" in str(e):
                    break  # no point retrying this model without JSON mode
    raise RuntimeError(f"All pSEO models failed: {last_err}")


async def generate_post(keyword: str, intent: str = "informational") -> dict:
    """Generate one long-form draft and save it to blog_posts (unpublished unless auto-publish)."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")

    data = await asyncio.get_running_loop().run_in_executor(
        None, _groq_json, PROMPT.format(keyword=keyword, intent=intent)
    )
    content = (data.get("content") or "").strip()
    words = len(content.split())
    if words < 600:
        raise RuntimeError(f"Draft too short ({words} words)")

    title = (data.get("title") or keyword.title()).strip()
    slug = await _unique_slug(slugify(keyword))
    faqs = [f for f in (data.get("faq_items") or []) if isinstance(f, dict) and f.get("question")]
    doc = {
        "id": str(uuid.uuid4()),
        "slug": slug,
        "keyword": keyword,
        "intent": intent,
        "title": title,
        "seo_title": f"{title} | ShowUp.ai"[:70],
        "meta_description": (data.get("meta_description") or "")[:160],
        "seo_description": (data.get("meta_description") or "")[:160],
        "excerpt": (data.get("excerpt") or "")[:220],
        "content": content,
        "faq_items": faqs[:6],
        "entities": data.get("entities") or [],
        "related_topics": data.get("related_topics") or [],
        "reading_time": max(1, round(words / 200)),
        "word_count": words,
        "author": "ShowUp.ai Team",
        "source": "pseo",
        "status": "published" if PSEO_AUTO_PUBLISH else "draft",
        "published": PSEO_AUTO_PUBLISH,
        "published_at": now_iso() if PSEO_AUTO_PUBLISH else None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.blog_posts.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def run_pipeline(count: int | None = None) -> dict:
    """Take `count` pending keywords, generate drafts. Safe to call from cron or manually."""
    count = count or PSEO_POSTS_PER_DAY
    await ensure_indexes()
    if await db.seo_candidates.count_documents({}) == 0:
        await seed_keywords()

    results = []
    for _ in range(count):
        cand = await db.seo_candidates.find_one_and_update(
            {"status": "pending"},
            {"$set": {"status": "processing", "started_at": now_iso()}},
            sort=[("created_at", 1)],
        )
        if not cand:
            break
        kw = cand["keyword"]
        try:
            post = await generate_post(kw, cand.get("intent", "informational"))
            await db.seo_candidates.update_one(
                {"_id": cand["_id"]}, {"$set": {"status": "drafted", "slug": post["slug"], "done_at": now_iso()}}
            )
            # Queue suggested follow-up topics for future runs
            for t in post.get("related_topics", [])[:3]:
                if isinstance(t, str):
                    await add_keyword(t, "informational")
            results.append({"keyword": kw, "slug": post["slug"], "status": post["status"]})
            logger.info(f"pSEO drafted '{kw}' -> {post['slug']}")
        except Exception as e:
            await db.seo_candidates.update_one(
                {"_id": cand["_id"]}, {"$set": {"status": "failed", "error": str(e)[:300]}}
            )
            results.append({"keyword": kw, "error": str(e)[:300]})
            logger.error(f"pSEO failed '{kw}': {e}")
    return {"ok": True, "processed": len(results), "results": results}


async def retry_failed() -> int:
    """Put failed keywords back in the queue."""
    res = await db.seo_candidates.update_many(
        {"status": {"$in": ["failed", "processing"]}}, {"$set": {"status": "pending"}, "$unset": {"error": ""}}
    )
    return res.modified_count


async def build_sitemap() -> str:
    static = [("/", "1.0", "weekly"), ("/blog", "0.8", "daily"), ("/waitlist", "0.7", "monthly")]
    urls = [
        f"<url><loc>{SITE_URL}{p}</loc><changefreq>{f}</changefreq><priority>{pr}</priority></url>"
        for p, pr, f in static
    ]
    rows = await db.blog_posts.find(
        {"published": True}, {"_id": 0, "slug": 1, "published_at": 1, "updated_at": 1}
    ).to_list(5000)
    for r in rows:
        last = (r.get("updated_at") or r.get("published_at") or "")[:10]
        lastmod = f"<lastmod>{last}</lastmod>" if last else ""
        urls.append(
            f"<url><loc>{SITE_URL}/blog/{r['slug']}</loc>{lastmod}"
            f"<changefreq>monthly</changefreq><priority>0.6</priority></url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"
    )
