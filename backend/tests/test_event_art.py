"""Event banner -> colours -> creatives. Offline: mongomock + an in-memory GridFS stand-in."""
import asyncio
import io
import os
import sys

import pytest

import _growth_helpers  # noqa: F401

os.environ.setdefault("JWT_SECRET", "test")
if not hasattr(sys.modules.get("database"), "social_images_fs"):
    sys.modules.pop("database", None)

mongomock_motor = pytest.importorskip("mongomock_motor")
from PIL import Image, ImageDraw  # noqa: E402

import brand_kit  # noqa: E402
import event_art as ea  # noqa: E402
import touch_visuals as tv  # noqa: E402

W = {"id": "w1", "owner_id": "u1", "title": "How to fill your webinar seats without paid ads",
     "starts_at": "2099-12-04T13:30:00Z", "timezone": "Asia/Kolkata", "speaker": "Ashu Pratap",
     "registration_link": "https://community.example.com/c/events/growth"}


def _banner(bg="#1B1035", accent="#8B5CF6", fmt="PNG", size=(1600, 840)) -> bytes:
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    d.ellipse([1000, -200, 1900, 700], fill=accent)
    b = io.BytesIO()
    im.save(b, fmt)
    return b.getvalue()


class FakeFS:
    def __init__(self):
        self.files, self.n = {}, 0

    async def upload_from_stream(self, name, data, metadata=None):
        self.n += 1
        self.files[self.n] = data
        return self.n

    async def delete(self, fid):
        self.files.pop(fid, None)

    async def open_download_stream(self, fid):
        data = self.files[fid]

        class S:
            async def read(self_inner):
                return data
        return S()


def test_dark_banner_gives_dark_cards_in_its_colour():
    jpg = ea.normalise_banner(_banner())
    p = ea.palette(jpg)
    assert p["accent"] and brand_kit._sat_light(p["accent"])[0] > 0.35
    t = ea.event_theme(jpg)
    assert brand_kit._lum(t["bg"]) < 0.1 and t["fg"].upper() == "#FFFFFF"
    assert brand_kit.contrast(t["fg"], t["bg"]) >= 4.5


def test_light_banner_gives_light_tinted_cards():
    t = ea.event_theme(ea.normalise_banner(_banner("#F4F1EA", "#0E9F6E")))
    assert brand_kit._lum(t["bg"]) > 0.8
    assert brand_kit.contrast(t["fg"], t["bg"]) >= 4.5


def test_normalise_takes_png_with_alpha_and_shrinks():
    im = Image.new("RGBA", (3000, 1500), (10, 20, 200, 128))
    b = io.BytesIO()
    im.save(b, "PNG")
    out = Image.open(io.BytesIO(ea.normalise_banner(b.getvalue())))
    assert out.format == "JPEG" and out.width == ea.BANNER_MAX_W


def test_junk_and_tiny_images_are_refused():
    with pytest.raises(ea.BannerError):
        ea.normalise_banner(b"<html>not an image</html>")
    with pytest.raises(ea.BannerError):
        ea.normalise_banner(_banner(size=(80, 40)))


@pytest.mark.parametrize("kind", list(ea.SIZES))
@pytest.mark.parametrize("with_banner", [True, False])
def test_every_creative_renders_at_its_size(kind, with_banner):
    jpg = ea.normalise_banner(_banner()) if with_banner else None
    w = {**W, "event_theme": ea.event_theme(jpg), "banner_hash": "x"} if jpg else W
    spec = ea.creative_spec(kind, w, {"name": "Acme Academy", "powered_by": True})
    img = Image.open(io.BytesIO(ea.render_creative(spec, jpg)))
    assert img.format == "JPEG" and img.size == ea.SIZES[kind]


def test_long_title_and_no_date_still_render():
    w = {"id": "w2", "owner_id": "u", "title": "A very long webinar title " * 8, "starts_at": ""}
    spec = ea.creative_spec("square", w)
    assert Image.open(io.BytesIO(ea.render_creative(spec))).size == (1080, 1080)


