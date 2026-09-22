"""Auth endpoints + initial settings seed."""
import uuid
from fastapi import APIRouter, HTTPException, Depends, Request, Body
from slowapi import Limiter
from slowapi.util import get_remote_address

from database import db
from auth_utils import hash_pw, verify_pw, make_token, now_iso, get_user
from models import UserSignup, UserLogin
from config import TOUCH_DEFS, SUPERADMIN_SECRET

router = APIRouter(prefix="/api/auth")
limiter = Limiter(key_func=get_remote_address)


@router.post("/register")
@limiter.limit("5/minute")
async def register(request: Request, data: UserSignup):
    existing = await db.users.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(400, "Email already registered")
    uid = str(uuid.uuid4())
    user = {"id": uid, "email": data.email.lower(), "name": data.name,
            "password": hash_pw(data.password), "created_at": now_iso()}
    await db.users.insert_one(user)
    await db.settings.insert_one({
        "owner_id": uid,
        "default_touches": {str(t["num"]): True for t in TOUCH_DEFS},
        "default_channels": {str(t["num"]): t["default_channels"] for t in TOUCH_DEFS},
        "per_touch_auto_send": {str(t["num"]): False for t in TOUCH_DEFS},
    })
    return {"token": make_token(uid), "user": {"id": uid, "email": user["email"], "name": user["name"], "role": "user"}}


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, data: UserLogin):
    user = await db.users.find_one({"email": data.email.lower()})
    if not user or not verify_pw(data.password, user["password"]):
        raise HTTPException(401, "Invalid credentials")
    return {"token": make_token(user["id"]),
            "user": {"id": user["id"], "email": user["email"], "name": user["name"], "role": user.get("role", "user")}}


@router.get("/me")
async def me(user=Depends(get_user)):
    return {k: v for k, v in user.items() if k != "password"}


# ══════════════════════════════════════════════
# ADMIN ROUTES
# ══════════════════════════════════════════════

async def get_admin(user=Depends(get_user)):
    if user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(403, "Admin access required")
    return user

