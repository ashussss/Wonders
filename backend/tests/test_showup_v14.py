"""ShowUpAI v1.4 backend tests — Circle.so post-to-feed (Admin API v2),
Buzz.ai custom-endpoint provider for email+LinkedIn, per-channel provider toggles,
and Circle webhook dual payload shape (legacy + community_member_created)."""
import os
import sys
import uuid
import requests
import pytest
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://touch-sequence.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "showup_db")
TEST_EMAIL = "test@showup.ai"
TEST_PASSWORD = "test1234"
ENC_PREFIX = "enc::"
MASK = "•" * 8


@pytest.fixture(scope="session")
def mongo_db():
    c = MongoClient(MONGO_URL); yield c[DB_NAME]; c.close()


@pytest.fixture(scope="session")
def auth_token():
    r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    if r.status_code != 200:
        requests.post(f"{API}/auth/register", json={"name": "T", "email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=15)
        r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def hdrs(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="session")
def user_id(mongo_db):
    u = mongo_db.users.find_one({"email": TEST_EMAIL}); assert u
    yield u["id"]
    # Cleanup v1.4 secret/config fields after session
    mongo_db.settings.update_one({"owner_id": u["id"]}, {"$unset": {
        "circle_api_key": "", "circle_space_id": "",
        "buzzai_api_key": "", "buzzai_email_endpoint": "", "buzzai_linkedin_endpoint": "",
        "buzzai_auth_header_name": "", "buzzai_auth_header_prefix": "",
        "linkedin_provider": "", "email_provider": "",
    }})


@pytest.fixture
def webinar(hdrs):
    p = {"title": "TEST_v14", "description": "v14", "speaker": "s", "target_audience": "a",
         "starts_at": "2030-12-01T10:00:00+00:00", "timezone": "UTC", "join_link": "https://e.com/j"}
    r = requests.post(f"{API}/webinars", json=p, headers=hdrs, timeout=30); assert r.status_code == 200
    wid = r.json()["id"]; yield wid
    requests.delete(f"{API}/webinars/{wid}", headers=hdrs, timeout=15)


# ---------- Circle test-send ----------
class TestCircleTestSend:
    def test_missing_api_key(self, hdrs, mongo_db, user_id):
        mongo_db.settings.update_one({"owner_id": user_id},
            {"$unset": {"circle_api_key": "", "circle_space_id": ""}})
        r = requests.post(f"{API}/test-send/circle", json={"subject": "t", "body": "b"}, headers=hdrs, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is False
        assert d.get("provider") == "circle"
        assert "missing circle_api_key" in (d.get("detail") or "").lower()

    def test_missing_space_id(self, hdrs):
        requests.patch(f"{API}/settings", json={"circle_api_key": "fake_circle_key_xyz"}, headers=hdrs, timeout=15)
        r = requests.post(f"{API}/test-send/circle", json={"subject": "t", "body": "b"}, headers=hdrs, timeout=20)
        d = r.json()
        assert d.get("ok") is False
        assert "missing circle_space_id" in (d.get("detail") or "").lower()

    def test_fake_creds_graceful_upstream_error(self, hdrs):
        requests.patch(f"{API}/settings", json={
            "circle_api_key": "fake_circle_key_xyz", "circle_space_id": "12345"
        }, headers=hdrs, timeout=15)
        r = requests.post(f"{API}/test-send/circle", json={"subject": "t", "body": "Line1\nLine2"},
                          headers=hdrs, timeout=30)
        assert r.status_code == 200  # graceful, not crash
        d = r.json()
        assert d.get("ok") is False
        # Detail should reference an upstream HTTP error code (401/403/404), not a 500 crash
        detail = (d.get("detail") or "")
        assert any(code in detail for code in ("401", "403", "404", "400")), f"expected upstream HTTP code, got {detail!r}"


# ---------- Buzz.ai routing ----------
class TestBuzzaiEmail:
    def test_missing_api_key(self, hdrs, mongo_db, user_id):
        mongo_db.settings.update_one({"owner_id": user_id},
            {"$unset": {"buzzai_api_key": "", "buzzai_email_endpoint": ""}})
        requests.patch(f"{API}/settings", json={"email_provider": "BuzzAI"}, headers=hdrs, timeout=15)
        r = requests.post(f"{API}/test-send/email", json={"to_email": "x@y.com", "subject": "s", "body": "b"},
                          headers=hdrs, timeout=20)
        d = r.json()
        assert d.get("provider") == "buzzai_email"
        assert d.get("ok") is False
        assert "missing buzzai_api_key" in (d.get("detail") or "").lower()

    def test_with_key_no_endpoint(self, hdrs, mongo_db, user_id):
        mongo_db.settings.update_one({"owner_id": user_id},
            {"$unset": {"buzzai_email_endpoint": ""}})
        requests.patch(f"{API}/settings", json={
            "email_provider": "BuzzAI", "buzzai_api_key": "buzz_key_abcd"
        }, headers=hdrs, timeout=15)
        r = requests.post(f"{API}/test-send/email", json={"to_email": "x@y.com", "subject": "s", "body": "b"},
                          headers=hdrs, timeout=20)
        d = r.json()
        assert d.get("provider") == "buzzai_email"
        assert "missing buzzai_email_endpoint" in (d.get("detail") or "").lower()

    def test_unresolvable_endpoint_graceful(self, hdrs):
        requests.patch(f"{API}/settings", json={
            "email_provider": "BuzzAI",
            "buzzai_api_key": "buzz_key_abcd",
            "buzzai_email_endpoint": "http://this-host-does-not-resolve-xyz12345.invalid/send"
        }, headers=hdrs, timeout=15)
        r = requests.post(f"{API}/test-send/email",
                          json={"to_email": "x@y.com", "subject": "s", "body": "b"},
                          headers=hdrs, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is False
        assert d.get("provider") == "buzzai_email"
        # Should not be missing-key, should be a DNS/connect error string
        detail = (d.get("detail") or "").lower()
        assert "missing" not in detail
        assert any(t in detail for t in ("resolve", "name", "connect", "dns", "host", "getaddrinfo", "nodename"))


class TestBuzzaiLinkedIn:
    def test_routing_to_buzz_when_provider_buzzai(self, hdrs, mongo_db, user_id):
        mongo_db.settings.update_one({"owner_id": user_id},
            {"$unset": {"buzzai_linkedin_endpoint": ""}})
        requests.patch(f"{API}/settings", json={
            "linkedin_provider": "buzzai", "buzzai_api_key": "buzz_key_abcd"
        }, headers=hdrs, timeout=15)
        r = requests.post(f"{API}/test-send/linkedin", json={"subject": "s", "body": "b"},
                          headers=hdrs, timeout=20)
        d = r.json()
        assert d.get("provider") == "buzzai_linkedin"
        assert "missing buzzai_linkedin_endpoint" in (d.get("detail") or "").lower()

    def test_routing_to_marketing_api_default(self, hdrs, mongo_db, user_id):
        # unset/marketing_api → goes to LinkedIn UGC missing-key
        mongo_db.settings.update_one({"owner_id": user_id},
            {"$unset": {"linkedin_marketing_token": "", "linkedin_org_urn": ""}})
        requests.patch(f"{API}/settings", json={"linkedin_provider": "marketing_api"},
                       headers=hdrs, timeout=15)
        r = requests.post(f"{API}/test-send/linkedin", json={"subject": "s", "body": "b"},
                          headers=hdrs, timeout=20)
        d = r.json()
        assert d.get("provider") == "linkedin"
        assert "missing" in (d.get("detail") or "").lower()


# ---------- Buzz.ai api_key encryption ----------
class TestBuzzaiKeyEncryption:
    def test_encrypted_at_rest_masked_on_get(self, hdrs, mongo_db, user_id):
        raw = "buzz-secret-1234"
        r = requests.patch(f"{API}/settings", json={"buzzai_api_key": raw}, headers=hdrs, timeout=15)
        assert r.status_code == 200
        s = requests.get(f"{API}/settings", headers=hdrs, timeout=15).json()
        assert s.get("buzzai_api_key") == MASK + "1234"
        doc = mongo_db.settings.find_one({"owner_id": user_id})
        v = doc.get("buzzai_api_key", "")
        assert v.startswith(ENC_PREFIX), f"buzzai_api_key not enc-prefixed: {v[:30]!r}"

    def test_secret_fields_includes_buzzai(self):
        from crypto_utils import SECRET_FIELDS
        assert "buzzai_api_key" in SECRET_FIELDS


# ---------- Buzz.ai header customization (code-path inspection) ----------
class TestBuzzaiAuthHeaderCustomization:
    def test_header_name_and_prefix_respected(self):
        """Inspect senders.send_buzzai code to verify header customization."""
        import inspect
        from senders import send_buzzai
        src = inspect.getsource(send_buzzai)
        assert 'buzzai_auth_header_name' in src
        assert 'buzzai_auth_header_prefix' in src
        # When header_prefix is None default 'Bearer ' is used; empty string '' is honoured
        assert 'header_prefix is None' in src or "header_prefix = " in src

    def test_tiptap_doc_shape(self):
        from senders import _circle_tiptap_body
        body = _circle_tiptap_body("hello\nworld")
        assert body["body"]["type"] == "doc"
        assert body["body"]["content"][0]["type"] == "paragraph"


# ---------- Circle webhook dual payload shape ----------
class TestCircleWebhookShapes:
    def test_official_community_member_shape(self, webinar):
        email = f"official_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/webinars/{webinar}/webhooks/circle",
                          json={"community_member": {"email": email, "name": "Official"}}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        # second post → dedup
        r2 = requests.post(f"{API}/webinars/{webinar}/webhooks/circle",
                           json={"community_member": {"email": email, "name": "Official"}}, timeout=15)
        assert r2.json().get("deduped") is True

    def test_registrant_has_source_circle_and_community_joined(self, hdrs, webinar):
        email = f"src_{uuid.uuid4().hex[:6]}@example.com"
        requests.post(f"{API}/webinars/{webinar}/webhooks/circle",
                      json={"community_member": {"email": email, "name": "Src"}}, timeout=15)
        regs = requests.get(f"{API}/webinars/{webinar}/registrants", headers=hdrs, timeout=15).json()
        match = [r for r in regs if r["email"] == email]
        assert match, f"registrant not created: {regs}"
        assert match[0].get("source") == "circle"
        assert match[0].get("community_joined") is True

    def test_legacy_flat_shape_backcompat(self, webinar):
        email = f"flat_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/webinars/{webinar}/webhooks/circle",
                          json={"email": email, "name": "Flat"}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True


# ---------- Circle spaces helper ----------
class TestCircleSpacesHelper:
    def test_missing_api_key(self, hdrs, mongo_db, user_id):
        mongo_db.settings.update_one({"owner_id": user_id}, {"$unset": {"circle_api_key": ""}})
        r = requests.get(f"{API}/circle/spaces", headers=hdrs, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("spaces") == []
        assert "missing circle_api_key" in (d.get("error") or "").lower()

    def test_fake_key_returns_upstream_error_not_500(self, hdrs):
        requests.patch(f"{API}/settings", json={"circle_api_key": "fake_circle_xyz"}, headers=hdrs, timeout=15)
        r = requests.get(f"{API}/circle/spaces", headers=hdrs, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("spaces") == []
        err = (d.get("error") or "").lower()
        assert "401" in err or "unauthor" in err or "403" in err


# ---------- Email provider dropdown options (model accepts BuzzAI) ----------
class TestEmailProviderOptions:
    def test_settings_accepts_buzzai(self, hdrs):
        for p in ("Brevo", "Mailchimp", "SendGrid", "BuzzAI"):
            r = requests.patch(f"{API}/settings", json={"email_provider": p}, headers=hdrs, timeout=15)
            assert r.status_code == 200, f"failed for {p}: {r.text}"


# ---------- Per-touch channel firing regression ----------
class TestPerTouchChannelFiring:
    def test_circle_channel_missing_key_returns_log_not_500(self, hdrs, webinar, mongo_db, user_id):
        mongo_db.settings.update_one({"owner_id": user_id},
            {"$unset": {"circle_api_key": "", "circle_space_id": ""}})
        # add a registrant so audience isn't empty (not used by circle channel but safe)
        requests.post(f"{API}/webinars/{webinar}/register",
                      json={"name": "A", "email": f"a_{uuid.uuid4().hex[:6]}@e.com"}, timeout=15)
        # take touch 1, set channels=['circle'], approve, send
        touches = requests.get(f"{API}/webinars/{webinar}/touches", headers=hdrs, timeout=15).json()
        t = touches[0]
        requests.patch(f"{API}/touches/{t['id']}",
                       json={"channels": ["circle"], "approval_status": "approved"},
                       headers=hdrs, timeout=15)
        r = requests.post(f"{API}/touches/{t['id']}/send-now", headers=hdrs, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is False
        log = d.get("log") or []
        circle_logs = [x for x in log if x.get("channel") == "circle"]
        assert circle_logs
        assert "missing circle" in (circle_logs[0].get("detail") or "").lower()

    def test_linkedin_buzzai_channel_missing_endpoint(self, hdrs, webinar, mongo_db, user_id):
        mongo_db.settings.update_one({"owner_id": user_id},
            {"$unset": {"buzzai_linkedin_endpoint": ""}})
        requests.patch(f"{API}/settings", json={
            "linkedin_provider": "buzzai", "buzzai_api_key": "buzz_k"
        }, headers=hdrs, timeout=15)
        requests.post(f"{API}/webinars/{webinar}/register",
                      json={"name": "B", "email": f"b_{uuid.uuid4().hex[:6]}@e.com"}, timeout=15)
        touches = requests.get(f"{API}/webinars/{webinar}/touches", headers=hdrs, timeout=15).json()
        t = touches[0]
        requests.patch(f"{API}/touches/{t['id']}",
                       json={"channels": ["linkedin"], "approval_status": "approved"},
                       headers=hdrs, timeout=15)
        r = requests.post(f"{API}/touches/{t['id']}/send-now", headers=hdrs, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        log = d.get("log") or []
        li_logs = [x for x in log if x.get("channel") == "linkedin"]
        assert li_logs
        assert "missing buzzai_linkedin_endpoint" in (li_logs[0].get("detail") or "").lower()


# ---------- AGENTS.md ----------
class TestAgentsDoc:
    def test_agents_md_exists_and_valid(self):
        p = "/app/AGENTS.md"
        assert os.path.exists(p)
        with open(p) as f:
            content = f.read()
        assert len(content) > 200
        # well-formed markdown — should have at least one header
        assert any(line.startswith("#") for line in content.splitlines())
