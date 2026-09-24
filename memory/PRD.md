# ShowUpAI — Product Requirements Document

## Original problem statement
Build a webinar attendance booster app per the attached PDF spec, including:
- Full data model (Webinars, Registrants, Touches, Lead magnets, Send plan entries)
- 8-touch reminder sequence with AI-generated copy (varying angle/hook per touch)
- AI orchestration logic for one send plan per webinar across email + LinkedIn + Meta/FB + Instagram + WhatsApp + Circle.so, fired together per touch
- Lead-magnet generator (case study, "did you know" snippets, one-pager) with "verify before sending" guardrail in UI
- Three registration capture sources (own form, Circle.so webhook, LinkedIn manual/API fallback) → single deduplicated table
- Approval queue UI: each card bundles email + ALL social captions for a touch
- Analytics view prioritising attendance-rate-by-channel
- Settings page with all API credential fields from doc
- Use Claude (Anthropic API) for every AI task

Final product name: **ShowUpAI**

## Architecture
- **Backend**: FastAPI + Motor (Mongo) + APScheduler + emergentintegrations (Claude Sonnet 4.5)
- **Frontend**: React 19 + Tailwind + shadcn/ui + Recharts + Sonner toasts
- **Auth**: JWT-based custom login (single tenant per user, all webinars owner-scoped)
- **AI**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) via Emergent Universal LLM Key

## Implemented (June 2026 — v1)
- Auth (register/login/me) with bcrypt + JWT
- Webinars CRUD; on-create auto-spawns 8 touches + lead-magnet doc; AI fires in background
- Touch model with 2 variants per channel (safe + casual), AI reasoning note, per-touch channel mapping
- Lead magnets: case study (150-250 w), 3-5 snippets, one-pager outline — all marked AI illustrative
- Registration: public form `/r/:wid`, Circle.so webhook, CSV import for LinkedIn fallback — deduped by email
- Approval Queue page bundling email + every social caption per touch with safe/casual switch
- Analytics: overall rate, by-channel attendance, per-webinar trend (Recharts)
- Settings: API key fields for Brevo/Mailchimp/SendGrid, LinkedIn Marketing/Events, Meta Graph + Page ID, Instagram Business ID, Twilio, Circle.so + default touch sequence toggles + per-touch auto-send
- Scheduler: APScheduler ticks every minute, marks approved touches as `sent`/`queued` after scheduled time

## Guardrails enforced
- "AI-generated illustrative content — verify before sending" banner on lead magnets & approval queue
- LinkedIn personal channel labelled "Manual copy-paste only" (no auto-post)
- No auto-send without approval in v1; explicit `per_touch_auto_send` opt-in even after approval
- Claude prompt explicitly instructs no fabricated company names or precise statistics

## Backlog / Next
- P1: Wire real channel deliveries (Brevo / Meta Graph / Twilio) when keys present
- P1: ICS calendar generation for touch 1 confirmation
- P1: PDF generation for one-pager lead magnet
- P2: Circle.so member sync & community signals targeting
- P2: LinkedIn Events API integration when scope available
- P2: Community-join conversion attribution in analytics

