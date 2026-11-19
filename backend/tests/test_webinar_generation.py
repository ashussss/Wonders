"""Webinar copy generation runs as a tracked background job, reports failures, and heals
itself when a job was cut off. Offline: mongomock + stubbed AI, no mongod or LLM needed."""
import asyncio
import os
import sys
import types

import pytest

import _growth_helpers  # noqa: F401  (puts backend/ on sys.path)

os.environ.setdefault("JWT_SECRET", "test")
if not hasattr(sys.modules.get("database"), "social_images_fs"):
    sys.modules.pop("database", None)

mongomock_motor = pytest.importorskip("mongomock_motor")

import ai  # noqa: E402
import routes_webinars as rw  # noqa: E402

COPY = {"angle": "a", "touch_type": "reminder", "channels": {"email": {"safe": {"subject": "s", "body": "b"},
                                                                      "casual": {"subject": "s", "body": "b"}}}}


def _setup(monkeypatch, copy_fn):
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(rw, "db", db)
    monkeypatch.setattr(rw, "_jobs", {})
    monkeypatch.setattr(rw, "generate_touch_copy", copy_fn)

    async def kit(w):
        return {}
    monkeypatch.setattr(rw, "_ensure_kit", kit)

    async def voice(_db, _uid):
        return ""
    monkeypatch.setattr(rw.brand_kit, "voice_brief", voice)

    async def reason(*a, **k):
        return "why"
    monkeypatch.setattr(rw, "touch_reasoning", reason)
    return db


async def _seed(db, n=3, starts_at="2099-01-01T10:00:00+00:00"):
    await db.webinars.insert_one({"id": "w1", "owner_id": "u1", "title": "T", "starts_at": starts_at})
    await db.touches.insert_many([{"id": f"t{i}", "webinar_id": "w1", "owner_id": "u1", "touch_num": i,
                                   "channels": ["email"], "ai_copy": {}} for i in range(1, n + 1)])


async def _wait(wid="w1"):
    t = rw._jobs.get(wid)
    if t:
        await t


def test_job_fills_every_touch_and_marks_done(monkeypatch):
    async def ok(w, num, channels, **kw):
        return COPY
    db = _setup(monkeypatch, ok)
    monkeypatch.setattr(rw, "_llm_ok_since", lambda started: True)

    async def run():
        await _seed(db)
        assert rw.start_generation("w1") is True
        assert rw.start_generation("w1") is False  # one job per webinar
        await _wait()
        rows = await db.touches.find({}).to_list(10)
        w = await db.webinars.find_one({"id": "w1"})
        return rows, w
    rows, w = asyncio.run(run())
    assert all(r["ai_copy"]["channels"] for r in rows)
    assert w["generation"]["status"] == "done" and w["generation"]["done"] == 3
    assert "w1" not in rw._jobs


def test_failure_is_recorded_with_reason(monkeypatch):
    async def boom(w, num, channels, **kw):
        raise RuntimeError("no provider")
    db = _setup(monkeypatch, boom)
    monkeypatch.setattr(ai, "LLM_STATUS", {"groq": {"last_error": {"at": "z", "model": "m", "error": "401 bad key"}}})

    async def run():
        await _seed(db)
        rw.start_generation("w1")
        await _wait()
        return await db.webinars.find_one({"id": "w1"})
    w = asyncio.run(run())
    assert w["generation"]["status"] == "failed"
    assert "3 touches have no copy" in w["generation"]["error"] and "401 bad key" in w["generation"]["error"]


def test_page_load_heals_touches_left_empty_by_a_restart(monkeypatch):
    calls = []

    async def ok(w, num, channels, **kw):
        calls.append(num)
        return COPY
    db = _setup(monkeypatch, ok)

    async def no_backfill(*a):
        return None
    monkeypatch.setattr(rw, "_backfill_touches", no_backfill)

    async def run():
        await _seed(db)
        # touch 1 already has copy; a dead job left "running" on the doc
        await db.touches.update_one({"id": "t1"}, {"$set": {"ai_copy": COPY}})
        await db.webinars.update_one({"id": "w1"}, {"$set": {"generation": {"status": "running"}}})
        rows = await rw.list_touches("w1", user={"id": "u1"})
        await _wait()
        return rows
    asyncio.run(run())
    assert sorted(calls) == [2, 3]  # only the missing ones


def test_recent_failure_is_not_retried_on_every_page_load():
    from datetime import datetime, timezone
    w = {"id": "w9", "generation": {"status": "failed", "finished_at": datetime.now(timezone.utc).isoformat()}}
    assert rw._should_heal(w, [{"ai_copy": {}}]) is False
    w["generation"]["finished_at"] = "2020-01-01T00:00:00+00:00"
    assert rw._should_heal(w, [{"ai_copy": {}}]) is True
    assert rw._should_heal(w, [{"ai_copy": COPY}]) is False


