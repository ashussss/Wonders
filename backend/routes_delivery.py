"""Delivery, file downloads, third-party integrations, social image generation."""
import os
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging
from bson import ObjectId

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from database import db, social_images_fs, showup_scores_fs
from auth_utils import get_user, now_iso
from senders import dispatch as send_dispatch
from files import build_ics, build_one_pager_pdf
from integrations import circle_sync_members, circle_diagnose, linkedin_list_events
from image_gen import generate_webinar_social_image
from showup_score import render_showup_score
from crypto_utils import decrypt_settings

logger = logging.getLogger("showup.delivery")

router = APIRouter(prefix="/api")


async def _user_settings_decrypted(user_id: str) -> Dict[str, Any]:
    s = await db.settings.find_one({"owner_id": user_id}, {"_id": 0}) or {}
    return decrypt_settings(s)


# ---------- File downloads (public) ----------
@router.get("/webinars/{wid}/calendar.ics")
async def get_ics(wid: str):
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    data = build_ics(w)
    return Response(content=data, media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="{wid}.ics"'})


@router.get("/webinars/{wid}/one-pager.pdf")
async def get_pdf(wid: str):
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    lm = await db.lead_magnets.find_one({"webinar_id": wid}, {"_id": 0}) or {}
    one_pager = ((lm.get("edited_content") or {}).get("one_pager")
                 or (lm.get("ai_content") or {}).get("one_pager")
                 or {"title": w["title"], "outline": []})
    pdf = build_one_pager_pdf(w, one_pager)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{wid}-one-pager.pdf"'})


# ---------- GridFS helpers ----------
async def _put_in_gridfs(bucket, filename: str, data: bytes, mime: str, metadata: Dict[str, Any]) -> ObjectId:
    return await bucket.upload_from_stream(filename, data,
                                            metadata={**metadata, "mime_type": mime})


async def _delete_from_gridfs(bucket, file_id: ObjectId) -> None:
    try:
        await bucket.delete(file_id)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"GridFS delete failed for {file_id}: {e}")


async def _stream_gridfs(bucket, file_id: ObjectId, mime: str):
    grid_out = await bucket.open_download_stream(file_id)

    async def iter_chunks():
        while True:
            chunk = await grid_out.readchunk()
            if not chunk:
                break
            yield chunk

    return StreamingResponse(iter_chunks(), media_type=mime,
                              headers={"Cache-Control": "public, max-age=300"})


# ---------- Social image generation (Nano Banana → GridFS) ----------
@router.post("/webinars/{wid}/social-image/generate")
async def generate_social_image(wid: str, payload: Dict[str, Any] = Body(default={}), user=Depends(get_user)):
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404, "Webinar not found")
    img_type = (payload or {}).get("image_type") or "carousel"
    try:
        result = await generate_webinar_social_image(wid, w["title"], w.get("target_audience",""), w.get("starts_at",""), touch_type=img_type)
    except Exception as e:
        logger.error(f"Image generation exception: {e}")
        raise HTTPException(500, f"Image generation failed: {str(e)}")
    if not result or not isinstance(result, tuple) or len(result) != 2:
        raise HTTPException(500, "Image generation returned no data — Pillow may not be installed")
    image_bytes, mime = result
    if not image_bytes:
        raise HTTPException(500, "Image generation produced empty bytes")
    prev = await db.social_images.find_one({"webinar_id": wid}, {"_id": 0})
    if prev and prev.get("file_id"):
        await _delete_from_gridfs(social_images_fs, prev["file_id"])
    file_id = await _put_in_gridfs(social_images_fs, f"{wid}.png", image_bytes, mime,
                                    {"webinar_id": wid, "owner_id": user["id"]})
    await db.social_images.update_one({"webinar_id": wid},
                                       {"$set": {"webinar_id": wid, "owner_id": user["id"],
                                                 "file_id": file_id, "mime_type": mime,
                                                 "bytes": len(image_bytes),
                                                 "generated_at": now_iso()},
                                        "$unset": {"data": ""}}, upsert=True)
    import base64
    from time import time as _time
    ts = int(_time())
    b64 = base64.b64encode(image_bytes).decode()
    return {"ok": True, "url": f"/api/webinars/{wid}/social-image.png?v={ts}",
            "bytes": len(image_bytes), "mime": mime, "image_type": img_type,
            "base64": f"data:{mime};base64,{b64}"}


