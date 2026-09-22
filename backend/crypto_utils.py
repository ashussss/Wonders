"""Field-level encryption for secret-bearing settings columns."""
import os
import logging
from typing import Dict, Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("showup.crypto")

# Fields that contain user-supplied secrets and MUST be encrypted at rest.
SECRET_FIELDS = (
    "brevo_api_key", "mailchimp_api_key", "sendgrid_api_key",
    "linkedin_marketing_token", "linkedin_events_token",
    "meta_graph_token", "twilio_sid", "twilio_token", "circle_api_key",
    "buzzai_api_key",
)

_FERNET_KEY = os.environ.get("FERNET_KEY") or ""
_fernet: Fernet | None = None
_IS_PRODUCTION = bool(os.environ.get("RENDER") or os.environ.get("PRODUCTION"))

if _FERNET_KEY:
    try:
        _fernet = Fernet(_FERNET_KEY.encode())
        logger.info("Encryption initialized successfully")
    except Exception as e:
        logger.error(f"Invalid FERNET_KEY: {e}")
        if _IS_PRODUCTION:
            raise RuntimeError(f"Invalid FERNET_KEY in production: {e}")
else:
    if _IS_PRODUCTION:
        raise RuntimeError(
            "FERNET_KEY is required in production. "
            "Generate with: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
        )
    logger.warning("FERNET_KEY not set — secrets stored in plaintext (DEV MODE ONLY)")

_PREFIX = "enc::"  # marker so we know a value is encrypted


def encrypt_value(value: str) -> str:
    if not value or not _fernet:
        return value
    if value.startswith(_PREFIX):
        return value  # already encrypted
    token = _fernet.encrypt(value.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt_value(value: str) -> str:
    if not value or not _fernet:
        return value
    if not value.startswith(_PREFIX):
        return value
    try:
        return _fernet.decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.error("Failed to decrypt — wrong FERNET_KEY?")
        return value


def encrypt_settings(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(doc)
    for k in SECRET_FIELDS:
        if k in out and isinstance(out[k], str):
            out[k] = encrypt_value(out[k])
    return out


def decrypt_settings(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(doc)
    for k in SECRET_FIELDS:
        if k in out and isinstance(out[k], str):
            out[k] = decrypt_value(out[k])
    return out


def mask_settings_for_api(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy where secret fields are masked '••••••<last4>' for safe UI display.

    Decrypts internally first.
    """
    out = decrypt_settings(doc)
    for k in SECRET_FIELDS:
        v = out.get(k)
        if isinstance(v, str) and v:
            out[k] = ("•" * 8) + v[-4:] if len(v) > 4 else ("•" * len(v))
    return out