def test_regenerate_all_returns_at_once(monkeypatch):
    async def slow(w, num, channels, **kw):
        await asyncio.sleep(0.2)
        return COPY
    db = _setup(monkeypatch, slow)

    async def run():
        await _seed(db)
        r = await rw.regen_all_touches("w1", user={"id": "u1"})
        running = rw.generation_running("w1")
        await _wait()
        return r, running
    r, running = asyncio.run(run())
    assert r["started"] is True and r["total"] == 3 and running


def test_startup_resumes_only_upcoming_webinars(monkeypatch):
    async def ok(w, num, channels, **kw):
        return COPY
    db = _setup(monkeypatch, ok)

    async def run():
        await _seed(db)
        await db.webinars.insert_one({"id": "old", "owner_id": "u1", "starts_at": "2020-01-01T00:00:00+00:00"})
        await db.touches.insert_one({"id": "o1", "webinar_id": "old", "owner_id": "u1", "touch_num": 1, "ai_copy": {}})
        n = await rw.resume_stuck_generations()
        await _wait()
        return n
    assert asyncio.run(run()) == 1


# ── _call_llm: the providers' "thinking" models need room, JSON mode and fallbacks ──

class _GroqRec:
    def __init__(self, fail_models=(), text='{"ok": true}'):
        self.kws, self.fail_models, self.text = [], set(fail_models), text
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.kws.append(kw)
        if kw["model"] in self.fail_models:
            raise Exception("Error code: 404 - model_not_found: The model does not exist")
        msg = types.SimpleNamespace(content=self.text)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg, finish_reason="stop")])


def _llm(monkeypatch, groq, gemini=None):
    monkeypatch.setattr(ai, "gemini_client", gemini)
    monkeypatch.setattr(ai, "groq_client", groq)
    monkeypatch.setattr(ai, "_llm_sem", None)
    monkeypatch.setattr(ai, "_gemini_blocked_until", 0.0)
    monkeypatch.setattr(ai, "_dead_models", set())
    monkeypatch.setattr(ai, "GROQ_MODELS", ["openai/gpt-oss-20b", "openai/gpt-oss-120b"])
    monkeypatch.setattr(ai, "GEMINI_MODELS", ["gem-a", "gem-b"])


def test_groq_gets_room_low_reasoning_and_json_mode(monkeypatch):
    g = _GroqRec()
    _llm(monkeypatch, g)
    assert asyncio.run(ai._call_llm("p", max_tokens=1400)) == '{"ok": true}'
    kw = g.kws[0]
    assert kw["max_tokens"] >= 8000
    assert kw["extra_body"] == {"reasoning_effort": "low"}
    assert kw["response_format"] == {"type": "json_object"}


def test_retired_groq_model_falls_through_to_next(monkeypatch):
    g = _GroqRec(fail_models={"openai/gpt-oss-20b"})
    _llm(monkeypatch, g)
    assert asyncio.run(ai._call_llm("p")) == '{"ok": true}'
    assert "openai/gpt-oss-20b" in ai._dead_models
    g.kws.clear()
    asyncio.run(ai._call_llm("p"))
    assert [k["model"] for k in g.kws] == ["openai/gpt-oss-120b"]  # retired model not retried


def test_gemini_empty_text_and_retired_model_fall_back(monkeypatch):
    calls = []

    def gen(model, contents, config):
        calls.append(model)
        if model == "gem-a":
            raise Exception("404 NOT_FOUND. models/gem-a is not found for API version v1beta")
        return types.SimpleNamespace(text=None, candidates=[types.SimpleNamespace(finish_reason="MAX_TOKENS")])
    gem = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=gen))
    g = _GroqRec()
    _llm(monkeypatch, g, gem)
    assert asyncio.run(ai._call_llm("p")) == '{"ok": true}'
    assert calls[0] == "gem-a" and "gem-a" in ai._dead_models
    assert "MAX_TOKENS" in ai.LLM_STATUS["gemini"]["last_error"]["error"]


def test_job_running_elsewhere_is_left_alone_until_stale():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    w = {"id": "w8", "generation": {"status": "running", "started_at": now.isoformat()}}
    assert rw._should_heal(w, [{"ai_copy": {}}]) is False  # another worker is writing it
    w["generation"]["started_at"] = (now - timedelta(minutes=20)).isoformat()
    assert rw._should_heal(w, [{"ai_copy": {}}]) is True   # died in a restart


def test_gemini_that_rejects_json_mode_is_asked_plainly_after(monkeypatch):
    seen = []

    def gen(model, contents, config):
        lean = config.response_mime_type == "application/json"
        seen.append(lean)
        if lean:
            raise Exception("400 INVALID_ARGUMENT: thinking_level is not supported")
        return types.SimpleNamespace(text='{"ok": true}')
    gem = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=gen))
    _llm(monkeypatch, None, gem)
    monkeypatch.setattr(ai, "_no_lean", set())
    assert asyncio.run(ai._call_llm("p")) == '{"ok": true}'
    assert asyncio.run(ai._call_llm("p")) == '{"ok": true}'
    assert seen == [True, False, False]  # second call skips the rejected settings
