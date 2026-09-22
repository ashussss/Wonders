# ShowUp.ai — Codebase Map for AI Assistants

This file is the **primary entry point for AI coding agents** (Claude, GPT, Cursor, Aider, etc.) to understand and safely extend this codebase. Read it first.

## What the product does
ShowUp.ai is a B2B webinar attendance booster. It generates an 8-touch reminder sequence per webinar (registration → 7d → 3d → 1d → 3h → 15min → post-event thank-you → post-event re-engagement), produces AI-written copy with two variants (safe/casual) per channel, coordinates sends across email + LinkedIn + Facebook + Instagram + WhatsApp + Circle.so, and tracks attendance-rate-by-channel + community conversion. Final product name: **ShowUp.ai**.

## Tech stack
- **Backend**: Python 3.11 + FastAPI + Motor (async MongoDB) + APScheduler + slowapi (rate limiting) + httpx + Pydantic v2
- **AI**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) for text via `emergentintegrations`; Gemini Nano Banana (`gemini-3.1-flash-image-preview`) for Instagram social images
- **Storage**: MongoDB (documents) + GridFS (image bytes)
- **Encryption**: cryptography Fernet for at-rest secrets
- **Frontend**: React 19 + Tailwind + shadcn/ui + Recharts + Sonner toasts + Lucide icons + Outfit/IBM Plex Sans typography
- **Auth**: JWT (custom, bcrypt) — single-user per account, all data owner-scoped

## Directory map

```
/app/
├── backend/
│   ├── server.py          # ~55-line app factory: lifespan + middleware + router mounts
│   ├── config.py          # env vars + TOUCH_DEFS (the 8-touch definitions)
│   ├── database.py        # AsyncIOMotorClient + scheduler + GridFS buckets
│   ├── auth_utils.py      # hash_pw, verify_pw, make_token, get_user dep
│   ├── models.py          # Pydantic input models (User/Webinar/Touch/Settings…)
│   ├── ai.py              # Claude generators for touch copy + lead magnets
│   ├── image_gen.py       # Nano Banana social-image generation
│   ├── showup_score.py    # Pillow renderer for the post-event share PNG
│   ├── files.py           # ICS calendar + reportlab PDF lead-magnet
│   ├── crypto_utils.py    # Fernet field-level encryption (SECRET_FIELDS list)
│   ├── senders.py         # Outbound dispatch: Brevo/Mailchimp/SendGrid/BuzzAI emails,
│   │                      #   Meta FB/IG, Twilio WhatsApp+SMS, LinkedIn UGC, Circle.so
│   ├── integrations.py    # Circle.so members sync + LinkedIn Events (best-effort)
│   ├── routes_auth.py     # /api/auth/{register,login,me}
│   ├── routes_webinars.py # /api/webinars/* + touches + registrants + lead-magnets + approval-queue
│   ├── routes_settings.py # /api/settings + /api/analytics/overview
│   ├── routes_delivery.py # test-send, send-now, ICS/PDF, social-image, showup-score, Circle, LinkedIn
│   ├── tests/             # pytest suites: test_showup_api.py, _v11.py, _v12.py, _v13.py
│   ├── requirements.txt
│   └── .env               # MONGO_URL, DB_NAME, JWT_SECRET, EMERGENT_LLM_KEY,
│                          #   FERNET_KEY, PUBLIC_BACKEND_URL
├── frontend/
│   └── src/
│       ├── App.js                       # Router + AuthProvider
│       ├── lib/api.js                   # axios instance + API_BASE + CHANNEL_META
│       ├── lib/auth.jsx                 # AuthProvider hook + JWT token
│       ├── components/Layout.jsx        # sidebar nav
│       ├── components/CreateWebinarDialog.jsx
│       └── pages/
│           ├── Login.jsx / Register.jsx
│           ├── Dashboard.jsx            # KPIs + webinars table
│           ├── WebinarDetail.jsx        # Send Plan + Registrants + Lead Magnets tabs + ShowUp Score card
│           ├── ApprovalQueue.jsx        # bundled email+social per touch
│           ├── Analytics.jsx            # attendance-rate-by-channel + community-join attribution
│           ├── Settings.jsx             # ALL provider API keys + per-channel toggles
│           └── PublicRegister.jsx       # /r/:wid public registration form
└── memory/
    ├── PRD.md
    ├── test_credentials.md
    └── (this AGENTS.md is at /app/AGENTS.md — repo root)
```

