"""_call_llm: shared concurrency cap, Gemini cooldown after a rate limit, timeout fallback."""
import asyncio
import threading
import time
import types

import ai


class _GeminiModels:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, 0

    def generate_content(self, **kw):
        self.calls += 1
        return self.behaviour(self.calls)


class _Groq:
    def __init__(self):
        self.calls, self.active, self.peak = 0, 0, 0
        self.lock = threading.Lock()
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, **kw):
        with self.lock:
            self.calls += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(0.05)
        with self.lock:
            self.active -= 1
        msg = types.SimpleNamespace(content='{"from": "groq"}')
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


def _setup(monkeypatch, gemini_behaviour, concurrency=6, timeout=45):
    models = _GeminiModels(gemini_behaviour) if gemini_behaviour else None
    monkeypatch.setattr(ai, "gemini_client", types.SimpleNamespace(models=models) if models else None)
    groq = _Groq()
    monkeypatch.setattr(ai, "groq_client", groq)
    monkeypatch.setattr(ai, "LLM_CONCURRENCY", concurrency)
    monkeypatch.setattr(ai, "LLM_TIMEOUT", timeout)
    monkeypatch.setattr(ai, "_llm_sem", None)
    monkeypatch.setattr(ai, "_gemini_blocked_until", 0.0)
    return models, groq


def test_rate_limit_sends_later_calls_straight_to_groq(monkeypatch):
    def limited(n):
        raise Exception("429 RESOURCE_EXHAUSTED")
    models, groq = _setup(monkeypatch, limited)

    async def run():
        return [await ai._call_llm("p") for _ in range(5)]
    out = asyncio.run(run())
    assert all(o == '{"from": "groq"}' for o in out)
    assert models.calls == 1      # one 429, then Gemini is skipped during the cooldown
    assert groq.calls == 5


def test_concurrency_is_capped(monkeypatch):
    _, groq = _setup(monkeypatch, None, concurrency=3)

    async def run():
        await asyncio.gather(*[ai._call_llm("p") for _ in range(12)])
    asyncio.run(run())
    assert groq.calls == 12
    assert groq.peak <= 3


def test_hung_gemini_falls_back_to_groq(monkeypatch):
    def hang(n):
        time.sleep(0.5)
        return types.SimpleNamespace(text='{"from": "gemini"}')
    _, groq = _setup(monkeypatch, hang, timeout=0.1)
    out = asyncio.run(ai._call_llm("p"))
    assert out == '{"from": "groq"}'


def test_gemini_ok(monkeypatch):
    _, groq = _setup(monkeypatch, lambda n: types.SimpleNamespace(text='```json\n{"a": 1}\n```'))
    assert asyncio.run(ai._call_llm("p")) == '{"a": 1}'
    assert groq.calls == 0
