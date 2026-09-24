"""ShowUpAI v1.1 backend API tests — ICS/PDF, test-send guardrails, circle sync, linkedin events,
send-now, community analytics, settings new fields."""
import os
import time
import uuid
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://touch-sequence.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

TEST_EMAIL = "test@showup.ai"
TEST_PASSWORD = "test1234"


@pytest.fixture(scope="session")
def auth_token():
    r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def hdrs(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="session")
def webinar(hdrs):
    payload = {
        "title": "TEST_v11_Webinar",
        "description": "v1.1 test webinar.",
        "speaker": "Spk",
        "target_audience": "Bursars",
        "starts_at": "2030-07-01T10:00:00+00:00",
        "timezone": "Europe/London",
        "join_link": "https://example.com/join",
    }
    r = requests.post(f"{API}/webinars", json=payload, headers=hdrs, timeout=30)
    assert r.status_code == 200, r.text
    wid = r.json()["id"]
    yield wid
    requests.delete(f"{API}/webinars/{wid}", headers=hdrs, timeout=15)


@pytest.fixture(scope="session")
def cleanup_settings(hdrs):
    """Make sure no real Brevo/Twilio/etc keys are set in test user's settings (v1 left TEST_brevo)."""
    requests.patch(f"{API}/settings", json={
        "brevo_api_key": "", "brevo_sender_email": None, "brevo_sender_name": "",
        "meta_graph_token": "", "meta_page_id": "", "meta_ig_user_id": "",
        "twilio_sid": "", "twilio_auth_token": "", "twilio_whatsapp_from": "", "twilio_sms_from": "",
        "linkedin_marketing_token": "", "linkedin_events_token": "", "linkedin_org_urn": "",
        "mailchimp_api_key": "", "sendgrid_api_key": "", "twilio_token": "",
        "circle_api_key": "",
    }, headers=hdrs, timeout=15)
    yield


# ---------- ICS calendar ----------
class TestICS:
    def test_ics_download(self, webinar):
        r = requests.get(f"{API}/webinars/{webinar}/calendar.ics", timeout=15)
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "text/calendar" in ct, ct
        body = r.text
        assert "BEGIN:VCALENDAR" in body
        assert "BEGIN:VEVENT" in body
        assert "DTSTART" in body
        assert "DTEND" in body
        assert "SUMMARY" in body
        assert "TEST_v11_Webinar" in body
        assert f"showup-{webinar}@showupai.live" in body
        assert len(body.encode()) > 200


# ---------- PDF one-pager ----------
class TestPDF:
    def test_pdf_initial(self, webinar):
        r = requests.get(f"{API}/webinars/{webinar}/one-pager.pdf", timeout=20)
        assert r.status_code == 200, r.text
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 1000

    def test_pdf_after_regenerate(self, webinar, hdrs):
        r0 = requests.post(f"{API}/webinars/{webinar}/lead-magnets/regenerate", headers=hdrs, timeout=20)
        assert r0.status_code in (200, 202)
        time.sleep(30)
        r = requests.get(f"{API}/webinars/{webinar}/one-pager.pdf", timeout=20)
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 1000


