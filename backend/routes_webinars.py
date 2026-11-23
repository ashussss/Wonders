"""Webinars, touches, registrants, and lead magnets endpoints."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Body, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from database import db
from auth_utils import get_user, now_iso
from billing import require_webinar_quota
from models import WebinarIn, WebinarPatch, RegistrantIn, TouchPatch, LeadMagnetPatch
from config import TOUCH_DEFS
import touch_visuals
import brand_kit
import invites
import ai
from ai import (generate_touch_copy, generate_lead_magnets, compute_send_time, compute_dynamic_schedule,
                touch_reasoning, kit_from_lead_magnets)

router = APIRouter(prefix="/api")
limiter = Limiter(key_func=get_remote_address)


def _webinar_doc(uid: str, data: WebinarIn) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "owner_id": uid,
        "title": data.title,
        "description": data.description,
        "speaker": data.speaker,
        "speakers": data.speakers or "",
        "target_audience": data.target_audience,
        "custom_context": data.custom_context or "",
        "key_topics": data.key_topics or "",
        "starts_at": data.starts_at,
        "timezone": data.timezone,
        "join_link": data.join_link,
        "registration_link": data.registration_link,
        "after_signup_url": data.after_signup_url or "",
        "status": "scheduled",
        "created_at": now_iso(),
        "enabled_touches": {str(t["num"]): True for t in TOUCH_DEFS},
    }


import logging
logger = logging.getLogger("showup.webinars")


# Running generation jobs, by webinar id. asyncio only keeps a weak reference to a task,
# so a fire-and-forget create_task() could be garbage collected halfway through and the
# webinar's touches stayed empty for good. Keeping them here also stops two jobs for the
# same webinar running at once.
_jobs: Dict[str, asyncio.Task] = {}
RETRY_FAILED_AFTER = 300  # seconds before a page load retries a failed generation
STALE_RUNNING_AFTER = 900  # a "running" job this old died (restart/deploy) and may be restarted


_bg: set = set()  # strong refs for small background tasks (banner import)


def _start_cover_import(w: Dict[str, Any], url: str) -> None:
    import event_art
    from database import social_images_fs
    task = asyncio.create_task(event_art.import_cover(db, social_images_fs, w, url))
    _bg.add(task)
    task.add_done_callback(_bg.discard)


def generation_running(webinar_id: str) -> bool:
    t = _jobs.get(webinar_id)
    return bool(t and not t.done())


def start_generation(webinar_id: str, only_missing: bool = False) -> bool:
    """Start (or keep) the background job that writes the kit and every touch's copy."""
    if generation_running(webinar_id):
        return False
    task = asyncio.create_task(_bg_generate_all(webinar_id, only_missing=only_missing))
    _jobs[webinar_id] = task
    task.add_done_callback(lambda _t, wid=webinar_id: _jobs.pop(wid, None) if _jobs.get(wid) is _t else None)
    return True


def _has_copy(t: Dict[str, Any]) -> bool:
    return bool((t.get("ai_copy") or {}).get("channels"))


def _llm_ok_since(started: str) -> bool:
    for st in ai.LLM_STATUS.values():
        ok = (st or {}).get("last_ok") or {}
        if ok.get("at", "") >= started:
            return True
    return False


def _llm_last_error() -> str:
    errs = [(st or {}).get("last_error") or {} for st in ai.LLM_STATUS.values()]
    errs = [e for e in errs if e.get("error")]
    if not errs:
        return "No AI provider answered. Check GEMINI_API_KEY / GROQ_API_KEY on Render."
    e = max(errs, key=lambda e: e.get("at", ""))
    return f"{e.get('model')}: {e.get('error')}"


async def _set_gen(webinar_id: str, owner_id: str, **fields) -> None:
    await db.webinars.update_one({"id": webinar_id, "owner_id": owner_id},
                                 {"$set": {f"generation.{k}": v for k, v in fields.items()}})


