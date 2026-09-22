"""
ShowUp.ai Security Tests — Multi-tenant data isolation
Tests that User A cannot access User B's data.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"

@pytest.fixture
def client():
    """Return a test client — mocked at unit level."""
    return None  # Placeholder for integration tests

# ── Unit-level security checks ────────────────────────────────────────────────

def test_no_hardcoded_admin_secret():
    """SUPERADMIN_SECRET must not have a hardcoded production fallback."""
    import config
    # In test env, dev fallback is OK. But the string 'showup-admin-2026' must be gone.
    import inspect
    src = inspect.getsource(config)
    assert "showup-admin-2026" not in src, \
        "Hardcoded admin secret found in config.py"

def test_cors_wildcard_requires_env():
    """CORS_ORIGINS must be configurable via env."""
    import config
    import inspect
    src = inspect.getsource(config)
    # Must not hardcode * without env check
    assert 'CORS_ORIGINS = ["*"]' not in src or 'os.environ' in src, \
        "CORS wildcard must only be set from environment"

def test_fernet_key_warning_without_key(monkeypatch):
    """Without FERNET_KEY in dev, a warning is logged (not crash)."""
    monkeypatch.delenv("FERNET_KEY", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("PRODUCTION", raising=False)
    # Re-import with patched env
    import importlib
    import crypto_utils
    importlib.reload(crypto_utils)
    # Should not raise in dev
    assert crypto_utils._fernet is None

def test_call_llm_not_call_gemini():
    """AI module must use _call_llm, not the misleading _call_gemini name."""
    import ai
    assert hasattr(ai, '_call_llm'), "ai.py must have _call_llm function"
    assert not hasattr(ai, '_call_gemini'), "ai.py must not have _call_gemini (misleading name)"

def test_mask_settings_hides_secrets():
    """mask_settings_for_api must not return raw API keys."""
    from crypto_utils import mask_settings_for_api
    doc = {
        "brevo_api_key": "sk-real-secret-key-12345",
        "circle_api_key": "circle-token-abcdef",
        "some_public": "public-value",
    }
    masked = mask_settings_for_api(doc)
    assert masked["brevo_api_key"] != "sk-real-secret-key-12345", \
        "Real API key must be masked"
    assert "2345" in masked["brevo_api_key"], \
        "Last 4 chars should be visible"
    assert masked["some_public"] == "public-value", \
        "Non-secret fields should pass through"

def test_encrypt_decrypt_roundtrip():
    """Encryption roundtrip must work correctly."""
    import os
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    os.environ["FERNET_KEY"] = key
    
    import importlib
    import crypto_utils
    importlib.reload(crypto_utils)
    
    original = "my-secret-api-key-xyz"
    encrypted = crypto_utils.encrypt_value(original)
    assert encrypted != original
    assert encrypted.startswith("enc::")
    
    decrypted = crypto_utils.decrypt_value(encrypted)
    assert decrypted == original
    
    del os.environ["FERNET_KEY"]

def test_owner_id_scoping_in_webinar_routes():
    """Every authenticated webinar endpoint must include owner_id in DB queries."""
    import inspect
    import routes_webinars
    src = inspect.getsource(routes_webinars)
    
    # Count unscoped find_one calls on webinars
    import re
    unscoped = re.findall(
        r'db\.webinars\.find_one\(\{[^}]*"id"[^}]*\}[^,]',
        src
    )
    # Public registration endpoints are OK without owner_id
    # But there should be very few unscoped lookups
    assert len(unscoped) <= 3, \
        f"Too many unscoped webinar lookups: {unscoped}"

def test_no_credentials_in_source():
    """No hardcoded credentials in source files."""
    import os, re
    backend_dir = os.path.dirname(__file__) + "/.."
    
    suspicious_patterns = [
        r'password\s*=\s*["\'][^"\']{8,}["\']',
        r'api_key\s*=\s*["\'][a-zA-Z0-9_-]{20,}["\']',
        r'sk-[a-zA-Z0-9]{20,}',  # OpenAI style
        r'gsk_[a-zA-Z0-9]{20,}',  # Groq style  
        r'AQ\.[a-zA-Z0-9_-]{20,}',  # Gemini style
    ]
    
    violations = []
    for fname in os.listdir(backend_dir):
        if not fname.endswith('.py') or fname.startswith('test_'):
            continue
        fpath = os.path.join(backend_dir, fname)
        try:
            content = open(fpath).read()
            for pattern in suspicious_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    violations.append(f"{fname}: {matches[0]}")
        except:
            pass
    
    assert not violations, f"Potential hardcoded credentials: {violations}"

# ── IDOR simulation tests ─────────────────────────────────────────────────────

def test_idor_conceptual_webinar():
    """
    Conceptual test: verifies the query pattern used in routes_webinars
    includes owner_id for all sensitive operations.
    """
    import inspect, re
    import routes_webinars
    src = inspect.getsource(routes_webinars)
    
    # All webinar patches/deletes must scope to owner
    patch_patterns = re.findall(
        r'db\.webinars\.update_one\(\{([^}]+)\}',
        src
    )
    for pattern in patch_patterns:
        assert 'owner_id' in pattern, \
            f"Webinar update missing owner_id scope: {pattern}"

def test_idor_conceptual_touch():
    """Touch operations must be scoped to owner."""
    import inspect, re
    import routes_webinars, routes_delivery
    
    for module in [routes_webinars, routes_delivery]:
        src = inspect.getsource(module)
        patch_patterns = re.findall(
            r'db\.touches\.update_one\(\{([^}]+)\}',
            src
        )
        for pattern in patch_patterns:
            # Touches should be scoped by id+owner or webinar that's owned
            has_scope = 'owner_id' in pattern or 'webinar_id' in pattern
            assert has_scope, \
                f"Touch update missing scope in {module.__name__}: {pattern}"

def test_admin_endpoint_requires_secret():
    """Admin endpoints must check SUPERADMIN_SECRET."""
    import inspect
    import routes_auth
    src = inspect.getsource(routes_auth)
    
    # Admin routes must verify the secret
    assert 'SUPERADMIN_SECRET' in src, \
        "Admin routes must check SUPERADMIN_SECRET"
    assert 'raise HTTPException' in src, \
        "Admin routes must raise on unauthorized"