## v1.1 Implemented (Feb 2026)
- **Real outbound delivery**: Brevo email (+ ICS attachment on touch #1), Meta Facebook Page, Meta Instagram (image_url required), Twilio WhatsApp w/ SMS fallback, LinkedIn UGC company-page post. `linkedin_personal` channel hard-coded to refuse auto-send (guardrail).
- **ICS + PDF**: `GET /api/webinars/{wid}/calendar.ics` and `GET /api/webinars/{wid}/one-pager.pdf` (reportlab). Both linked from the Webinar Detail header.
- **Per-touch Send-Now** button (`POST /api/touches/{tid}/send-now`) with delivery_log captured per (channel × recipient).
- **Scheduler** now actually delivers when per_touch_auto_send=true; otherwise marks `queued` for manual review.
- **Test-send endpoints** `POST /api/test-send/{channel}` with provider-specific missing-field error messages.
- **Circle.so member sync** (`POST /api/circle/sync`) populates `community_members` + auto-flags matching registrants `community_joined=true`.
- **LinkedIn Events API** best-effort endpoint with realistic fallback messaging.
- **Analytics**: `community_joined_total` KPI + `community_per_webinar` table — "did the webinar grow the community?" alongside attendance rate.
- **Settings additions**: Brevo sender email/name, LinkedIn Organization URN, per-provider Test buttons, Circle sync button.

## Backlog / Next
- P1.2: LinkedIn personal-post "Copy & Paste" UX polish
- P1.2: Wire Mailchimp / SendGrid in addition to Brevo
- P2: Auto-image generation for Instagram (IG Graph API requires media — Sora/Nano-Banana could fill this)
- P2: Refactor server.py (~780 lines) into routers (auth, webinars, registrants, touches, analytics, integrations, files)
- P2: Rate-limit public /register + /webhooks/circle endpoints

## v1.2 Implemented (Feb 2026)
- **Nano Banana social image** (`image_gen.py`): Gemini-3.1-flash-image-preview generates a 1080×1080 promotional image per webinar. Stored in `db.social_images`, served publicly at `/api/webinars/{wid}/social-image.png` so Meta Graph IG endpoint can fetch it. Touch #2/#3/#7/#8 with Instagram in channels auto-attaches this image on send.
- **Mailchimp (Mandrill) + SendGrid** wired in `senders.py`. Settings page exposes provider-specific sender-email fields. Provider selected via `settings.email_provider` ("Brevo" | "Mailchimp" | "SendGrid"). Each provider validates its own credentials — no cross-provider fallback.
- **LinkedIn personal "Copy & Paste" UX polish**: manual-only channels render with amber-bg cards, bold "⚠ Manual paste only" badge, prominent amber "Copy for LinkedIn" button + "Open LinkedIn ↗" deep link. Applied in both TouchCard and Approval Queue.
- **Rate limiting** (slowapi 0.1.10): `/api/webinars/{wid}/register` 10/min, `/api/webinars/{wid}/webhooks/circle` 60/min. Confirmed 429s fire against direct backend.
- **Backend refactor**: `server.py` slimmed from 780 → 56 lines. Code split into `config.py`, `database.py`, `auth_utils.py`, `models.py`, `ai.py` + 4 router modules (`routes_auth.py`, `routes_webinars.py`, `routes_settings.py`, `routes_delivery.py`). Lifespan handler replaces deprecated `@app.on_event`. 57/57 backend tests pass (v1.0 + v1.1 + v1.2).

## Backlog / Next
- P2: Move social-image bytes from Mongo BinData to GridFS or object storage when usage scales > ~1000 webinars
- P2: Persist user-supplied API secrets encrypted at rest (currently plain string in `db.settings`)
- P3: Optional: ShowUp Score share image (mentioned in v1 finish summary)

## v1.3 Implemented (Feb 2026)
- **GridFS migration** (`database.py` + `routes_delivery.py`): Nano Banana social images and Pillow ShowUp Score images now stored in `social_images_fs` and `showup_scores_fs` GridFS buckets respectively. Lifecycle: prior file deleted on regen, doc holds only `{file_id, mime_type, bytes, generated_at}`. Legacy BinData rows still served via fallback path.
- **At-rest encryption** (`crypto_utils.py`): Fernet (cryptography) field-level encryption of all 9 user-supplied API secret fields in `db.settings`. GET /api/settings returns masked `••••••••<last4>` strings; PATCH ignores masked values to prevent UI re-saves from corrupting secrets. Every delivery path (`test-send`, `send-now`, `scheduler_tick`, `circle/sync`, `linkedin/events`) decrypts via `_user_settings_decrypted` before contacting upstream APIs.
- **ShowUp Score** (`showup_score.py` + `routes_delivery.py`): Pillow renders a 1080×1080 PNG showing the webinar's attendance rate vs the 30% industry baseline (e.g. "100% — 3.3× the industry baseline"). Stored in GridFS, served at `/api/webinars/{wid}/showup-score.png` (lazy-generates on first GET). Touch #7 (post-event attendees) email body now auto-appends the share URL so attendees who liked the session can post it on LinkedIn for organic reach.
- **Frontend ShowUp Score card** on Webinar Detail (visible when `attendee_count > 0`): live preview, Share on LinkedIn button (pre-fills shareActive=true text), Download, Refresh.
- **75/75 tests pass** (v1.0 + v1.1 + v1.2 + v1.3 combined).

## Backlog / Next
- P3: ShowUp Score also appears in Analytics page summary
- P3: Rotate FERNET_KEY procedure (re-encrypt on key rotation)
- P3: Move long-lived secrets to a hardware-backed KMS (HashiCorp Vault / AWS KMS) instead of env file

## v1.4 Implemented (Feb 2026)
- **Circle.so post-to-feed** (`senders.py::post_circle_space`): Admin API v2 `POST /api/admin/v2/posts` with TipTap rich-text body. Settings page exposes `circle_space_id` field + "Pick from list" picker (calls `GET /api/circle/spaces`). Webhook listener now accepts the official `community_member_created` payload shape `{community_member:{email,name,…}}` AND legacy flat `{email,name}` — backward compatible. Webhook-created registrants are auto-flagged `community_joined=true`.
- **Buzz.ai as configurable custom-endpoint provider** (`senders.py::send_buzzai`): user pastes the endpoint URL + auth header (default `Authorization: Bearer <key>`) they got from Buzz support. Routes for both email and LinkedIn channels. `buzzai_api_key` is encrypted at rest. Per-channel provider toggles: `email_provider ∈ {Brevo, Mailchimp, SendGrid, BuzzAI}` and `linkedin_provider ∈ {marketing_api, buzzai}`.
- **AGENTS.md** at `/app/AGENTS.md`: codebase architecture doc for AI coding agents (Claude, GPT, Cursor) — explains directory map, data model, channel system, endpoint index, conventions, and common tasks. Always read first when extending.
- **96/96 tests pass** (full v1.0+v1.1+v1.2+v1.3+v1.4 regression).

## Backlog / Next
- P3: Mailchimp/SendGrid LinkedIn-style provider toggle for OTHER channels (Twilio currently single-provider)
- P3: Re-encrypt all settings on FERNET_KEY rotation (documented procedure)
- P3: Buzz.ai partner API doc support — when Buzz publishes their API, wire it natively instead of custom-endpoint

## v1.5 Implemented (Feb 2026)
- **OpenAI GPT-5.4 ad-hoc post generator** (`openai_gen.py` + `routes_delivery.py`): one-click "AI Quick Post" button on Webinar Detail → modal generates a single LinkedIn or Circle.so post via OpenAI GPT-5.4 (via Emergent Universal Key), with optional native poll (question + 2-4 options) and an accompanying gpt-image-1 generated image. Image stored in `social_images_fs` GridFS, post body + poll + hashtags stored in `adhoc_posts` collection. Copy-everything button to paste into LinkedIn manually.
- **Full UI overhaul with Framer Motion animations**: dark dramatic Login page with animated burnt-orange/amber radial blobs, glassmorphism login card with float-labels, hero stats with staggered reveal. Dashboard with active-state sidebar pill (layoutId animation), KPI hover-lift, staggered row entry. WebinarDetail / ApprovalQueue / Analytics / Settings all wrap in `motion.div` page transitions. Sidebar gets a mobile slide-over with hamburger toggle. Responsive grids (1/2/4/5 columns by breakpoint).
- **Mobile-first responsiveness**: `lg:` breakpoint for sidebar collapse, `sm:` and `md:` for grid columns, every page tested at 360px / 768px / 1920px viewports.

## Backlog / Next
- P3: Predicted attendance ROI panel (per-touch lift forecast) before approving send plan
- P3: Document FERNET_KEY rotation procedure

## v1.5.1 Hotfix (Feb 2026, same day as v1.5)
- **gpt-image-1 → Nano Banana fallback**: emergentintegrations layer routes `gpt-image-1` through `/v1/chat/completions` which OpenAI moved to `/v1/responses` — returns 404. Fixed by routing the ad-hoc image generation through the proven Gemini Nano Banana model (`gemini-3.1-flash-image-preview`). Text generation still uses GPT-5.4 as designed. Result: image generation works (692KB images returned end-to-end in ~10s).
- **AI Quick Post button**: explicit inline `background: linear-gradient(…)` to override any utility-class specificity issue — burnt-orange-to-amber gradient now visible.
- **Re-verified**: 102/103 backend tests pass (1 image-gen test now passes too). Frontend end-to-end works on the live preview URL.
