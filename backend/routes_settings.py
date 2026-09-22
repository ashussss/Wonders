"""Settings + Analytics endpoints."""
from typing import Dict
from fastapi import APIRouter, Depends

from database import db
from auth_utils import get_user
from models import SettingsIn
from crypto_utils import encrypt_settings, mask_settings_for_api

router = APIRouter(prefix="/api")


@router.get("/settings")
async def get_settings(user=Depends(get_user)):
    s = await db.settings.find_one({"owner_id": user["id"]}, {"_id": 0})
    if not s:
        return {}
    # Mask secrets before returning to UI (decrypts internally, then masks)
    return mask_settings_for_api(s)


@router.patch("/settings")
async def patch_settings(data: SettingsIn, user=Depends(get_user)):
    raw = {k: v for k, v in data.model_dump().items() if v is not None}
    # Drop fully-masked values (user didn't change the secret) so we don't overwrite real secrets
    cleaned = {k: v for k, v in raw.items() if not (isinstance(v, str) and v.startswith("••••••••"))}
    upd = encrypt_settings(cleaned)
    await db.settings.update_one({"owner_id": user["id"]}, {"$set": upd}, upsert=True)
    return {"ok": True}


@router.get("/analytics/overview")
async def analytics(user=Depends(get_user)):
    webinars = await db.webinars.find({"owner_id": user["id"]}, {"_id": 0}).to_list(500)

    # Single bulk fetch of every registrant owned by this user, instead of
    # one query per webinar (was N+1 — slow for users with many webinars).
    all_regs = await db.registrants.find({"owner_id": user["id"]}, {"_id": 0}).to_list(20000)
    regs_by_webinar: Dict[str, list] = {}
    for r in all_regs:
        regs_by_webinar.setdefault(r["webinar_id"], []).append(r)

    total_reg = 0
    total_att = 0
    community_joined = 0
    per_webinar = []
    community_per_webinar = []
    channel_buckets: Dict[str, Dict[str, int]] = {}

    for w in webinars:
        regs = regs_by_webinar.get(w["id"], [])
        att = sum(1 for r in regs if r.get("attended"))
        cj = sum(1 for r in regs if r.get("community_joined"))
        total_reg += len(regs)
        total_att += att
        community_joined += cj
        per_webinar.append({
            "id": w["id"], "title": w["title"], "starts_at": w["starts_at"],
            "registrants": len(regs), "attendees": att,
            "rate": round((att/len(regs))*100, 1) if regs else 0,
        })
        community_per_webinar.append({"id": w["id"], "title": w["title"], "community_joined": cj})
        for r in regs:
            ch = r.get("source", "form")
            b = channel_buckets.setdefault(ch, {"reg": 0, "att": 0})
            b["reg"] += 1
            if r.get("attended"):
                b["att"] += 1

    channel_rows = [{"channel": k, "registrants": v["reg"], "attendees": v["att"],
                     "attendance_rate": round((v["att"]/v["reg"])*100, 1) if v["reg"] else 0}
                    for k, v in channel_buckets.items()]
    channel_rows.sort(key=lambda x: -x["attendance_rate"])

    return {
        "total_webinars": len(webinars),
        "total_registrants": total_reg,
        "total_attendees": total_att,
        "overall_rate": round((total_att/total_reg)*100, 1) if total_reg else 0,
        "community_joined_total": community_joined,
        "community_per_webinar": community_per_webinar,
        "per_webinar": sorted(per_webinar, key=lambda x: x["starts_at"], reverse=True),
        "by_channel": channel_rows,
    }
