"""Brand Kit API: the customer's logo, colours, font and voice (see brand_kit.py)."""
import base64
import logging
import os
import re
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import Response

import brand_kit
from auth_utils import get_user
from database import db
from models import BrandKitIn

logger = logging.getLogger("showup.brand")
router = APIRouter(prefix="/api")

SAMPLE_KIT = {
    "problem": {"hook": "Most people who sign up for a webinar never show up",
                "example": "They meant to come. Then the day got busy and the link was buried."},
    "insights": [{"heading": "Send the link the day before", "detail": "Not a week before. Nobody digs for it."},
                 {"heading": "Ask one question up front", "detail": "People come back to hear their answer."},
                 {"heading": "Share something useful first", "detail": "A tip they can use today earns the hour."}],
    "story": {"before": "Half the seats were empty every month.",
              "change": "Every reminder started sharing one useful idea.",
              "after": "More people turned up, and stayed to the end.",
              "lesson": "Give before you ask."},
    "poll": {"question": "What stops you joining a webinar you signed up for?",
             "options": ["Forgot", "Something urgent came up", "Lost the link"]},
}


async def _view(owner_id: str) -> Dict[str, Any]:
    from billing import entitlement
    doc = brand_kit.public_view(await brand_kit.load(owner_id=owner_id, db=db))
    user = await db.users.find_one({"id": owner_id}, {"_id": 0}) or {}
    doc["can_hide_powered_by"] = entitlement(user).get("plan") == "agency" if user else False
    doc["theme"] = brand_kit.theme(doc)
    return doc


@router.get("/brand-kit")
async def get_brand_kit(user=Depends(get_user)):
    return await _view(user["id"])


@router.patch("/brand-kit")
async def patch_brand_kit(data: BrandKitIn, user=Depends(get_user)):
    try:
        fields = brand_kit.clean_fields(data.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await brand_kit.save(db, user["id"], fields)
    return await _view(user["id"])


@router.post("/brand-kit/logo")
async def upload_logo(payload: Dict[str, Any] = Body(...), user=Depends(get_user)):
    """Logo as a data URL (data:image/png;base64,...). PNG, JPG or WebP, up to 3 MB."""
    m = re.match(r"^data:image/(png|jpe?g|webp|gif);base64,(.+)$", payload.get("data_url") or "", re.S)
    if not m:
        raise HTTPException(400, "Upload a PNG, JPG or WebP logo. SVG isn't supported yet, export it as PNG.")
    try:
        raw = base64.b64decode(m.group(2), validate=False)
    except Exception:
        raise HTTPException(400, "That file couldn't be read")
    if len(raw) > 3_000_000:
        raise HTTPException(400, "Logo must be under 3 MB")
    try:
        await brand_kit.set_logo(db, user["id"], raw)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"That image couldn't be used as a logo: {e}")
    return await _view(user["id"])


@router.delete("/brand-kit/logo")
async def delete_logo(user=Depends(get_user)):
    await brand_kit.clear_logo(db, user["id"])
    return await _view(user["id"])


@router.post("/brand-kit/extract")
async def extract_brand(payload: Dict[str, Any] = Body(...), user=Depends(get_user)):
    """Read the brand off the customer's website and save it into their kit.

    Fields the site doesn't give are left as they were."""
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "Enter your website address")
    try:
        found = await brand_kit.extract_from_website(url)
    except brand_kit.UnsafeURL as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        logger.info(f"brand extract failed for {url}: {e}")
        raise HTTPException(400, "We couldn't read that website. Check the address, or fill the kit in by hand.")
    logo = found.pop("logo_png", None)
    fields = brand_kit.clean_fields(found)
    await brand_kit.save(db, user["id"], fields)
    if logo:
        await brand_kit.set_logo(db, user["id"], logo)
    view = await _view(user["id"])
    view["found"] = sorted(list(fields.keys()) + (["logo"] if logo else []))
    return view


@router.get("/brand/{kit_id}/logo.png")
async def public_logo(kit_id: str):
    """Public: email clients load the customer's logo from here."""
    doc = await db[brand_kit.COLLECTION].find_one({"id": kit_id}, {"_id": 0, "logo_png": 1})
    if not doc or not doc.get("logo_png"):
        raise HTTPException(404)
    return Response(bytes(doc["logo_png"]), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/brand-kit/preview.jpg")
async def preview_card(kind: str = "story", user=Depends(get_user)):
    """A sample touch card in the customer's brand, so they can see it before anything sends."""
    import asyncio
    import touch_visuals as tv
    touch = {"problem": 2, "insights": 3, "poll": 4, "story": 5}.get(kind, 5)
    w = {"id": "preview", "title": "How to get more people to show up", "starts_at": "2026-12-03T15:00:00Z",
         "timezone": "Europe/London", "speaker": (user.get("name") or "").strip()}
    brand = await brand_kit.resolve(db, user["id"])
    spec = tv.card_spec(touch, SAMPLE_KIT, w, brand)
    logo = await brand_kit.logo_png(db, user["id"]) if brand.get("logo_hash") else None
    fonts = await brand_kit.font_paths_async(brand.get("font") or "")
    jpeg = await asyncio.get_running_loop().run_in_executor(None, tv.render_card, spec, logo, fonts)
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/brand-kit/preview-email")
async def preview_email(request: Request, user=Depends(get_user)):
    """A sample reminder email in the customer's brand (HTML)."""
    from senders import build_email_html, text_to_email_html
    base = os.environ.get("PUBLIC_BACKEND_URL") or str(request.base_url).rstrip("/")
    brand = await brand_kit.resolve(db, user["id"], base)
    join = "https://example.com/join"
    body = ("Hi Riya,\n\nQuick one: our session is tomorrow at 3:00 PM.\n\n"
            "Here's your link so you don't have to dig for it:\n" + join + "\n\n"
            "If there's something you want me to cover, reply and tell me.\n\n" + ((user.get("name") or "").strip() or "Sam"))
    html_doc = build_email_html(text_to_email_html(body, None, brand, {join: brand.get("cta_label") or "Join the session"}),
                                subject="this time tomorrow", brand=brand)
    return {"html": html_doc}