async def _bg_generate_all(webinar_id: str, only_missing: bool = False):
    """Background job fired after webinar creation (and by Regenerate all, and by a page
    load that finds touches without copy): writes the content kit, then every touch's
    copy. Progress and the outcome are kept on webinar.generation for the UI."""
    started = now_iso()
    owner_id = None
    try:
        w = await db.webinars.find_one({"id": webinar_id}, {"_id": 0})
        if not w:
            logger.warning(f"_bg_generate_all: webinar {webinar_id} not found")
            return
        owner_id = w["owner_id"]
        touches = await db.touches.find({"webinar_id": webinar_id}, {"_id": 0}).sort("touch_num", 1).to_list(50)
        if only_missing:
            touches = [t for t in touches if not _has_copy(t)]
        await db.webinars.update_one({"id": webinar_id, "owner_id": owner_id}, {"$set": {"generation": {
            "status": "running", "started_at": started, "finished_at": None,
            "total": len(touches), "done": 0, "error": None}}})

        kit = await _ensure_kit(w)
        # The host's brand voice (Brand Kit, plus the older Settings brand fields)
        global_instructions = await brand_kit.voice_brief(db, w["owner_id"])

        async def _gen_one(t):
            try:
                copy = await generate_touch_copy(w, t["touch_num"], t.get("channels", ["email"]),
                                                  custom_instructions=global_instructions, kit=kit)
                upd = {"ai_copy": copy}
                if not only_missing:
                    upd["approval_status"] = "pending"
                if not t.get("ai_reasoning"):
                    upd["ai_reasoning"] = await touch_reasoning(t["touch_num"], t.get("channels", []))
                await db.touches.update_one({"id": t["id"], "owner_id": w["owner_id"]}, {"$set": upd})
            except Exception as e:
                logger.exception(f"_bg_generate_all: touch {t.get('touch_num')} for {webinar_id} failed: {e}")
            finally:
                await db.webinars.update_one({"id": webinar_id, "owner_id": owner_id}, {"$inc": {"generation.done": 1}})

        await asyncio.gather(*[_gen_one(t) for t in touches], return_exceptions=True)

        rows = await db.touches.find({"webinar_id": webinar_id}, {"_id": 0, "ai_copy": 1}).to_list(50)
        missing = sum(1 for t in rows if not _has_copy(t))
        if missing:
            await _set_gen(webinar_id, owner_id, status="failed", finished_at=now_iso(),
                           error=f"{missing} touches have no copy. {_llm_last_error()}")
        elif touches and not _llm_ok_since(started):
            # Every call failed, so the touches carry the generic fallback text.
            await _set_gen(webinar_id, owner_id, status="failed", finished_at=now_iso(),
                           error=f"AI was unavailable, so basic template copy was used. {_llm_last_error()}")
        else:
            await _set_gen(webinar_id, owner_id, status="done", finished_at=now_iso(), error=None)
        logger.info(f"_bg_generate_all: webinar {webinar_id}: {len(touches)} touches, {missing} without copy")
    except Exception as e:
        logger.exception(f"_bg_generate_all: webinar {webinar_id} failed entirely: {e}")
        try:
            if owner_id:
                await _set_gen(webinar_id, owner_id, status="failed", finished_at=now_iso(), error=str(e)[:300])
        except Exception:
            pass


def _should_heal(w: Dict[str, Any], touches: List[Dict[str, Any]]) -> bool:
    """A page load restarts generation when touches have no copy and nothing is writing it:
    the job died in a restart or deploy, or it failed more than 5 minutes ago."""
    if generation_running(w["id"]) or all(_has_copy(t) for t in touches):
        return False
    gen = w.get("generation") or {}

    def _age(key: str) -> float:
        try:
            return (datetime.now(timezone.utc) - datetime.fromisoformat(gen[key])).total_seconds()
        except Exception:
            return float("inf")
    # Running in another worker process (or just started): leave it alone.
    if gen.get("status") == "running" and _age("started_at") < STALE_RUNNING_AFTER:
        return False
    if gen.get("status") == "failed":
        return _age("finished_at") >= RETRY_FAILED_AFTER
    return True


