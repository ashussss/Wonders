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
import re

router = APIRouter(prefix="/api")
limiter = Limiter(key_func=get_remote_address)


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
        added += await pseo.add_keyword(str(k), intent)
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
    return {"ok": True}


@router.get("/sitemap.xml")
async def sitemap():
    """Live sitemap from published posts (proxied at showupai.live/sitemap.xml by Netlify)."""
    xml = await pseo.build_sitemap()
    return Response(content=xml, media_type="application/xml")


# --------- Blog Posts with Full Optimization ---------

@router.get("/blog")
async def list_blog_posts():
    """List all published blog posts, published first, sorted by SEO value."""
    rows = await db.blog_posts.find({"published": True}, {"_id": 0}).sort(
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