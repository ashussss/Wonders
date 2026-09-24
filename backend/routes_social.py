"""Social autopilot endpoints. Admin endpoints need X-API-KEY = SUPERADMIN_SECRET."""
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import Response

import social
from database import db
from routes_blog import _require_key, blog_cover_image

router = APIRouter(prefix="/api")


@router.get("/social/img/{iid}.jpg")
async def social_image(iid: str):
    doc = await db.social_images.find_one({"id": iid})
    if not doc:
        raise HTTPException(404, "Image not found")
    return Response(content=bytes(doc["jpg"]), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})


@router.get("/blog/{slug}/cover.jpg")
async def blog_cover_jpg(slug: str):
    """JPEG version of the cover (Instagram only accepts JPEG)."""
    png = await blog_cover_image(slug)
    return Response(content=social.si.cover_jpeg(png.body), media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/social/check")
async def social_check(request: Request):
    """Which platforms are connected for SOCIAL_ACCOUNT_EMAIL."""
    _require_key(request)
    s = await social.account_settings()
    return {"account": social.SOCIAL_ACCOUNT_EMAIL or None, "found_settings": bool(s), "connected": social.connected(s),
            "platforms": social.SOCIAL_PLATFORMS, "auto_approve_daily": social.SOCIAL_AUTO_APPROVE,
            "auto_approve_blog": social.SOCIAL_AUTO_BLOG, "times_ist": social.SOCIAL_TIMES_IST[: social.SOCIAL_POSTS_PER_DAY]}


@router.get("/social/queue")
async def social_queue(request: Request, status: str = ""):
    _require_key(request)
    q = {"status": status} if status else {}
    return await db.social_posts.find(q, {"_id": 0}).sort("scheduled_at", -1).to_list(100)


@router.post("/social/generate")
async def social_generate(request: Request, payload: dict = Body(default={})):
    """Generate today's posts now. Body: {"count": 4} (optional)."""
    _require_key(request)
    count = payload.get("count")
    return await social.generate_daily(int(count) if count else None)


@router.post("/social/approve")
async def social_approve(request: Request, payload: dict = Body(default={})):
    """Body: {"id": "..."} or {"ids": [...]} or {"all_pending": true}."""
    _require_key(request)
    if payload.get("all_pending"):
        r = await db.social_posts.update_many({"status": "pending"}, {"$set": {"status": "approved"}})
    else:
        ids = payload.get("ids") or [payload.get("id")]
        r = await db.social_posts.update_many({"id": {"$in": ids}, "status": "pending"}, {"$set": {"status": "approved"}})
    return {"ok": True, "approved": r.modified_count}


@router.post("/social/skip")
async def social_skip(request: Request, payload: dict = Body(default={})):
    _require_key(request)
    r = await db.social_posts.update_one({"id": payload.get("id"), "status": {"$in": ["pending", "approved"]}},
                                         {"$set": {"status": "skipped"}})
    return {"ok": bool(r.modified_count)}


@router.post("/social/edit")
async def social_edit(request: Request, payload: dict = Body(default={})):
    """Body: {"id": "...", "caption_linkedin": "...", "caption_facebook": "...", "caption_instagram": "...", "scheduled_at": "ISO"}"""
    _require_key(request)
    doc = await db.social_posts.find_one({"id": payload.get("id")}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Not found")
    caps = doc.get("captions") or {}
    for k in ("caption_linkedin", "caption_facebook", "caption_instagram"):
        if payload.get(k):
            caps[k] = payload[k]
    upd = {"captions": caps}
    if payload.get("scheduled_at"):
        upd["scheduled_at"] = payload["scheduled_at"]
    await db.social_posts.update_one({"id": doc["id"]}, {"$set": upd})
    return {"ok": True}


@router.post("/social/post-now")
async def social_post_now(request: Request, payload: dict = Body(default={})):
    """Post one item immediately (also retries platforms that failed)."""
    _require_key(request)
    doc = await db.social_posts.find_one({"id": payload.get("id")}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Not found")
    return await social.publish_post(doc)


@router.get("/social/substack/{slug}")
async def social_substack(request: Request, slug: str):
    """Substack-ready markdown for manual cross-posting."""
    _require_key(request)
    post = await db.blog_posts.find_one({"slug": slug, "published": True}, {"_id": 0})
    if not post:
        raise HTTPException(404, "Post not found")
    return Response(content=social.substack_markdown(post), media_type="text/markdown; charset=utf-8")