def test_unsafe_urls_are_refused():
    for url in ("http://127.0.0.1/a.png", "http://169.254.169.254/latest", "file:///etc/passwd"):
        with pytest.raises(ea.BannerError):
            asyncio.run(ea.download_image(url))


def _db():
    return mongomock_motor.AsyncMongoMockClient()["t"]


def test_store_banner_sets_theme_and_creatives_follow_it(monkeypatch):
    db, fs = _db(), FakeFS()

    async def resolve(_db, owner, base=""):
        return {"name": "Acme", "powered_by": True}

    async def no_logo(*a):
        return None
    monkeypatch.setattr(brand_kit, "resolve", resolve)
    monkeypatch.setattr(brand_kit, "logo_png", no_logo)

    async def run():
        await db.webinars.insert_one(dict(W))
        out = await ea.store_banner(db, fs, W, _banner())
        w = await db.webinars.find_one({"id": "w1"}, {"_id": 0})
        r1 = await ea.ensure_creative(db, fs, w, "promo")
        r2 = await ea.ensure_creative(db, fs, w, "promo")  # cached
        await ea.store_banner(db, fs, w, _banner("#F4F1EA", "#0E9F6E"))  # new banner
        w2 = await db.webinars.find_one({"id": "w1"}, {"_id": 0})
        r3 = await ea.ensure_creative(db, fs, w2, "promo")
        return out, w, r1, r2, r3, w2
    out, w, r1, r2, r3, w2 = asyncio.run(run())
    assert out["event_theme"] and w["banner_url"].startswith("/api/webinars/w1/banner.img")
    assert r1["hash"] == r2["hash"] and r3["hash"] != r1["hash"]
    assert len(fs.files) == 2  # old banner and old creative were deleted


def test_import_cover_keeps_a_host_banner_and_records_failures(monkeypatch):
    db, fs = _db(), FakeFS()

    async def fake_download(url):
        if "bad" in url:
            raise ea.BannerError("That link isn't an image")
        return _banner()
    monkeypatch.setattr(ea, "download_image", fake_download)

    async def run():
        await db.webinars.insert_one(dict(W))
        bad = await ea.import_cover(db, fs, W, "https://x.com/bad.png")
        w_bad = await db.webinars.find_one({"id": "w1"}, {"_id": 0})
        ok = await ea.import_cover(db, fs, W, "https://x.com/cover.png")
        again = await ea.import_cover(db, fs, W, "https://x.com/other.png")  # host banner kept
        w = await db.webinars.find_one({"id": "w1"}, {"_id": 0})
        return bad, w_bad, ok, again, w
    bad, w_bad, ok, again, w = asyncio.run(run())
    assert bad is None and "isn't an image" in w_bad["banner_error"]
    assert ok and again is None and "banner_error" not in w and w["event_theme"]


def test_value_cards_wear_the_event_colours():
    theme = ea.event_theme(ea.normalise_banner(_banner()))
    kit = {"insights": [{"heading": "a", "detail": "b"}]}
    spec = tv.card_spec(3, kit, {**W, "event_theme": theme}, {"theme": {"bg": "#FFFFFF"}})
    assert spec["brand"]["theme"] == theme
    assert tv.card_spec(3, kit, W, None)["brand"]["theme"] is None


def test_confirmation_starting_and_live_touches_get_event_creatives(monkeypatch):
    db, fs = _db(), FakeFS()

    async def resolve(_db, owner, base=""):
        return {"name": "Acme"}
    monkeypatch.setattr(brand_kit, "resolve", resolve)
    assert all(tv.has_visual(n) for n in (1, 9, 12))

    async def run():
        await db.webinars.insert_one(dict(W))
        rows = []
        for n in (1, 9, 12):
            t = {"id": f"t{n}", "webinar_id": "w1", "owner_id": "u1", "touch_num": n}
            rows.append(await tv.ensure_visual(db, fs, t, dict(W), kit={}, brand={"name": "Acme"}))
        return rows
    rows = asyncio.run(run())
    assert [r["kind"] for r in rows] == ["youre_in", "starting", "live"]
    assert all(r["touch_id"] == f"t{n}" for r, n in zip(rows, (1, 9, 12)))
