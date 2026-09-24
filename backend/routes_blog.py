"""Blog endpoints — programmatic SEO with LLM/AEO/GEO optimization.

Enhanced version with:
- Full meta fields for SEO
- AEO structures (Q&A, featured snippet potential)
- GEO entities & relationships
- Value-driven content framework
- Follows exact patterns from routes_webinars.py
"""

"""Blog, touches, registrants, and lead magnets endpoints — enhanced."""

import asyncio
import uuid
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Body, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from fastapi.responses import Response

from database import db
from auth_utils import get_user, now_iso
from models import BlogPostIn, BlogPostPatch
from config import SUPERADMIN_SECRET
import pseo
from routes_webinars import limiter as _web_limiter
import os
import re

router = APIRouter(prefix="/api")
limiter = Limiter(key_func=get_remote_address)


NETLIFY_BUILD_HOOK = os.environ.get("NETLIFY_BUILD_HOOK", "")
INDEXNOW_KEY = os.environ.get("INDEXNOW_KEY", "eb888803ca7889eb7c7da380d3457df5")  # key file: frontend/public/<key>.txt


async def _indexnow(urls, delay: int = 0):
    """Tell Bing (and so ChatGPT search / Copilot), Yandex, Naver, Seznam, Yep about new/changed URLs."""
    import asyncio
    import httpx
    if delay:
        await asyncio.sleep(delay)  # give Netlify time to rebuild the prerendered page first
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post("https://api.indexnow.org/indexnow", json={
                "host": "showupai.live", "key": INDEXNOW_KEY,
                "keyLocation": f"https://showupai.live/{INDEXNOW_KEY}.txt",
                "urlList": list(urls)[:10000],
            })
            return r.status_code
    except Exception:
        return None


def _indexnow_later(urls):
    import asyncio
    try:
        asyncio.get_running_loop().create_task(_indexnow(urls, delay=300))
    except RuntimeError:
        pass


async def _trigger_rebuild(reason: str):
    """Ask Netlify to rebuild so the prerendered blog HTML (for Google/AI crawlers) picks up changes."""
    if not NETLIFY_BUILD_HOOK:
        return False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(NETLIFY_BUILD_HOOK, params={"trigger_title": f"Blog: {reason}"[:120]})
        return True
    except Exception:
        return False


def _require_key(request: Request):
    """Admin/cron endpoints: require X-API-KEY == SUPERADMIN_SECRET."""
    if not SUPERADMIN_SECRET or request.headers.get("X-API-KEY") != SUPERADMIN_SECRET:
        raise HTTPException(403, "Unauthorized")


# --------- Programmatic SEO pipeline ---------

@router.post("/seo/research")
async def seo_research(request: Request, payload: dict = Body(default={})):
    """Add keyword(s) to the queue. Body: {"keyword": "..."} or {"keywords": ["...", ...]}."""
    _require_key(request)
    kws = payload.get("keywords") or ([payload["keyword"]] if payload.get("keyword") else [])
    if not kws:
        raise HTTPException(400, "keyword or keywords required")
    intent = payload.get("intent", "informational")
    added = 0
    for k in kws:
        # each item: "keyword" or {"keyword": "...", "notes": "your first-hand experience", "intent": "..."}
        if isinstance(k, dict):
            added += await pseo.add_keyword(str(k.get("keyword", "")), k.get("intent", intent), k.get("notes", ""))
        else:
            added += await pseo.add_keyword(str(k), intent, payload.get("notes", "") if len(kws) == 1 else "")
    return {"ok": True, "added": added, "submitted": len(kws)}


@router.post("/seo/run")
async def seo_run(request: Request, payload: dict = Body(default={})):
    """Run the pipeline now: generate drafts for the next N queued keywords (default PSEO_POSTS_PER_DAY)."""
    _require_key(request)
    count = int(payload.get("count") or pseo.PSEO_POSTS_PER_DAY)
    return await pseo.run_pipeline(min(max(count, 1), 5))


@router.post("/seo/retry")
async def seo_retry(request: Request):
    """Re-queue keywords that failed (e.g. after fixing a model/API issue)."""
    _require_key(request)
    return {"ok": True, "requeued": await pseo.retry_failed()}