async def resume_stuck_generations() -> int:
    """On startup: webinars whose job was cut off by a restart or deploy get it again."""
    now = now_iso()
    wids = await db.touches.distinct("webinar_id", {"$or": [{"ai_copy": {}}, {"ai_copy": None},
                                                             {"ai_copy.channels": {}}]})
    started = 0
    for wid in wids:
        w = await db.webinars.find_one({"id": wid}, {"_id": 0, "id": 1, "starts_at": 1})
        if w and (w.get("starts_at") or "") >= now and start_generation(wid, only_missing=True):
            started += 1
    if started:
        logger.info(f"resume_stuck_generations: restarted copy for {started} webinars")
    return started


@router.get("/ai/health")
async def ai_health(user=Depends(get_user)):
    """Admin: one tiny real call to Gemini and to Groq, with the error if one fails."""
    if user.get("role") not in {"admin", "superadmin"}:
        raise HTTPException(403, "Admin only")
    return await ai.llm_health()


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
    await require_webinar_quota(user)
    doc = _webinar_doc(user["id"], data)
    await db.webinars.insert_one(doc)
    settings = await db.settings.find_one({"owner_id": user["id"]}, {"_id": 0}) or {}
    default_channels = settings.get("default_channels", {})
    touches = []
    for tdef in TOUCH_DEFS:
        tnum = tdef["num"]
        channels = default_channels.get(str(tnum), tdef["default_channels"])
        sched = await compute_dynamic_schedule(data.starts_at, tnum, tz=data.timezone) if tnum != 1 else None
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
    start_generation(doc["id"])
    if data.cover_image_url:
        _start_cover_import(doc, data.cover_image_url)
    return {"id": doc["id"]}


@router.get("/webinars/{wid}")
async def get_webinar(wid: str, user=Depends(get_user)):
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    w["registrant_count"] = await db.registrants.count_documents({"webinar_id": wid})
    w["attendee_count"] = await db.registrants.count_documents({"webinar_id": wid, "attended": True})
    w["attendance_rate"] = round((w["attendee_count"]/w["registrant_count"])*100, 1) if w["registrant_count"] else 0
    w["generation"] = {**(w.get("generation") or {}), "running": generation_running(wid)}
    return w


@router.patch("/webinars/{wid}")
async def patch_webinar(wid: str, data: WebinarPatch, user=Depends(get_user)):
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    if not upd:
        return {"ok": True}
    await db.webinars.update_one({"id": wid, "owner_id": user["id"]}, {"$set": upd})
    if "starts_at" in upd or "timezone" in upd:
        w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0}) or {}
        for tdef in TOUCH_DEFS:
            if tdef["num"] == 1:
                continue
            sched = await compute_dynamic_schedule(w.get("starts_at"), tdef["num"], tz=w.get("timezone"))
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


async def _confirm_registrant(wid: str, reg_id: str):
    from routes_delivery import send_confirmation
    try:
        await send_confirmation(wid, reg_id)
    except Exception as e:                                  # noqa: BLE001
        logger.error(f"confirmation failed for webinar={wid} registrant={reg_id}: {e}")


@router.post("/webinars/{wid}/register")
@limiter.limit("10/minute")
async def public_register(wid: str, data: RegistrantIn, request: Request):
    w = await db.webinars.find_one({"id": wid}, {"_id": 0})
    if not w:
        raise HTTPException(404, "Webinar not found")
    existing = await db.registrants.find_one({"webinar_id": wid, "email": data.email.lower()})
    if existing:
        return {"ok": True, "deduped": True, "next_url": _safe_url(w.get("after_signup_url"))}
    reg = {"id": str(uuid.uuid4()), "webinar_id": wid, "owner_id": w["owner_id"],
           "name": data.name, "email": data.email.lower(), "phone": data.phone,
           "source": data.source, "attended": False, "registered_at": now_iso()}
    await db.registrants.insert_one(reg)
    await invites.mark_registered(db, wid, reg["email"])
    asyncio.create_task(_confirm_registrant(wid, reg["id"]))
    return {"ok": True, "id": reg["id"], "next_url": _safe_url(w.get("after_signup_url"))}


