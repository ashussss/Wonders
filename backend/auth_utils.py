"""Auth helpers and FastAPI dependency."""
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import JWT_SECRET, JWT_ALG
from database import db

bearer = HTTPBearer(auto_error=False)


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_pw(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def make_token(uid: str) -> str:
    return jwt.encode(
        {"sub": uid, "exp": datetime.now(timezone.utc) + timedelta(days=14)},
        JWT_SECRET, algorithm=JWT_ALG)


async def get_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds:
        raise HTTPException(401, "Missing token")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
    except Exception:
        raise HTTPException(401, "Invalid token")
    if await _session_revoked(payload):
        raise HTTPException(401, "Password was changed, please sign in again")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def _session_revoked(payload: dict) -> bool:
    """A password reset signs out every session that started before it."""
    from password_reset import token_issued_before_password_change
    u = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0, "password_changed_at": 1})
    return bool(u) and token_issued_before_password_change(payload, u.get("password_changed_at"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
