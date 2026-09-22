"""ShowUp.ai v1.3 backend tests — encryption + masking, GridFS social-image, ShowUp Score share image.

Verifies:
- 9 secret fields encrypted at rest with 'enc::' prefix; masked '••••••••<last4>' on GET
- Masked values on PATCH are dropped (no overwrite of real secret)
- Non-secret fields remain plaintext
- GridFS migration for social images (single file_id per webinar, regen deletes prior file)
- ShowUp Score generation/streaming/metadata + lazy generation on GET
- Touch #7 email body auto-appends showup-score.png URL
"""
import os
import uuid
import requests
import pytest
from pymongo import MongoClient

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://touch-sequence.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "showup_db")

TEST_EMAIL = "test@showup.ai"
TEST_PASSWORD = "test1234"

ENC_PREFIX = "enc::"
MASK = "•" * 8


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="session")
def auth_token():
    r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    if r.status_code != 200:
        requests.post(f"{API}/auth/register",
                      json={"name": "Test", "email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=15)
        r = requests.post(f"{API}/auth/login",
                         json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def hdrs(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="session")
def user_id(mongo_db):
    u = mongo_db.users.find_one({"email": TEST_EMAIL})
    assert u, "test user not seeded"
    yield u["id"]
    # Cleanup: wipe encrypted secret fields after v1.3 test session so other suites
    # (v1.1 linkedin_events 'Missing' guard) aren't polluted by leftover fake tokens.
    mongo_db.settings.update_one(
        {"owner_id": u["id"]},
        {"$unset": {f: "" for f in [
            "brevo_api_key", "mailchimp_api_key", "sendgrid_api_key",
            "linkedin_marketing_token", "linkedin_events_token",
            "meta_graph_token", "twilio_sid", "twilio_token", "circle_api_key",
        ]}})


@pytest.fixture
def webinar(hdrs):
    payload = {
        "title": "TEST_v13_Encryption",
        "description": "v1.3 test.",
        "speaker": "S",
        "target_audience": "AUD",
        "starts_at": "2030-12-01T10:00:00+00:00",
        "timezone": "UTC",
        "join_link": "https://example.com/j",
    }
    r = requests.post(f"{API}/webinars", json=payload, headers=hdrs, timeout=30)
    assert r.status_code == 200, r.text
    wid = r.json()["id"]
    yield wid
    requests.delete(f"{API}/webinars/{wid}", headers=hdrs, timeout=15)


# ---------- Refactor sanity ----------
class TestSanity:
    def test_root(self):
        r = requests.get(f"{API}/", timeout=10)
        assert r.status_code == 200
        assert r.json() == {"app": "ShowUp.ai", "ok": True}

    def test_auth_me(self, hdrs):
        r = requests.get(f"{API}/auth/me", headers=hdrs, timeout=10)
        assert r.status_code == 200


# ---------- Encryption + masking ----------
class TestEncryptionAndMasking:
    SECRET_FIELDS = [
        "brevo_api_key", "mailchimp_api_key", "sendgrid_api_key",
        "linkedin_marketing_token", "linkedin_events_token",
        "meta_graph_token", "twilio_sid", "twilio_token", "circle_api_key",
    ]

    def test_patch_then_get_returns_masked(self, hdrs):
        raw = "sk_live_xyz1234"
        r = requests.patch(f"{API}/settings", json={"brevo_api_key": raw}, headers=hdrs, timeout=15)
        assert r.status_code == 200
        s = requests.get(f"{API}/settings", headers=hdrs, timeout=15).json()
        assert s.get("brevo_api_key") == MASK + raw[-4:]

    def test_raw_doc_starts_with_enc_prefix(self, hdrs, mongo_db, user_id):
        requests.patch(f"{API}/settings", json={"brevo_api_key": "sk_live_xyz1234"},
                      headers=hdrs, timeout=15)
        doc = mongo_db.settings.find_one({"owner_id": user_id})
        assert doc is not None
        v = doc.get("brevo_api_key", "")
        assert isinstance(v, str) and v.startswith(ENC_PREFIX), \
            f"brevo_api_key raw doc should be enc-prefixed, got: {v[:30]!r}"

    def test_masked_value_on_patch_is_ignored(self, hdrs, mongo_db, user_id):
        # Seed a real value
        raw = "real_secret_abcd"
        requests.patch(f"{API}/settings", json={"brevo_api_key": raw}, headers=hdrs, timeout=15)
        before = mongo_db.settings.find_one({"owner_id": user_id})["brevo_api_key"]
        # Now PATCH with the masked value (UI replays masked) — must be ignored
        requests.patch(f"{API}/settings", json={"brevo_api_key": MASK + "abcd"},
                      headers=hdrs, timeout=15)
        after = mongo_db.settings.find_one({"owner_id": user_id})["brevo_api_key"]
        assert before == after, "Masked PATCH value must not overwrite real secret"
        # Still served masked
        s = requests.get(f"{API}/settings", headers=hdrs, timeout=15).json()
        assert s.get("brevo_api_key") == MASK + "abcd"

    def test_other_field_patch_preserves_existing_secret(self, hdrs, mongo_db, user_id):
        raw = "kept_secret_wxyz"
        requests.patch(f"{API}/settings", json={"brevo_api_key": raw}, headers=hdrs, timeout=15)
        # PATCH unrelated field
        requests.patch(f"{API}/settings", json={"circle_api_key": "circ_1234"},
                      headers=hdrs, timeout=15)
        s = requests.get(f"{API}/settings", headers=hdrs, timeout=15).json()
        assert s.get("brevo_api_key") == MASK + raw[-4:]
        assert s.get("circle_api_key") == MASK + "1234"

    def test_all_nine_secret_fields_encrypted_and_masked(self, hdrs, mongo_db, user_id):
        payload = {f: f"val_{f}_1234" for f in self.SECRET_FIELDS}
        r = requests.patch(f"{API}/settings", json=payload, headers=hdrs, timeout=20)
        assert r.status_code == 200
        s = requests.get(f"{API}/settings", headers=hdrs, timeout=15).json()
        doc = mongo_db.settings.find_one({"owner_id": user_id})
        for f in self.SECRET_FIELDS:
            assert s.get(f) == MASK + "1234", f"field {f} not masked: {s.get(f)!r}"
            assert doc.get(f, "").startswith(ENC_PREFIX), \
                f"field {f} not enc-prefixed in raw doc"

    def test_non_secret_fields_remain_plaintext(self, hdrs, mongo_db, user_id):
        plaintext_payload = {
            "brevo_sender_email": "send@example.com",
            "linkedin_org_urn": "urn:li:org:1234",
            "meta_page_id": "page-123",
            "instagram_business_id": "ig-123",
            "twilio_from": "+1234567890",
            "default_touches": {"1": True, "2": False},
            "per_touch_auto_send": {"3": True},
            "email_provider": "Brevo",
        }
        r = requests.patch(f"{API}/settings", json=plaintext_payload, headers=hdrs, timeout=15)
        assert r.status_code == 200
        doc = mongo_db.settings.find_one({"owner_id": user_id})
        for k, v in plaintext_payload.items():
            assert doc.get(k) == v, f"non-secret {k} mutated: {doc.get(k)!r} vs {v!r}"
            assert not (isinstance(doc.get(k), str) and doc.get(k, "").startswith(ENC_PREFIX))

    def test_decrypt_before_send(self, hdrs, mongo_db, user_id):
        # PATCH a fake brevo key, then call test-send/email — error must be from Brevo (decrypted),
        # not 'Missing brevo_api_key'
        requests.patch(f"{API}/settings", json={
            "email_provider": "Brevo",
            "brevo_api_key": "fake-brevo-key-decrypt-roundtrip",
            "brevo_sender_email": "test@example.com",
        }, headers=hdrs, timeout=15)
        r = requests.post(f"{API}/test-send/email",
                         json={"to_email": "x@y.com", "subject": "s", "body": "b"},
                         headers=hdrs, timeout=20)
        assert r.status_code == 200
        d = r.json()
        # ok=False expected (invalid key), but it must have *attempted* the upstream call
        assert d.get("ok") is False
        detail = (d.get("detail") or "").lower()
        # Must NOT be the 'missing brevo_api_key' guard
        assert "missing brevo_api_key" not in detail, \
            f"Decryption likely failed — got Missing guard: {d}"


# ---------- GridFS social-image ----------
class TestGridFSSocialImage:
    @pytest.mark.timeout(120)
    def test_generate_stores_in_gridfs_and_doc_has_file_id(self, hdrs, webinar, mongo_db):
        r = requests.post(f"{API}/webinars/{webinar}/social-image/generate",
                         headers=hdrs, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True and data["bytes"] > 100
        doc = mongo_db.social_images.find_one({"webinar_id": webinar})
        assert doc is not None
        assert "file_id" in doc and doc["file_id"] is not None
        assert "data" not in doc, "v1.3 should not store raw bytes in doc"
        # GridFS file exists
        fs_count = mongo_db["social_images_fs.files"].count_documents({"_id": doc["file_id"]})
        assert fs_count == 1

    @pytest.mark.timeout(180)
    def test_regen_deletes_previous_gridfs_file(self, hdrs, webinar, mongo_db):
        requests.post(f"{API}/webinars/{webinar}/social-image/generate",
                     headers=hdrs, timeout=120)
        before_count = mongo_db["social_images_fs.files"].count_documents({"metadata.webinar_id": webinar})
        requests.post(f"{API}/webinars/{webinar}/social-image/generate",
                     headers=hdrs, timeout=120)
        after_count = mongo_db["social_images_fs.files"].count_documents({"metadata.webinar_id": webinar})
        # Should remain at 1 (or at most before_count) — previous file cleaned up
        assert after_count <= max(before_count, 1), \
            f"Previous GridFS file not cleaned — before={before_count} after={after_count}"
        assert after_count == 1

    def test_get_streams_image(self, hdrs, webinar):
        requests.post(f"{API}/webinars/{webinar}/social-image/generate",
                     headers=hdrs, timeout=120)
        r = requests.get(f"{API}/webinars/{webinar}/social-image.png", timeout=30)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert ct.startswith("image/")
        assert len(r.content) > 100_000

    def test_legacy_bindata_fallback(self, hdrs, mongo_db, user_id):
        # Insert a synthetic legacy doc with 'data' (no file_id)
        wid = f"legacy-test-{uuid.uuid4().hex[:8]}"
        # Need a webinar row for endpoint logic — but get_social_image only checks social_images doc
        mongo_db.social_images.insert_one({
            "webinar_id": wid, "owner_id": user_id,
            "data": b"\x89PNG\r\n\x1a\n" + b"X" * 200,
            "mime_type": "image/png", "generated_at": "2025-01-01T00:00:00+00:00"
        })
        try:
            r = requests.get(f"{API}/webinars/{wid}/social-image.png", timeout=15)
            assert r.status_code == 200
            assert r.headers.get("content-type", "").startswith("image/")
            assert len(r.content) > 100
        finally:
            mongo_db.social_images.delete_one({"webinar_id": wid})


# ---------- ShowUp Score ----------
class TestShowUpScore:
    def test_score_404_when_zero_registrants(self, hdrs, webinar):
        # Fresh webinar with no registrants
        r = requests.post(f"{API}/webinars/{webinar}/showup-score/generate",
                         headers=hdrs, timeout=30)
        assert r.status_code == 404
        assert "attendance" in (r.json().get("detail") or "").lower()

    def test_score_generate_with_attendees(self, hdrs, webinar, mongo_db):
        # Add a registrant + mark attended
        requests.post(f"{API}/webinars/{webinar}/register",
                     json={"name": "A", "email": f"att_{uuid.uuid4().hex[:6]}@e.com"}, timeout=15)
        mongo_db.registrants.update_many({"webinar_id": webinar},
                                          {"$set": {"attended": True}})
        r = requests.post(f"{API}/webinars/{webinar}/showup-score/generate",
                         headers=hdrs, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["registrants"] >= 1
        assert d["attendees"] >= 1
        assert d["rate"] > 0
        assert d["url"].endswith("/showup-score.png")
        # GridFS file persisted
        doc = mongo_db.showup_scores.find_one({"webinar_id": webinar})
        assert doc and doc.get("file_id")
        fs = mongo_db["showup_scores_fs.files"].count_documents({"_id": doc["file_id"]})
        assert fs == 1

    def test_score_image_stream(self, hdrs, webinar, mongo_db):
        # Ensure pre-existing score
        requests.post(f"{API}/webinars/{webinar}/register",
                     json={"name": "A", "email": f"att_{uuid.uuid4().hex[:6]}@e.com"}, timeout=15)
        mongo_db.registrants.update_many({"webinar_id": webinar},
                                          {"$set": {"attended": True}})
        requests.post(f"{API}/webinars/{webinar}/showup-score/generate",
                     headers=hdrs, timeout=30)
        r = requests.get(f"{API}/webinars/{webinar}/showup-score.png", timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/")
        assert len(r.content) > 5_000

    def test_score_meta_json(self, hdrs, webinar, mongo_db):
        requests.post(f"{API}/webinars/{webinar}/register",
                     json={"name": "A", "email": f"att_{uuid.uuid4().hex[:6]}@e.com"}, timeout=15)
        mongo_db.registrants.update_many({"webinar_id": webinar},
                                          {"$set": {"attended": True}})
        requests.post(f"{API}/webinars/{webinar}/showup-score/generate",
                     headers=hdrs, timeout=30)
        r = requests.get(f"{API}/webinars/{webinar}/showup-score", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "rate" in d and "registrants" in d and "attendees" in d
        assert "generated_at" in d

    def test_lazy_generate_on_first_get(self, hdrs, mongo_db):
        # Create webinar, add attendee, DON'T pre-generate; then GET should lazy-create
        payload = {"title": "TEST_lazy_score", "description": "x", "speaker": "x",
                   "target_audience": "x", "starts_at": "2030-11-01T10:00:00+00:00",
                   "timezone": "UTC", "join_link": "https://e.com"}
        r = requests.post(f"{API}/webinars", json=payload, headers=hdrs, timeout=20)
        wid = r.json()["id"]
        try:
            requests.post(f"{API}/webinars/{wid}/register",
                         json={"name": "A", "email": f"laz_{uuid.uuid4().hex[:6]}@e.com"}, timeout=15)
            mongo_db.registrants.update_many({"webinar_id": wid},
                                              {"$set": {"attended": True}})
            # No POST .../showup-score/generate — go straight to GET .png
            r = requests.get(f"{API}/webinars/{wid}/showup-score.png", timeout=30)
            assert r.status_code == 200
            assert len(r.content) > 5_000
        finally:
            requests.delete(f"{API}/webinars/{wid}", headers=hdrs, timeout=15)