def _safe_url(url) -> str:
    url = (url or "").strip()
    return url if url.startswith("https://") or url.startswith("http://") else ""


@router.get("/webinars/{wid}/public")
async def public_webinar(wid: str):
    """What the public sign-up page shows: no owner data, no join link."""
    w = await db.webinars.find_one({"id": wid}, {"_id": 0})
    if not w:
        raise HTTPException(404, "Webinar not found")
    brand = await brand_kit.resolve(db, w.get("owner_id") or "", "")
    has_banner = bool(await db.banners.find_one({"webinar_id": wid}, {"_id": 1}))
    return {"id": wid, "title": w.get("title") or "", "starts_at": w.get("starts_at") or "",
            "timezone": w.get("timezone") or "UTC",
            "speaker": (w.get("speakers") or w.get("speaker") or ""),
            "description": (w.get("description") or "")[:600],
            "has_banner": has_banner, "next_url": _safe_url(w.get("after_signup_url")),
            "brand_name": brand.get("name") or "", "cta_label": brand.get("cta_label") or "",
            "button_color": brand.get("button_color") or "",
            "button_text_color": brand_kit.readable_on(brand["button_color"]) if brand.get("button_color") else ""}


@router.post("/webinars/{wid}/registrants/import")
async def import_registrants(wid: str, items: List[RegistrantIn], user=Depends(get_user)):
    if not await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 1}):
        raise HTTPException(404)
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


@router.get("/webinars/{wid}/invitees")
async def list_invitees(wid: str, user=Depends(get_user)):
    if not await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 1}):
        raise HTTPException(404)
    items = await db.invitees.find({"webinar_id": wid, "owner_id": user["id"]}, {"_id": 0}).to_list(invites.MAX_INVITEES)
    return {"summary": await invites.summary(db, wid), "items": items}


@router.post("/webinars/{wid}/invitees/import")
async def import_invitees(wid: str, items: List[RegistrantIn], user=Depends(get_user)):
    """Add people who haven't registered yet. They get every email touch except the
    confirmation and the attendee thank-you (invites.INVITE_TOUCHES), with the registration
    link and an unsubscribe link, until they sign up and become registrants."""
    if not await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 1}):
        raise HTTPException(404)
    existing = await db.invitees.count_documents({"webinar_id": wid})
    if existing + len(items) > invites.MAX_INVITEES:
        raise HTTPException(400, f"An invite list can hold up to {invites.MAX_INVITEES} people")
    out = await invites.import_invitees(db, wid, user["id"], [{"name": i.name, "email": i.email} for i in items])
    return {**out, "summary": await invites.summary(db, wid)}


@router.delete("/webinars/{wid}/invitees")
async def clear_invitees(wid: str, user=Depends(get_user)):
    """Empty the invite list. Unsubscribes are kept so they stay suppressed next time."""
    r = await db.invitees.delete_many({"webinar_id": wid, "owner_id": user["id"], "unsubscribed": {"$ne": True}})
    return {"deleted": r.deleted_count}


def _unsub_page(body: str):
    from fastapi.responses import HTMLResponse
    return HTMLResponse("<!DOCTYPE html><html><head><meta charset='utf-8'>"
                        "<meta name='viewport' content='width=device-width,initial-scale=1'><title>Unsubscribe</title>"
                        "</head><body style='font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:480px;"
                        f"margin:80px auto;padding:0 20px;color:#111827;line-height:1.6'>{body}</body></html>")


@router.get("/unsubscribe/{token}")
async def unsubscribe_page(token: str):
    """A confirm button, not an instant unsubscribe: mail scanners open every link in an email."""
    return _unsub_page("<p>Stop getting invitations from this list?</p>"
                       "<form method='post'><button type='submit' style='padding:10px 18px;border-radius:8px;"
                       "border:1px solid #d1d5db;background:#fff;font-size:15px;cursor:pointer'>Unsubscribe</button></form>")