## Data model (collections, top-level fields)

### users
`{id, email, name, password (bcrypt hash), created_at}`

### webinars
`{id, owner_id, title, description, speaker, target_audience, starts_at (ISO), timezone, join_link, registration_link, status, enabled_touches, created_at}`

### touches (the send plan, 8 per webinar)
```
{
  id, webinar_id, owner_id,
  touch_num: 1-8,
  name: "Registration confirmation" | "7-day announcement" | …,
  trigger: "on_registration" | "before_event" | "after_event_attendees" | "after_event_noshows",
  channels: ["email","linkedin","facebook","instagram","whatsapp","circle","linkedin_personal"],
  scheduled_at: ISO datetime (null for touch 1 which fires on registration),
  ai_copy: {
    angle: "single-line unique hook",
    channels: {
      "<channel>": {
        "safe":   {subject?, body},
        "casual": {subject?, body}
      }
    }
  },
  ai_reasoning: string,
  selected_variant: 0 (safe) | 1 (casual),
  copy_overrides: { "<channel>": "user-edited text" },
  approval_status: "pending" | "approved" | "rejected",
  sent_status: "planned" | "queued" | "sent" | "failed",
  sent_at, approved_at,
  delivery_log: [{channel, recipient?, ok, detail}]
}
```

### registrants
`{id, webinar_id, owner_id, name, email (lowercased, deduped), phone, source, attended, community_joined, registered_at}`. Source ∈ {`form`, `circle`, `linkedin_manual`}.

### lead_magnets
`{id, webinar_id, owner_id, ai_content:{case_study, snippets[], one_pager:{title, outline[]}}, edited_content, approval_status, generated_at}`

### settings (per user)
All user-supplied secrets are stored encrypted with `enc::` prefix (Fernet). See `crypto_utils.SECRET_FIELDS`. Read via `decrypt_settings()`, present to UI via `mask_settings_for_api()` (returns `••••••••<last4>`).

### social_images / showup_scores
Metadata docs `{webinar_id, owner_id, file_id (GridFS), mime_type, bytes, generated_at}`. Bytes live in `social_images_fs` / `showup_scores_fs` GridFS buckets.

### community_members
Circle.so synced members `{owner_id, email, name, member_id, joined_at, tags, synced_at}`.

## Channel system

Defined in `senders.py::dispatch(channel, settings, …)`. Adding a new channel = adding a new branch here + handling it in `routes_delivery.py::_deliver_touch` audience selection.

| Channel | Provider routing | Auto-send | Notes |
|---|---|---|---|
| `email` | `settings.email_provider` → Brevo/Mailchimp/SendGrid/BuzzAI | yes (per-touch) | ICS attached on touch 1; ShowUp Score URL appended on touch 7 |
| `linkedin` | `settings.linkedin_provider` → `marketing_api` (default) or `buzzai` | yes | UGC company-page post |
| `linkedin_personal` | — | **never** (guardrail) | "Manual paste only" — drafts only |
| `facebook` | Meta Graph API | yes | Page feed post |
| `instagram` | Meta Graph API | yes | Requires `image_url` (auto-supplied from `social_images` GridFS) |
| `whatsapp` | Twilio (SMS fallback) | yes | Per-registrant |
| `circle` | Circle.so Admin API v2 (`POST /api/admin/v2/posts`) | yes | Requires `circle_api_key` + `circle_space_id`. TipTap rich-text body. |

