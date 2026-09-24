# ShowUp.ai: Tasks & Latest Updates

_Last updated: 24 September 2026_
Priorities: **P0** = do now / blocking · **P1** = next · **P2** = soon · **P3** = later

---

## Latest updates (22–24 Sep 2026)

| Date | Commit | What changed |
|---|---|---|
| 23 Sep | several | Blog feature added (`routes_blog.py`, `Blog.jsx`, `BlogPost.jsx`, App.js routes, blog link on landing). Several partial fixes for merge-conflict markers and syntax errors. |
| 24 Sep | `7e90423` | **Netlify build fixed.** The blog pages imported modules that don't exist (`@/lib/router`, `@/lib/seo`, `@/lib/hooks`, `LoadingSkeleton`, fake react-icons) and had invalid JS; both pages were rewritten. Backend: removed the non-existent `BlogPostOut` import (it crashed startup) and fixed the doubled `/api/api/blog` paths. The public blog list no longer needs login. |
| 24 Sep | `618b3a5` | **Programmatic SEO pipeline built** (`backend/pseo.py`): keyword queue, then 1,300–1,800-word Groq drafts, then review, then publish. Daily job at 03:30 UTC. Admin endpoints `/api/seo/run`, `/drafts`, `/publish`, `/unpublish`, `/research`, `/queue`, `/generate`. Live `/api/sitemap.xml`, proxied by Netlify at `showupai.live/sitemap.xml` (the static sitemap with a broken `[slug]` URL was removed). Article + FAQPage JSON-LD on posts. GSC router mounted. `cron_jobs.yaml` reduced to one valid backup job. |
| 24 Sep | `e2addc7` | **Blog link fix.** `/blog` routes had been inside the protected app layout, so clicking Blog went to login or the admin area. They are now public, with a home link and a "Get started" button on the blog. |
| 24 Sep | next commit | **Groq model fix.** `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` were shut down by Groq on 16 Aug 2026, so blog generation and social-image text were failing. They now use `openai/gpt-oss-120b` / `gpt-oss-20b`. Added `POST /api/seo/retry` to re-queue failed keywords. |
| 24 Sep | `40e006b` | `DOCUMENTATION.md` (full project docs) and this `TASK.md` added. |

Verified: the frontend passes `CI=true npm run build`, the backend server imports cleanly, and the SEO pipeline was tested end to end (queue → draft → hidden until published → published → sitemap) against a mock DB with a mocked AI response.

---

## P0: Do now

- [ ] **Revoke the GitHub PAT** shared in chat on 23–24 Sep. GitHub → Settings → Developer settings → Fine-grained tokens. It was still active on 24 Sep.
- [ ] **Rotate the older exposed credentials**: a previous GitHub PAT and the Groq API key, both shared in an earlier chat. Update `GROQ_API_KEY` on Render after rotating.
- [ ] **Repo is public.** Anyone can read `ashussss/Wonders`. The current files contain no keys (scanned 24 Sep), but older git history wasn't checked. Consider making the repo private (GitHub → Settings → Danger zone).
- [ ] **Netlify deploy**: *Clear cache and deploy site* so commits `7e90423`, `618b3a5` and `e2addc7` go live.
- [ ] **Render env check**: confirm `GROQ_API_KEY` and `SUPERADMIN_SECRET` are set, and that the deploy log shows `Scheduler started` with no import errors.
- [ ] **Smoke test live**: `showupai.live/blog` loads publicly, `showupai.live/sitemap.xml` returns XML, and the landing-page Blog link works when logged out.
- [ ] **First posts**: run `POST /api/seo/run` with `{"count":3}`, review with `GET /api/seo/drafts`, and publish the good ones. Read each draft for accuracy before publishing.
- [ ] **Payments**: Razorpay international payments. Product details have been sent to Razorpay; awaiting their response. Note: there is **no Razorpay code in the repo yet**, so checkout/billing still has to be built once the account is approved.

## P1: Next

- [x] **Prerender blog pages** (done 24 Sep: `scripts/prerender-blog.mjs` + Netlify build hook). Needs `NETLIFY_BUILD_HOOK` set on Render.
- [ ] **Fix unverified claims in `frontend/public/index.html`** ("62%+ average attendance", "31% industry average", "uses Claude AI", "8-touch" vs the actual 11 touches). They appear in meta tags and schema on every page, including prerendered blog pages.
- [ ] **Comparison pages**: approved fact sheets per competitor (see COMPETITORS.md), then a comparison template.
- [ ] **Original data**: publish anonymised aggregate attendance data from ShowUp.ai once there is enough.
- [ ] **Off-site presence**: G2/Capterra listings, LinkedIn posts per article, community answers.
- [ ] **Draft review screen** in the admin area (`/app/admin` → Blog tab): list drafts, preview, edit, publish/unpublish, add keywords. Currently this is done with curl.
- [ ] **Search Console**: verify `showupai.live` in GSC, submit `https://showupai.live/sitemap.xml`, create a service account, and set `GSC_SERVICE_ACCOUNT_BASE64` on Render.
- [ ] **Backup cron**: if Render sleeps (free plan), add the `cron_jobs.yaml` job to cron-job.org with the real `X-API-KEY`.
- [ ] **Fix the known live bugs** noted at launch (list them here as they're found).

## P2: Soon

- [ ] **Internal linking**: add "Related posts" at the bottom of each article (same-topic published posts) and link posts from the landing page.
- [ ] **Blog cover / OG images**: reuse `image_gen.py` to render a 1200×630 card per post and set `og_image`.
- [ ] **Remove legacy SEO scripts**: `seo_generator.py`, `long_form_seo.py` and `minimal_long_form.py` write to the wrong database (`MONGO_URI` / `wonders_db`), use a deprecated model, and are superseded by `pseo.py`.
- [ ] **Tests** for `pseo.py` and the SEO endpoints in `backend/tests/` (the end-to-end test from 24 Sep can be turned into a pytest suite).
- [ ] **Repo cleanup**: `README.md` is a placeholder; update `AGENTS.md` (it still says Claude via emergentintegrations and 8 touches, but the app now uses Gemini/Groq and 11 touches); remove `THEME_*.md`, `showupai-bw-theme-finish.patch`, `vercel.json` (Netlify is the host) and the unused root `frontend/_redirects`.
- [ ] **netlify.toml**: drop the redundant second `npm install lucide-react@0.400.0` (it's already pinned in package.json).
- [ ] **UI redesign** toward the uncensored.com-style reference (white/light background, serif headings, pill buttons, numbered sections). Confirm what has already shipped and what remains.

## P3: Later

- [ ] Predicted-attendance / ROI panel per touch before approving a send plan.
- [ ] Documented `FERNET_KEY` rotation procedure (re-encrypt all settings).
- [ ] ShowUp Score summary on the Analytics page.
- [ ] Native Buzz.ai API once it's published (currently a custom endpoint).
- [ ] Programmatic landing pages beyond the blog (e.g. "webinar reminders for {industry}" templates) once the blog pipeline has proven quality.

---

## Guardrails for anyone changing the code

- Run `cd frontend && CI=true npm run build` before every frontend push; it is the exact Netlify build.
- Don't import files that don't exist. Check `frontend/src/lib` and `components` first.
- Public pages go outside `<Protected>` in `App.js`.
- Backend routers already have `prefix="/api"`, so route paths must **not** start with `/api` again.
- Never paste tokens or keys into chats or commits.
