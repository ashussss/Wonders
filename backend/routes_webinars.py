"""Webinars, touches, registrants, and lead magnets endpoints."""
import asyncio
import uuid
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Body, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from database import db
from auth_utils import get_user, now_iso
from models import WebinarIn, WebinarPatch, RegistrantIn, TouchPatch, LeadMagnetPatch
from config import TOUCH_DEFS
from ai import generate_touch_copy, generate_lead_magnets, compute_send_time, compute_dynamic_schedule, touch_reasoning

router = APIRouter(prefix="/api")
limiter = Limiter(key_func=get_remote_address)


def _webinar_doc(uid: str, data: WebinarIn) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "owner_id": uid,
        "title": data.title,
        "description": data.description,
        "speaker": data.speaker,
        "target_audience": data.target_audience,
        "starts_at": data.starts_at,
        "timezone": data.timezone,
        "join_link": data.join_link,
        "registration_link": data.registration_link,
        "status": "scheduled",
        "created_at": now_iso(),
        "enabled_touches": {str(t["num"]): True for t in TOUCH_DEFS},
    }


import logging
logger = logging.getLogger("showup.webinars")


async def _bg_generate_all(webinar_id: str):
    """Background task fired after webinar creation — generates AI copy for
    lead magnets and all 8 touches in parallel. Errors are logged, not swallowed,
    so failures are visible instead of silently doing nothing."""
    try:
        w = await db.webinars.find_one({"id": webinar_id}, {"_id": 0})
        if not w:
            logger.warning(f"_bg_generate_all: webinar {webinar_id} not found")
            return

        lm_data = await generate_lead_magnets(w)
        await db.lead_magnets.update_one({"webinar_id": webinar_id},
                                          {"$set": {"ai_content": lm_data, "generated_at": now_iso()}})

        touches = await db.touches.find({"webinar_id": webinar_id}, {"_id": 0}).to_list(50)

        # Get user settings for brand tone
        settings = await db.settings.find_one({"owner_id": w["owner_id"]}, {"_id": 0}) or {}
        brand_instructions = []
        if settings.get("brand_tone"):
            brand_instructions.append(f"Tone: {settings['brand_tone']}")
        if settings.get("brand_language"):
            brand_instructions.append(f"Language: {settings['brand_language']}")
        if settings.get("brand_audience"):
            brand_instructions.append(f"Audience: {settings['brand_audience']}")
        if settings.get("brand_always_include"):
            brand_instructions.append(f"Always include: {settings['brand_always_include']}")
        if settings.get("brand_banned_phrases"):
            brand_instructions.append(f"Never use these phrases: {settings['brand_banned_phrases']}")
        global_instructions = "\n".join(brand_instructions)

        async def _gen_one(t):
            try:
                copy = await generate_touch_copy(w, t["touch_num"], t.get("channels", ["email"]),
                                                  custom_instructions=global_instructions)
                reasoning = await touch_reasoning(t["touch_num"], t["channels"])
                await db.touches.update_one({"id": t["id"], "owner_id": user["id"]},
                                             {"$set": {"ai_copy": copy, "ai_reasoning": reasoning}})
            except Exception as e:
                logger.error(f"_bg_generate_all: touch {t.get('touch_num')} for {webinar_id} failed: {e}")

        await asyncio.gather(*[_gen_one(t) for t in touches], return_exceptions=True)
    except Exception as e:
        logger.error(f"_bg_generate_all: webinar {webinar_id} failed entirely: {e}")


# --------- Webinars ---------
@router.get("/webinars")
async def list_webinars(user=Depends(get_user)):
    rows = await db.webinars.find({"owner_id": user["id"]}, {"_id": 0}).sort("starts_at", -1).to_list(500)
    for w in rows:
        w["registrant_count"] = await db.registrants.count_documents({"webinar_id": w["id"]})
        w["attendee_count"] = await db.registrants.count_documents({"webinar_id": w["id"], "attended": True})
        w["attendance_rate"] = round((w["attendee_count"]/w["registrant_count"])*100, 1) if w["registrant_count"] else 0
    return rows