## Touch sequence (8 touches)

Defined in `config.py::TOUCH_DEFS`. Each touch has a unique angle/hook enforced via Claude prompt. Touch 1 fires on registration (no scheduled_at); touches 2-6 fire before event; touches 7-8 fire post-event with audience filtering (`after_event_attendees` vs `after_event_noshows`).

## AI orchestration

`ai.py::generate_touch_copy()` prompt enforces:
- distinctly different angle per touch
- 2 variants per channel (`safe` polished / `casual` urgent)
- channel-specific length/format constraints
- no fabricated stats or company names

`ai.py::generate_lead_magnets()` produces a case study + 3-5 did-you-know snippets + one-pager outline, with a hard "no fabricated specifics" guardrail.

## Scheduler

`routes_delivery.py::scheduler_tick()` runs every minute (APScheduler). Finds approved touches with `scheduled_at <= now`. If `per_touch_auto_send` is on, calls `_deliver_touch()` → real upstream API calls. Otherwise flips status to `queued` (user must click "Send now" on the touch card).

## Endpoints index

### Auth (`routes_auth.py`)
- `POST /api/auth/register` — JWT signup
- `POST /api/auth/login`
- `GET /api/auth/me`

### Webinars (`routes_webinars.py`)
- `GET/POST /api/webinars`, `GET/PATCH/DELETE /api/webinars/{wid}`
- `GET /api/webinars/{wid}/touches`, `PATCH /api/touches/{tid}`, `POST /api/touches/{tid}/regenerate`
- `GET /api/webinars/{wid}/registrants`, `POST /api/webinars/{wid}/register` (public, **rate-limited 10/min**)
- `POST /api/webinars/{wid}/registrants/import`, `PATCH /api/registrants/{rid}`
- `POST /api/webinars/{wid}/webhooks/circle` (public, **60/min**) — supports `{community_member:{email,name}}` AND flat `{email,name}` shapes
- `POST /api/webinars/{wid}/mark-attendance`
- `GET /api/webinars/{wid}/lead-magnets`, `POST /api/webinars/{wid}/lead-magnets/regenerate`, `PATCH /api/lead-magnets/{lmid}`
- `GET /api/approval-queue`

### Settings & analytics (`routes_settings.py`)
- `GET /api/settings` → masked values
- `PATCH /api/settings` → encrypts secrets, ignores masked values to prevent UI re-save corruption
- `GET /api/analytics/overview` → KPIs incl. community_joined attribution

### Delivery & files (`routes_delivery.py`)
- `GET /api/webinars/{wid}/calendar.ics` (public)
- `GET /api/webinars/{wid}/one-pager.pdf`
- `POST /api/webinars/{wid}/social-image/generate` → Nano Banana
- `GET /api/webinars/{wid}/social-image.png` (public; serves from GridFS)
- `POST /api/webinars/{wid}/showup-score/generate` (post-event score share)
- `GET /api/webinars/{wid}/showup-score.png` (public; lazy-generates on first GET)
- `GET /api/webinars/{wid}/showup-score` (JSON metadata)
- `POST /api/circle/sync`, `GET /api/circle/members`, `GET /api/circle/spaces` (helper for picker)
- `GET /api/linkedin/events` (best-effort)
- `POST /api/test-send/{channel}` — fires the channel with a test payload using stored creds
- `POST /api/touches/{tid}/send-now` — manual send for an approved touch

## Conventions for AI agents extending this code