@router.get("/webinars/{wid}/social-image.png")
async def get_social_image(wid: str):
    meta = await db.social_images.find_one({"webinar_id": wid}, {"_id": 0})
    if not meta:
        raise HTTPException(404, "No social image generated yet")
    if meta.get("file_id"):
        return await _stream_gridfs(social_images_fs, meta["file_id"], meta.get("mime_type") or "image/png")
    # Legacy BinData path (pre-v1.3 storage). Serve once, then user can regenerate.
    if meta.get("data"):
        return Response(content=meta["data"], media_type=meta.get("mime_type") or "image/png",
                        headers={"Cache-Control": "public, max-age=300"})
    raise HTTPException(404, "No social image generated yet")
@router.get("/webinars/{wid}/adhoc-post")
async def get_adhoc_post(wid: str, user=Depends(get_user)):
    """Return last generated adhoc post for a webinar if any."""
    doc = await db.adhoc_posts.find_one({"webinar_id": wid, "owner_id": user["id"]}, {"_id": 0})
    return doc or {}


@router.post("/webinars/{wid}/adhoc-post/generate")
async def generate_adhoc(wid: str, payload: Dict[str, Any], user=Depends(get_user)):
    from ai import generate_adhoc_post as _gen_adhoc
    from image_gen import generate_webinar_social_image

    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)

    audience   = payload.get("audience", "linkedin")
    with_poll  = bool(payload.get("with_poll", False))
    custom_brief = payload.get("brief", "")
    with_image = bool(payload.get("with_image", True))

    # Generate text copy
    text_data = await _gen_adhoc(w, channel=audience, with_poll=with_poll, custom_brief=custom_brief)

    # Normalise: backend returns "content", frontend expects "post_text"
    post_text = text_data.get("content") or text_data.get("post_text") or ""
    hashtags  = text_data.get("hashtags", [])
    poll_q    = text_data.get("poll_question", "")

    image_url = None
    if with_image:
        try:
            # Pick template: quote_card for thought-provoking/insight, infographic for case_study/poll, carousel for rest
            img_type = payload.get("image_type", "")
            if not img_type:
                if any(word in post_text.lower() for word in ["?", "most ", "why ", "what if"]):
                    img_type = "quote_card"
                elif any(word in post_text.lower() for word in ["steps", "ways", "things", "tips", "here's"]):
                    img_type = "infographic"
                else:
                    img_type = "carousel"

            extra = {}
            if img_type == "quote_card":
                # Extract first sentence as the quote
                sentences = [s.strip() for s in post_text.replace("\n","").split(".") if len(s.strip()) > 20]
                extra["quote"] = sentences[0] if sentences else post_text[:120]
                extra["author"] = w.get("speaker","") or "ShowUp Webinar"
            elif img_type == "infographic":
                # Build points from post text lines
                lines = [l.strip() for l in post_text.split("\n") if l.strip() and len(l.strip()) > 10]
                extra["points"] = lines[:5] if lines else [post_text[:80]]

            result = await generate_webinar_social_image(wid, w["title"], w.get("target_audience",""), w.get("starts_at",""), touch_type=img_type, extra=extra)
            if result:
                image_bytes, mime = result
                prev = await db.adhoc_posts.find_one({"webinar_id": wid, "owner_id": user["id"]}, {"_id": 0})
                if prev and prev.get("file_id"):
                    await _delete_from_gridfs(social_images_fs, prev["file_id"])
                file_id = await _put_in_gridfs(social_images_fs, f"{wid}-adhoc.png", image_bytes, mime,
                                                {"webinar_id": wid, "owner_id": user["id"], "kind": "adhoc"})
                image_url = f"/api/webinars/{wid}/adhoc-image.png"
                await db.adhoc_posts.update_one({"webinar_id": wid, "owner_id": user["id"]},
                                                 {"$set": {"file_id": file_id, "mime_type": mime, "img_type": img_type}}, upsert=True)
        except Exception as img_err:
            pass

    await db.adhoc_posts.update_one({"webinar_id": wid, "owner_id": user["id"]},
                                     {"$set": {"text_data": text_data, "audience": audience,
                                               "generated_at": now_iso()}}, upsert=True)

    return {
        "ok": True,
        "audience": audience,
        "post_text": post_text,
        "hashtags": hashtags,
        "poll_question": poll_q,
        "poll_options": text_data.get("poll_options", []),
        "image_url": image_url,
    }


