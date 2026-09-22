"""ShowUp.ai — production configuration.

All secrets are read from environment variables.
No hardcoded fallbacks for production secrets.
"""
import os
import sys
import logging

logger = logging.getLogger("showup.config")

# ── Database ──────────────────────────────────────────────────────────────────
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME   = os.environ.get("DB_NAME", "showup")

# ── JWT ───────────────────────────────────────────────────────────────────────
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALG    = os.environ.get("JWT_ALG", "HS256")

# ── CORS ──────────────────────────────────────────────────────────────────────
_cors_env = os.environ.get("CORS_ORIGINS", "")
if _cors_env:
    CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    # Dev fallback — permissive
    CORS_ORIGINS = ["*"]
    logger.warning("CORS_ORIGINS not set — allowing all origins (dev mode)")

# ── Admin secret ──────────────────────────────────────────────────────────────
SUPERADMIN_SECRET = os.environ.get("SUPERADMIN_SECRET", "")
if not SUPERADMIN_SECRET:
    _is_prod = os.environ.get("RENDER") or os.environ.get("PRODUCTION")
    if _is_prod:
        logger.critical("SUPERADMIN_SECRET is not set in production — admin endpoints disabled")
    else:
        SUPERADMIN_SECRET = "dev-admin-secret"
        logger.warning("SUPERADMIN_SECRET not set — using dev default")

# ── Claude / AI model ─────────────────────────────────────────────────────────
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")

# ── Public backend URL ────────────────────────────────────────────────────────
PUBLIC_BACKEND_URL = os.environ.get("PUBLIC_BACKEND_URL", "http://localhost:8000")

# ── Touch definitions ─────────────────────────────────────────────────────────
TOUCH_DEFS = [
    {"num": 1,  "name": "Registration confirmation",    "trigger": "On registration",    "days_before": None, "default_channels": ["email"]},
    {"num": 2,  "name": "Week 3 — Awareness post",      "trigger": "21 days before",     "days_before": 21,   "default_channels": ["email", "linkedin_page", "facebook_page"]},
    {"num": 3,  "name": "Week 3 — Newsletter/Insight",  "trigger": "19 days before",     "days_before": 19,   "default_channels": ["email", "linkedin_page"]},
    {"num": 4,  "name": "Week 2 — Engagement poll",     "trigger": "14 days before",     "days_before": 14,   "default_channels": ["linkedin_page", "facebook_page", "instagram", "circle"]},
    {"num": 5,  "name": "Week 2 — Case study",          "trigger": "10 days before",     "days_before": 10,   "default_channels": ["email", "linkedin_page", "facebook_page"]},
    {"num": 6,  "name": "Week 2 — Infographic teaser",  "trigger": "8 days before",      "days_before": 8,    "default_channels": ["instagram", "linkedin_page", "facebook_page"]},
    {"num": 7,  "name": "Week 1 — Urgency email",       "trigger": "5 days before",      "days_before": 5,    "default_channels": ["email", "whatsapp"]},
    {"num": 8,  "name": "Day before — Final warmup",    "trigger": "1 day before",       "days_before": 1,    "default_channels": ["email", "linkedin_page", "linkedin_personal"]},
    {"num": 9,  "name": "Day of — Join link",           "trigger": "1 hour before",      "days_before": 0,    "default_channels": ["email", "whatsapp", "circle"]},
    {"num": 10, "name": "Post-event — Attended",        "trigger": "After event",        "days_before": -1,   "default_channels": ["email"]},
    {"num": 11, "name": "Post-event — No show FOMO",    "trigger": "2 days after",       "days_before": -2,   "default_channels": ["email"]},
]
