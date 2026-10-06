"""Shared helpers for the Growth Engine test suite."""
import os
import sys

import pytest

# Make the backend modules (which import each other flat, e.g. `import pseo`)
# importable regardless of how pytest is invoked.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

DEFAULT_MONGO = "mongodb://127.0.0.1:27019"


def mongo_available(url: str = None) -> bool:
    """True if a mongod is reachable at the test URL."""
    url = url or os.environ.get("MONGO_URL", DEFAULT_MONGO)
    try:
        from pymongo import MongoClient
        c = MongoClient(url, serverSelectionTimeoutMS=1500)
        c.admin.command("ping")
        c.close()
        return True
    except Exception:
        return False


def require_mongo():
    """Skip a test module when no mongod is available (keeps CI green offline)."""
    if not mongo_available():
        pytest.skip("no mongod reachable — start one or set MONGO_URL", allow_module_level=True)


@pytest.fixture(scope="session")
def monkeypatch_module():
    """Session-scoped monkeypatch.

    pytest only ships a function-scoped ``monkeypatch``, but the Growth tests need
    session-scoped patching so the motor client and the AI stub stay on one loop.
    """
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()