@router.get("/webinars/{wid}/adhoc-image.png")
async def get_adhoc_image(wid: str):
    row = await db.adhoc_posts.find_one({"webinar_id": wid}, {"_id": 0})
    if not row or not row.get("file_id"):
        raise HTTPException(404, "No ad-hoc image generated yet")
    return await _stream_gridfs(social_images_fs, row["file_id"], row.get("mime_type") or "image/png")



# ---------- ShowUp Score share image (Pillow → GridFS) ----------
async def _render_and_store_score(wid: str, owner_id: str, w: Dict[str, Any]) -> Dict[str, Any]:
    regs = await db.registrants.count_documents({"webinar_id": wid})
    atts = await db.registrants.count_documents({"webinar_id": wid, "attended": True})
    if regs == 0:
        raise HTTPException(404, "No attendance data yet — score not available")
    rate = round((atts / regs) * 100, 1)
    png = render_showup_score(w["title"], rate, regs, atts)
    prev = await db.showup_scores.find_one({"webinar_id": wid}, {"_id": 0})
    if prev and prev.get("file_id"):
        await _delete_from_gridfs(showup_scores_fs, prev["file_id"])
    file_id = await _put_in_gridfs(showup_scores_fs, f"{wid}-score.png", png, "image/png",
                                    {"webinar_id": wid, "owner_id": owner_id})
    await db.showup_scores.update_one({"webinar_id": wid},
                                       {"$set": {"webinar_id": wid, "owner_id": owner_id,
                                                 "file_id": file_id, "rate": rate,
                                                 "attendees": atts, "registrants": regs,
                                                 "generated_at": now_iso()}}, upsert=True)
    return {"rate": rate, "registrants": regs, "attendees": atts}


@router.post("/webinars/{wid}/showup-score/generate")
async def generate_score(wid: str, user=Depends(get_user)):
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    meta = await _render_and_store_score(wid, user["id"], w)
    return {"ok": True, "url": f"/api/webinars/{wid}/showup-score.png", **meta}


@router.get("/webinars/{wid}/showup-score.png")
async def get_score_image(wid: str):
    meta = await db.showup_scores.find_one({"webinar_id": wid}, {"_id": 0})
    if not meta or not meta.get("file_id"):
        w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
        if not w:
            raise HTTPException(404)
        await _render_and_store_score(wid, w["owner_id"], w)
        meta = await db.showup_scores.find_one({"webinar_id": wid}, {"_id": 0})
    return await _stream_gridfs(showup_scores_fs, meta["file_id"], "image/png")


@router.get("/webinars/{wid}/showup-score")
async def get_score_meta(wid: str):
    meta = await db.showup_scores.find_one({"webinar_id": wid}, {"_id": 0, "file_id": 0})
    if meta:
        return meta
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    regs = await db.registrants.count_documents({"webinar_id": wid})
    atts = await db.registrants.count_documents({"webinar_id": wid, "attended": True})
    rate = round((atts / regs) * 100, 1) if regs else 0
    return {"webinar_id": wid, "rate": rate, "registrants": regs, "attendees": atts,
            "generated_at": None}


# ---------- Circle.so sync + LinkedIn events ----------
@router.post("/circle/sync")
async def circle_sync(user=Depends(get_user)):
    s = await _user_settings_decrypted(user["id"])
    token = s.get("circle_api_key") or ""
    if not token:
        return {"members_synced": 0, "error": "Missing circle_api_key — add it in Settings → Circle.so"}
    members = await circle_sync_members(token)
    upserted = 0
    for m in members:
        email = (m.get("email") or "").lower().strip()
        if not email:
            continue
        await db.community_members.update_one(
            {"owner_id": user["id"], "email": email},
            {"$set": {
                "owner_id": user["id"],
                "member_id": str(m.get("id") or m.get("user_id") or ""),
                "name": m.get("name") or m.get("full_name") or email,
                "email": email,
                "joined_at": m.get("created_at") or m.get("joined_at"),
                "tags": m.get("tags") or [],
                "synced_at": now_iso(),
            }}, upsert=True)
        await db.registrants.update_many({"owner_id": user["id"], "email": email},
                                          {"$set": {"community_joined": True}})
        upserted += 1
    return {"members_synced": upserted}


