"""IndexNow queue: URLs are pinged only once the Netlify build that carries them is live (no server or Mongo)."""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _AnyDB(types.ModuleType):
    def __getattr__(self, name):
        return None


_saved = sys.modules.get("database")
sys.modules["database"] = _AnyDB("database")
try:
    import routes_blog as rb  # noqa: E402
except Exception as e:  # pragma: no cover - app deps missing locally
    import pytest
    pytest.skip(f"routes_blog not importable: {e}", allow_module_level=True)
finally:
    if _saved is not None:
        sys.modules["database"] = _saved

Q = [{"url": "a", "at": "2026-11-18T10:00:00+00:00"}, {"url": "b", "at": "2026-11-18T10:30:00+00:00"}]


def test_waits_for_build_to_deploy():
    assert rb._indexnow_ready(Q, "2026-11-18T10:00:30+00:00", "2026-11-18T10:10:00+00:00", True) == []


def test_sends_urls_changed_before_the_build_only():
    out = rb._indexnow_ready(Q, "2026-11-18T10:00:30+00:00", "2026-11-18T10:20:00+00:00", True)
    assert [e["url"] for e in out] == ["a"]


def test_nothing_without_any_build():
    assert rb._indexnow_ready(Q, None, "2026-11-18T12:00:00+00:00", True) == []


def test_without_build_hook_waits_five_minutes():
    out = rb._indexnow_ready(Q, None, "2026-11-18T10:33:00+00:00", False)
    assert [e["url"] for e in out] == ["a"]