# ---------- Test-send guardrails (no keys -> ok:false with detail) ----------
class TestSendGuardrails:
    def test_email_missing_key(self, hdrs, cleanup_settings):
        r = requests.post(f"{API}/test-send/email", headers=hdrs,
                          json={"subject": "x", "body": "y"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is False
        assert d.get("provider") == "brevo"
        assert "Missing" in (d.get("detail") or "") and "brevo_api_key" in (d.get("detail") or "")

    def test_facebook_missing(self, hdrs, cleanup_settings):
        r = requests.post(f"{API}/test-send/facebook", headers=hdrs, json={"body": "y"}, timeout=20)
        d = r.json()
        assert d["ok"] is False
        assert d["provider"] == "facebook"
        assert "Missing" in d["detail"]

    def test_whatsapp_missing(self, hdrs, cleanup_settings):
        r = requests.post(f"{API}/test-send/whatsapp", headers=hdrs,
                          json={"body": "y", "to_phone": "+15555550100"}, timeout=20)
        d = r.json()
        assert d["ok"] is False
        assert d["provider"] in ("whatsapp", "twilio")
        assert "Missing" in d["detail"]

    def test_linkedin_missing(self, hdrs, cleanup_settings):
        r = requests.post(f"{API}/test-send/linkedin", headers=hdrs, json={"body": "y"}, timeout=20)
        d = r.json()
        assert d["ok"] is False
        assert d["provider"] == "linkedin"
        assert "Missing" in d["detail"]

    def test_instagram_missing(self, hdrs, cleanup_settings):
        r = requests.post(f"{API}/test-send/instagram", headers=hdrs, json={"body": "y"}, timeout=20)
        d = r.json()
        assert d["ok"] is False
        assert d["provider"] == "instagram"
        assert "Missing" in d["detail"]

    def test_linkedin_personal_guardrail(self, hdrs):
        # Even with keys this should be Manual copy-paste only
        r = requests.post(f"{API}/test-send/linkedin_personal", headers=hdrs, json={"body": "y"}, timeout=20)
        d = r.json()
        assert d["ok"] is False
        assert "Manual copy-paste only" in d["detail"]


# ---------- Settings new fields ----------
class TestSettingsNewFields:
    def test_settings_accepts_new_fields(self, hdrs):
        r = requests.patch(f"{API}/settings", json={
            "brevo_sender_email": "sender@example.com",
            "brevo_sender_name": "ShowUp Test",
            "linkedin_org_urn": "urn:li:organization:12345",
        }, headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        s = requests.get(f"{API}/settings", headers=hdrs, timeout=15).json()
        assert s.get("brevo_sender_email") == "sender@example.com"
        assert s.get("brevo_sender_name") == "ShowUp Test"
        assert s.get("linkedin_org_urn") == "urn:li:organization:12345"

    def test_settings_invalid_email_422(self, hdrs):
        r = requests.patch(f"{API}/settings", json={"brevo_sender_email": "not-an-email"},
                          headers=hdrs, timeout=15)
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


# ---------- Circle sync ----------
class TestCircle:
    def test_circle_sync_no_key(self, hdrs):
        # Clear key just to be sure
        requests.patch(f"{API}/settings", json={"circle_api_key": ""}, headers=hdrs, timeout=15)
        r = requests.post(f"{API}/circle/sync", headers=hdrs, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("members_synced") == 0

    def test_circle_sync_fake_key(self, hdrs):
        requests.patch(f"{API}/settings", json={"circle_api_key": "foo-bar"}, headers=hdrs, timeout=15)
        r = requests.post(f"{API}/circle/sync", headers=hdrs, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("members_synced") == 0
        # clean up
        requests.patch(f"{API}/settings", json={"circle_api_key": ""}, headers=hdrs, timeout=15)

    def test_circle_members_list(self, hdrs):
        r = requests.get(f"{API}/circle/members", headers=hdrs, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- LinkedIn events ----------
class TestLinkedInEvents:
    def test_linkedin_events_missing_keys(self, hdrs, cleanup_settings):
        r = requests.get(f"{API}/linkedin/events", headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "_error" in d
        assert "Missing" in d["_error"]


# ---------- Send-now ----------
class TestSendNow:
    def test_send_now_not_approved_400(self, webinar, hdrs):
        touches = requests.get(f"{API}/webinars/{webinar}/touches", headers=hdrs, timeout=15).json()
        # find one that is pending
        pending = [t for t in touches if t.get("approval_status") != "approved"]
        assert pending
        tid = pending[0]["id"]
        r = requests.post(f"{API}/touches/{tid}/send-now", headers=hdrs, timeout=15)
        assert r.status_code == 400
        assert "approved" in r.text.lower()

    def test_send_now_approved_no_keys(self, webinar, hdrs):
        # Ensure no keys
        requests.patch(f"{API}/settings", json={"brevo_api_key": "", "brevo_sender_email": None},
                       headers=hdrs, timeout=15)
        # Create a registrant so per-registrant log is populated
        email = f"TEST_sn_{uuid.uuid4().hex[:6]}@example.com"
        requests.post(f"{API}/webinars/{webinar}/register",
                      json={"name": "SN User", "email": email, "source": "form"}, timeout=15)
        touches = requests.get(f"{API}/webinars/{webinar}/touches", headers=hdrs, timeout=15).json()
        # touch_num 1 has email channel
        t1 = [t for t in touches if t["touch_num"] == 1][0]
        tid = t1["id"]
        # Approve it
        r0 = requests.patch(f"{API}/touches/{tid}", json={"approval_status": "approved"},
                            headers=hdrs, timeout=15)
        assert r0.status_code == 200
        # send-now
        r = requests.post(f"{API}/touches/{tid}/send-now", headers=hdrs, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is False  # no keys
        assert isinstance(d.get("log"), list) and len(d["log"]) >= 1
        # persistence
        touches2 = requests.get(f"{API}/webinars/{webinar}/touches", headers=hdrs, timeout=15).json()
        t1b = [t for t in touches2 if t["id"] == tid][0]
        assert t1b.get("sent_status") == "failed"
        assert isinstance(t1b.get("delivery_log"), list) and len(t1b["delivery_log"]) >= 1


# ---------- Community-join analytics ----------
class TestCommunityAnalytics:
    def test_analytics_includes_community(self, hdrs):
        r = requests.get(f"{API}/analytics/overview", headers=hdrs, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "community_joined_total" in d
        assert isinstance(d["community_joined_total"], int)
        assert "community_per_webinar" in d
        assert isinstance(d["community_per_webinar"], list)
        if d["community_per_webinar"]:
            row = d["community_per_webinar"][0]
            assert "id" in row and "title" in row and "community_joined" in row

    def test_patch_registrant_community_joined(self, webinar, hdrs):
        email = f"TEST_cj_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/webinars/{webinar}/register",
                          json={"name": "CJ", "email": email, "source": "form"}, timeout=15)
        rid = r.json()["id"]
        # baseline count
        base = requests.get(f"{API}/analytics/overview", headers=hdrs, timeout=15).json()
        before = base["community_joined_total"]
        # PATCH community_joined
        r2 = requests.patch(f"{API}/registrants/{rid}", json={"community_joined": True},
                            headers=hdrs, timeout=15)
        assert r2.status_code == 200
        # confirm persisted
        regs = requests.get(f"{API}/webinars/{webinar}/registrants", headers=hdrs, timeout=15).json()
        match = [x for x in regs if x["id"] == rid]
        assert match and match[0].get("community_joined") is True
        after = requests.get(f"{API}/analytics/overview", headers=hdrs, timeout=15).json()["community_joined_total"]
        assert after >= before + 1