@router.get("/circle/spaces")
async def list_circle_spaces(user=Depends(get_user)):
    """Helper to populate the space_id picker in Settings."""
    s = await _user_settings_decrypted(user["id"])
    token = s.get("circle_api_key") or ""
    if not token:
        return {"spaces": [], "error": "Missing circle_api_key"}
    from integrations import _circle_get  # local import to avoid cycles
    status, text, data, scheme = await _circle_get(token, "/api/admin/v2/spaces",
                                                     params={"per_page": 100})
    if status >= 400:
        return {"spaces": [], "error": f"{status}: {text[:300]}", "auth_scheme_tried": scheme}
    rows = data.get("records") or data.get("data") or []
    return {"spaces": [{"id": x.get("id"), "name": x.get("name"), "slug": x.get("slug")} for x in rows],
            "auth_scheme_used": scheme}


@router.get("/circle/diagnose")
async def circle_diagnose_route(user=Depends(get_user)):
    """Run a token diagnostic against Circle.so. Surfaces the exact failure reason."""
    s = await _user_settings_decrypted(user["id"])
    return await circle_diagnose(s.get("circle_api_key") or "")


@router.get("/circle/members")
async def list_community(user=Depends(get_user)):
    rows = await db.community_members.find({"owner_id": user["id"]}, {"_id": 0}).to_list(2000)
    return rows


@router.get("/linkedin/events")
async def linkedin_events(user=Depends(get_user)):
    s = await _user_settings_decrypted(user["id"])
    return await linkedin_list_events(
        s.get("linkedin_events_token") or s.get("linkedin_marketing_token") or "",
        s.get("linkedin_org_urn") or "")


# ---------- Test send (per provider) ----------
@router.post("/test-send/{channel}")
async def test_send(channel: str, payload: Dict[str, Any], user=Depends(get_user)):
    s = await _user_settings_decrypted(user["id"])
    image_url = None
    if channel == "instagram" and payload.get("auto_image"):
        img = await db.social_images.find_one({"owner_id": user["id"]}, {"_id": 0})
        if img:
            backend = os.environ.get("PUBLIC_BACKEND_URL") or payload.get("public_backend_url") or ""
            image_url = f"{backend}/api/webinars/{img['webinar_id']}/social-image.png"
    res = await send_dispatch(
        channel, s,
        to_email=payload.get("to_email") or user["email"],
        to_phone=payload.get("to_phone"),
        subject=payload.get("subject") or "ShowUp.ai test",
        body=payload.get("body") or "This is a ShowUp.ai test message.",
        image_url=image_url,
    )
    return res


