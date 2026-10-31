"""Offline tests: value touches share real content (tips, case study, poll, checklist)
and carry a card on every channel. No mongod or LLM needed."""
import asyncio
import io
import os
import sys

import pytest

import _growth_helpers  # noqa: F401  (puts backend/ on sys.path)

os.environ.setdefault("JWT_SECRET", "test")
# Other suites stub `database` with a bare namespace at import time; these tests need the real module.
if not hasattr(sys.modules.get("database"), "social_images_fs"):
    sys.modules.pop("database", None)

import ai  # noqa: E402
import routes_delivery  # noqa: E402
import senders  # noqa: E402
import touch_visuals as tv  # noqa: E402

W = {"id": "w1", "owner_id": "u1", "title": "Fix your onboarding", "starts_at": "2026-10-20T12:30:00Z",
     "timezone": "Asia/Kolkata", "join_link": "https://zoom.us/j/123", "speaker": "Ashu Pratap"}

RAW_KIT = {
    "problem": {"hook": "New users sign up and never come back", "example": "Stuck on step one, gone by day two."},
    "insights": [{"heading": "Cut the form to 2 fields", "detail": "Email and password only."},
                 {"heading": "Show one result fast", "detail": "Pre-load sample data."},
                 {"heading": "Email the stuck", "detail": "Only when someone stops twice."}],
    "poll": {"question": "Where do users drop off?", "options": ["Signup", "Setup", "After login"]},
    "story": {"before": "Most trial users never finished setup.", "change": "They showed a sample dashboard first.",
              "after": "More users reached the dashboard on day one.", "lesson": "Show value before work."},
    "agenda": ["Where users quit", "Finding your drop-off", "A day-one email"],
    "myth": {"myth": "Longer tours help — users learn more", "truth": "Tours get skipped. One real task teaches more."},
    "checklist": ["Your signup flow open", "The step you think loses users", "One question"],
    "takeaways": ["Remove one signup field", "Add sample data", "Set up a stuck-user email"],
    "case_study": "A story.", "snippets": ["a", "b"], "one_pager": {"title": "t", "outline": []},
}


def test_normalize_kit_cleans_and_drops_broken_pieces():
    kit = ai.normalize_kit({**RAW_KIT, "poll": {"question": "Q?", "options": ["only one"]}, "story": "not a dict"})
    assert "poll" not in kit and "story" not in kit
    assert "—" not in kit["myth"]["myth"]
    assert ai.normalize_kit("garbage")["snippets"] == []
    # Old kits (snippets only) still give touch 3 something to teach.
    assert ai.normalize_kit({"snippets": ["tip one"]})["insights"][0]["heading"] == "tip one"


def test_each_value_touch_gets_its_own_piece():
    kit = ai.normalize_kit(RAW_KIT)
    briefs = {n: ai.kit_brief(kit, n) for n in range(1, 13)}
    assert "Cut the form to 2 fields" in briefs[3]
    assert "B) Setup" in briefs[4]
    assert "sample dashboard" in briefs[5]
    assert "Tours get skipped" in briefs[7]
    assert "Prep checklist" in briefs[8] and "Your signup flow open" in briefs[8]
    assert briefs[9] == "The one thing to have ready: Your signup flow open"
    assert briefs[10] == briefs[11] and "Remove one signup field" in briefs[10]
    assert briefs[1] == briefs[12] == ""
    assert len({briefs[n] for n in (2, 3, 4, 5, 6, 7, 8)}) == 7      # no two touches repeat
    # The host's edited case study wins.
    lm = {"ai_content": {"case_study": "AI"}, "edited_content": {"case_study": "Mine"}}
    assert ai.kit_brief(ai.kit_from_lead_magnets(lm), 5) == "Case study:\nMine"


def test_copy_prompt_carries_the_content(monkeypatch):
    prompts = []

    async def fake_llm(prompt, max_tokens=0):
        prompts.append(prompt)
        return '{"safe": {"body": "Tip one.\\n\\n{{join_link}}"}, "casual": {"body": "Tip."}}'

    monkeypatch.setattr(ai, "_call_llm", fake_llm)
    out = asyncio.run(ai.generate_touch_copy(W, 3, ["linkedin"], kit=ai.normalize_kit(RAW_KIT)))
    assert "CONTENT TO SHARE IN THIS MESSAGE" in prompts[0] and "Show one result fast" in prompts[0]
    assert "Show one result fast" in out["content"]