@router.post("/webinars")
async def create_webinar(data: WebinarIn, user=Depends(get_user)):
    doc = _webinar_doc(user["id"], data)
    await db.webinars.insert_one(doc)
    settings = await db.settings.find_one({"owner_id": user["id"]}, {"_id": 0}) or {}
    default_channels = settings.get("default_channels", {})
    touches = []
    for tdef in TOUCH_DEFS:
        tnum = tdef["num"]
        channels = default_channels.get(str(tnum), tdef["default_channels"])
        sched = await compute_dynamic_schedule(data.starts_at, tnum) if tnum != 1 else None
        touches.append({
            "id": str(uuid.uuid4()), "webinar_id": doc["id"], "owner_id": user["id"],
            "touch_num": tnum, "name": tdef["name"], "trigger": tdef["trigger"],
            "channels": channels, "scheduled_at": sched, "ai_reasoning": "", "ai_copy": {},
            "selected_variant": 0, "copy_overrides": {},
            "approval_status": "pending", "sent_status": "planned",
            "sent_at": None, "created_at": now_iso(),
        })
    if touches:
        await db.touches.insert_many(touches)
    await db.lead_magnets.insert_one({
        "id": str(uuid.uuid4()), "webinar_id": doc["id"], "owner_id": user["id"],
        "ai_content": {}, "edited_content": {}, "approval_status": "pending", "created_at": now_iso(),
    })
    asyncio.create_task(_bg_generate_all(doc["id"]))
    return {"id": doc["id"]}


@router.get("/webinars/{wid}")
async def get_webinar(wid: str, user=Depends(get_user)):
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    w["registrant_count"] = await db.registrants.count_documents({"webinar_id": wid})
    w["attendee_count"] = await db.registrants.count_documents({"webinar_id": wid, "attended": True})
    w["attendance_rate"] = round((w["attendee_count"]/w["registrant_count"])*100, 1) if w["registrant_count"] else 0
    return w


@router.patch("/webinars/{wid}")
async def patch_webinar(wid: str, data: WebinarPatch, user=Depends(get_user)):
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    if not upd:
        return {"ok": True}
    await db.webinars.update_one({"id": wid, "owner_id": user["id"]}, {"$set": upd})
    if "starts_at" in upd:
        for tdef in TOUCH_DEFS:
            if tdef["num"] == 1:
                continue
            sched = await compute_dynamic_schedule(upd["starts_at"], tdef["num"])
            await db.touches.update_one({"webinar_id": wid, "touch_num": tdef["num"]},
                                         {"$set": {"scheduled_at": sched}})
    return {"ok": True}


@router.delete("/webinars/{wid}")
async def delete_webinar(wid: str, user=Depends(get_user)):
    await db.webinars.delete_one({"id": wid, "owner_id": user["id"]})
    await db.touches.delete_many({"webinar_id": wid})
    await db.registrants.delete_many({"webinar_id": wid})
    await db.lead_magnets.delete_many({"webinar_id": wid})
    return {"ok": True}


# --------- Registrants ---------
@router.get("/webinars/{wid}/registrants")
async def list_registrants(wid: str, user=Depends(get_user)):
    return await db.registrants.find({"webinar_id": wid, "owner_id": user["id"]}, {"_id": 0}).to_list(2000)


async def _trigger_touch1(wid: str):
    t1 = await db.touches.find_one({"webinar_id": wid, "touch_num": 1}, {"_id": 0})
    if t1 and not t1.get("ai_copy"):
        w = await db.webinars.find_one({"id": wid}, {"_id": 0})
        copy = await generate_touch_copy(w, 1, t1["channels"])
        await db.touches.update_one({"id": t1["id"], "owner_id": user["id"]}, {"$set": {"ai_copy": copy}})


@router.post("/webinars/{wid}/register")
@limiter.limit("10/minute")
async def public_register(wid: str, data: RegistrantIn, request: Request):
    w = await db.webinars.find_one({"id": wid}, {"_id": 0})
    if not w:
        raise HTTPException(404, "Webinar not found")
    existing = await db.registrants.find_one({"webinar_id": wid, "email": data.email.lower()})
    if existing:
        return {"ok": True, "deduped": True}
    reg = {"id": str(uuid.uuid4()), "webinar_id": wid, "owner_id": w["owner_id"],
           "name": data.name, "email": data.email.lower(), "phone": data.phone,
           "source": data.source, "attended": False, "registered_at": now_iso()}
    await db.registrants.insert_one(reg)
    asyncio.create_task(_trigger_touch1(wid))
    return {"ok": True, "id": reg["id"]}