# ---------- Manual Send-Now (touch) ----------
async def _deliver_touch(t: Dict[str, Any], settings: Dict[str, Any], public_backend_url: str = "") -> Dict[str, Any]:
    w = await db.webinars.find_one({"id": t["webinar_id"], "owner_id": t.get("owner_id", "")}, {"_id": 0})
    if not w:
        return {"ok": False, "detail": "Webinar missing"}
    ai_ch = (t.get("ai_copy") or {}).get("channels") or {}
    variant_key = "casual" if t.get("selected_variant") == 1 else "safe"
    delivery_log: List[Dict[str, Any]] = []
    ics_bytes = build_ics(w) if t["touch_num"] == 1 else None

    audience_filter: Dict[str, Any] = {"webinar_id": t["webinar_id"]}
    if t["trigger"] == "after_event_attendees":
        audience_filter["attended"] = True
    elif t["trigger"] == "after_event_noshows":
        audience_filter["attended"] = {"$ne": True}
    regs = await db.registrants.find(audience_filter, {"_id": 0}).to_list(5000)

    ig_image_url = None
    if "instagram" in (t.get("channels") or []):
        img = await db.social_images.find_one({"webinar_id": t["webinar_id"]}, {"_id": 0})
        if img and public_backend_url:
            ig_image_url = f"{public_backend_url}/api/webinars/{t['webinar_id']}/social-image.png"

    for ch in t.get("channels") or []:
        c = ai_ch.get(ch, {}).get(variant_key) or {}
        subject = c.get("subject") or w["title"]
        body = c.get("body") or ""
        # Touch #7 (post-event attendees) gets a ShowUp Score share link appended
        if t["touch_num"] == 7 and ch == "email" and public_backend_url:
            score_url = f"{public_backend_url}/api/webinars/{t['webinar_id']}/showup-score.png"
            body = body + f"\n\n📊 Share the energy from this session — your ShowUp Score: {score_url}"
        if ch in ("email", "whatsapp"):
            if not regs:
                delivery_log.append({"channel": ch, "ok": False,
                                      "detail": "No recipients in audience — share the registration link first"})
                continue
            for r in regs:
                res = await send_dispatch(ch, settings,
                                           to_email=r.get("email"), to_phone=r.get("phone"),
                                           subject=subject, body=body,
                                           ics_bytes=ics_bytes if ch == "email" else None)
                delivery_log.append({"channel": ch, "recipient": r.get("email") or r.get("phone"),
                                      "ok": res.get("ok"), "detail": res.get("detail")})
        else:
            res = await send_dispatch(ch, settings, to_email=None, to_phone=None,
                                       subject=subject, body=body,
                                       image_url=ig_image_url if ch == "instagram" else None)
            delivery_log.append({"channel": ch, "ok": res.get("ok"), "detail": res.get("detail")})
    ok_any = any(d.get("ok") for d in delivery_log)
    return {"ok": ok_any, "log": delivery_log}


@router.post("/touches/{tid}/send-now")
async def send_now(tid: str, request: Request, user=Depends(get_user)):
    t = await db.touches.find_one({"id": tid, "owner_id": user["id"]}, {"_id": 0})
    if not t:
        raise HTTPException(404)
    if t.get("approval_status") != "approved":
        raise HTTPException(400, "Touch must be approved before sending")
    settings = await _user_settings_decrypted(user["id"])
    public_url = os.environ.get("PUBLIC_BACKEND_URL") or str(request.base_url).rstrip("/")
    result = await _deliver_touch(t, settings, public_backend_url=public_url)
    await db.touches.update_one({"id": tid, "owner_id": user["id"]},
                                  {"$set": {"sent_status": "sent" if result["ok"] else "failed",
                                            "sent_at": now_iso(),
                                            "delivery_log": result.get("log", [])}})
    return result


# ---------- Scheduler tick ----------
async def scheduler_tick():
    now = datetime.now(timezone.utc).isoformat()
    sent_count = 0
    candidates = await db.touches.find({"approval_status": "approved", "sent_status": "planned",
                                          "scheduled_at": {"$lte": now}}, {"_id": 0}).to_list(200)
    for t in candidates:
        settings = await _user_settings_decrypted(t["owner_id"])
        auto = (settings.get("per_touch_auto_send") or {}).get(str(t["touch_num"]), False)
        if auto:
            public_url = os.environ.get("PUBLIC_BACKEND_URL", "")
            result = await _deliver_touch(t, settings, public_backend_url=public_url)
            await db.touches.update_one({"id": t["id"], "owner_id": t.get("owner_id", "")},
                                          {"$set": {"sent_status": "sent" if result["ok"] else "failed",
                                                    "sent_at": now_iso(),
                                                    "delivery_log": result.get("log", [])}})
            if result.get("ok"):
                sent_count += 1
        else:
            await db.touches.update_one({"id": t["id"], "owner_id": t.get("owner_id", "")},
                                          {"$set": {"sent_status": "queued", "sent_at": now_iso()}})

    # Auto-archive webinars 2 days after event date
    try:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        archived = await db.webinars.update_many(
            {"starts_at": {"$lt": cutoff}, "status": {"$nin": ["archived", "completed"]}},
            {"$set": {"status": "archived"}}
        )
        if archived.modified_count:
            logger.info(f"Auto-archived {archived.modified_count} webinars")
    except Exception as e:
        logger.error(f"Auto-archive error: {e}")

    logger.info(f"Scheduler tick: {sent_count} touches delivered")


