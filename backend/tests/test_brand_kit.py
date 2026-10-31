"""Offline tests: every customer's output wears their own brand kit, with only a small
Powered by ShowUp AI mark. No mongod, network or LLM needed."""
import asyncio
import io
import os
import sys

import pytest

import _growth_helpers  # noqa: F401  (puts backend/ on sys.path)

os.environ.setdefault("JWT_SECRET", "test")
if not hasattr(sys.modules.get("database"), "social_images_fs"):
    sys.modules.pop("database", None)

import ai  # noqa: E402
import brand_kit as bk  # noqa: E402
import routes_delivery  # noqa: E402
import senders  # noqa: E402
import touch_render  # noqa: E402
import touch_visuals as tv  # noqa: E402
from test_touch_value_content import RAW_KIT, W, _Bucket, _DB  # noqa: E402

SITE = """<!doctype html><html><head>
<title>Acme Physio | Get moving again</title>
<meta name="description" content="We help desk workers fix back pain in 6 weeks, without surgery.">
<meta name="theme-color" content="#0E7C66">
<link rel="stylesheet" href="/main.css">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;700&display=swap" rel="stylesheet">
<link rel="apple-touch-icon" href="/icon-180.png">
<style>:root{--brand-primary:#0e7c66;--grey:#777777} body{background:#F6F3EE;color:#1a1a1a}</style>
</head><body><header><img class="site-logo" src="/logo.png" alt="Acme Physio"></header>
<h1>Back pain? Let's sort it.</h1>
<p>Most of our clients sit at a desk all day. We give you three simple moves and a plan that fits around work.</p>
</body></html>"""


def _png(w=300, h=90, color=(14, 124, 102, 255)):
    from PIL import Image
    img = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (w, h), color), (20, 20))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


# ── colours ──────────────────────────────────────────────────────────────────

def test_theme_keeps_text_readable():
    assert bk.theme({}) is None                                   # no brand colour: old themes stay
    t = bk.theme({"primary_color": "#0E7C66", "background_color": "#F6F3EE"})
    assert t["accent"] == "#0E7C66" and bk.contrast(t["fg"], t["bg"]) >= 4.5
    # A pale yellow brand on white can't be read as text: the accent falls back to the text colour.
    pale = bk.theme({"primary_color": "#FFE600"})
    assert pale["accent"] == pale["fg"] and bk.contrast(pale["on_accent"], pale["accent"]) >= 4.5
    # Unreadable text colour picked by the customer is replaced.
    dark = bk.theme({"primary_color": "#FFD400", "background_color": "#111111", "text_color": "#222222"})
    assert dark["fg"] == "#FFFFFF"


def test_clean_fields_validates_and_normalises():
    out = bk.clean_fields({"primary_color": "#abc", "website": "acme.com", "hide_powered_by": 1,
                           "tone": "  warm   and direct "})
    assert out == {"primary_color": "#AABBCC", "website": "https://acme.com", "hide_powered_by": True,
                   "tone": "warm and direct"}
    assert bk.clean_fields({"primary_color": ""}) == {"primary_color": ""}
    with pytest.raises(ValueError):
        bk.clean_fields({"primary_color": "green-ish"})


# ── reading a website ────────────────────────────────────────────────────────

def test_extract_from_website(monkeypatch):
    pages = {"https://acme.example/": (SITE.encode(), "text/html"),
             "https://acme.example/main.css": (b"a{color:#0E7C66} .btn{background:#0E7C66} .x{color:#ff0000}", "text/css"),
             "https://acme.example/logo.png": (_png(), "image/png")}

    async def fake_get(client, url, limit):
        body, ctype = pages[url]
        return url, body, ctype

    async def fake_voice(name, excerpt):
        assert "desk workers" in excerpt
        return {"tone": "Friendly and plain.", "cta_label": "Save my spot"}

    monkeypatch.setattr(bk, "_get", fake_get)
    monkeypatch.setattr(bk, "_describe_voice", fake_voice)
    out = asyncio.run(bk.extract_from_website("acme.example/"))
    assert out["business_name"] == "Acme Physio"
    assert out["primary_color"] == "#0E7C66" and out["background_color"] == "#F6F3EE"
    assert out["text_color"] == "#1A1A1A"
    assert out["font"] == "DM Sans"
    assert out["tone"] == "Friendly and plain." and out["cta_label"] == "Save my spot"
    assert "Back pain" in out["voice_sample"]
    assert out["logo_png"].startswith(b"\x89PNG")