@router.post("/webinars/{wid}/registrants/import")
async def import_registrants(wid: str, items: List[RegistrantIn], user=Depends(get_user)):
    inserted = 0
    deduped = 0
    for it in items:
        existing = await db.registrants.find_one({"webinar_id": wid, "email": it.email.lower()})
        if existing:
            deduped += 1
            continue
        await db.registrants.insert_one({"id": str(uuid.uuid4()), "webinar_id": wid, "owner_id": user["id"],
                                          "name": it.name, "email": it.email.lower(), "phone": it.phone,
                                          "source": it.source or "linkedin_manual", "attended": False,
                                          "registered_at": now_iso()})
        inserted += 1
    return {"inserted": inserted, "deduped": deduped}


@router.post("/webinars/{wid}/webhooks/circle")
@limiter.limit("60/minute")
async def circle_webhook(wid: str, payload: Dict[str, Any], request: Request):
    # Circle's official community_member_created shape: {community_member: {email, name, ...}}
    member = payload.get("community_member") or payload
    email = (member.get("email") or "").lower().strip()
    name = member.get("name") or member.get("full_name") or (email.split("@")[0] if email else "")
    if not email:
        raise HTTPException(400, "email required")
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    existing = await db.registrants.find_one({"webinar_id": wid, "email": email})
    if existing:
        return {"ok": True, "deduped": True}
    await db.registrants.insert_one({"id": str(uuid.uuid4()), "webinar_id": wid, "owner_id": w["owner_id"],
                                      "name": name, "email": email, "phone": member.get("phone"),
                                      "source": "circle", "attended": False,
                                      "community_joined": True, "registered_at": now_iso()})
    return {"ok": True}


@router.patch("/registrants/{rid}")
async def update_registrant(rid: str, payload: Dict[str, Any], user=Depends(get_user)):
    allowed = {k: v for k, v in payload.items() if k in ("attended", "name", "phone", "community_joined")}
    await db.registrants.update_one({"id": rid, "owner_id": user["id"]}, {"$set": allowed})
    return {"ok": True}


@router.post("/webinars/{wid}/mark-attendance")
async def mark_attendance(wid: str, payload: Dict[str, Any], user=Depends(get_user)):
    emails = [e.lower() for e in payload.get("emails", [])]
    await db.registrants.update_many({"webinar_id": wid, "email": {"$in": emails}}, {"$set": {"attended": True}})
    await db.webinars.update_one({"id": wid, "owner_id": user["id"]}, {"$set": {"status": "completed"}})
    return {"ok": True, "marked": len(emails)}


# --------- Touches ---------
@router.get("/webinars/{wid}/touches")
async def list_touches(wid: str, user=Depends(get_user)):
    return await db.touches.find({"webinar_id": wid, "owner_id": user["id"]}, {"_id": 0}).sort("touch_num", 1).to_list(50)


@router.patch("/touches/{tid}")
async def patch_touch(tid: str, data: TouchPatch, user=Depends(get_user)):
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    if "approval_status" in upd and upd["approval_status"] == "approved":
        upd["approved_at"] = now_iso()
    await db.touches.update_one({"id": tid, "owner_id": user["id"]}, {"$set": upd})
    if "channels" in upd:
        t = await db.touches.find_one({"id": tid, "owner_id": user["id"]}, {"_id": 0})
        if not t:
            raise HTTPException(404)
        w = await db.webinars.find_one({"id": t["webinar_id"], "owner_id": user["id"]}, {"_id": 0})
        copy = await generate_touch_copy(w, t["touch_num"], upd["channels"])
        await db.touches.update_one({"id": tid, "owner_id": user["id"]}, {"$set": {"ai_copy": copy}})
    return {"ok": True}