# ---------- Schedule overview (calendar feed) ----------
@router.get("/schedule")
async def get_schedule(user=Depends(get_user)):
    """Return all pending/planned touches with scheduling info for the calendar view."""
    touches = await db.touches.find(
        {"owner_id": user["id"], "sent_status": {"$in": ["planned", "queued"]}},
        {"_id": 0}
    ).to_list(1000)

    # Bulk fetch webinars (no N+1)
    wid_set = list({t["webinar_id"] for t in touches})
    webinars_list = await db.webinars.find(
        {"id": {"$in": wid_set}}, {"_id": 0, "id": 1, "title": 1, "starts_at": 1, "status": 1}
    ).to_list(500)
    wmap = {w["id"]: w for w in webinars_list}

    result = []
    for t in touches:
        w = wmap.get(t["webinar_id"], {})
        result.append({
            "touch_id": t["id"],
            "touch_num": t["touch_num"],
            "touch_name": t["name"],
            "trigger": t["trigger"],
            "scheduled_at": t.get("scheduled_at"),
            "approval_status": t["approval_status"],
            "sent_status": t["sent_status"],
            "channels": t.get("channels", []),
            "webinar_id": t["webinar_id"],
            "webinar_title": w.get("title", "?"),
            "webinar_starts_at": w.get("starts_at"),
            "webinar_status": w.get("status", "?"),
        })

    result.sort(key=lambda x: (x.get("scheduled_at") or "9999"))
    return result


# ══════════════════════════════════════════════
# EMAIL ANALYTICS — open, click, bounce, unsub
# ══════════════════════════════════════════════