@router.get("/admin/stats")
async def admin_stats(user=Depends(get_admin)):
    total_users     = await db.users.count_documents({})
    total_webinars  = await db.webinars.count_documents({})
    total_registrants = await db.registrants.count_documents({})
    total_touches   = await db.touches.count_documents({})
    approved_touches= await db.touches.count_documents({"approval_status": "approved"})
    sent_touches    = await db.touches.count_documents({"sent_status": "sent"})

    # Recent users
    users = await db.users.find({}, {"_id": 0, "password": 0}).sort("created_at", -1).limit(20).to_list(20)

    # Webinars per user
    pipeline = [
        {"$group": {"_id": "$owner_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}, {"$limit": 10}
    ]
    webinars_per_user = await db.webinars.aggregate(pipeline).to_list(10)

    # Recent webinars enriched with owner info — bulk fetch owners
    webinars_raw = await db.webinars.find({}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    owner_ids = list({w["owner_id"] for w in webinars_raw})
    owners_list = await db.users.find({"id": {"$in": owner_ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(100)
    owners_map = {o["id"]: o for o in owners_list}
    webinars = []
    for w in webinars_raw:
        owner = owners_map.get(w["owner_id"], {})
        webinars.append({**w, "owner_name": owner.get("name",""), "owner_email": owner.get("email","")})

    return {
        "stats": {
            "total_users": total_users,
            "total_webinars": total_webinars,
            "total_registrants": total_registrants,
            "total_touches": total_touches,
            "approved_touches": approved_touches,
            "sent_touches": sent_touches,
            "approval_rate": round(approved_touches / max(total_touches, 1) * 100, 1),
        },
        "recent_users": users,
        "recent_webinars": webinars,
        "webinars_per_user": webinars_per_user,
    }


@router.get("/admin/users")
async def admin_list_users(user=Depends(get_admin)):
    users = await db.users.find({}, {"_id": 0, "password": 0}).sort("created_at", -1).to_list(500)
    # Enrich with webinar count
    for u in users:
        u["webinar_count"] = await db.webinars.count_documents({"owner_id": u["id"]})
        u["registrant_count"] = await db.registrants.count_documents({"owner_id": u["id"]})
    return users


@router.patch("/admin/users/{uid}/role")
async def admin_set_role(uid: str, payload: dict, user=Depends(get_admin)):
    role = payload.get("role", "user")
    if role not in ("user", "moderator", "admin"):
        raise HTTPException(400, "Invalid role")
    # Superadmin protection
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    if target.get("role") == "superadmin":
        raise HTTPException(403, "Cannot change superadmin role")
    await db.users.update_one({"id": uid}, {"$set": {"role": role}})
    return {"ok": True, "role": role}


@router.delete("/admin/users/{uid}")
async def admin_delete_user(uid: str, user=Depends(get_admin)):
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404)
    if target.get("role") in ("admin", "superadmin"):
        raise HTTPException(403, "Cannot delete admin users")
    await db.users.delete_one({"id": uid})
    await db.webinars.delete_many({"owner_id": uid})
    await db.touches.delete_many({"owner_id": uid})
    await db.registrants.delete_many({"owner_id": uid})
    return {"ok": True}


@router.post("/admin/invite")
async def admin_invite(payload: dict, user=Depends(get_admin)):
    """Create a new team member account directly."""
    import uuid
    from auth_utils import hash_pw
    email = payload.get("email", "").lower().strip()
    name  = payload.get("name", "Team Member")
    role  = payload.get("role", "moderator")
    password = payload.get("password", str(uuid.uuid4())[:12])
    if not email:
        raise HTTPException(400, "Email required")
    if role not in ("moderator", "admin"):
        raise HTTPException(400, "Role must be moderator or admin")
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(400, "Email already registered")
    uid = str(uuid.uuid4())
    await db.users.insert_one({
        "id": uid, "email": email, "name": name, "role": role,
        "password": hash_pw(password), "created_at": now_iso(),
        "invited_by": user["id"]
    })
    await db.settings.insert_one({"owner_id": uid})
    return {"ok": True, "id": uid, "email": email, "role": role, "temp_password": password}


# Make first registered user superadmin automatically
@router.post("/admin/make-superadmin")
async def make_superadmin(payload: dict, user=Depends(get_user)):
    """One-time setup — makes a user superadmin. Only works if no superadmin exists."""
    existing_sa = await db.users.find_one({"role": "superadmin"})
    if existing_sa:
        raise HTTPException(403, "Superadmin already exists")
    secret = payload.get("secret", "")
    if secret != SUPERADMIN_SECRET:
        raise HTTPException(403, "Invalid secret")
    await db.users.update_one({"id": user["id"]}, {"$set": {"role": "superadmin"}})
    return {"ok": True, "message": f"{user['email']} is now superadmin"}


# ══════════════════════════════════════════════
# WAITLIST
# ══════════════════════════════════════════════
@router.post("/waitlist")
@limiter.limit("3/minute")
async def join_waitlist(request: Request, payload: dict = Body(default={})):
    email = payload.get("email", "").lower().strip()
    name  = payload.get("name", "").strip()
    role  = payload.get("role", "").strip()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email required")
    existing = await db.waitlist.find_one({"email": email})
    if existing:
        return {"ok": True, "already": True, "position": existing.get("position", 1)}
    count = await db.waitlist.count_documents({})
    position = count + 1
    await db.waitlist.insert_one({
        "email": email, "name": name, "role": role,
        "position": position, "joined_at": now_iso(),
        "source": payload.get("source", "landing")
    })
    return {"ok": True, "already": False, "position": position}

@router.get("/waitlist/count")
async def waitlist_count():
    count = await db.waitlist.count_documents({})
    return {"count": count}

@router.get("/admin/waitlist")
async def admin_waitlist(user=Depends(get_admin)):
    entries = await db.waitlist.find({}, {"_id": 0}).sort("position", 1).to_list(1000)
    return entries