def test_private_addresses_are_refused():
    for url in ("http://127.0.0.1/", "http://169.254.169.254/latest", "ftp://acme.com", "http://localhost:8001"):
        with pytest.raises(bk.UnsafeURL):
            bk._check_public(url)


def test_logo_is_trimmed_and_shrunk():
    from PIL import Image
    png = bk.normalise_logo(_png(1200, 400))
    img = Image.open(io.BytesIO(png))
    assert img.size == (600, 200)                         # transparent margin gone, longest side 600


# ── cards ────────────────────────────────────────────────────────────────────

BRAND = {"theme": bk.theme({"primary_color": "#0E7C66", "background_color": "#F6F3EE"}), "font": "",
         "logo_hash": "abc", "name": "Acme Physio", "powered_by": True}


def test_card_wears_the_brand_and_powered_by_mark():
    from PIL import Image
    kit = ai.normalize_kit(RAW_KIT)
    spec = tv.card_spec(5, kit, W, BRAND)
    img = Image.open(io.BytesIO(tv.render_card(spec, bk.normalise_logo(_png()))))
    assert img.size == (1080, 1350)
    assert img.getpixel((5, 5)) == pytest.approx((246, 243, 238), abs=3)        # brand background
    # The logo sits top-right.
    assert img.getpixel((1080 - 80 - 20, 105)) == pytest.approx((14, 124, 102), abs=8)
    # Changing the brand changes the card hash, so stored cards are redrawn.
    other = tv.card_spec(5, kit, W, {**BRAND, "logo_hash": "new"})
    assert tv.spec_hash(other) != tv.spec_hash(spec)
    hidden = tv.render_card(tv.card_spec(5, kit, W, {**BRAND, "powered_by": False}))
    shown = tv.render_card(tv.card_spec(5, kit, W, BRAND))
    assert hidden != shown


@pytest.mark.parametrize("touch", [2, 3, 4, 5, 6, 7, 8, 10, 11])
def test_branded_cards_render_for_every_value_touch(touch):
    from PIL import Image
    spec = tv.card_spec(touch, ai.normalize_kit(RAW_KIT), W, {**BRAND, "logo_hash": ""})
    assert Image.open(io.BytesIO(tv.render_card(spec))).size == (1080, 1350)


def test_only_agency_can_hide_the_mark():
    class _Users:
        def __init__(self, user):
            self.user = user

        async def find_one(self, q, proj=None):
            return self.user

    class _Kits:
        async def find_one(self, q, proj=None):
            return {"id": "k1", "owner_id": "u1", "hide_powered_by": True, "primary_color": "#0E7C66"}

    class _FakeDB:
        def __init__(self, user):
            self.users = _Users(user)

        def __getitem__(self, name):
            return _Kits()

    pro = {"id": "u1", "created_at": "2020-01-01T00:00:00+00:00", "billing": {"plan": "pro", "status": "ACTIVE"}}
    agency = {**pro, "billing": {"plan": "agency", "status": "ACTIVE"}}
    assert asyncio.run(bk.resolve(_FakeDB(pro), "u1"))["powered_by"] is True
    assert asyncio.run(bk.resolve(_FakeDB(agency), "u1"))["powered_by"] is False


# ── emails ───────────────────────────────────────────────────────────────────

def test_email_uses_brand_button_logo_and_powered_by():
    brand = {"link_color": "#0E7C66", "button_color": "#0E7C66", "logo_url": "https://api.x/api/brand/k1/logo.png?v=1",
             "website": "https://acme.example", "name": "Acme Physio", "powered_by": True}
    w = {**W, "recording_url": "https://rec.example/1"}
    labels = touch_render.link_labels(w, "Save my spot")
    body = "Hi Riya,\n\nHere's your link:\nhttps://zoom.us/j/123\n\nOr read https://zoom.us/j/123 inline.\n\nAshu"
    html = senders.build_email_html(senders.text_to_email_html(body, None, brand, labels), "s", brand=brand)
    assert 'background:#0E7C66' in html and ">Save my spot</a>" in html          # own-line link -> button
    assert html.count(">Save my spot</a>") == 1                                     # inline one stays a link
    assert 'href="https://acme.example"' in html and "logo.png" in html
    assert "Powered by ShowUp AI" in html
    plain = senders.build_email_html("Hi", "s", brand={**brand, "powered_by": False, "logo_url": ""})
    assert "Powered by" not in plain and "<img" not in plain
    assert labels["https://rec.example/1"] == "Watch the recording"