@router.get("/email-analytics")
async def email_analytics(user=Depends(get_user)):
    """Aggregate email stats across all sent touches — pulled from Brevo."""
    import httpx
    from datetime import datetime, timedelta

    settings = await db.settings.find_one({"owner_id": user["id"]}, {"_id": 0})
    if not settings or not settings.get("brevo_api_key"):
        return {"error": "Brevo not configured", "stats": {}, "touches": []}

    api_key = settings["brevo_api_key"]

    # Get all sent email touches for this user
    sent_touches = await db.touches.find(
        {"owner_id": user["id"], "sent_status": "sent", "channels": {"$in": ["email"]}},
        {"_id": 0}
    ).sort("updated_at", -1).to_list(100)

    # Pull Brevo campaign/transactional stats
    headers = {"api-key": api_key, "Content-Type": "application/json"}

    # Overall transactional stats last 30 days
    start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    end_date = datetime.utcnow().strftime("%Y-%m-%d")

    aggregate = {
        "sent": 0, "delivered": 0, "opens": 0, "unique_opens": 0,
        "clicks": 0, "unique_clicks": 0, "bounces": 0,
        "soft_bounces": 0, "hard_bounces": 0, "unsubscribes": 0,
        "spam": 0,
    }

    touch_stats = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Overall transactional email stats
            r = await client.get(
                "https://api.brevo.com/v3/smtp/statistics/aggregatedReport",
                headers=headers,
                params={"startDate": start_date, "endDate": end_date, "days": 30}
            )
            if r.status_code == 200:
                data = r.json()
                aggregate["sent"]          = data.get("requests", 0)
                aggregate["delivered"]     = data.get("delivered", 0)
                aggregate["opens"]         = data.get("opens", 0)
                aggregate["unique_opens"]  = data.get("uniqueOpens", 0)
                aggregate["clicks"]        = data.get("clicks", 0)
                aggregate["unique_clicks"] = data.get("uniqueClicks", 0)
                aggregate["bounces"]       = data.get("hardBounces", 0) + data.get("softBounces", 0)
                aggregate["hard_bounces"]  = data.get("hardBounces", 0)
                aggregate["soft_bounces"]  = data.get("softBounces", 0)
                aggregate["unsubscribes"]  = data.get("unsubscribes", 0)
                aggregate["spam"]          = data.get("spamReports", 0)

            # Per-day stats for chart
            r2 = await client.get(
                "https://api.brevo.com/v3/smtp/statistics/reports",
                headers=headers,
                params={"startDate": start_date, "endDate": end_date, "days": 30}
            )
            daily = []
            if r2.status_code == 200:
                reports = r2.json().get("reports", [])
                for day in reports:
                    daily.append({
                        "date": day.get("date", ""),
                        "sent": day.get("requests", 0),
                        "opens": day.get("opens", 0),
                        "clicks": day.get("clicks", 0),
                        "bounces": day.get("hardBounces", 0) + day.get("softBounces", 0),
                        "unsubscribes": day.get("unsubscribes", 0),
                    })

            # Per-touch stats — enrich with webinar info
            for t in sent_touches[:20]:
                w = await db.webinars.find_one({"id": t["webinar_id"]}, {"_id": 0, "title": 1})
                touch_stats.append({
                    "touch_id": t["id"],
                    "touch_num": t["touch_num"],
                    "touch_name": t["name"],
                    "touch_type": t.get("ai_copy", {}).get("touch_type", "reminder"),
                    "webinar_title": w["title"] if w else "?",
                    "webinar_id": t["webinar_id"],
                    "sent_at": t.get("updated_at"),
                    "registrant_count": t.get("registrant_count", 0),
                    "delivery_log": t.get("delivery_log", []),
                    # Individual stats not available in transactional free plan
                    # but message IDs stored for webhook enrichment
                    "message_ids": [
                        log.get("external_id") for log in t.get("delivery_log", [])
                        if log.get("channel") == "email" and log.get("external_id")
                    ],
                })

    except Exception as e:
        return {"error": str(e), "stats": aggregate, "touches": touch_stats, "daily": []}

    # Computed rates
    sent = aggregate["sent"] or 1
    rates = {
        "open_rate":    round(aggregate["unique_opens"] / sent * 100, 1),
        "click_rate":   round(aggregate["unique_clicks"] / sent * 100, 1),
        "bounce_rate":  round(aggregate["bounces"] / sent * 100, 1),
        "unsub_rate":   round(aggregate["unsubscribes"] / sent * 100, 1),
        "delivery_rate":round(aggregate["delivered"] / sent * 100, 1),
    }

    return {
        "stats": aggregate,
        "rates": rates,
        "daily": daily,
        "touches": touch_stats,
        "period": f"{start_date} to {end_date}",
    }


# ══════════════════════════════════════════════
# WE'RE LIVE — instant broadcast to all registrants
# ══════════════════════════════════════════════
@router.post("/webinars/{wid}/go-live")
async def go_live(wid: str, user=Depends(get_user)):
    """Send instant 'We are live!' message to all registrants."""
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    registrants = await db.registrants.find({"webinar_id": wid}, {"_id": 0}).to_list(5000)
    if not registrants:
        return {"ok": True, "sent": 0, "message": "No registrants to notify"}

    settings = await _user_settings_decrypted(user["id"])
    join_link = w.get("join_link") or w.get("registration_link") or ""

    subject = f"We're live now — {w['title']}"
    body = f"""We are live right now!

{w['title']}

Join here: {join_link}

See you inside!
"""
    sent = 0
    for reg in registrants:
        if reg.get("email"):
            try:
                result = await send_email(settings, reg["email"], subject, body)
                if result.ok:
                    sent += 1
            except:
                pass

    await db.webinars.update_one({"id": wid}, {"$set": {"went_live_at": now_iso()}})
    return {"ok": True, "sent": sent, "total": len(registrants)}