@router.post("/touches/{tid}/regenerate")
async def regen_touch(tid: str, user=Depends(get_user)):
    t = await db.touches.find_one({"id": tid, "owner_id": user["id"]}, {"_id": 0})
    if not t:
        raise HTTPException(404)
    w = await db.webinars.find_one({"id": t["webinar_id"]}, {"_id": 0})
    copy = await generate_touch_copy(w, t["touch_num"], t["channels"])
    await db.touches.update_one({"id": tid, "owner_id": user["id"]}, {"$set": {"ai_copy": copy, "approval_status": "pending"}})
    return {"ok": True, "copy": copy}


# --------- Lead Magnets ---------
@router.get("/webinars/{wid}/lead-magnets")
async def get_lead_magnets(wid: str, user=Depends(get_user)):
    lm = await db.lead_magnets.find_one({"webinar_id": wid, "owner_id": user["id"]}, {"_id": 0})
    return lm or {}


@router.post("/webinars/{wid}/lead-magnets/regenerate")
async def regen_lead_magnets(wid: str, user=Depends(get_user)):
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    content = await generate_lead_magnets(w)
    await db.lead_magnets.update_one({"webinar_id": wid},
                                      {"$set": {"ai_content": content, "approval_status": "pending",
                                                "generated_at": now_iso()}})
    return {"ok": True, "content": content}


@router.patch("/lead-magnets/{lmid}")
async def patch_lm(lmid: str, data: LeadMagnetPatch, user=Depends(get_user)):
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    await db.lead_magnets.update_one({"id": lmid, "owner_id": user["id"]}, {"$set": upd})
    return {"ok": True}