@router.post("/unsubscribe/{token}")
@limiter.limit("20/minute")
async def unsubscribe_invitee(token: str, request: Request):
    row = await invites.unsubscribe(db, token)
    return _unsub_page("<p>You're unsubscribed. You won't get any more invitations from this list.</p>" if row
                       else "<p>This link isn't valid any more. You're not on this list.</p>")


@router.post("/webinars/{wid}/webhooks/circle")
@limiter.limit("60/minute")
async def circle_webhook(wid: str, payload: Dict[str, Any], request: Request):
    # Circle's official community_member_created shape: {community_member: {email, name, ...}}
    member = payload.get("community_member") or payload
    email = (member.get("email") or "").lower().strip()
    name = member.get("name") or member.get("full_name") or (email.split("@")[0] if email else "")
    if not email:
        raise HTTPException(400, "email required")
    w = await db.webinars.find_one({"id": wid}, {"_id": 0})
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
    if not await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 1}):
        raise HTTPException(404)
    emails = [e.lower() for e in payload.get("emails", [])]
    await db.registrants.update_many({"webinar_id": wid, "owner_id": user["id"], "email": {"$in": emails}},
                                     {"$set": {"attended": True}})
    await db.webinars.update_one({"id": wid, "owner_id": user["id"]}, {"$set": {"status": "completed"}})
    return {"ok": True, "marked": len(emails)}


# --------- Touches ---------
async def _backfill_touches(wid: str, owner_id: str) -> None:
    """Webinars created before a touch was added to TOUCH_DEFS get it, if it's still ahead."""
    w = await db.webinars.find_one({"id": wid, "owner_id": owner_id}, {"_id": 0})
    if not w:
        return
    have = {t["touch_num"] for t in await db.touches.find({"webinar_id": wid}, {"_id": 0, "touch_num": 1}).to_list(50)}
    settings = await db.settings.find_one({"owner_id": owner_id}, {"_id": 0}) or {}
    for tdef in TOUCH_DEFS:
        if tdef["num"] in have or tdef["num"] == 1:
            continue
        sched = await compute_dynamic_schedule(w.get("starts_at"), tdef["num"], tz=w.get("timezone"))
        if not sched:
            continue
        channels = (settings.get("default_channels") or {}).get(str(tdef["num"]), tdef["default_channels"])
        t = {"id": str(uuid.uuid4()), "webinar_id": wid, "owner_id": owner_id,
             "touch_num": tdef["num"], "name": tdef["name"], "trigger": tdef["trigger"],
             "channels": channels, "scheduled_at": sched, "ai_reasoning": "", "ai_copy": {},
             "selected_variant": 0, "copy_overrides": {},
             "approval_status": "pending", "sent_status": "planned",
             "sent_at": None, "created_at": now_iso()}
        # Upsert so two page loads at once can't both add it.
        r = await db.touches.update_one({"webinar_id": wid, "touch_num": tdef["num"]},
                                        {"$setOnInsert": t}, upsert=True)
        if not r.upserted_id:
            continue
        copy = await generate_touch_copy(w, tdef["num"], channels,
                                         custom_instructions=await brand_kit.voice_brief(db, owner_id))
        await db.touches.update_one({"id": t["id"], "owner_id": owner_id}, {"$set": {"ai_copy": copy}})


async def _ensure_kit(w: Dict[str, Any]) -> Dict[str, Any]:
    """The webinar's content kit. Webinars created before the kit had tips, polls and
    checklists get a fresh one, so their regenerated touches carry real content too."""
    lm = await db.lead_magnets.find_one({"webinar_id": w["id"]}, {"_id": 0})
    kit = kit_from_lead_magnets(lm)
    if kit.get("insights") and kit.get("checklist"):
        return kit
    fresh = await generate_lead_magnets(w)
    if not (fresh.get("insights") or fresh.get("checklist")):
        return kit
    # Keep the lead magnets the host may already have reviewed.
    old = (lm or {}).get("ai_content") or {}
    merged = {**fresh, **{k: old[k] for k in ("case_study", "snippets", "one_pager") if old.get(k)}}
    await db.lead_magnets.update_one({"webinar_id": w["id"], "owner_id": w["owner_id"]},
                                     {"$set": {"ai_content": merged, "generated_at": now_iso()}}, upsert=True)
    return kit_from_lead_magnets(await db.lead_magnets.find_one({"webinar_id": w["id"]}, {"_id": 0}))