# ══════════════════════════════════════════════
# POST-WEBINAR — no-show FOMO + takeaways
# ══════════════════════════════════════════════
@router.post("/webinars/{wid}/post-webinar")
async def post_webinar_sequence(wid: str, payload: dict = Body(default={}), user=Depends(get_user)):
    """Send post-webinar sequences to attendees and no-shows separately."""
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)

    settings = await _user_settings_decrypted(user["id"])
    registrants = await db.registrants.find({"webinar_id": wid}, {"_id": 0}).to_list(5000)

    attendees  = [r for r in registrants if r.get("attended")]
    no_shows   = [r for r in registrants if not r.get("attended")]
    recording  = payload.get("recording_url", "")

    sent_att, sent_ns = 0, 0

    # Attendee email — thank you + recording
    att_subject = f"Thank you for joining — {w['title']}"
    att_body = f"""Thank you for joining us today!

{w['title']}

{"Here is the recording: " + recording if recording else "The recording will be shared shortly."}

We hope it was valuable. See you at the next one!
"""
    for reg in attendees:
        if reg.get("email"):
            try:
                result = await send_email(settings, reg["email"], att_subject, att_body)
                if result.ok:
                    sent_att += 1
            except:
                pass

    # No-show FOMO email
    ns_subject = f"You missed it — here's what happened at {w['title']}"
    ns_body = f"""We missed you today at {w['title']}.

Here's what the attendees learned:
• How to significantly improve webinar attendance rates
• Practical strategies that work for your audience
• Real examples and case studies

{"Watch the recording here: " + recording if recording else "We'll share the recording soon — watch out for it."}

Don't miss the next one — we run these regularly.
"""
    for reg in no_shows:
        if reg.get("email"):
            try:
                result = await send_email(settings, reg["email"], ns_subject, ns_body)
                if result.ok:
                    sent_ns += 1
            except:
                pass

    return {
        "ok": True,
        "attendees_emailed": sent_att,
        "no_shows_emailed": sent_ns,
        "total_registrants": len(registrants)
    }


@router.post("/webinars/{wid}/carousel/generate")
async def generate_carousel(wid: str, payload: Dict[str, Any] = Body(default={}), user=Depends(get_user)):
    """Generate full carousel (all slides) as ZIP download."""
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    
    from image_gen import make_carousel_preview, make_slide
    import asyncio, zipfile, io, base64
    
    groq_key = os.environ.get("GROQ_API_KEY", "")
    slides_content = []
    
    if groq_key:
        try:
            from groq import Groq as G
            def _gen():
                g = G(api_key=groq_key)
                resp = g.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": f"""Create 4 LinkedIn carousel slides about: {w.get('title','')}
Audience: {w.get('target_audience','webinar hosts')}
Return ONLY JSON: {{"slides": [{{"heading": "max 40 chars", "body": "max 120 chars"}}]}}"""}],
                    max_tokens=500, temperature=0.7,
                )
                return resp.choices[0].message.content
            import json, re
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(None, _gen)
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                slides_content = json.loads(m.group()).get("slides", [])
        except Exception as e:
            logger.error(f"Carousel gen: {e}")
    
    if not slides_content:
        slides_content = [
            {"heading": "The Problem", "body": "70% of webinar registrants never show up to the live event."},
            {"heading": "Root Cause", "body": "People lose the reason to care between registration and the event."},
            {"heading": "The Fix", "body": "Send value not reminders — insight, poll, case study, join link."},
            {"heading": "The Result", "body": "Attendance jumps from 31% to 62%+ with right 8-touch sequence."},
        ]
    
    total = len(slides_content) + 2
    loop = asyncio.get_event_loop()
    all_slides = []
    
    # Cover
    cover = await loop.run_in_executor(None, make_slide, 0, total, 
                                        w.get('title',''), 
                                        f"For {w.get('target_audience','')}" if w.get('target_audience') else "Swipe →",
                                        True, False)
    all_slides.append(("slide_01_cover.png", cover))
    
    # Content slides
    for i, s in enumerate(slides_content):
        slide = await loop.run_in_executor(None, make_slide, i+1, total,
                                           s["heading"], s["body"], False, False)
        all_slides.append((f"slide_{i+2:02d}.png", slide))
    
    # CTA
    cta = await loop.run_in_executor(None, make_slide, total-1, total, "", "", False, True)
    all_slides.append((f"slide_{total:02d}_cta.png", cta))
    
    # Pack ZIP
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        for name, data in all_slides:
            zf.writestr(name, data)
    
    zip_bytes = zip_buf.getvalue()
    b64 = base64.b64encode(zip_bytes).decode()
    
    return {
        "ok": True,
        "slides": len(all_slides),
        "base64": f"data:application/zip;base64,{b64}",
        "filename": f"carousel-{w.get('title','webinar')[:30]}.zip"
    }
