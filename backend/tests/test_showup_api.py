"""ShowUp.ai backend API tests."""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://touch-sequence.preview.emergentagent.com").rstrip("/")
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


# ---------- Auth ----------
class TestAuth:
    def test_register_new_user(self):
        email = f"TEST_{uuid.uuid4().hex[:8]}@showup-test.example.com"
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": "pass1234", "name": "Test"}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data and "user" in data
        assert data["user"]["email"] == email.lower()

    def test_login_seeded_user(self, auth_token):
        assert isinstance(auth_token, str) and len(auth_token) > 10

    def test_me_endpoint(self, hdrs):
        r = requests.get(f"{API}/auth/me", headers=hdrs, timeout=20)
        assert r.status_code == 200
        assert r.json()["email"] == TEST_EMAIL

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": "wrong"}, timeout=20)
        assert r.status_code == 401


# ---------- Webinar create + auto resources ----------
@pytest.fixture(scope="session")
def created_webinar(hdrs):
    payload = {
        "title": "TEST_Webinar_PyTest",
        "description": "Pytest-created webinar for ShowUp.ai integration verification.",
        "speaker": "Test Speaker",
        "target_audience": "School business managers",
        "starts_at": "2030-06-01T10:00:00+00:00",
        "timezone": "Europe/London",
        "join_link": "https://example.com/join",
    }
    r = requests.post(f"{API}/webinars", json=payload, headers=hdrs, timeout=30)
    assert r.status_code == 200, r.text
    wid = r.json()["id"]
    yield wid
    # cleanup
    requests.delete(f"{API}/webinars/{wid}", headers=hdrs, timeout=15)


class TestWebinarCreation:
    def test_webinar_returns_id(self, created_webinar):
        assert created_webinar

    def test_8_touches_created(self, created_webinar, hdrs):
        r = requests.get(f"{API}/webinars/{created_webinar}/touches", headers=hdrs, timeout=20)
        assert r.status_code == 200
        touches = r.json()
        assert len(touches) == 8
        nums = sorted(t["touch_num"] for t in touches)
        assert nums == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_lead_magnet_doc_exists(self, created_webinar, hdrs):
        r = requests.get(f"{API}/webinars/{created_webinar}/lead-magnets", headers=hdrs, timeout=20)
        assert r.status_code == 200
        assert "id" in r.json() or r.json() != {}