# --------- Approval Queue ---------
@router.get("/approval-queue")
async def approval_queue(user=Depends(get_user), webinar_id: str = None):
    # Get only active (non-archived) webinars
    active_webinars = await db.webinars.find(
        {"owner_id": user["id"], "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "title": 1, "starts_at": 1}
    ).to_list(200)
    active_ids = [w["id"] for w in active_webinars]
    webinar_map = {w["id"]: w for w in active_webinars}

    # Filter by specific webinar if provided
    query = {"owner_id": user["id"], "approval_status": "pending",
             "sent_status": {"$ne": "sent"}, "webinar_id": {"$in": active_ids}}
    if webinar_id:
        query["webinar_id"] = webinar_id

    rows = await db.touches.find(query, {"_id": 0}).to_list(500)
    for r in rows:
        w = webinar_map.get(r["webinar_id"], {})
        r["webinar_title"] = w.get("title", "?")
        r["webinar_starts_at"] = w.get("starts_at")
    rows.sort(key=lambda x: (x.get("webinar_starts_at") or "9999", x.get("scheduled_at") or "9999", x["touch_num"]))

    # Return active webinars list for dropdown
    return {
        "touches": rows,
        "webinars": [{"id": w["id"], "title": w["title"], "starts_at": w.get("starts_at")} for w in active_webinars],
        "total": len(rows)
    }


# --------- Regenerate ALL touches for a webinar ---------
@router.post("/webinars/{wid}/regenerate-all")
async def regen_all_touches(wid: str, user=Depends(get_user)):
    import asyncio
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    touches = await db.touches.find({"webinar_id": wid, "owner_id": user["id"]}, {"_id": 0}).to_list(20)
    if not touches:
        raise HTTPException(404, "No touches found for this webinar")

    async def regen_one(t):
        try:
            copy = await generate_touch_copy(w, t["touch_num"], t.get("channels", ["email"]))
            await db.touches.update_one(
                {"id": t["id"]},
                {"$set": {"ai_copy": copy, "approval_status": "pending"}}
            )
            return True
        except Exception:
            return False

    results = await asyncio.gather(*[regen_one(t) for t in touches], return_exceptions=True)
    count = sum(1 for r in results if r is True)
    return {"ok": True, "regenerated": count, "total": len(touches)}


# ══════════════════════════════════════════════
# CONTENT LIBRARY — approved touches with images
# ══════════════════════════════════════════════
@router.get("/content-library")
async def content_library(user=Depends(get_user)):
    """All approved touches across all webinars, with image URLs."""
    touches = await db.touches.find(
        {"owner_id": user["id"], "approval_status": "approved"},
        {"_id": 0}
    ).sort("updated_at", -1).to_list(200)

    result = []
    for t in touches:
        w = await db.webinars.find_one({"id": t["webinar_id"]}, {"_id": 0, "title": 1, "starts_at": 1})

        # Check if social image exists for this webinar
        img_meta = await db.social_images.find_one({"webinar_id": t["webinar_id"]}, {"_id": 0, "generated_at": 1})

        result.append({
            "touch_id": t["id"],
            "touch_num": t["touch_num"],
            "touch_name": t["name"],
            "touch_type": t.get("ai_copy", {}).get("touch_type", "reminder"),
            "webinar_id": t["webinar_id"],
            "webinar_title": w["title"] if w else "?",
            "webinar_starts_at": w["starts_at"] if w else None,
            "channels": t.get("channels", []),
            "selected_variant": t.get("selected_variant", 0),
            "ai_copy": t.get("ai_copy", {}),
            "approval_status": t["approval_status"],
            "sent_status": t.get("sent_status", "planned"),
            "has_image": bool(img_meta),
            "image_url": f"/api/webinars/{t['webinar_id']}/social-image.png" if img_meta else None,
            "scheduled_at": t.get("scheduled_at"),
            "approved_at": t.get("updated_at"),
        })

    return result


# ══════════════════════════════════════════════
# AI WEBINAR HEALTH SCORE + ATTENDANCE PREDICTION
# ══════════════════════════════════════════════

@router.get("/webinars/{wid}/ai-insights")
async def ai_insights(wid: str, user=Depends(get_user)):
    """AI-powered health score + attendance prediction + recommendations."""
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)

    # Gather data
    touches     = await db.touches.find({"webinar_id": wid}, {"_id": 0}).to_list(20)
    registrants = await db.registrants.find({"webinar_id": wid}, {"_id": 0}).to_list(5000)
    total_reg   = len(registrants)
    attended    = sum(1 for r in registrants if r.get("attended"))
    approved    = sum(1 for t in touches if t.get("approval_status") == "approved")
    sent        = sum(1 for t in touches if t.get("sent_status") == "sent")
    pending     = sum(1 for t in touches if t.get("approval_status") == "pending")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    try:
        event_dt = datetime.fromisoformat(w["starts_at"].replace("Z", "+00:00"))
        days_until = (event_dt - now).days
        is_past = days_until < 0
    except:
        days_until = None
        is_past = False

    # Compute health score (0-100)
    score = 0
    factors = []

    # AI copy generated (20 pts)
    copy_generated = sum(1 for t in touches if t.get("ai_copy") and t["ai_copy"].get("channels"))
    copy_pct = copy_generated / max(len(touches), 1) * 100
    copy_pts = int(copy_pct * 0.20)
    score += copy_pts
    factors.append({"factor": "AI Copy Generated", "score": copy_pts, "max": 20,
                    "detail": f"{copy_generated}/{len(touches)} touches have AI copy"})

    # Approval rate (20 pts)
    approval_pct = approved / max(len(touches), 1) * 100
    approval_pts = int(approval_pct * 0.20)
    score += approval_pts
    factors.append({"factor": "Touch Approvals", "score": approval_pts, "max": 20,
                    "detail": f"{approved}/{len(touches)} touches approved"})

    # Registrant count (20 pts)
    reg_pts = min(20, total_reg * 2) if total_reg < 10 else 20
    score += reg_pts
    factors.append({"factor": "Registration", "score": reg_pts, "max": 20,
                    "detail": f"{total_reg} registrants" + (" — keep promoting!" if total_reg < 10 else "")})

    # Channel diversity (20 pts)
    all_channels = set()
    for t in touches:
        all_channels.update(t.get("channels", []))
    channel_pts = min(20, len(all_channels) * 3)
    score += channel_pts
    factors.append({"factor": "Channel Coverage", "score": channel_pts, "max": 20,
                    "detail": f"{len(all_channels)} channels active: {', '.join(sorted(all_channels))}"})

    # Delivery progress (20 pts)
    delivery_pts = int(sent / max(len(touches), 1) * 20) if is_past else 20
    score += delivery_pts
    factors.append({"factor": "Delivery Progress", "score": delivery_pts, "max": 20,
                    "detail": f"{sent}/{len(touches)} touches sent" if is_past else "Pre-event — on track"})

    # Attendance prediction
    if is_past:
        actual_rate = round(attended / max(total_reg, 1) * 100, 1)
        prediction = {"rate": actual_rate, "attendees": attended, "confidence": "actual", "label": "Final"}
    elif total_reg == 0:
        prediction = {"rate": 0, "attendees": 0, "confidence": "low", "label": "No registrants yet"}
    else:
        base_rate = 0.35  # industry baseline
        # Boost for more approvals
        approval_boost = (approved / max(len(touches), 1)) * 0.15
        # Boost for email channel
        has_email = any("email" in t.get("channels", []) for t in touches)
        email_boost = 0.08 if has_email else 0
        # Boost for multi-channel
        channel_boost = min(0.10, (len(all_channels) - 1) * 0.02)
        predicted_rate = min(0.85, base_rate + approval_boost + email_boost + channel_boost)
        predicted_att  = round(total_reg * predicted_rate)
        confidence = "high" if approved >= 6 and total_reg >= 10 else "medium" if approved >= 3 else "low"
        prediction = {
            "rate": round(predicted_rate * 100, 1),
            "attendees": predicted_att,
            "registrants": total_reg,
            "confidence": confidence,
            "label": "Predicted",
            "no_show_pct": round((1 - predicted_rate) * 100, 1)
        }

    # Recommendations
    recs = []
    if pending > 0:
        recs.append({"priority": "high", "action": f"Approve {pending} pending touches", "impact": "Enables automated delivery on schedule"})
    if len(all_channels) < 3:
        recs.append({"priority": "medium", "action": "Add more channels (WhatsApp, LinkedIn)", "impact": "Multi-channel sequences get 2x attendance"})
    if total_reg < 10 and not is_past:
        recs.append({"priority": "high", "action": "Boost registration — share the public link", "impact": "More registrants = more attendees"})
    if copy_generated < len(touches) and not is_past:
        recs.append({"priority": "high", "action": "Regenerate AI copy for incomplete touches", "impact": "All 8 touches should have copy before launch"})
    if score < 60:
        recs.append({"priority": "medium", "action": "Review webinar description and target audience", "impact": "Better context = better AI copy"})
    if not recs:
        recs.append({"priority": "low", "action": "Looking great! Share your public registration link", "impact": "More visibility = more registrants"})

    return {
        "health_score": score,
        "health_label": "Excellent" if score >= 80 else "Good" if score >= 60 else "Needs Work" if score >= 40 else "At Risk",
        "factors": factors,
        "prediction": prediction,
        "recommendations": recs,
        "stats": {
            "total_registrants": total_reg,
            "touches_total": len(touches),
            "touches_approved": approved,
            "touches_sent": sent,
            "touches_pending": pending,
            "channels_active": len(all_channels),
            "days_until": days_until,
            "is_past": is_past
        }
    }