@router.get("/webinars/{wid}/touches")
async def list_touches(wid: str, user=Depends(get_user)):
    asyncio.create_task(_backfill_touches(wid, user["id"]))
    rows = await db.touches.find({"webinar_id": wid, "owner_id": user["id"]}, {"_id": 0}).sort("touch_num", 1).to_list(50)
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0, "id": 1, "generation": 1})
    if w and rows and _should_heal(w, rows):
        logger.info(f"list_touches: {wid} has touches without copy and no job, restarting generation")
        start_generation(wid, only_missing=True)
    for r in rows:
        r["has_visual"] = touch_visuals.has_visual(r["touch_num"])
    return rows


async def _schedule_update(tid: str, owner_id: str, upd: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a new send time / auto-post switch and re-arm the touch for the scheduler.

    A touch the scheduler already passed over (queued, or failed after retries) goes
    back to planned when its send time is in the future, so it fires at the new time.
    """
    t = await db.touches.find_one({"id": tid, "owner_id": owner_id}, {"_id": 0})
    if not t:
        raise HTTPException(404)
    extra: Dict[str, Any] = {}
    if "scheduled_at" in upd:
        try:
            when = datetime.fromisoformat(upd["scheduled_at"].replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "scheduled_at must be an ISO date-time") from None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        extra["scheduled_at"] = when.astimezone(timezone.utc).isoformat()
    when_iso = extra.get("scheduled_at") or t.get("scheduled_at")
    if (t.get("sent_status") in ("queued", "failed") and when_iso
            and when_iso > datetime.now(timezone.utc).isoformat()):
        extra.update(sent_status="planned", sent_at=None, send_attempts=0, retry_at=None)
    return extra


@router.patch("/touches/{tid}")
async def patch_touch(tid: str, data: TouchPatch, user=Depends(get_user)):
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    if "approval_status" in upd and upd["approval_status"] == "approved":
        upd["approved_at"] = now_iso()
    if "scheduled_at" in upd or "auto_send" in upd:
        upd.update(await _schedule_update(tid, user["id"], upd))
    await db.touches.update_one({"id": tid, "owner_id": user["id"]}, {"$set": upd})
    if "channels" in upd:
        t = await db.touches.find_one({"id": tid, "owner_id": user["id"]}, {"_id": 0})
        if not t:
            raise HTTPException(404)
        w = await db.webinars.find_one({"id": t["webinar_id"], "owner_id": user["id"]}, {"_id": 0})
        copy = await generate_touch_copy(w, t["touch_num"], upd["channels"],
                                         custom_instructions=await brand_kit.voice_brief(db, user["id"]))
        await db.touches.update_one({"id": tid, "owner_id": user["id"]}, {"$set": {"ai_copy": copy}})
    return {"ok": True}


@router.post("/touches/{tid}/regenerate")
async def regen_touch(tid: str, user=Depends(get_user)):
    t = await db.touches.find_one({"id": tid, "owner_id": user["id"]}, {"_id": 0})
    if not t:
        raise HTTPException(404)
    w = await db.webinars.find_one({"id": t["webinar_id"], "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    copy = await generate_touch_copy(w, t["touch_num"], t["channels"], kit=await _ensure_kit(w),
                                     custom_instructions=await brand_kit.voice_brief(db, user["id"]))
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
        r["has_visual"] = touch_visuals.has_visual(r["touch_num"])
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
    """Starts the rewrite in the background and returns at once. Doing ~40 AI calls inside
    the request ran past the browser/Render timeout, so the button showed "Regeneration
    failed" while the work was still going (or was cut off)."""
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0, "id": 1})
    if not w:
        raise HTTPException(404)
    total = await db.touches.count_documents({"webinar_id": wid, "owner_id": user["id"]})
    if not total:
        raise HTTPException(404, "No touches found for this webinar")
    started = start_generation(wid)
    return {"ok": True, "started": started, "already_running": not started,
            "regenerated": total, "total": total}


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

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(400, "Only image files allowed")
    contents = await file.read()
    if len(contents) > 8 * 1024 * 1024:
        raise HTTPException(400, "Image must be under 8MB")
    import event_art
    try:
        out = await event_art.store_banner(db, social_images_fs, w, contents, source="upload",
                                           filename=file.filename or "banner")
    except event_art.BannerError as e:
        raise HTTPException(400, str(e))
    await db.webinars.update_one({"id": wid, "owner_id": user["id"]}, {"$unset": {"banner_error": ""}})
    return {"ok": True, "url": out["url"], "event_theme": out["event_theme"], "size": len(contents)}


