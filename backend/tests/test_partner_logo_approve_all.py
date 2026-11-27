"""Partner logo on cards/creatives (host | partner) and Approve all in the Send Plan."""
import asyncio
import io
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

import _growth_helpers  # noqa: F401

os.environ.setdefault("JWT_SECRET", "test")
if not hasattr(sys.modules.get("database"), "social_images_fs"):
    sys.modules.pop("database", None)
mm = pytest.importorskip("mongomock_motor")
from PIL import Image  # noqa: E402

import ai  # noqa: E402
import auth_utils  # noqa: E402
import brand_kit as bk  # noqa: E402
import event_art as ea  # noqa: E402
import partner_logo  # noqa: E402
import routes_auth  # noqa: E402
import routes_webinars  # noqa: E402
import touch_visuals as tv  # noqa: E402
from test_touch_value_content import RAW_KIT  # noqa: E402

W = {"id": "w1", "owner_id": "u1", "title": "Budgets that survive the spring term",
     "starts_at": "2099-12-08T10:00:00Z", "timezone": "Europe/London", "speaker": "Alka"}
BRAND = {"theme": bk.theme({"primary_color": "#0E7C66", "background_color": "#F6F3EE"}), "font": "",
         "logo_hash": "abc", "name": "SBM", "powered_by": True}