1. **All backend routes MUST be prefixed `/api`.** Kubernetes ingress depends on it.
2. **Never log or return raw secrets.** Use `mask_settings_for_api()` for any path that returns settings to the UI.
3. **Per-user scoping.** Every Mongo query touching user data must include `owner_id`. The exceptions are the three public endpoints: `/api/webinars/{wid}/register`, `/api/webinars/{wid}/webhooks/circle`, and the public `*.png`/`.ics`/`.pdf` download routes.
4. **Adding a new channel** (e.g. Discord, Slack):
   - Add it to `senders.py::dispatch()` branch
   - Add a `CHANNEL_META` entry in `frontend/src/lib/api.js` with `{label, icon, autoSendCapable, manualOnly}`
   - Add it to the `default_channels` of relevant touches in `config.py::TOUCH_DEFS`
   - Add settings fields to `SettingsIn` (`models.py`) + register secrets in `crypto_utils.SECRET_FIELDS` if applicable
   - Add UI rows to `Settings.jsx`
   - **No new code anywhere else** — the rest of the pipeline (Approval Queue, scheduler, Send-Now, test-send, delivery_log) just works.
5. **Adding a new email provider:** add `send_<provider>_email()` to `senders.py`, wire it into the `send_email()` router on the `email_provider` setting value. Mirror the test-send + missing-key error UX.
6. **Adding a new AI generator:** add to `ai.py`. Always set `system_message` with explicit guardrails ("no fabricated stats / no real company names") and always return JSON (let `claude_json()` parse it).
7. **Never bypass the encryption layer.** Read settings via `_user_settings_decrypted()` (in `routes_delivery.py`) when you need plaintext to call upstream APIs.
8. **Frontend `data-testid`** — every interactive element must have one. The pytest suites + Playwright depend on them.
9. **Hot reload is on.** Don't restart the supervisor for code changes; restart only for `.env` or new pip installs.
10. **Tests:** `pytest /app/backend/tests/ -v`. Add a new test file `test_showup_v1<N>.py` when shipping a new feature batch. Always update assertions in older suites if you change a contract (encryption was one such case).

## Common tasks cheat sheet

### Add a new touch (e.g. T9 "2-day reminder")
1. Edit `config.py::TOUCH_DEFS` — append `{"num":9, …}`
2. Edit `routes_webinars.py` — the loop already iterates `TOUCH_DEFS` so it works
3. Old webinars need a backfill — write a one-off script that inserts the missing touch row
4. Frontend Settings → add a new `touch-row-9` UI entry (the loop in `Settings.jsx` reads `TOUCHES` array — update that too)

### Add a new lead-magnet type
1. Edit the Claude prompt in `ai.py::generate_lead_magnets()` to ask for the new field
2. Render it in `WebinarDetail.jsx::LeadMagnetsTab` (add a new `<Section>`)
3. Optionally add a download endpoint (mirror `one-pager.pdf` in `routes_delivery.py`)

### Rotate FERNET_KEY (encryption key)
**Currently undocumented + risky.** Procedure: dump settings, decrypt with old key, encrypt with new key, write back. No script exists yet — backlog item.

## Test credentials
See `/app/memory/test_credentials.md`. Default: `test@showup.ai / test1234`.

## Known limitations / non-issues
- Outbound deliveries are real HTTP calls but only succeed when the user has saved real keys. Without keys, every channel returns `{ok:false, detail:"Missing <field> …"}` with friendly guidance.
- `linkedin_personal` is **intentionally** blocked from auto-send (spec guardrail).
- Instagram requires an image — the social-image route auto-supplies one from GridFS for the touch's webinar; if not yet generated, IG delivery will fail with a clear error.
- Buzz.ai has no documented public REST API — implemented as a **configurable custom endpoint** the user pastes in. Settings UI explains this.
- Cloudflare proxy can mask the originating IP, so rate-limit verification through the public preview URL is unreliable; rate limits **do** fire against direct localhost calls.

---
*If you're an AI agent reading this: respect the encryption layer, the per-user scoping, and the guardrails. Don't introduce auto-posting for `linkedin_personal`. Don't fabricate stats or company names in AI prompts. Always run `pytest /app/backend/tests/` before claiming success.*