# ══════════════════════════════════════════════
# BANNER UPLOAD
# ══════════════════════════════════════════════
from fastapi import UploadFile, File
from database import social_images_fs

@router.post("/webinars/{wid}/banner")
async def upload_banner(wid: str, file: UploadFile = File(...), user=Depends(get_user)):
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)

    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, "Only image files allowed")

    # Max 5MB
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image must be under 5MB")

    # Delete old banner if exists
    old = await db.banners.find_one({"webinar_id": wid}, {"_id": 0})
    if old and old.get("file_id"):
        try:
            await social_images_fs.delete(old["file_id"])
        except: pass

    # Store in GridFS
    from bson import ObjectId
    file_id = await social_images_fs.upload_from_stream(
        f"banner-{wid}{file.filename[-4:]}",
        contents,
        metadata={"webinar_id": wid, "owner_id": user["id"], "mime": file.content_type}
    )

    await db.banners.update_one(
        {"webinar_id": wid},
        {"$set": {"webinar_id": wid, "owner_id": user["id"],
                  "file_id": file_id, "mime": file.content_type,
                  "filename": file.filename, "size": len(contents),
                  "uploaded_at": now_iso()}},
        upsert=True
    )

    # Store banner URL reference on webinar
    await db.webinars.update_one(
        {"id": wid},
        {"$set": {"banner_url": f"/api/webinars/{wid}/banner.img"}}
    )

    return {"ok": True, "url": f"/api/webinars/{wid}/banner.img", "size": len(contents)}


