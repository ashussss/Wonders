"""Offline: a user can't import registrants into, or mark attendance on, someone else's webinar."""
import os
import sys

import pytest
from fastapi import HTTPException

import _growth_helpers  # noqa: F401  (puts backend/ on sys.path)

os.environ.setdefault("JWT_SECRET", "test")
if not hasattr(sys.modules.get("database"), "social_images_fs"):
    sys.modules.pop("database", None)

import routes_webinars  # noqa: E402
from models import RegistrantIn  # noqa: E402


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, q, proj=None):
        return next((dict(d) for d in self.docs if all(d.get(k) == v for k, v in q.items())), None)

    async def insert_one(self, doc):
        self.docs.append(doc)

    async def update_many(self, q, upd):
        for d in self.docs:
            if all((d.get(k) in v["$in"]) if isinstance(v, dict) else d.get(k) == v for k, v in q.items()):
                d.update(upd["$set"])

    async def update_one(self, q, upd):
        await self.update_many(q, upd)


class _DB:
    def __init__(self):
        self.webinars = _Coll([{"id": "w1", "owner_id": "owner"}])
        self.registrants = _Coll([{"id": "r1", "webinar_id": "w1", "owner_id": "owner",
                                   "email": "a@b.com", "attended": False}])


@pytest.fixture
def db(monkeypatch):
    fake = _DB()
    monkeypatch.setattr(routes_webinars, "db", fake)
    return fake


async def test_import_into_foreign_webinar_rejected(db):
    with pytest.raises(HTTPException) as e:
        await routes_webinars.import_registrants("w1", [RegistrantIn(name="x", email="x@y.com")], user={"id": "intruder"})
    assert e.value.status_code == 404
    assert len(db.registrants.docs) == 1


async def test_import_into_own_webinar_works(db):
    r = await routes_webinars.import_registrants("w1", [RegistrantIn(name="x", email="x@y.com")], user={"id": "owner"})
    assert r["inserted"] == 1


async def test_mark_attendance_on_foreign_webinar_rejected(db):
    with pytest.raises(HTTPException):
        await routes_webinars.mark_attendance("w1", {"emails": ["a@b.com"]}, user={"id": "intruder"})
    assert db.registrants.docs[0]["attended"] is False


async def test_mark_attendance_on_own_webinar(db):
    await routes_webinars.mark_attendance("w1", {"emails": ["A@b.com"]}, user={"id": "owner"})
    assert db.registrants.docs[0]["attended"] is True
