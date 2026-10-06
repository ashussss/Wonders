"""Pytest bootstrap for the backend suite.

Every Growth Engine test shares ONE session-scoped motor client and ONE event
loop. This is required, not stylistic: the app's motor client is created at
import time (``database.py``) and motor pins a client to the loop it is first
awaited on. Two clients, or per-test loops, make every request after the first
raise "Future attached to a different loop".
"""
import os
import sys

import pytest
import pytest_asyncio

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(BACKEND_DIR, "tests")
for _p in (BACKEND_DIR, TESTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27019")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def growth_client():
    """One motor client + one loop for all Growth tests."""
    try:
        from pymongo import MongoClient
        probe = MongoClient(MONGO_URL, serverSelectionTimeoutMS=1500)
        probe.admin.command("ping")
        probe.close()
    except Exception:
        pytest.skip("no mongod reachable — Growth tests need MongoDB")

    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(MONGO_URL)
    yield client
    client.close()


@pytest.fixture(scope="session")
def monkeypatch_module():
    """Session-scoped monkeypatch (pytest only ships a function-scoped one)."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()