def _png(color, size=(600, 200)):
    im = Image.new("RGBA", size, color + (255,))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def test_lockup_puts_both_logos_side_by_side():
    import social_images as si
    t = BRAND["theme"]
    lock = partner_logo.lockup(si, t, BRAND, _png((14, 124, 102)), _png((200, 30, 30)), 520, 70)
    assert lock.height <= 70 and lock.width <= 520
    left, right = lock.getpixel((5, lock.height // 2)), lock.getpixel((lock.width - 5, lock.height // 2))
    assert left[:3] == pytest.approx((14, 124, 102), abs=8)     # host (Brand Kit) first
    assert right[:3] == pytest.approx((200, 30, 30), abs=8)     # partner second
    # Name only, no partner image: the partner's name is drawn in text.
    named = partner_logo.lockup(si, t, {**BRAND, "partner_name": "Acme Schools"}, _png((14, 124, 102)), None, 520, 70)
    assert named.width > lock.width // 3


def test_partner_changes_card_hash_but_plain_webinars_keep_theirs():
    kit = ai.normalize_kit(RAW_KIT)
    plain = tv.card_spec(5, kit, W, BRAND)
    with_partner = tv.card_spec(5, kit, {**W, "partner_logo_hash": "p1"}, BRAND)
    assert plain and "partner_hash" not in plain["brand"]
    assert with_partner["brand"]["partner_hash"] == "p1"
    assert tv.spec_hash(plain) != tv.spec_hash(with_partner)
    assert "partner_hash" not in ea.creative_spec("promo", W, BRAND)["brand"]


def test_card_and_creatives_render_with_partner():
    kit = ai.normalize_kit(RAW_KIT)
    w = {**W, "partner_logo_hash": "p1", "partner_name": "Acme"}
    spec = tv.card_spec(5, kit, w, BRAND)
    img = Image.open(io.BytesIO(tv.render_card(spec, bk.normalise_logo(_png((14, 124, 102))),
                                               None, bk.normalise_logo(_png((200, 30, 30))))))
    assert img.size == (1080, 1350)
    # Partner (red) is right-most in the top-right corner.
    assert img.getpixel((1080 - 80 - 10, 105))[:3] == pytest.approx((200, 30, 30), abs=10)
    for kind in ea.SIZES:
        cs = ea.creative_spec(kind, w, BRAND)
        out = Image.open(io.BytesIO(ea.render_creative(cs, None, bk.normalise_logo(_png((14, 124, 102))),
                                                       None, bk.normalise_logo(_png((200, 30, 30))))))
        assert out.size == ea.SIZES[kind]


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture()
def env(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    d = mm.AsyncMongoMockClient()["t"]
    for mod in (auth_utils, routes_auth, routes_webinars):
        monkeypatch.setattr(mod, "db", d)
    app = FastAPI()
    app.state.limiter = routes_webinars.limiter
    app.include_router(routes_webinars.router)

    async def setup():
        u = await routes_auth.create_user("host@sbm.test", "SBM", "pw12345678")
        await d.webinars.insert_one({**W, "owner_id": u["id"]})
        now = datetime.now(timezone.utc)
        copy = {"channels": {"email": {"safe": {"subject": "s", "body": "b"}}}}
        rows = [
            {"id": "t2", "touch_num": 2, "scheduled_at": (now + timedelta(days=5)).isoformat(), "ai_copy": copy},
            {"id": "t3", "touch_num": 3, "scheduled_at": (now - timedelta(hours=2)).isoformat(), "ai_copy": copy},
            {"id": "t4", "touch_num": 4, "scheduled_at": (now + timedelta(days=2)).isoformat(), "ai_copy": {}},
            {"id": "t5", "touch_num": 5, "scheduled_at": (now + timedelta(days=1)).isoformat(), "ai_copy": copy,
             "selected_variant": 1},
            {"id": "t6", "touch_num": 6, "scheduled_at": (now + timedelta(days=1)).isoformat(), "ai_copy": copy,
             "approval_status": "approved"},
        ]
        for r in rows:
            await d.touches.insert_one({"webinar_id": "w1", "owner_id": u["id"], "approval_status": "pending",
                                        "sent_status": "planned", **r})
        return {"Authorization": "Bearer " + auth_utils.make_token(u["id"])}
    return d, TestClient(app), asyncio.run(setup())


def _status(d):
    async def go():
        return {t["id"]: (t["approval_status"], t.get("selected_variant"))
                async for t in d.touches.find({}, {"_id": 0})}
    return asyncio.run(go())


def test_approve_all_skips_past_due_and_unwritten(env):
    d, client, h = env
    r = client.post("/api/webinars/w1/touches/approve-all", json={}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approved"] == 2 and body["skipped_past"] == [3] and body["skipped_no_copy"] == [4]
    s = _status(d)
    assert s["t2"] == ("approved", 0)          # no pick yet -> first version
    assert s["t5"] == ("approved", 1)          # the version picked on the card is kept
    assert s["t3"][0] == "pending" and s["t4"][0] == "pending"
    # Asked for explicitly, past-due ones go too.
    assert client.post("/api/webinars/w1/touches/approve-all", json={"include_past": True}, headers=h).json()["approved"] == 1


def test_approve_all_is_owner_only(env):
    d, client, h = env
    other = asyncio.run(routes_auth.create_user("x@y.test", "X", "pw12345678"))
    r = client.post("/api/webinars/w1/touches/approve-all", json={},
                    headers={"Authorization": "Bearer " + auth_utils.make_token(other["id"])})
    assert r.status_code == 404


def test_partner_logo_upload_name_and_remove(env):
    d, client, h = env
    r = client.post("/api/webinars/w1/partner-logo", headers=h, data={"name": "Acme Schools"},
                    files={"file": ("logo.png", _png((200, 30, 30)), "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["partner_logo_url"].startswith("/api/webinars/w1/partner-logo.png")
    w = client.get("/api/webinars/w1", headers=h).json()
    assert w["partner_name"] == "Acme Schools" and w["partner_logo_hash"]
    img = client.get("/api/webinars/w1/partner-logo.png")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert client.post("/api/webinars/w1/partner-logo", headers=h, data={"name": "Acme"}).json()["partner_name"] == "Acme"
    bad = client.post("/api/webinars/w1/partner-logo", headers=h, files={"file": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 400
    assert client.delete("/api/webinars/w1/partner-logo", headers=h).status_code == 200
    assert client.get("/api/webinars/w1/partner-logo.png").status_code == 404
    assert not client.get("/api/webinars/w1", headers=h).json()["partner_logo_url"]
