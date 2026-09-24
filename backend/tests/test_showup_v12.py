"""ShowUpAI v1.2 backend tests — Nano Banana social image, email provider routing (Mailchimp/SendGrid/Brevo),
rate limiting, and refactor sanity."""
import os
import time
import uuid
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://touch-sequence.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
LOCAL = "http://localhost:8001/api"

TEST_EMAIL = "test@showup.ai"
TEST_PASSWORD = "test1234"


@pytest.fixture(scope="session")
def auth_token():
    r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    if r.status_code != 200:
        # try to register
        requests.post(f"{API}/auth/register", json={"name": "Test", "email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=15)
        r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def hdrs(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="session")
def webinar(hdrs):
    payload = {
        "title": "TEST_v12_NanoBanana",
        "description": "v1.2 test webinar.",
        "speaker": "Spk",
        "target_audience": "UK Bursars",
        "starts_at": "2030-08-01T10:00:00+00:00",
        "timezone": "Europe/London",
        "join_link": "https://example.com/join",
    }
    r = requests.post(f"{API}/webinars", json=payload, headers=hdrs, timeout=30)
    assert r.status_code == 200, r.text
    wid = r.json()["id"]
    yield wid
    requests.delete(f"{API}/webinars/{wid}", headers=hdrs, timeout=15)


# ---------- Refactor sanity ----------
class TestRefactorSanity:
    def test_root_endpoint(self):
        r = requests.get(f"{API}/", timeout=10)
        assert r.status_code == 200
        assert r.json() == {"app": "ShowUpAI", "ok": True}

    def test_auth_me(self, hdrs):
        r = requests.get(f"{API}/auth/me", headers=hdrs, timeout=10)
        assert r.status_code == 200
        assert r.json()["email"] == TEST_EMAIL

    def test_webinar_list(self, hdrs):
        r = requests.get(f"{API}/webinars", headers=hdrs, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_settings_get(self, hdrs):
        r = requests.get(f"{API}/settings", headers=hdrs, timeout=10)
        assert r.status_code == 200

    def test_analytics(self, hdrs):
        r = requests.get(f"{API}/analytics/overview", headers=hdrs, timeout=15)
        assert r.status_code == 200

    def test_approval_queue(self, hdrs):
        r = requests.get(f"{API}/approval-queue", headers=hdrs, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Nano Banana social image ----------
class TestSocialImage:
    def test_social_image_404_when_not_generated(self, webinar):
        # Different webinar with no image
        r = requests.get(f"{API}/webinars/{uuid.uuid4()}/social-image.png", timeout=15)
        assert r.status_code == 404

    def test_generate_social_image(self, hdrs, webinar):
        r = requests.post(f"{API}/webinars/{webinar}/social-image/generate", headers=hdrs, timeout=90)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:300]}"
        data = r.json()
        assert data["ok"] is True
        assert data["bytes"] > 0
        assert data["mime"] in ("image/png", "image/jpeg")
        assert data["url"].endswith("/social-image.png")

    def test_public_image_fetch(self, webinar):
        # No auth header — must be publicly accessible
        r = requests.get(f"{API}/webinars/{webinar}/social-image.png", timeout=20)
        assert r.status_code == 200, f"Public image fetch failed: {r.status_code}"
        ct = r.headers.get("content-type", "")
        assert ct.startswith("image/"), f"Bad content-type: {ct}"
        assert len(r.content) > 100


# ---------- Email provider routing ----------
class TestEmailProviderRouting:
    @pytest.fixture(autouse=True)
    def reset_settings(self, hdrs):
        # Clear provider-specific keys before each test (direct mongo for sender_email unset)
        from pymongo import MongoClient
        mongo = MongoClient(os.environ.get("MONGO_URL"))
        sdb = mongo[os.environ.get("DB_NAME")]
        u = sdb.users.find_one({"email": TEST_EMAIL})
        if u:
            sdb.settings.update_one(
                {"owner_id": u["id"]},
                {"$unset": {"brevo_sender_email": "", "mailchimp_sender_email": "", "sendgrid_sender_email": ""},
                 "$set": {"email_provider": "Brevo", "brevo_api_key": "",
                          "mailchimp_api_key": "", "sendgrid_api_key": ""}})
        yield
        u = sdb.users.find_one({"email": TEST_EMAIL})
        if u:
            sdb.settings.update_one(
                {"owner_id": u["id"]},
                {"$unset": {"brevo_sender_email": "", "mailchimp_sender_email": "", "sendgrid_sender_email": ""},
                 "$set": {"email_provider": "Brevo", "mailchimp_api_key": "", "sendgrid_api_key": ""}})
        mongo.close()

    def test_brevo_default(self, hdrs):
        r = requests.post(f"{API}/test-send/email", json={"to_email": "x@y.com"}, headers=hdrs, timeout=15)
        assert r.status_code == 200
        body = r.json()
        # provider field OR detail mentions brevo
        assert (body.get("provider") == "brevo") or ("brevo" in (body.get("detail") or "").lower())
        assert body["ok"] is False

    def test_sendgrid_provider(self, hdrs):
        requests.patch(f"{API}/settings", json={
            "email_provider": "SendGrid", "sendgrid_api_key": "fake-key",
        }, headers=hdrs, timeout=10)
        r = requests.post(f"{API}/test-send/email", json={"to_email": "x@y.com"}, headers=hdrs, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("provider") == "sendgrid"
        # missing sender field
        assert "sendgrid_sender_email" in (body.get("detail") or "")
        assert body["ok"] is False

    def test_mailchimp_provider(self, hdrs):
        requests.patch(f"{API}/settings", json={
            "email_provider": "Mailchimp", "mailchimp_api_key": "fake-key",
        }, headers=hdrs, timeout=10)
        r = requests.post(f"{API}/test-send/email", json={"to_email": "x@y.com"}, headers=hdrs, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("provider") == "mailchimp"
        assert "mailchimp_sender_email" in (body.get("detail") or "")
        assert body["ok"] is False

    def test_settings_persists_new_fields(self, hdrs):
        requests.patch(f"{API}/settings", json={
            "mailchimp_sender_email": "mc@example.com",
            "sendgrid_sender_email": "sg@example.com",
        }, headers=hdrs, timeout=10)
        r = requests.get(f"{API}/settings", headers=hdrs, timeout=10)
        s = r.json()
        assert s.get("mailchimp_sender_email") == "mc@example.com"
        assert s.get("sendgrid_sender_email") == "sg@example.com"


# ---------- Rate limiting (local backend only — Cloudflare rewrites X-Forwarded-For) ----------
class TestRateLimiting:
    def test_register_rate_limit_local(self, hdrs):
        # Create webinar via local
        wpayload = {"title": "TEST_rl", "description": "x", "speaker": "x", "target_audience": "x",
                    "starts_at": "2030-09-01T10:00:00+00:00", "timezone": "UTC", "join_link": "https://e.com"}
        r = requests.post(f"{LOCAL}/webinars", json=wpayload, headers=hdrs, timeout=15)
        assert r.status_code == 200
        wid = r.json()["id"]
        try:
            statuses = []
            for i in range(12):
                rr = requests.post(f"{LOCAL}/webinars/{wid}/register",
                                   json={"name": f"u{i}", "email": f"rl_{i}_{uuid.uuid4().hex[:6]}@e.com"},
                                   timeout=8)
                statuses.append(rr.status_code)
            assert 429 in statuses, f"Expected 429 in {statuses}"
        finally:
            requests.delete(f"{LOCAL}/webinars/{wid}", headers=hdrs, timeout=10)

    def test_circle_webhook_not_rate_limited_at_10(self, hdrs):
        wpayload = {"title": "TEST_rl_circle", "description": "x", "speaker": "x", "target_audience": "x",
                    "starts_at": "2030-10-01T10:00:00+00:00", "timezone": "UTC", "join_link": "https://e.com"}
        r = requests.post(f"{LOCAL}/webinars", json=wpayload, headers=hdrs, timeout=15)
        assert r.status_code == 200
        wid = r.json()["id"]
        try:
            statuses = []
            for i in range(11):
                rr = requests.post(f"{LOCAL}/webinars/{wid}/webhooks/circle",
                                   json={"email": f"cw_{i}_{uuid.uuid4().hex[:6]}@e.com", "name": "x"},
                                   timeout=8)
                statuses.append(rr.status_code)
            assert 429 not in statuses, f"Circle webhook should not 429 at 11/min: {statuses}"
        finally:
            requests.delete(f"{LOCAL}/webinars/{wid}", headers=hdrs, timeout=10)


# ---------- Core regression ----------
class TestCoreRegression:
    def test_public_register(self, webinar):
        r = requests.post(f"{API}/webinars/{webinar}/register",
                          json={"name": "Reg", "email": f"reg_{uuid.uuid4().hex[:6]}@e.com"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_touches_list(self, hdrs, webinar):
        r = requests.get(f"{API}/webinars/{webinar}/touches", headers=hdrs, timeout=15)
        assert r.status_code == 200
        touches = r.json()
        assert len(touches) >= 5

    def test_ics_download(self, webinar):
        r = requests.get(f"{API}/webinars/{webinar}/calendar.ics", timeout=15)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/calendar")

    def test_pdf_download(self, webinar):
        r = requests.get(f"{API}/webinars/{webinar}/one-pager.pdf", timeout=20)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