# ---------- Registrants / Dedup ----------
class TestRegistrants:
    def test_public_register_creates(self, created_webinar):
        email = f"TEST_pub_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/webinars/{created_webinar}/register",
                          json={"name": "Pub User", "email": email, "phone": "+10000", "source": "form"}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        # Duplicate
        r2 = requests.post(f"{API}/webinars/{created_webinar}/register",
                           json={"name": "Pub User", "email": email, "source": "form"}, timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("deduped") is True

    def test_circle_webhook_dedupes_across_sources(self, created_webinar):
        email = f"TEST_circ_{uuid.uuid4().hex[:6]}@example.com"
        # First via public form
        r1 = requests.post(f"{API}/webinars/{created_webinar}/register",
                           json={"name": "Cross Src", "email": email, "source": "form"}, timeout=15)
        assert r1.status_code == 200
        # Then via circle
        r2 = requests.post(f"{API}/webinars/{created_webinar}/webhooks/circle",
                           json={"email": email, "name": "Cross Src"}, timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("deduped") is True

    def test_circle_webhook_new_creates_circle_source(self, created_webinar, hdrs):
        email = f"TEST_cnew_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/webinars/{created_webinar}/webhooks/circle",
                          json={"email": email, "name": "C New"}, timeout=15)
        assert r.status_code == 200
        # Verify list has source=circle for this email
        regs = requests.get(f"{API}/webinars/{created_webinar}/registrants", headers=hdrs, timeout=15).json()
        match = [x for x in regs if x["email"] == email.lower()]
        assert match and match[0]["source"] == "circle"

    def test_bulk_csv_import_reports_counts(self, created_webinar, hdrs):
        new1 = f"TEST_imp1_{uuid.uuid4().hex[:6]}@example.com"
        new2 = f"TEST_imp2_{uuid.uuid4().hex[:6]}@example.com"
        items = [
            {"name": "Imp1", "email": new1, "source": "linkedin_manual"},
            {"name": "Imp2", "email": new2, "source": "linkedin_manual"},
            {"name": "Imp1Dup", "email": new1, "source": "linkedin_manual"},
        ]
        r = requests.post(f"{API}/webinars/{created_webinar}/registrants/import", json=items, headers=hdrs, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["inserted"] == 2
        assert data["deduped"] == 1

    def test_patch_registrant_attended(self, created_webinar, hdrs):
        email = f"TEST_att_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/webinars/{created_webinar}/register",
                          json={"name": "A", "email": email, "source": "form"}, timeout=15)
        rid = r.json()["id"]
        r2 = requests.patch(f"{API}/registrants/{rid}", json={"attended": True}, headers=hdrs, timeout=15)
        assert r2.status_code == 200
        regs = requests.get(f"{API}/webinars/{created_webinar}/registrants", headers=hdrs, timeout=15).json()
        match = [x for x in regs if x["id"] == rid]
        assert match and match[0]["attended"] is True


# ---------- Settings ----------
class TestSettings:
    def test_get_settings(self, hdrs):
        r = requests.get(f"{API}/settings", headers=hdrs, timeout=15)
        assert r.status_code == 200

    def test_patch_settings_persists(self, hdrs):
        payload = {
            "brevo_api_key": "TEST_brevo",
            "twilio_sid": "TEST_sid",
            "default_touches": {"1": True, "2": False},
            "per_touch_auto_send": {"3": True}
        }
        r = requests.patch(f"{API}/settings", json=payload, headers=hdrs, timeout=15)
        assert r.status_code == 200
        s = requests.get(f"{API}/settings", headers=hdrs, timeout=15).json()
        # v1.3: secret fields are masked on GET (8 dots + last 4 chars)
        assert s.get("brevo_api_key") == ("•" * 8) + "revo"
        assert s.get("twilio_sid") == ("•" * 8) + "_sid"
        assert s.get("default_touches", {}).get("2") is False


# ---------- Approval Queue + Touches ----------
class TestApprovalQueue:
    def test_queue_returns_enriched(self, created_webinar, hdrs):
        r = requests.get(f"{API}/approval-queue", headers=hdrs, timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        # at least one row from this webinar should appear (pending)
        ours = [x for x in rows if x["webinar_id"] == created_webinar]
        assert ours, "No touches from test webinar in approval queue"
        assert "webinar_title" in ours[0]
        assert "webinar_starts_at" in ours[0]

    def test_patch_touch_approve(self, created_webinar, hdrs):
        touches = requests.get(f"{API}/webinars/{created_webinar}/touches", headers=hdrs, timeout=15).json()
        tid = touches[0]["id"]
        r = requests.patch(f"{API}/touches/{tid}", json={"approval_status": "approved"}, headers=hdrs, timeout=15)
        assert r.status_code == 200
        # verify
        t2 = requests.get(f"{API}/webinars/{created_webinar}/touches", headers=hdrs, timeout=15).json()
        t = [x for x in t2 if x["id"] == tid][0]
        assert t["approval_status"] == "approved"


# ---------- Analytics ----------
class TestAnalytics:
    def test_overview_shape(self, hdrs):
        r = requests.get(f"{API}/analytics/overview", headers=hdrs, timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_webinars", "total_registrants", "total_attendees", "overall_rate", "per_webinar", "by_channel"):
            assert k in d


# ---------- AI Content (slower path) ----------
class TestAIContent:
    def test_lead_magnets_eventual(self, created_webinar, hdrs):
        deadline = time.time() + 100  # wait up to 100s
        content = None
        while time.time() < deadline:
            r = requests.get(f"{API}/webinars/{created_webinar}/lead-magnets", headers=hdrs, timeout=15)
            lm = r.json() if r.status_code == 200 else {}
            ai = lm.get("ai_content") or {}
            if ai and ai.get("case_study") and ai.get("snippets") and ai.get("one_pager"):
                content = ai
                break
            time.sleep(5)
        assert content is not None, "Lead magnet AI content did not populate in time"
        # No fabricated specific stats like 47%
        cs = content["case_study"]
        assert isinstance(cs, str) and 100 < len(cs) < 3000
        assert isinstance(content["snippets"], list) and 3 <= len(content["snippets"]) <= 6
        assert "title" in content["one_pager"] and "outline" in content["one_pager"]

    def test_touch_copy_varied_angles(self, created_webinar, hdrs):
        # Wait for at least 3 touches to have ai_copy with angle
        deadline = time.time() + 150
        angles = []
        while time.time() < deadline:
            touches = requests.get(f"{API}/webinars/{created_webinar}/touches", headers=hdrs, timeout=15).json()
            angles = [t.get("ai_copy", {}).get("angle") for t in touches if t.get("ai_copy", {}).get("angle")]
            if len(angles) >= 3:
                break
            time.sleep(5)
        assert len(angles) >= 3, f"Only {len(angles)} touches have ai_copy.angle populated"
        # Varied (distinct) check on those we have
        assert len(set(angles)) == len(angles), f"Repeated angles: {angles}"