def test_dispatch_wraps_email_in_the_hosts_brand(monkeypatch):
    got = {}

    async def fake_send(settings, to, subject, html, ics_bytes=None):
        got["html"] = html
        return {"ok": True}

    monkeypatch.setattr(senders, "send_email", fake_send)
    settings = {"_brand": {"link_color": "#0E7C66", "button_color": "#0E7C66", "powered_by": True}}
    asyncio.run(senders.dispatch("email", settings, "r@x.io", None, "s", "Hi\n\nhttps://zoom.us/j/123",
                                 link_labels={"https://zoom.us/j/123": "Join the session"}))
    assert got["html"].startswith("<!DOCTYPE") and ">Join the session</a>" in got["html"]


def test_delivery_brands_cards_and_emails(monkeypatch):
    fake, bucket, sent = _DB(), _Bucket(), []
    fake["brand_kits"].docs.append({"id": "k1", "owner_id": "u1", "primary_color": "#0E7C66",
                                    "business_name": "Acme Physio", "cta_label": "Save my spot"})

    async def fake_dispatch(ch, settings, to_email=None, to_phone=None, subject="", body="", ics_bytes=None,
                            image_url=None, link_labels=None):
        sent.append((ch, settings.get("_brand"), link_labels))
        return {"ok": True}

    async def fake_kit(wid):
        return ai.normalize_kit(RAW_KIT)

    monkeypatch.setattr(routes_delivery, "db", fake)
    monkeypatch.setattr(routes_delivery, "social_images_fs", bucket)
    monkeypatch.setattr(routes_delivery, "send_dispatch", fake_dispatch)
    monkeypatch.setattr(ai, "load_kit", fake_kit)
    copy = {"safe": {"subject": "s", "body": "b"}}
    t = {"id": "t5", "webinar_id": "w1", "owner_id": "u1", "touch_num": 5, "trigger": "x",
         "channels": ["email", "linkedin_personal"], "ai_copy": {"channels": {"email": copy, "linkedin_personal": copy}}}
    res = asyncio.run(routes_delivery._deliver_touch(t, {}, public_backend_url="https://api.x"))
    assert res["ok"]
    brand = sent[0][1]
    assert brand["name"] == "Acme Physio" and brand["theme"]["accent"] == "#0E7C66"
    assert sent[0][2]["https://zoom.us/j/123"] == "Save my spot"
    assert fake["touch_visuals"].docs[0]["hash"]


# ── copy ─────────────────────────────────────────────────────────────────────

def test_voice_brief_goes_into_the_copy_prompt(monkeypatch):
    kit = {"business_name": "Acme Physio", "website": "https://acme.example", "tone": "Warm, plain, a bit cheeky.",
           "voice_sample": "Back pain? Let's sort it.", "cta_label": "Save my spot"}
    brief = bk.build_voice_brief(kit, {"brand_banned_phrases": "synergy", "brand_language": "UK English"})
    assert "Acme Physio" in brief and "Never mention ShowUp AI" in brief and "synergy" in brief
    assert "Back pain? Let's sort it." in brief and "UK English" in brief
    assert bk.build_voice_brief({}, {}) == ""

    prompts = []

    async def fake_llm(prompt, max_tokens=0):
        prompts.append(prompt)
        return '{"safe": {"body": "Tip.\\n\\n{{join_link}}"}, "casual": {"body": "Tip."}}'

    monkeypatch.setattr(ai, "_call_llm", fake_llm)
    asyncio.run(ai.generate_touch_copy(W, 3, ["linkedin"], custom_instructions=brief, kit=ai.normalize_kit(RAW_KIT)))
    assert "BRAND VOICE" in prompts[0] and "a bit cheeky" in prompts[0]