@router.post("/webinars/{wid}/banner/from-url")
async def banner_from_url(wid: str, payload: dict = Body(default={}), user=Depends(get_user)):
    """Use an image link (or the event page's cover) as the banner."""
    import event_art
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    url = (payload.get("url") or w.get("cover_image_url") or "").strip()
    if not url:
        raise HTTPException(400, "Paste the image link")
    try:
        data = await event_art.download_image(url)
        out = await event_art.store_banner(db, social_images_fs, w, data, source=url)
    except event_art.BannerError as e:
        raise HTTPException(400, str(e))
    await db.webinars.update_one({"id": wid, "owner_id": user["id"]},
                                 {"$set": {"cover_image_url": url}, "$unset": {"banner_error": ""}})
    return {"ok": True, "url": out["url"], "event_theme": out["event_theme"]}


@router.get("/webinars/{wid}/creatives")
async def list_creatives(wid: str, user=Depends(get_user)):
    """The event's ready-to-post creatives, in the event banner's look."""
    import event_art
    w = await db.webinars.find_one({"id": wid, "owner_id": user["id"]}, {"_id": 0})
    if not w:
        raise HTTPException(404)
    brand = await brand_kit.resolve(db, user["id"])
    out = []
    for kind in event_art.DOWNLOADS:
        row = await event_art.ensure_creative(db, social_images_fs, w, kind, brand)
        if row:
            out.append({"kind": kind, "label": event_art.LABELS[kind], "size": row["size"],
                        "url": event_art.creative_url("", row)})
    return {"has_banner": bool(w.get("banner_hash")), "event_theme": w.get("event_theme"),
            "banner_error": w.get("banner_error"), "creatives": out}


@router.get("/webinars/{wid}/creatives/{kind}.jpg")
async def get_creative(wid: str, kind: str):
    """Public, like touch cards: social networks and email clients fetch it by URL."""
    import event_art
    from fastapi.responses import StreamingResponse
    w = await db.webinars.find_one({"id": wid}, {"_id": 0})
    if not w or kind not in event_art.SIZES:
        raise HTTPException(404)
    row = await event_art.ensure_creative(db, social_images_fs, w, kind)
    if not row:
        raise HTTPException(404)
    try:
        stream = await social_images_fs.open_download_stream(row["file_id"])
    except Exception:
        raise HTTPException(404)
    return StreamingResponse(stream, media_type="image/jpeg",
                             headers={"Cache-Control": "public, max-age=300",
                                      "Content-Disposition": f'inline; filename="{kind}.jpg"'})


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
    await db.webinars.update_one({"id": wid, "owner_id": user["id"]},
                                 {"$unset": {"banner_url": "", "banner_hash": "", "event_theme": ""}})
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
    
    from datetime import datetime, timezone
    from integrations import circle_list_upcoming_events
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return await circle_list_upcoming_events(api_key, now)
