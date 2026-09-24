# ShowUpAI: Project Documentation

_Last updated: 24 September 2026_

ShowUpAI (live at **https://showupai.live**) is a B2B SaaS that raises webinar attendance. A host adds a webinar, and ShowUpAI builds an AI-written, multi-channel reminder sequence. The sequence covers email, LinkedIn, Facebook, Instagram, WhatsApp/SMS, Circle.so and calendar invites, timed from three weeks before the event through to post-event follow-up. Registrants therefore keep getting well-timed nudges instead of forgetting.

This document explains how the whole system fits together: where code runs, where data lives, how each feature works and how to operate it. `AGENTS.md` is an older, AI-agent-oriented codebase map. Where the two disagree, this document is newer.

---

## 1. Architecture at a glance

```
             Visitor / Customer browser
                        │
                        ▼
  Netlify (static React app) ── showupai.live
    • serves the built React SPA
    • /sitemap.xml  ──proxy──►  Render /api/sitemap.xml
    • /*            ──►  index.html (client-side routing)
                        │  axios calls (REACT_APP_BACKEND_URL)
                        ▼
  Render (FastAPI backend) ── showup-backend-2bfj.onrender.com
    • REST API under /api
    • APScheduler: sends due touches every minute,
      writes new SEO blog drafts daily at 03:30 UTC
    • calls AI providers and delivery providers
          │                          │
          ▼                          ▼
  MongoDB (MONGO_URL/DB_NAME)   External APIs: Gemini, Groq (AI);
    • all app data               Brevo, Mailchimp, SendGrid, Buzz.ai (email);
    • GridFS for images          Meta Graph (FB/IG); Twilio (WhatsApp/SMS);
                                 LinkedIn; Circle.so; Google Search Console
```

Nothing runs on a laptop in production. Code lives in GitHub, and data lives in MongoDB.

| Piece | Where | Deploys how |
|---|---|---|
| Source code | GitHub `ashussss/Wonders` (branch `main`) | — |
| Frontend | Netlify site `extraordinary-cocada-bbf9a2`, domain showupai.live | **Manual**: Netlify, then *Clear cache and deploy site* |
| Backend | Render service `showup-backend-2bfj` | **Automatic** on every push to `main` |
| Database | MongoDB, from `MONGO_URL` + `DB_NAME` (default `showup`) | — |
| Images / files | MongoDB GridFS buckets | — |

---

## 2. Tech stack

**Backend:** Python 3.11, FastAPI, Motor (async MongoDB), APScheduler, slowapi (rate limiting), httpx, Pydantic v2, Pillow (image rendering), reportlab (PDF), ics (calendar files), cryptography/Fernet (secret encryption).

**AI:** Gemini (`gemini-3.5-flash-lite`) is the primary model for touch copy, with Groq (`openai/gpt-oss-20b`) as fallback, both in `ai.py`. Groq `openai/gpt-oss-20b` writes the text for social images. Groq `openai/gpt-oss-120b`, falling back to `openai/gpt-oss-20b`, writes SEO blog posts in `pseo.py`.

**Frontend:** React 19 (Create React App + CRACO), Tailwind CSS, shadcn/ui (Radix), Framer Motion, Recharts, Sonner toasts, lucide-react icons, React Router 7.

**Auth:** Custom JWT with bcrypt password hashing. Roles are `user`, `moderator`, `admin` and `superadmin`. All user data is scoped by `owner_id`.

---

## 3. Repository layout

```
Wonders/
├── backend/
│   ├── server.py            App factory: middleware, routers, scheduler jobs
│   ├── config.py            Env vars + TOUCH_DEFS (the 11-touch sequence)
│   ├── database.py          Mongo client, db, APScheduler, GridFS buckets
│   ├── auth_utils.py        Password hashing, JWT, get_user dependency, now_iso
│   ├── models.py            Pydantic request models (webinars, settings, blog…)
│   ├── crypto_utils.py      Fernet encryption of user API keys (enc:: prefix)
│   ├── ai.py                Touch copy, lead magnets, scheduling logic (Gemini→Groq)
│   ├── image_gen.py         Carousel / infographic / quote card / score images (Pillow)
│   ├── showup_score.py      Post-event "ShowUp Score" share image
│   ├── openai_gen.py        Ad-hoc "AI Quick Post" generator
│   ├── files.py             ICS calendar + PDF one-pager
│   ├── senders.py           Outbound delivery to every channel/provider
│   ├── integrations.py      Circle.so member sync, LinkedIn events
│   ├── pseo.py              Programmatic SEO pipeline (NEW, Sep 2026)
│   ├── routes_auth.py       Auth, admin user management, waitlist
│   ├── routes_webinars.py   Webinars, registrants, touches, lead magnets, approvals
│   ├── routes_delivery.py   Sending, files, images, Circle, schedule, email analytics
│   ├── routes_settings.py   User settings + analytics overview
│   ├── routes_blog.py       Blog + SEO pipeline endpoints + sitemap
│   ├── routes_gsc.py        Google Search Console performance endpoints
│   ├── seo_generator.py, long_form_seo.py, minimal_long_form.py
│   │                        LEGACY standalone scripts, not used by the app (see TASK.md)
│   ├── create_indexes.py    One-off Mongo index script
│   ├── tests/               pytest suites (API v1–v15 + security)
│   └── requirements.txt
├── frontend/
│   ├── public/              index.html (site JSON-LD), robots.txt, llms.txt, _redirects, icons
│   ├── src/App.js           All routes (public + protected)
│   ├── src/lib/             api.js (axios), auth.jsx, theme.jsx, utils.js
│   ├── src/components/      Layout (app sidebar), dialogs, backgrounds, ui/ (shadcn)
│   ├── src/pages/           One file per screen (see §6)
│   ├── craco.config.js      "@" alias → src, chunk splitting
│   └── package.json
├── netlify.toml             Netlify build config (base=frontend, Node 20)
├── cron_jobs.yaml           Optional backup trigger for the SEO pipeline
├── AGENTS.md                Older codebase map for AI coding agents
├── DOCUMENTATION.md         This file
├── TASK.md                  Latest updates + open tasks
└── memory/PRD.md            Product requirements + version history (v1–v1.5.1)
```

---

## 4. Core product: how a webinar campaign works

1. **Create a webinar.** The host creates it manually (`CreateWebinarDialog`) or pastes an event URL (`POST /api/webinars/fetch-from-url`). Circle.so upcoming events can also be pulled in.
2. **Send plan generated.** For each touch in `config.py::TOUCH_DEFS`, the backend calculates a send time relative to the event (`ai.compute_dynamic_schedule`). It then generates copy for every channel of that touch, with two variants (safe/polished and casual/urgent).
3. **Review and approve.** The host edits, picks variants and approves touches on the Webinar Detail page or in the Approval Queue. The LinkedIn personal channel is never auto-sent; it is copy-and-paste only.
4. **Registrants come in** through the public form `/r/:wid`, CSV import, or the Circle.so webhook. The first touch (registration confirmation, with an ICS calendar file) fires on registration.
5. **Scheduler sends.** Every minute, `routes_delivery.scheduler_tick` finds approved touches whose time has come. If auto-send is on it delivers through `senders.py`; otherwise it marks them `queued` for a manual *Send now*. Every attempt is written to the touch's `delivery_log`.
6. **Go live and after the event.** *Go live* sends an instant "we're live" message. After the event, the host marks attendance, and attendees and no-shows get different follow-ups.
7. **Measure.** Analytics shows attendance rate by channel, community-join attribution (Circle) and email analytics. The **ShowUp Score** image, attendance compared with a 30% industry baseline, can be shared on LinkedIn.

### The 11-touch sequence (`config.py::TOUCH_DEFS`)

| # | Touch | When | Default channels |
|---|---|---|---|
| 1 | Registration confirmation | On registration | email |
| 2 | Awareness post | 21 days before | email, LinkedIn page, Facebook page |
| 3 | Newsletter / insight | 19 days before | email, LinkedIn page |
| 4 | Engagement poll | 14 days before | LinkedIn page, Facebook, Instagram, Circle |
| 5 | Case study | 10 days before | email, LinkedIn page, Facebook |
| 6 | Infographic teaser | 8 days before | Instagram, LinkedIn page, Facebook |
| 7 | Urgency email | 5 days before | email, WhatsApp |
| 8 | Final warm-up | 1 day before | email, LinkedIn page, LinkedIn personal (manual) |
| 9 | Join link | 1 hour before | email, WhatsApp, Circle |
| 10 | Thank-you (attended) | After event | email |
| 11 | No-show FOMO | 2 days after | email |

### Channels and providers (`senders.py`)

| Channel | Provider | Auto-send |
|---|---|---|
| Email | Brevo, Mailchimp (Mandrill), SendGrid or Buzz.ai (`settings.email_provider`) | Yes |
| LinkedIn page | LinkedIn Marketing API or Buzz.ai | Yes |
| LinkedIn personal | — | **Never**, manual paste only |
| Facebook / Instagram | Meta Graph API (Instagram needs an image, supplied automatically) | Yes |
| WhatsApp | Twilio, with SMS fallback | Yes |
| Circle.so | Admin API v2 posts | Yes |

Users' own provider API keys are stored **encrypted** (Fernet, `enc::` prefix) in `settings`, and shown masked in the UI.

### Generated assets

- **Social images** (`image_gen.py`): 6-slide carousel, vertical infographic and quote card, rendered with Pillow using Groq-written text, in several platform sizes.
- **ShowUp Score** (`showup_score.py`): post-event share image.
- **Lead magnets** (`ai.generate_lead_magnets`): case study, snippets, and a one-pager PDF.
- **AI Quick Post** (`openai_gen.py`): one-off LinkedIn or Circle post with an optional poll and image.
- Image bytes are stored in GridFS buckets `social_images_fs` and `showup_scores_fs`.

---

## 5. Blog and programmatic SEO (added September 2026)

### What it does
It automatically writes long-form, SEO-focused articles about webinar attendance. A human approves each one before it goes live, and published posts appear on the public blog and in the sitemap without any redeploy.

### Flow
```
seo_candidates (keyword queue)
   │  daily 03:30 UTC (09:00 IST) via APScheduler, or POST /api/seo/run
   ▼
pseo.generate_post(): Groq gpt-oss-120b writes JSON:
   title, meta description, excerpt, 1300–1800-word markdown article, 4–6 FAQs,
   entities, related topics   (prompt forbids invented stats, links, fluff)
   ▼
blog_posts  (published: false, status: "draft")
   + related topics are appended to the queue, so the queue refills itself
   ▼
Human review:   GET /api/seo/drafts
   ▼
Publish:        POST /api/seo/publish {"slug": "..."}
   ▼
Live immediately at showupai.live/blog/<slug> and in showupai.live/sitemap.xml
```

- On the first run, the queue seeds itself with 20 starter keywords (`pseo.SEED_KEYWORDS`).
- Slugs are cleaned (lowercase, hyphens) and de-duplicated (`-2`, `-3`…).
- Drafts under 600 words are rejected, and the keyword is marked `failed` with the error message.
- Public endpoints only ever return **published** posts.

### Where things are
- **Code:** `backend/pseo.py` (logic), `backend/routes_blog.py` (endpoints), the job registration in `backend/server.py`, and `frontend/src/pages/Blog.jsx` + `BlogPost.jsx` (display).
- **Data:** MongoDB `seo_candidates` (queue) and `blog_posts` (drafts and posts).
- **Sitemap:** generated live by `GET /api/sitemap.xml`. Netlify proxies `showupai.live/sitemap.xml` to it through `frontend/public/_redirects`.

### Blog pages (frontend)
- `/blog`: public list of published posts, as cards.
- `/blog/:slug`: the article. It sets the title, meta, Open Graph, Twitter and canonical tags, and adds **Article + FAQPage JSON-LD**. Markdown content is rendered safely as React elements; HTML content is rendered as HTML.
- Both are **public routes**. They are not inside the logged-in app.

### Operating commands
Set `SECRET` to the value of `SUPERADMIN_SECRET` from Render.
```bash
B=https://showup-backend-2bfj.onrender.com/api; K="X-API-KEY: SECRET"
curl -X POST $B/seo/run      -H "$K" -H "Content-Type: application/json" -d '{"count":1}'   # write N drafts now (max 5)
curl        $B/seo/drafts    -H "$K"                                                            # review drafts
curl -X POST $B/seo/publish  -H "$K" -H "Content-Type: application/json" -d '{"slug":"..."}'
curl -X POST $B/seo/unpublish -H "$K" -H "Content-Type: application/json" -d '{"slug":"..."}'
curl -X POST $B/seo/research -H "$K" -H "Content-Type: application/json" -d '{"keywords":["kw1","kw2"]}'
curl        $B/seo/queue     -H "$K"                                                            # queue status
curl -X POST $B/seo/retry    -H "$K"                                                            # re-queue failed keywords
curl -X POST $B/seo/edit     -H "$K" -H "Content-Type: application/json" -d '{"slug":"...","edits":[{"find":"old text","replace":"new text"}]}'  # fix text (add "regex":true for patterns)
curl -X POST $B/seo/generate -H "$K" -H "Content-Type: application/json" -d '{"keyword":"..."}'  # one keyword now
```

### Settings (Render env)
| Var | Default | Meaning |
|---|---|---|
| `PSEO_POSTS_PER_DAY` | `4` | Drafts written per daily run |
| `PSEO_AUTO_TOPICS` | `false` | `true` lets AI-suggested related topics join the queue |
| `AUTHOR_NAME`, `AUTHOR_BIO`, `AUTHOR_URL` | see pseo.py | Byline, author box and Person schema on every post (E-E-A-T) |
| `NETLIFY_BUILD_HOOK` | — | Netlify build hook URL; publish/unpublish/edit triggers a rebuild so prerendered pages update |
| `PSEO_AUTO_PUBLISH` | `false` | `true` publishes without review (not recommended yet) |
| `PSEO_MODEL` | `openai/gpt-oss-120b` | Groq model for articles |

### Prerendering (for AI crawlers and link previews)
After `craco build`, `frontend/scripts/prerender-blog.mjs` fetches all published posts and writes full HTML to `build/blog/index.html` and `build/blog/<slug>/index.html`, with title, meta, canonical, OG/Twitter image, Article + FAQPage + Breadcrumb JSON-LD, author, sources and related links. Netlify serves these files directly, so GPTBot, PerplexityBot, ClaudeBot, LinkedIn and X see the whole article; React then mounts over it for humans. If the API is unreachable the script skips and the build still succeeds. Publishing, unpublishing or editing a published post calls `NETLIFY_BUILD_HOOK`, so pages refresh within a few minutes (`POST /api/seo/rebuild` does it manually).

### Sourced facts, author and notes
`pseo.FACTS` holds verified statistics with URLs; the writer may cite only these, as links, and they are listed under *Sources* on the post. Add keywords with first-hand notes: `{"keywords":[{"keyword":"...","notes":"what I have seen"}]}` on `/seo/research`. See `COMPETITORS.md` for the competitor research.

### Reader experience and AI-search features (added 24 Sep)
- Every post card and related-post link opens in a **new tab**.
- **Quick answer** box: the first paragraph (the direct answer) is highlighted; AI engines weigh a page's opening words most.
- **Table of contents** (3+ H2s) with stable heading anchors (`#why-people-skip`), a **reading progress bar**, **share buttons** (LinkedIn, X, WhatsApp, copy link), **Published / Updated** dates, and **Keep reading** (3 related posts by keyword overlap).
- **IndexNow**: publishing or editing a published post pings `api.indexnow.org` five minutes later (after the Netlify rebuild), which reaches Bing (used by ChatGPT search and Copilot), Yandex, Naver, Seznam and Yep. Key file: `frontend/public/<INDEXNOW_KEY>.txt`; `POST /api/seo/indexnow` resubmits every published URL.
- The prerender step also writes **`/rss.xml`** and appends a **Blog articles** list to **`/llms.txt`**.

### Links inside articles (added 24 Sep)
Every published article is guaranteed to contain (a) a link to https://showupai.live and (b) contextual links to other published posts. The writer prompt lists published articles and asks for 2-3 natural in-text links; then `pseo.autolink()` runs on publish and fills any gaps: it links the first plain mention of ShowUpAI, links another post's keyword/title phrase where it appears in a paragraph or list (never in headings, bold, code or tables; max 4; never self-links), and if fewer than 2 internal links exist adds a **Related reading** line before the third section. `pseo.relink_all()` runs on every publish, so older posts also gain links to the new one. `POST /api/seo/relink` runs it on demand. All in-article links open in a new tab.

### Brand name
The product name is **ShowUpAI** (no dot); the domain is **showupai.live**. The wordmark is "ShowUp" + orange "AI". `pseo.rebrand()` converts any "ShowUp.ai" the AI writes (and in older posts) to `BRAND_NAME` (env, default `ShowUpAI`); `POST /api/seo/relink` applies it to every stored post.

### Scheduled and hand-written posts
- `POST /api/seo/schedule` `{"slug": "...", "publish_at": "2026-09-25T10:00:00+05:30"}` schedules a draft (timezone required; `null` unschedules). `GET /api/seo/scheduled` lists the queue. A scheduler job runs every 10 minutes and publishes anything due (same path as manual publish: relink, Netlify rebuild, IndexNow).
- Hand-written posts live in `backend/content/*.md` (frontmatter: slug, title, keyword, meta_description, excerpt, publish_at; a trailing `## FAQ` with `### Question` blocks becomes FAQ schema). They are inserted as scheduled drafts on the next job run if the slug doesn't exist yet. First one: `what-is-showupai-features` (features + USP), scheduled for 25 Sep 2026 10:00 IST.

### Email capture (blog subscribers)
`frontend/src/components/SubscribeBox.jsx` collects first name + email in four places: the top of `/blog`, mid-article (before the first H2 after ~40% of the post), end of each post, and a dismissible sticky bar that appears after 45% scroll. It posts to `POST /api/blog/subscribe` (public, 5/min per IP, honeypot field, emails de-duplicated, every signup's post and placement recorded) into the `blog_subscribers` collection. Export with `GET /api/seo/subscribers.csv` (admin key) and import into Brevo/Mailchimp; `GET /api/seo/subscribers` lists them.

### Known limits
- **Render sleeping.** If Render sleeps at 03:30 UTC the daily run can be missed. `cron_jobs.yaml` has a backup HTTP trigger.

### SEO assets already in place
`robots.txt` explicitly allows AI crawlers; `llms.txt` exists; `index.html` carries site-wide JSON-LD; the Search Console router (`routes_gsc.py`) is mounted but needs `GSC_SERVICE_ACCOUNT_BASE64` to work.

---

## 6. Frontend routes (`src/App.js`)

**Public:** `/` Landing · `/login` · `/register` · `/waitlist` · `/r/:wid` public registration form · `/blog` · `/blog/:slug`

**Protected (login required, inside the sidebar `Layout`):**
| Route | Page | Purpose |
|---|---|---|
| `/app` | Dashboard | KPIs + webinars table |
| `/app/webinars/:id` | WebinarDetail | Send plan, registrants, lead magnets, images, score |
| `/app/approvals` | ApprovalQueue | Approve copy across webinars |
| `/app/analytics` | Analytics | Attendance by channel, community attribution |
| `/app/schedule` | Schedule | Calendar of upcoming sends |
| `/app/library` | ContentLibrary | All generated content |
| `/app/email` | EmailAnalytics | Email performance |
| `/app/settings` | Settings | Provider API keys + channel toggles |
| `/app/admin` | AdminDashboard | Users, roles, waitlist (admins) |

`/dashboard` redirects to `/app`. The frontend calls the backend through `src/lib/api.js`, whose base URL is `REACT_APP_BACKEND_URL` or the Render URL, plus `/api`. The JWT is taken from `localStorage.showup_token`.

---

## 7. API reference (all under `/api`)

**Auth and admin (`routes_auth.py`):** `POST /register`, `POST /login`, `GET /me`, `GET /admin/stats`, `GET /admin/users`, `PATCH /admin/users/{uid}/role`, `DELETE /admin/users/{uid}`, `POST /admin/invite`, `POST /admin/make-superadmin`, `POST /waitlist`, `GET /waitlist/count`, `GET /admin/waitlist`

**Webinars (`routes_webinars.py`):** `GET|POST /webinars`, `GET|PATCH|DELETE /webinars/{wid}`, `POST /webinars/fetch-from-url`, `GET /webinars/{wid}/registrants`, `POST /webinars/{wid}/register` (public, 10/min), `POST /webinars/{wid}/registrants/import`, `POST /webinars/{wid}/webhooks/circle` (public, 60/min), `PATCH /registrants/{rid}`, `POST /webinars/{wid}/mark-attendance`, `GET /webinars/{wid}/touches`, `PATCH /touches/{tid}`, `POST /touches/{tid}/regenerate`, `POST /webinars/{wid}/regenerate-all`, `GET /webinars/{wid}/lead-magnets`, `POST /webinars/{wid}/lead-magnets/regenerate`, `PATCH /lead-magnets/{lmid}`, `GET /approval-queue`, `GET /content-library`, `GET /webinars/{wid}/ai-insights`, `POST|DELETE /webinars/{wid}/banner`, `GET /webinars/{wid}/banner.img`, `GET /circle/upcoming-events`

**Delivery and files (`routes_delivery.py`):** `GET /webinars/{wid}/calendar.ics`, `GET /webinars/{wid}/one-pager.pdf`, `POST /webinars/{wid}/social-image/generate`, `GET /webinars/{wid}/social-image.png`, `POST /webinars/{wid}/carousel/generate`, `GET|POST /webinars/{wid}/adhoc-post[/generate]`, `GET /webinars/{wid}/adhoc-image.png`, `POST /webinars/{wid}/showup-score/generate`, `GET /webinars/{wid}/showup-score[.png]`, `POST /circle/sync`, `GET /circle/spaces`, `GET /circle/diagnose`, `GET /circle/members`, `GET /linkedin/events`, `POST /test-send/{channel}`, `POST /touches/{tid}/send-now`, `GET /schedule`, `GET /email-analytics`, `POST /webinars/{wid}/go-live`, `POST /webinars/{wid}/post-webinar`

**Settings (`routes_settings.py`):** `GET|PATCH /settings`, `GET /analytics/overview`

**Blog and SEO (`routes_blog.py`):** public: `GET /blog`, `GET /blog/{slug}`, `GET /sitemap.xml`. Admin key required: `POST /seo/research`, `POST /seo/run`, `POST /seo/generate`, `GET /seo/queue`, `GET /seo/drafts`, `POST /seo/publish`, `POST /seo/unpublish`. Superadmin login required: `POST /blog`, `PUT /blog/{slug}`, `POST /blog/generate`, `GET /blog/{slug}/aeo-analysis`, `GET /blog/{slug}/geo-entities`

**Search Console (`routes_gsc.py`, superadmin):** `POST /seo/gsc-fetch`, `GET /seo/performance`, `POST /seo/manual-gsc-trigger`

---

## 8. Data model (MongoDB collections)

| Collection | Holds |
|---|---|
| `users` | id, email, name, bcrypt password, role, created_at |
| `webinars` | owner_id, title, description, speaker, audience, starts_at, timezone, links, status, enabled touches |
| `touches` | One per touch per webinar: schedule, AI copy (per channel, 2 variants), overrides, approval + send status, delivery_log |
| `registrants` | webinar_id, name, email (deduped), phone, source, attended, community_joined |
| `lead_magnets` | AI case study, snippets, one-pager outline, edits, approval |
| `settings` | Per-user provider config; secrets encrypted |
| `social_images`, `showup_scores` | Metadata pointing to GridFS files |
| `adhoc_posts` | AI Quick Post outputs |
| `community_members` | Synced Circle.so members |
| `waitlist` | Waitlist sign-ups |
| `seo_candidates` | SEO keyword queue: keyword, intent, status (pending/processing/drafted/failed), slug, error |
| `blog_posts` | Blog posts: slug (unique), title, SEO fields, content, faq_items, entities, related_topics, reading_time, word_count, published, status, published_at |
| `seo_performance` | Search Console metrics (once GSC is configured) |

---

## 9. Environment variables

**Render (backend):**
| Var | Required | Purpose |
|---|---|---|
| `MONGO_URL`, `DB_NAME` | Yes | Database connection |
| `JWT_SECRET` | Yes | Login token signing |
| `FERNET_KEY` | Yes | Encrypts user API keys; the app refuses to start without it |
| `GROQ_API_KEY` | Yes | AI fallback, image text, SEO articles |
| `GEMINI_API_KEY` | Recommended | Primary AI for touch copy |
| `SUPERADMIN_SECRET` | Yes (for SEO) | The `X-API-KEY` for SEO and cron endpoints |
| `CORS_ORIGINS` | Recommended | Allowed frontend origins (all origins allowed if unset) |
| `PUBLIC_BACKEND_URL` | Yes | Public URL used in links, images and ICS files |
| `PSEO_POSTS_PER_DAY`, `PSEO_AUTO_PUBLISH`, `PSEO_MODEL` | Optional | SEO pipeline tuning |
| `GSC_SERVICE_ACCOUNT_BASE64` | Optional | Google Search Console access |
| `CLAUDE_MODEL`, `JWT_ALG` | Optional | Legacy / defaults |

**Netlify (frontend):** `REACT_APP_BACKEND_URL`, which falls back to the Render URL if unset.

Users' own channel keys (Brevo, Meta, Twilio, Circle…) are **not** env vars. Each user enters them on the Settings page, and they are stored encrypted per user.

---

## 10. Deploying

1. Push to `main` on GitHub.
2. **Backend:** Render redeploys automatically. Check *Logs* for `Scheduler started`.
3. **Frontend:** in Netlify, go to *Deploys*, then *Trigger deploy*, then **Clear cache and deploy site**. The build runs `npm install --legacy-peer-deps` and `craco build` in `frontend/`, publishing `frontend/build`.
4. Smoke test: `/`, `/blog`, `/login`, `/sitemap.xml`.

### Local development
```bash
# backend
cd backend && pip install -r requirements.txt
export MONGO_URL=... DB_NAME=showup JWT_SECRET=dev FERNET_KEY=$(python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())") GROQ_API_KEY=...
uvicorn server:app --reload --port 8000

# frontend
cd frontend && npm install --legacy-peer-deps
REACT_APP_BACKEND_URL=http://localhost:8000 npm start
```
Always run `CI=true npm run build` before pushing frontend changes. It is exactly what Netlify runs, and it catches bad imports.

---

## 11. Security notes

- All user-data queries are scoped by `owner_id`. IDOR fixes and security tests are in `backend/tests/test_security.py`.
- User provider secrets are encrypted at rest and masked in API responses.
- Public endpoints are rate-limited (registration 10/min, Circle webhook 60/min).
- SEO and cron endpoints require `X-API-KEY = SUPERADMIN_SECRET`, and are disabled if the secret is unset.
- Never paste tokens (GitHub PATs, API keys) into chats or commits. Rotate any that have been exposed (see TASK.md).

---

## 12. Conventions for changes

- Every backend route is prefixed `/api`.
- Never return raw secrets; use the masking helpers.
- Match existing patterns (`routes_webinars.py`, `Dashboard.jsx`) when adding routes or pages.
- Only import things that exist: use the `@/` alias for `frontend/src`, and check a file exists before importing it.
- Public marketing pages go **outside** the `<Protected>` route block in `App.js`.
- Add or extend tests in `backend/tests/` for new backend features.
