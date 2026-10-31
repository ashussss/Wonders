# Link building (Growth Engine)

Code: `backend/growth_engine/link_engine.py`. Admin page: `/app/links`. API: `/api/growth/links*`.

- Curated catalog of trusted sites (Product Hunt, G2, Capterra, SaaSHub, AlternativeTo, Crunchbase,
  BetaList, Indie Hackers, Substack, Medium, LinkedIn articles, Qwoted, Featured, Help a B2B Writer,
  SourceBottle, Reddit, Quora). Stored in Mongo `growth_links`.
- `growth-links-weekly` (Mon 03:00 UTC): drafts the next `GROWTH_LINKS_PER_WEEK` (default 3) one-time
  sites by priority, plus a fresh Substack / Medium / LinkedIn article draft from the newest blog post.
- On demand: paste a journalist query, a community question or a guest-post target; it drafts an answer/pitch.
- `growth-links-verify` (Sun 05:00 UTC): GETs each submitted/live URL and records whether the link to
  showupai.live exists and whether it is followed. submitted -> live, live -> lost.

Anti-spam contract: the engine never submits, posts or emails anywhere. A human approves each draft and
submits it from their own account. No paid links, link swaps, PBNs or comment link drops. Each site gets
its own wording. `tests/test_growth_links.py::test_engine_never_sends_anything` guards this.

## Question finder (`question_finder.py`)
`growth-questions-daily` (02:30 UTC / 08:00 IST) reads public Reddit search RSS and Hacker News (Algolia)
for recent webinar-attendance questions, scores them, and drafts `GROWTH_QUESTIONS_PER_DAY` (default 3)
answers into the queue (`source: finder`, `asset: answer`). One draft per thread, ever. Read-only GETs;
the owner posts from their own account. Tune with `GROWTH_QUESTION_SUBREDDITS` / `GROWTH_QUESTION_QUERIES`.

## Autofill helper (`frontend/src/lib/autofill.js`)
A "ShowUp Fill" bookmarklet on /app/links. "Copy for autofill" puts the approved draft on the clipboard; the
bookmarklet fills matching empty fields on the submit form and outlines them. It never signs up, never
submits, and skips password, email, personal-name, file and hidden fields.