@router.post("/seo/indexnow")
async def seo_indexnow(request: Request):
    """Submit every published blog URL to IndexNow right now."""
    _require_key(request)
    rows = await db.blog_posts.find({"published": True}, {"_id": 0, "slug": 1}).to_list(5000)
    urls = [f"{pseo.SITE_URL}/blog"] + [f"{pseo.SITE_URL}/blog/{r['slug']}" for r in rows]
    status = await _indexnow(urls)
    return {"ok": status in (200, 202), "status": status, "submitted": len(urls)}


@router.post("/seo/rebuild")
async def seo_rebuild(request: Request):
    """Manually trigger a Netlify rebuild (refreshes prerendered blog pages)."""
    _require_key(request)
    ok = await _trigger_rebuild("manual")
    return {"ok": ok, "note": None if ok else "Set NETLIFY_BUILD_HOOK on Render first"}


@router.post("/seo/generate")
async def seo_generate(request: Request, payload: dict = Body(default={})):
    """Generate a draft for one specific keyword right now."""
    _require_key(request)
    keyword = (payload.get("keyword") or "").strip()
    if not keyword:
        raise HTTPException(400, "Keyword required")
    await pseo.ensure_indexes()
    post = await pseo.generate_post(keyword.lower(), payload.get("intent", "informational"))
    return {"ok": True, "slug": post["slug"], "title": post["title"], "status": post["status"]}