@router.get("/webinars/{wid}/banner.img")
async def get_banner(wid: str):
    meta = await db.banners.find_one({"webinar_id": wid}, {"_id": 0})
    if not meta:
        raise HTTPException(404)
    from fastapi.responses import StreamingResponse
    try:
        stream = await social_images_fs.open_download_stream(meta["file_id"])
        return StreamingResponse(stream, media_type=meta.get("mime", "image/jpeg"))
    except:
        raise HTTPException(404)


@router.delete("/webinars/{wid}/banner")
async def delete_banner(wid: str, user=Depends(get_user)):
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]})
    if not w:
        raise HTTPException(404)
    old = await db.banners.find_one({"webinar_id": wid})
    if old and old.get("file_id"):
        try: await social_images_fs.delete(old["file_id"])
        except: pass
    await db.banners.delete_one({"webinar_id": wid})
    await db.webinars.update_one({"id": wid, "owner_id": user["id"]}, {"$unset": {"banner_url": ""}})
    return {"ok": True}


# ══════════════════════════════════════════════
# FETCH WEBINAR FROM LINK
# ══════════════════════════════════════════════
@router.post("/webinars/fetch-from-url")
async def fetch_from_url(payload: dict = Body(default={}), user=Depends(get_user)):
    """Fetch webinar details from any platform URL."""
    from integrations import fetch_webinar_from_url
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "URL required")
    settings = await db.settings.find_one({"owner_id": user["id"]}, {"_id": 0}) or {}
    # Decrypt sensitive keys
    from crypto_utils import decrypt_value
    for key in ["circle_api_key", "linkedin_marketing_token"]:
        if settings.get(key):
            try:
                settings[key] = decrypt_value(settings[key])
            except Exception:
                pass
    result = await fetch_webinar_from_url(url, settings)
    # Log what we got for debugging
    logger.info(f"Fetch result: title={result.get('title')}, starts_at={result.get('starts_at')}, attendees={len(result.get('attendees', []))}, cover={result.get('cover_image_url','none')}")
    return result


# ══════════════════════════════════════════════
# CIRCLE EVENTS LIST — for dropdown picker
# ══════════════════════════════════════════════
@router.get("/circle/upcoming-events")
async def circle_upcoming_events(user=Depends(get_user)):
    """Fetch list of upcoming Circle.so events for the user to pick from."""
    from integrations import _circle_get
    from crypto_utils import decrypt_value
    
    settings = await db.settings.find_one({"owner_id": user["id"]}, {"_id": 0}) or {}
    api_key = settings.get("circle_api_key", "")
    if api_key:
        try:
            api_key = decrypt_value(api_key)
        except:
            pass
    
    if not api_key:
        raise HTTPException(400, "Circle API key not configured")
    
    space_id = settings.get("circle_space_id", "")
    
    # Try v1 events API
    import httpx
    results = []
    bases = ["https://app.circle.so", "https://eu.app.circle.so"]
    
    async with httpx.AsyncClient(timeout=15) as client:
        for base in bases:
            for scheme in ("Bearer", "Token"):
                headers = {"Authorization": f"{scheme} {api_key}", "Accept": "application/json"}
                try:
                    params = {"per_page": 50, "sort": "latest"}
                    if space_id:
                        params["space_id"] = space_id
                    r = await client.get(f"{base}/api/admin/v2/posts", headers=headers, params=params)
                    if r.status_code == 200:
                        posts = r.json().get("records", [])
                        for p in posts:
                            if p.get("name"):
                                results.append({
                                    "id": p.get("id"),
                                    "name": p.get("name"),
                                    "slug": p.get("slug"),
                                    "published_at": p.get("published_at"),
                                    "cover_image_url": p.get("cover_image_url"),
                                    "url": p.get("url"),
                                })
                        return {"events": results, "count": len(results)}
                except:
                    continue
    
    return {"events": [], "count": 0}