@pytest.mark.parametrize("touch", [2, 3, 4, 5, 6, 7, 8, 10, 11])
def test_cards_render_for_every_value_touch(touch):
    from PIL import Image
    spec = tv.card_spec(touch, ai.normalize_kit(RAW_KIT), W)
    img = Image.open(io.BytesIO(tv.render_card(spec)))
    assert img.size == (1080, 1350) and img.format == "JPEG"


def test_card_spec_rules():
    kit = ai.normalize_kit(RAW_KIT)
    assert tv.card_spec(9, kit, W) is None and tv.card_spec(1, kit, W) is None
    assert tv.card_spec(4, {}, W) is None                       # nothing to show, no card
    title, sub = tv.card_spec(3, kit, W)["footer"]
    assert title == "Fix your onboarding" and "Tue 20 Oct, 6:00 PM IST" in sub and "Ashu Pratap" in sub
    assert "Recording" in tv.card_spec(10, kit, W)["footer"][1]
    # A new date changes the card, so it gets re-rendered.
    moved = tv.card_spec(3, kit, {**W, "starts_at": "2026-10-21T12:30:00Z"})
    assert tv.spec_hash(moved) != tv.spec_hash(tv.card_spec(3, kit, W))


def test_email_card_sits_before_the_sign_off():
    html = senders.text_to_email_html("Hi Riya,\n\nTip one.\n\nAshu", "https://api.x/api/touches/t1/visual.jpg?v=1")
    assert html.index("Tip one.") < html.index("<img") < html.index("Ashu")
    assert "<img" not in senders.text_to_email_html("Hi Riya,\n\nTip one.\n\nAshu")


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(upd.get("$set", {}))
                return
        if upsert:
            self.docs.append({**q, **upd.get("$set", {})})

    def find(self, q, proj=None):
        docs = self.docs

        class _Cur:
            async def to_list(self, n):
                return [dict(d) for d in docs]
        return _Cur()


class _DB:
    def __init__(self):
        self._c = {"webinars": _Coll([dict(W)]),
                   "lead_magnets": _Coll([{"webinar_id": "w1", "ai_content": RAW_KIT}]),
                   "registrants": _Coll([{"id": "r1", "webinar_id": "w1", "name": "Riya", "email": "r@x.io",
                                          "phone": "+919999999999"}])}

    def __getitem__(self, name):
        return self._c.setdefault(name, _Coll())

    __getattr__ = __getitem__


class _Bucket:
    def __init__(self):
        self.files = {}

    async def upload_from_stream(self, name, data, metadata=None):
        self.files[name + str(len(self.files))] = data
        return name + str(len(self.files) - 1)

    async def delete(self, fid):
        self.files.pop(fid, None)


def test_delivery_sends_the_card_everywhere(monkeypatch):
    fake, bucket, sent = _DB(), _Bucket(), []

    async def fake_dispatch(ch, settings, to_email=None, to_phone=None, subject="", body="", ics_bytes=None, image_url=None):
        sent.append((ch, image_url))
        return {"ok": True}

    async def fake_kit(wid):
        return ai.normalize_kit(RAW_KIT)

    monkeypatch.setattr(routes_delivery, "db", fake)
    monkeypatch.setattr(routes_delivery, "social_images_fs", bucket)
    monkeypatch.setattr(routes_delivery, "send_dispatch", fake_dispatch)
    monkeypatch.setattr(ai, "load_kit", fake_kit)
    copy = {"safe": {"subject": "s", "body": "b"}}
    t = {"id": "t5", "webinar_id": "w1", "owner_id": "u1", "touch_num": 5, "trigger": "x",
         "channels": ["email", "whatsapp", "linkedin_personal", "facebook_page", "instagram"],
         "ai_copy": {"channels": {c: copy for c in ["email", "whatsapp", "linkedin_personal", "facebook_page", "instagram"]}}}
    res = asyncio.run(routes_delivery._deliver_touch(t, {}, public_backend_url="https://api.x"))
    assert res["ok"] and len(sent) == 5
    assert all(url and url.startswith("https://api.x/api/touches/t5/visual.jpg?v=") for _, url in sent)
    assert len(bucket.files) == 1
    # Sending again reuses the stored card instead of drawing it twice.
    asyncio.run(routes_delivery._deliver_touch(t, {}, public_backend_url="https://api.x"))
    assert len(bucket.files) == 1
    # The one-hour reminder stays a plain short text.
    sent.clear()
    asyncio.run(routes_delivery._deliver_touch({**t, "id": "t9", "touch_num": 9}, {}, public_backend_url="https://api.x"))
    assert all(url is None for ch, url in sent if ch != "instagram")