@router.get("/seo/queue")
async def seo_queue(request: Request):
    """See queued / drafted / failed keywords."""
    _require_key(request)
    rows = await db.seo_candidates.find({}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return rows


@router.get("/seo/drafts")
async def seo_drafts(request: Request):
    """List unpublished drafts for review (full content included)."""
    _require_key(request)
    return await db.blog_posts.find({"published": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.post("/seo/publish")
async def seo_publish(request: Request, payload: dict = Body(default={})):
    """Publish a reviewed draft. Body: {"slug": "..."}."""
    _require_key(request)
    slug = payload.get("slug")
    if not slug:
        raise HTTPException(400, "Slug required")
    post = await db.blog_posts.find_one({"slug": slug}, {"_id": 0})
    if not post:
        raise HTTPException(404, "Draft not found")
    pseo.clean_post_fields(post)
    ts = now_iso()
    post.update({"published": True, "status": "published", "published_at": post.get("published_at") or ts, "updated_at": ts})
    await db.blog_posts.update_one({"slug": slug}, {"$set": post})
    await _trigger_rebuild(f"published {slug}")
    _indexnow_later([f"{pseo.SITE_URL}/blog/{slug}", f"{pseo.SITE_URL}/blog"])
    return {"ok": True, "url": f"{pseo.SITE_URL}/blog/{slug}"}


@router.post("/seo/edit")
async def seo_edit(request: Request, payload: dict = Body(default={})):
    """Edit a post's text. Body: {"slug": "...", "title": "...optional", "edits": [{"find": "...", "replace": "...", "regex": false}]}.
    Edits apply to the article body; each result says how many places changed (0 = text not found)."""
    _require_key(request)
    slug = payload.get("slug")
    post = await db.blog_posts.find_one({"slug": slug}, {"_id": 0})
    if not post:
        raise HTTPException(404, "Post not found")
    pseo.clean_post_fields(post)
    content = post["content"]
    results = []
    for e in payload.get("edits") or []:
        find, repl = e.get("find", ""), e.get("replace", "")
        if not find:
            continue
        if e.get("regex"):
            content, n = re.subn(find, repl, content, flags=re.I)
        else:
            n = content.count(find)
            content = content.replace(find, repl)
        results.append({"find": find[:60], "changed": n})
    post["content"] = content
    for k in ("title", "excerpt", "meta_description"):
        if payload.get(k):
            post[k] = payload[k]
    if payload.get("title"):
        post["seo_title"] = f"{payload['title']} | ShowUp.ai"[:70]
    if payload.get("meta_description"):
        post["seo_description"] = payload["meta_description"]
    pseo.clean_post_fields(post)
    post["updated_at"] = now_iso()
    await db.blog_posts.update_one({"slug": slug}, {"$set": post})
    if post.get("published"):
        await _trigger_rebuild(f"edited {slug}")
        _indexnow_later([f"{pseo.SITE_URL}/blog/{slug}"])
    return {"ok": True, "results": results, "word_count": post["word_count"]}


@router.post("/seo/unpublish")
async def seo_unpublish(request: Request, payload: dict = Body(default={})):
    """Take a post offline (back to draft)."""
    _require_key(request)
    result = await db.blog_posts.update_one(
        {"slug": payload.get("slug")}, {"$set": {"published": False, "status": "draft", "updated_at": now_iso()}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Post not found")
    await _trigger_rebuild(f"unpublished {payload.get('slug')}")
    return {"ok": True}


_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[a-zA-Z]{2,24}$")


@router.post("/blog/subscribe")
@_web_limiter.limit("5/minute")
async def blog_subscribe(request: Request, payload: dict = Body(default={})):
    """Public: newsletter / lead capture from the blog. Body: {name, email, slug?, placement?, website? (honeypot)}."""
    if payload.get("website"):  # bots fill hidden fields
        return {"ok": True}
    email = str(payload.get("email", "")).strip().lower()
    name = str(payload.get("name", "")).strip()[:80]
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "Please enter a valid email")
    if not name:
        raise HTTPException(400, "Please enter your name")
    ts = now_iso()
    source = {"slug": str(payload.get("slug", ""))[:120], "placement": str(payload.get("placement", ""))[:40], "at": ts}
    await db.blog_subscribers.update_one(
        {"email": email},
        {"$setOnInsert": {"email": email, "created_at": ts, "first_source": source, "status": "subscribed"},
         "$set": {"name": name, "updated_at": ts},
         "$push": {"sources": {"$each": [source], "$slice": -20}}},
        upsert=True,
    )
    return {"ok": True}


@router.get("/seo/subscribers")
async def seo_subscribers(request: Request):
    """List blog subscribers (newest first)."""
    _require_key(request)
    rows = await db.blog_subscribers.find({}, {"_id": 0, "sources": 0}).sort("created_at", -1).to_list(10000)
    return {"count": len(rows), "subscribers": rows}


@router.get("/seo/subscribers.csv")
async def seo_subscribers_csv(request: Request):
    """CSV export for Brevo / Mailchimp import."""
    _require_key(request)
    import csv, io
    rows = await db.blog_subscribers.find({}, {"_id": 0}).sort("created_at", -1).to_list(10000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "name", "created_at", "first_post", "placement"])
    for x in rows:
        fs = x.get("first_source") or {}
        w.writerow([x.get("email"), x.get("name"), x.get("created_at"), fs.get("slug"), fs.get("placement")])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=blog-subscribers.csv"})


@router.get("/sitemap.xml")
async def sitemap():
    """Live sitemap from published posts (proxied at showupai.live/sitemap.xml by Netlify)."""
    xml = await pseo.build_sitemap()
    return Response(content=xml, media_type="application/xml")


# --------- Blog Posts with Full Optimization ---------

@router.get("/blog")
async def list_blog_posts():
    """List all published blog posts, published first, sorted by SEO value."""
    rows = await db.blog_posts.find({"published": True}, {"_id": 0, "content": 0, "faq_items": 0}).sort(
        [("published_at", -1), ("reading_time", -1)]
    ).to_list(500)
    published = [r for r in rows if r.get("published")]
    not_published = [r for r in rows if not r.get("published")]
    return published + not_published


@router.get("/blog/{slug}")
async def get_blog_post(slug: str):
    """Get a single blog post by slug with full optimization data."""
    row = await db.blog_posts.find_one({"slug": slug, "published": True}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Blog post not found")
    return row


@router.get("/blog/{slug}/cover.png")
async def blog_cover_image(slug: str):
    """Branded cover image (1200x630). Generated on first request and cached in Mongo;
    regenerated automatically when the post title changes."""
    import hashlib
    import asyncio
    from bson import Binary
    import blog_cover

    post = await db.blog_posts.find_one({"slug": slug}, {"_id": 0, "title": 1, "keyword": 1})
    if not post:
        raise HTTPException(404, "Post not found")
    title = post.get("title") or slug.replace("-", " ").title()
    key = hashlib.md5((title + "|v1").encode()).hexdigest()
    cached = await db.blog_covers.find_one({"slug": slug})
    if cached and cached.get("key") == key:
        png = bytes(cached["png"])
    else:
        png = await asyncio.get_running_loop().run_in_executor(
            None, blog_cover.render_cover, title, slug, post.get("keyword", "")
        )
        await db.blog_covers.update_one(
            {"slug": slug}, {"$set": {"slug": slug, "key": key, "png": Binary(png), "updated_at": now_iso()}}, upsert=True
        )
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.post("/blog")
async def create_blog_post(data: BlogPostIn, user=Depends(get_user)):
    """Create a new blog post (admin only) with full SEO/LLM/AEO/GEO fields."""
    # Check superadmin auth
    if user.get("role", "") != "superadmin":
        raise HTTPException(403, "Superadmin access required")

    # Build optimized document with all fields
    doc = {
        "id": str(uuid.uuid4()),
        "slug": data.slug,
        "title": data.title,
        "excerpt": data.excerpt,
        "content": data.content,
        "meta_description": data.meta_description or "",
        "meta_keywords": data.meta_keywords or "",
        "published_at": now_iso() if data.published else None,
        "author": user.get("full_name", "Admin"),
        "reading_time": data.reading_time or 5,
        "published": data.published,
        "created_at": now_iso(),
        
        # ✅ SEO Fields
        "seo_title": data.seo_title or data.title,
        "seo_description": data.seo_description 
            or (data.excerpt[:160] + "..." if data.excerpt else ""),
        "seo_keywords": data.seo_keywords 
            or (data.meta_keywords or "webinar, attendance, software"),
        "og_title": data.og_title or data.title,
        "og_description": data.og_description 
            or (data.excerpt[:160] + "..." if data.excerpt else ""),
        "og_image": data.og_image or "/blog-featured.jpg",
        "twitter_card": data.twitter_card or "summary_large_image",
        "twitter_title": data.twitter_title or data.title,
        "twitter_description": data.twitter_description
            or (data.excerpt[:120] + "..." if data.excerpt else ""),
        "twitter_image": data.twitter_image or "/blog-featured.jpg",
        
        # ✅ AEO Fields (Answer Engine Optimization)
        "faq_items": data.faq_items or [],
        "common_questions": data.common_questions or [],
    "schema_type": "Article",  # For JSON-LD generation
    
    # ✅ GEO Fields (Generative Engine Optimization)
    "entities": data.entities or [],  # Key entities mentioned
    "related_topics": data.related_topics or [],
    "answer_focus": data.answer_focus or "",  # What question this answers
    "authority_signals": data.authority_signals or [],  # Credibility markers
    
    # ✅ Value-Driven Framework
    "problem_statement": data.problem_statement or "",
    "solution_framework": data.solution_framework or "",
    "actionable_takeaways": data.actionable_takeaways or [],
    "case_studies": data.case_studies or [],
    
    # Engagement tracking
    "registrations_from_page": 0,
    "attendees_from_page": 0,
    "conversion_rate": 0,
    
    "seo_score": 0,  # Will be calculated by automation
    "aeo_optimized": False,
    "geo_optimized": False,
    
    "status": "draft" if not data.published else "pending_review",
    "workflow_state": "created",
}

    await db.blog_posts.insert_one(doc)
    return {"ok": True, "id": doc["id"]}


@router.put("/blog/{slug}")
async def update_blog_post(slug: str, data: BlogPostPatch, user=Depends(get_user)):
    """Update a blog post (admin only, superadmin check) with full optimization."""
    # Check superadmin auth
    if user.get("role", "") != "superadmin":
        raise HTTPException(403, "Superadmin access required")

    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    if not upd:
        return {"ok": True}

    # Remove fields that shouldn't be updated directly
    upd.pop("id", None)
    upd.pop("slug", None)
    upd.pop("created_at", None)

    # Preserve existing optimization fields if not being updated
    existing = await db.blog_posts.find_one({"slug": slug}, {"_id": 0})
    if existing:
        # Keep existing AEO/GEO fields if not provided in update
        for key in ["faq_items", "common_questions", "entities", "related_topics",
                     "answer_focus", "authority_signals", "problem_statement",
                     "solution_framework", "actionable_takeaways", "case_studies",
                     "seo_score", "aeo_optimized", "geo_optimized"]:
            if key not in upd and key in existing:
                upd[key] = existing[key]

    result = await db.blog_posts.update_one(
        {"slug": slug}, {"$set": upd}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Blog post not found")

    return {"ok": True}


# --------- AI-Powered Blog Post Generation (Next Level) ---------

@router.post("/blog/generate")
async def generate_blog_post(
    keyword: str = Body(...),
    intent: str = Body("informational"),
    user=Depends(get_user)
):
    """Generate a draft blog post with AI (superadmin only)."""
    if user.get("role", "") != "superadmin":
        raise HTTPException(403, "Superadmin access required")
    await pseo.ensure_indexes()
    return await pseo.generate_post(keyword.strip().lower(), intent)


# --------- Helper Endpoints for Optimization ---------

@router.get("/blog/{slug}/aeo-analysis")
async def aeo_analysis(slug: str, user=Depends(get_user)):
    """AEO analysis: featured snippet potential, question rankings, etc."""
    post = await db.blog_posts.find_one({"slug": slug}, {"_id": 0})
    if not post:
        raise HTTPException(404)

    # Analyze for AEO factors
    content = post.content or ""
    questions = post.common_questions or []
    faq_items = post.faq_items or []

    # Extract potential featured snippet answers
    snippet_candidates = []
    import re
    sentences = re.split(r'[.!?]+', content)
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 50 and len(sentence) < 300:
            snippet_candidates.append(sentence)

    # Score based on structure
    has_lists = bool(re.search(r'(^\d+\.|^\- |\^\w+:)', content, re.MULTILINE))
    has_tables = "|" in content and content.count("|") > 3
    has_bold_important = bool(re.search(r'\*\*[^\*]{30}\*\*', content))
    
    return {
        "ok": True,
        "slug": slug,
        "featured_snippet_potential": len(snippet_candidates),
        "snippet_candidates": snippet_candidates[:3],
        "has_qa_structure": len(questions) > 0 or len(faq_items) > 0,
        "list_structure": has_lists,
        "table_structure": has_tables,
        "bold_important": has_bold_important,
        "question_count": len(questions),
        "recommendations": _get_aeo_recommendations(
            len(questions) > 0, has_lists, has_tables, len(snippet_candidates)
        ),
    }


@router.get("/blog/{slug}/geo-entities")
async def geo_entities(slug: str, user=Depends(get_user)):
    """GEO analysis: entity relationships, salience, LLM readability."""
    post = await db.blog_posts.find_one({"slug": slug}, {"_id": 0})
    if not post:
        raise HTTPException(404)

    content = post.content or ""
    entities = post.entities or []
    related_topics = post.related_topics or []

    # Simple entity salience scoring
    # Capitalized terms, proper nouns, technical terms
    import re
    capitalized = re.findall(r'\b[A-Z][a-z]+(?:[\s-][A-Z][a-z]+)*\b', content)
    
    # Count unique capitalized terms
    unique_entities = list(set(capitalized))
    
    return {
        "ok": True,
        "slug": slug,
        "entities_detected": len(unique_entities),
        "top_entities": unique_entities[:10],
        "entities_from_db": entities,
        "related_topics": related_topics,
        "salience_score": min(100, len(unique_entities) * 5 + len(related_topics) * 3),
        "llm_readability": _calculate_llm_readability(content),
        "recommendations": _get_geo_recommendations(entities, related_topics),
    }


def _get_aeo_recommendations(has_qa: bool, has_lists: bool, has_tables: bool, 
                             snippet_count: int) -> List[str]:
    """Generate AEO optimization recommendations."""
    recs = []
    if not has_qa:
        recs.append("Add Q&A section with common questions")
    if not has_lists:
        recs.append("Add numbered or bulleted lists for scannability")
    if not has_tables:
        recs.append("Use tables for comparative data")
    if snippet_count < 3:
        recs.append("Expand concise answers (50-300 chars) for snippet potential")
    if not recs:
        recs.append("Content well-structured for featured snippets")
    return recs


def _calculate_llm_readability(content: str) -> Dict[str, any]:
    """Calculate LLM readability metrics."""
    sentences = [s.strip() for s in content.split('.') if s.strip()]
    avg_sentence_length = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
    
    return {
        "avg_sentence_length": round(avg_sentence_length, 1),
        "readability_score": min(100, max(0, 100 - abs(avg_sentence_length - 20))),
        "is_optimal": 15 <= avg_sentence_length <= 25,
    }


def _get_geo_recommendations(entities: List[str], related_topics: List[str]) -> List[str]:
    """Generate GEO optimization recommendations."""
    recs = []
    if not entities:
        recs.append("Add proper nouns and key terms for entity recognition")
    if not related_topics:
        recs.append("Include related topics for semantic breadth")
    if len(entities) < 5:
        recs.append("Mention 5+ key entities for LLM context")
    if not recs:
        recs.append("Entity and topic coverage strong for GEO")
    return recs