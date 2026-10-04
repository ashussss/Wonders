"""One-off refresh of the blog posts published before the pipeline fixes (Sept 24 - Oct 4, 2026).

Why: the first 44 posts were written from one prompt and share one skeleton (ON24 60% opener, the full 11-touch
table, a "400 registrants" worked example), several contain invented numbers or wrong sums, and 9 of them duplicate
another post's search intent. This module:

1. backs up every post it touches to `blog_posts_backup` (restore with POST /api/seo/refresh/restore),
2. rewrites each kept AI post from a per-post brief: its own worked-example scenario, only the facts that fit the
   topic, what to fix, and the content of any duplicate merged into it,
3. accepts a rewrite only if it passes the same checks new drafts must pass (no unsourced %, correct sums, no hollow
   tables, no banned phrases, brand mentioned at most twice, long enough); otherwise the post is left as it was,
4. unpublishes the merged duplicates and the hollow industry-benchmarks post (301s live in frontend/public/_redirects),
   points links to them at the post they were merged into, then relinks the site and rebuilds Netlify.

Run it with POST /api/seo/refresh {"apply": true}; it works in the background and is resumable (posts already
refreshed in the same run are skipped). Progress: GET /api/seo/refresh/status.
"""

import asyncio
import logging
import re
import uuid

from database import db
import pseo

logger = logging.getLogger("showup.refresh")

RUN_ID = "2026-10-refresh"
CADENCE_SLUG = "webinar-reminder-cadence-for-b2b-saas"  # the one post that keeps the full 11-touch table

# Fact indices refer to pseo.FACTS: 0 ON24, 1 Livestorm, 2 Demio 2022, 3 Banzai email notifications,
# 4 TwentyThree via Zoom (307 sign-ups / 58% / 42.6% frequency), 5 BigMarker via Zoom (business hours, CTA CTR),
# 6 TwentyThree State of Webinars (35% dedicated teams).
#
# scenario: the numbers this post's worked example must use, so no two posts share an example.
REFRESH = [
    {"slug": CADENCE_SLUG, "facts": [3], "scenario": "a SaaS product-launch webinar with 620 registrants, moving from a 38% to a 47% show-up rate",
     "brief": "This is the site's home for the full 11-touch sequence: keep the timing table. Remove the unsourced "
              "'12% absolute lift' and 'AI can cut churn by 15%' claims. Add the reasoning for each touch's timing and "
              "what to cut for a smaller event."},
    {"slug": "live-vs-on-demand-webinar-attendance", "facts": [0], "scenario": "1,050 registrants, 35% join live and a further 22% of no-shows watch the replay within 7 days",
     "brief": "The post claims an 11-touch sequence but shows 4 touches; drop that claim. Remove the unsourced '15-20% lift' "
              "from replays. Focus on when to push live vs when on-demand is the better product, and how to report both."},
    {"slug": "how-to-write-a-webinar-confirmation-email", "facts": [3], "scenario": "260 registrations in the first week, 31 of them not opening the confirmation within 24 hours",
     "brief": "The worked example is muddled ('41 / 40 = 1 additional attendee'); replace it. Remove 'WhatsApp reminders boost "
              "attendance by 8%'. Give three complete confirmation emails (B2B SaaS, EdTech, community event) and 12 subject lines."},
    {"slug": "webinar-poll-ideas-to-boost-engagement", "facts": [0], "scenario": "150 live attendees answering 3 polls, 112 responding to the first",
     "brief": "Keep all 30 poll questions. Remove the 11-touch table; this post is about in-session engagement, not reminders. "
              "Add how to use poll answers in the follow-up."},
    {"slug": "how-far-in-advance-to-promote-a-webinar", "facts": [5], "scenario": "three timelines: a 7-day community session, a 3-week B2B webinar and a 6-week flagship event gaining about 90 registrations a week",
     "brief": "Answer the question directly in the first paragraph (a range by event type). Replace the weak sample subject "
              "line. Remove the 11-touch table and the unsourced '10% lift'."},
    {"slug": "webinar-reminder-sms-examples", "facts": [3], "scenario": "300 registrants who opted into SMS, 45 of whom click the T-5 minute 'we're live' text",
     "brief": "The worked example has empty steps; replace it. The title promises examples: give at least 20 ready-to-paste SMS "
              "messages under 160 characters, grouped by moment (confirmation, day before, 1 hour, 5 minutes, live now, replay)."},
    {"slug": "linkedin-event-reminder-message", "facts": [], "scenario": "2,300 people who clicked 'Attend' on a LinkedIn Event, 410 of whom registered on the webinar platform",
     "brief": "Give at least 15 ready-to-paste messages: event-page updates, DMs to attendees, comment replies, and the post-event "
              "update. Remove the unsourced ON24 line and the 11-touch table. Be specific to how LinkedIn Events notify people."},
    {"slug": "circle-community-event-attendance", "facts": [], "scenario": "a 4,000-member Circle community with 180 RSVPs to a live session",
     "brief": "The title promises Circle-specific tactics; make every section about Circle: event RSVPs, space posts, Circle "
              "notifications and digests, DMs, live streams inside Circle. Include ready-to-paste Circle post templates. "
              "Remove the ON24 60% benchmark and the 11-touch table."},
    {"slug": "how-agencies-run-webinars-for-clients", "facts": [6], "scenario": "an agency running webinars for three clients in one month with 220, 90 and 510 registrants",
     "brief": "Keep the agency angle (client approval, reporting, pricing the service). Replace the unsourced '10-15% lift'. "
              "Make the email cadence consistent with the rest of the post."},
    {"slug": "how-to-get-people-to-attend-a-free-webinar", "facts": [2], "scenario": "a coach's free masterclass with 850 registrants and a 25% show-up rate",
     "brief": "The worked example math is wrong ('45% + 36% of 45% = 61%'); replace it. Focus on what is different about free "
              "events: low commitment, how to raise it (pre-work, a reason to attend live, live-only bonus)."},
    {"slug": "webinar-reminder-whatsapp-template", "facts": [], "scenario": "540 registrants who opted into WhatsApp, 85 of them replying to the T-1 day message",
     "absorb": ["webinar-reminder-whatsapp-message"],
     "brief": "The opening sentence is broken ('For B2B marketers, it offers...'); rewrite the opening. This becomes the single "
              "WhatsApp page: merge in the useful tips from the absorbed post (length, weekends, timing). Give at least 15 "
              "ready-to-paste WhatsApp templates grouped by moment, and note WhatsApp Business template-approval rules. "
              "Remove the unsourced '+4% per touch'."},
    {"slug": "how-to-increase-webinar-registrations", "facts": [4], "scenario": "a landing page with 2,000 visitors converting at 18%, improved to 24%",
     "absorb": ["webinar-registration-optimization"],
     "brief": "This becomes the single registrations page: merge in the absorbed post's useful timeline and templates. Add the "
              "subject-line and social-post copy the post promises. Keep registration and attendance as separate stages."},
    {"slug": "segmenting-webinar-registrants-for-higher-engagement", "facts": [3], "scenario": "700 registrants split into 4 segments (customers, open opportunities, cold leads, partners)",
     "brief": "Keep the segment-to-cadence mapping. Remove the 11-touch table and any line implying the ON24 figure is doubtful."},
    {"slug": "how-to-create-engaging-webinar-content", "facts": [0], "scenario": "a 45-minute session where 210 people join and 160 are still there at minute 30",
     "brief": "The worked example adds percentages that don't add up; replace it. Remove the reminder-sequence table, this post "
              "is about the content of the session (agenda, slides, interaction, demo, Q&A)."},
    {"slug": "b2b-lead-nurturing-via-webinars", "facts": [5], "scenario": "180 attendees and 95 no-shows, nurtured into sales conversations over 30 days",
     "brief": "Refocus on nurturing after and between webinars (scoring by engagement, sales handoff, content tracks). The "
              "attendance table is cut off mid-row and it cites 'internal tests' that don't exist; remove both."},
    {"slug": "using-linkedin-to-promote-b2b-webinars", "facts": [], "scenario": "a $600 LinkedIn ads budget plus organic posts driving 140 registrations",
     "absorb": ["using-linkedin-for-b2b-event-promotion", "leveraging-linkedin-for-b2b-event-marketing"],
     "brief": "This becomes the single LinkedIn promotion page: merge in the absorbed posts' useful parts (banner sizes, InMail "
              "template, teaser post sequence, ad targeting). Drop the off-topic '62% of firms experience a data-breach' and "
              "the unsourced '900 million professionals'. Leave LinkedIn Events details to the LinkedIn Events post."},
    {"slug": "how-to-write-compelling-webinar-subject-lines", "facts": [3], "scenario": "an A/B test on a 3,000-person list: subject A opened by 690, subject B by 840",
     "brief": "The title promises subject lines: give at least 25, grouped by touch (invite, confirmation, reminders, last call, "
              "replay). Remove the 11-touch table."},
    {"slug": "using-linkedin-events-to-boost-webinar-signups", "facts": [], "scenario": "1,400 LinkedIn Event attendees of whom 260 completed webinar registration",
     "brief": "Keep it specific to the LinkedIn Events feature (event page, invites, the native reminder, getting people from the "
              "event to the real registration). Remove the 11-touch table and the unsourced benchmark lift."},
    {"slug": "best-practices-for-post-webinar-followup", "facts": [5], "scenario": "230 attendees and 170 no-shows, followed up over 7 days",
     "absorb": ["best-practices-for-webinar-postevent-followup", "best-practices-for-webinar-followup-emails"],
     "brief": "This becomes the single post-webinar follow-up page: merge in the absorbed posts' email templates and timing. "
              "Separate attendee and no-show tracks; for the no-show email itself, link to the no-show post."},
    {"slug": "how-to-write-compelling-webinar-titles", "facts": [], "scenario": "two titles tested on 1,800 sends each: 54 vs 81 registrations",
     "brief": "Remove the unsourced 'outperform by roughly 2x' claim. Give at least 20 example titles before/after. Remove the "
              "reminder schedule table; this post is about titles."},
    {"slug": "calendar-invite-for-webinar-attendance", "facts": [], "scenario": "480 registrants, 300 of whom add the event to their calendar",
     "brief": "Keep the add-to-calendar code. Remove the unsourced 'up to 5 points' lift and the 38% to 55% scenario. Cover .ics "
              "fields, updating an invite, time zones and why calendar holds matter."},
    {"slug": "edtech-webinar-attendance", "facts": [2], "scenario": "a parent information session with 1,200 registrants and a teacher training webinar with 140",
     "absorb": ["webinar-attendance-for-edtech-companies"],
     "title": "How to Boost EdTech Webinar Attendance: Tactics for Schools and EdTech Teams",
     "brief": "Remove the 'By the numbers' section and the '2024' framing. This becomes the single EdTech page: merge in the "
              "absorbed post's EdTech-specific parts (school communication rules, educator schedules). The worked example is "
              "cut off; replace it. Remove unsourced numbers ('40% grading time', '10% from calendar invites', 'WhatsApp 12%')."},
    {"slug": "webinar-promotion-checklist", "facts": [5], "scenario": "a 5-week promotion plan across email, LinkedIn and a partner newsletter reaching 260 registrations",
     "absorb": ["effective-webinar-promotion-tactics"],
     "brief": "This becomes the single promotion page: keep it a checklist and merge in the absorbed post's useful tactics."},
    {"slug": "automated-webinar-reminders", "facts": [3], "scenario": "4 webinars a month with 1,600 registrants in total, saving about 6 hours of manual sends",
     "brief": "The post promises templates it doesn't have: add at least 3 full reminder messages. Replace the unsourced "
              "'10 percentage point' improvement. Cover what to automate and what to keep manual."},
    {"slug": "how-to-reduce-webinar-drop-off", "facts": [0], "scenario": "210 people join, 140 are still there at minute 30 and 95 at the end",
     "title": "How to Reduce Webinar Drop-Off During the Live Session",
     "brief": "Rewrite around in-session drop-off: the first 5 minutes, mid-session dips, slides vs demo, Q&A, and how to read "
              "your platform's attention/retention data. Leave pre-event no-shows to the attendance post (link it)."},
    {"slug": "webinar-registration-to-attendance-ratio", "facts": [0, 1, 2], "scenario": "three webinars with 190, 320 and 75 registrants and 68, 131 and 41 attendees",
     "brief": "This is a rates topic, so one comparison table of the facts is fine; link the statistics page for detail. Show "
              "how to calculate and track the ratio per event and per channel. Remove the 11-touch table."},
    {"slug": "webinar-follow-up-email-for-no-shows", "facts": [], "scenario": "310 no-shows, 74 of whom watch the replay after the follow-up",
     "absorb": ["webinar-replay-email-for-no-shows"],
     "title": "Webinar Follow-Up Email for No-Shows: Templates and Timing",
     "brief": "This becomes the single no-show page: merge in the absorbed replay-email post's useful parts (its math was wrong; "
              "do not copy it). Give at least 6 ready-to-paste no-show emails for different situations."},
    {"slug": "b2b-webinar-marketing-strategy", "facts": [4, 6], "scenario": "a quarterly program of 3 webinars feeding 45 sales meetings",
     "brief": "Make it a strategy post (program goals, topic selection, cadence, team, measurement), not another reminder post. "
              "Remove the 11-touch schedule table."},
    {"slug": "best-time-to-send-webinar-reminder-emails", "facts": [5], "scenario": "a webinar at 11:00 New York time with registrants in New York, London and Bengaluru",
     "brief": "Keep the direct answer (7-10 days, 24-48 hours, 1-2 hours). Add time-zone handling with the scenario and 3 "
              "short reminder emails."},
    {"slug": "how-to-increase-webinar-attendance", "facts": [0, 1, 2], "scenario": "950 registrants, lifting show-up from 33% to 41%",
     "brief": "This is the main attendance page. Summarise the reminder sequence in one short paragraph and link the cadence "
              "post instead of repeating the table. Remove the unsourced 'cut your lead-gen cost by 20%' and fake scarcity."},
    {"slug": "webinar-reminder-email-sequence", "facts": [3], "scenario": "270 registrants receiving a 5-email sequence",
     "brief": "Give the full text of all 5 emails. Remove 'typically three to five emails' unless labelled as a recommendation."},
    {"slug": "why-people-register-for-webinars-but-dont-attend", "facts": [2], "scenario": "560 registrants grouped by when they signed up (3 weeks out, 1 week out, the day before)",
     "brief": "Keep the reasons-first angle. For each reason, give the fix and one ready-to-paste message. Remove fake "
              "scarcity ('20 seats left')."},
]

# duplicate -> the post it was merged into (also in frontend/public/_redirects)
MERGED = {
    "using-linkedin-for-b2b-event-promotion": "using-linkedin-to-promote-b2b-webinars",
    "leveraging-linkedin-for-b2b-event-marketing": "using-linkedin-to-promote-b2b-webinars",
    "best-practices-for-webinar-postevent-followup": "best-practices-for-post-webinar-followup",
    "best-practices-for-webinar-followup-emails": "best-practices-for-post-webinar-followup",
    "webinar-replay-email-for-no-shows": "webinar-follow-up-email-for-no-shows",
    "webinar-reminder-whatsapp-message": "webinar-reminder-whatsapp-template",
    "webinar-attendance-for-edtech-companies": "edtech-webinar-attendance",
    "webinar-registration-optimization": "how-to-increase-webinar-registrations",
    "effective-webinar-promotion-tactics": "webinar-promotion-checklist",
}
# removed (hollow: its industry table is all dashes) -> where its URL now points
REMOVED = {"webinar-attendance-benchmarks-by-industry": "webinar-statistics"}

# Hand-written posts are not rewritten; only exact edits (the same change is made in backend/content/*.md).
EXACT_EDITS = {
    "webinar-statistics": [(
        "For a practical reminder plan, see [how many webinar reminders to send](https://showupai.live/blog/how-many-webinar-reminders-to-send).",
        "For a practical reminder plan, see [how many reminders to send, and when](https://showupai.live/blog/webinar-reminder-cadence-for-b2b-saas).",
    )],
}


REFRESH_PROMPT = """You are the editor of a B2B blog about webinar attendance. Rewrite the article below so it reads as
a specific, trustworthy, practitioner-written piece. It is one of about 30 posts on the same site; readers and Google
see them side by side, so it must not repeat the other posts' skeleton.

TITLE: {title}
WHAT THIS POST MUST FIX OR ADD:
{brief}

WORKED EXAMPLE: use exactly this scenario for the arithmetic, and no other example numbers:
{scenario}
Show every step with real numbers, check each sum, and start the line with "Example:".

VERIFIED FACTS you may cite (only these; each with its markdown link on the same line, phrased "<Source> reports ..."):
{facts}

THE PRODUCT (mention ShowUpAI exactly once, linked to https://showupai.live, as a practical tool for one specific
problem in this article; only these facts are true): it generates an 11-touch reminder sequence from about three weeks
before the event to after it; channels are email, LinkedIn, Facebook, Instagram, WhatsApp/SMS, Circle.so and calendar
invites; the host approves every message before it sends; it tracks attendance by channel.

PUBLISHED POSTS you may link to (2-4 links, inside sentences, descriptive anchor text; copy the URL exactly):
{related}
{absorb}
ORIGINAL ARTICLE (markdown; keep everything that is useful and correct: templates, timings, checklists, tables with
real values, links to the posts above):
<<<
{article}
>>>

ORIGINAL FAQ:
{faq}

Rules:
- 1300 to 2200 words. Markdown only: "## " / "### " headings, "- " bullets, "1. " lists, paragraphs, simple tables,
  ``` code blocks for templates. No H1, no images, no emojis, no em-dashes (use "-").
- The first paragraph is shown as the "Quick answer": answer the title directly in 2-4 sentences, without statistics
  unless the topic is about benchmarks.
- Every line containing "%" must either carry one of the fact links above or start with / contain "Example". Any other
  statistic, benchmark, lift or study must be removed, not reworded. Do not attribute anything to "research",
  "studies", "industry data" or "internal tests".
- {table_rule}
- Do not use "400 registrants", and do not open with the ON24 60% figure unless the topic is benchmarks or rates.
- No fake scarcity or fake social proof. No "delve", "unlock", "game-changer", "mastering", "dive in", "landscape".
- Every table cell must have a real value; leave a table out rather than use "-" placeholders.
- Keep the post's topic and promise; every section must serve this exact title.

Return ONLY a JSON object:
{{"content": "the full markdown article", "meta_description": "max 155 chars",
  "excerpt": "1-2 sentences, max 200 chars", "faq_items": [{{"question": "...", "answer": "2-3 sentences"}}]}}"""


def _facts_text(idx: list) -> str:
    if not idx:
        return "(none for this post: use no statistics at all, only the labelled example)"
    return "\n".join(f"- {pseo.FACTS[i]['fact']} Link: {pseo.FACTS[i]['url']} (Source: {pseo.FACTS[i]['source']})" for i in idx)


def problems(content: str, original_words: int) -> list:
    """Reasons a rewrite is not good enough to replace the live post (empty list = acceptable)."""
    out = []
    words = len((content or "").split())
    if words < max(1100, int(original_words * 0.8)):
        out.append(f"too short ({words} words)")
    out += [f"unsourced number: {x[:100]}" for x in pseo.unsourced_numbers(content)[:5]]
    out += [f"wrong arithmetic: {x}" for x in pseo.bad_math(content)[:5]]
    if pseo.empty_tables(content):
        out.append("table with empty cells")
    if pseo.banned_phrases_in(content):
        out.append(f"banned phrases: {', '.join(pseo.banned_phrases_in(content))}")
    if pseo.brand_mentions(content) > 2:
        out.append(f"ShowUpAI mentioned {pseo.brand_mentions(content)} times")
    if re.search(r"\b400 registrants\b", content or "", re.I):
        out.append("reuses the '400 registrants' example")
    return out


def retarget_links(content: str, mapping: dict) -> str:
    """Point links at merged/removed posts to the post that replaced them."""
    for old, new in mapping.items():
        content = re.sub(r"(\]\((?:https?://(?:www\.)?showupai\.live)?/blog/)" + re.escape(old) + r"/?\)",
                         lambda m: f"{m.group(1)}{new})", content or "")
    return content


async def _backup(post: dict, reason: str):
    await db.blog_posts_backup.insert_one(
        {"id": str(uuid.uuid4()), "run_id": RUN_ID, "slug": post["slug"], "reason": reason,
         "saved_at": pseo.now_iso(), "post": {k: v for k, v in post.items() if k != "_id"}})


async def _status(**kw):
    await db.blog_refresh_runs.update_one({"run_id": RUN_ID}, {"$set": {**kw, "updated_at": pseo.now_iso()}}, upsert=True)


async def _log(entry: dict):
    await db.blog_refresh_runs.update_one({"run_id": RUN_ID}, {"$push": {"log": entry}}, upsert=True)


async def refresh_one(item: dict, published: list) -> dict:
    slug = item["slug"]
    post = await db.blog_posts.find_one({"slug": slug}, {"_id": 0})
    if not post or not post.get("published"):
        return {"slug": slug, "result": "skipped", "why": "not found or not published"}
    if post.get("refreshed_run") == RUN_ID:
        return {"slug": slug, "result": "already refreshed"}
    gone = set(MERGED) | set(REMOVED)
    related = "\n".join(f"- {p['title']} - {pseo.SITE_URL}/blog/{p['slug']}"
                        for p in published if p["slug"] != slug and p["slug"] not in gone)
    absorb = ""
    for s in item.get("absorb", []):
        dup = await db.blog_posts.find_one({"slug": s}, {"_id": 0, "title": 1, "content": 1})
        if dup:
            absorb += f"\nDUPLICATE POST BEING MERGED INTO THIS ONE (take its useful, correct parts; its URL will redirect here):\nTITLE: {dup['title']}\n<<<\n{dup.get('content', '')}\n>>>\n"
    title = item.get("title") or post["title"]
    table_rule = ("Keep the full 11-touch timing table; this post is its home." if slug == CADENCE_SLUG else
                  f"Do NOT include the 11-touch reminder table; if the sequence is relevant, describe it in one sentence and link {pseo.SITE_URL}/blog/{CADENCE_SLUG}.")
    faq = "\n".join(f"- Q: {f['question']} A: {f['answer']}" for f in post.get("faq_items") or [])
    prompt = REFRESH_PROMPT.format(title=title, brief=item["brief"], scenario=item["scenario"], facts=_facts_text(item["facts"]),
                                   related=related, absorb=absorb, article=post.get("content", ""), faq=faq or "(none)",
                                   table_rule=table_rule)
    original_words = post.get("word_count") or len((post.get("content") or "").split())
    loop = asyncio.get_running_loop()
    last = []
    for attempt in range(2):
        p = prompt if not last else prompt + "\n\nYOUR PREVIOUS VERSION WAS REJECTED FOR: " + "; ".join(last) + ". Fix all of these."
        try:
            data = await loop.run_in_executor(None, pseo._groq_json, p)
        except Exception as e:
            last = [f"model error: {e}"[:200]]
            continue
        content = pseo.clean_content((data.get("content") or "").strip(), bool(data.get("faq_items")))
        content, _ = await pseo.fact_check(content)
        content = await pseo.style_fix(content)
        content = retarget_links(content, {**MERGED, **REMOVED})
        last = problems(content, original_words)
        if last:
            continue
        faqs = [f for f in (data.get("faq_items") or []) if isinstance(f, dict) and f.get("question") and f.get("answer")]
        await _backup(post, "refresh")
        update = {
            "title": title, "seo_title": pseo.make_seo_title(title), "content": content,
            "meta_description": (data.get("meta_description") or post.get("meta_description") or "")[:160],
            "excerpt": (data.get("excerpt") or post.get("excerpt") or "")[:220],
            "faq_items": faqs[:6] or post.get("faq_items") or [],
            "refreshed_run": RUN_ID, "updated_at": pseo.now_iso(),
        }
        update["seo_description"] = update["meta_description"]
        update["sources"] = [{"source": f["source"], "url": f["url"]} for f in pseo.FACTS if f["url"] in content]
        doc = {**post, **update}
        pseo.clean_post_fields(doc)
        await db.blog_posts.update_one({"slug": slug}, {"$set": {k: doc[k] for k in list(update) + ["word_count", "reading_time"]}})
        return {"slug": slug, "result": "refreshed", "words": doc["word_count"], "attempts": attempt + 1}
    return {"slug": slug, "result": "kept original", "why": "; ".join(last)[:300]}


async def run(apply: bool = True, only: list | None = None) -> dict:
    """Refresh the posts, unpublish merged/removed ones, retarget links, relink. Returns a summary."""
    if not apply:
        return {"run_id": RUN_ID, "refresh": [i["slug"] for i in REFRESH], "merged": MERGED, "removed": REMOVED,
                "exact_edits": list(EXACT_EDITS)}
    await _status(state="running", started_at=pseo.now_iso())
    published = await db.blog_posts.find({"published": True}, {"_id": 0, "slug": 1, "title": 1}).to_list(5000)
    results = []
    for item in REFRESH:
        if only and item["slug"] not in only:
            continue
        try:
            r = await refresh_one(item, published)
        except Exception as e:
            r = {"slug": item["slug"], "result": "error", "why": str(e)[:300]}
        results.append(r)
        await _log(r)
        logger.info(f"refresh {r}")

    if not only:
        for slug, edits in EXACT_EDITS.items():
            post = await db.blog_posts.find_one({"slug": slug}, {"_id": 0})
            if not post:
                continue
            content = post.get("content", "")
            for find, repl in edits:
                content = content.replace(find, repl)
            if content != post.get("content"):
                await _backup(post, "exact edit")
                await db.blog_posts.update_one({"slug": slug}, {"$set": {"content": content, "updated_at": pseo.now_iso()}})
                await _log({"slug": slug, "result": "edited"})

        for slug, target in {**MERGED, **REMOVED}.items():
            post = await db.blog_posts.find_one({"slug": slug}, {"_id": 0})
            if not post or not post.get("published"):
                continue
            await _backup(post, "merged" if slug in MERGED else "removed")
            await db.blog_posts.update_one({"slug": slug}, {"$set": {
                "published": False, "status": "merged" if slug in MERGED else "removed",
                "redirect_to": target, "updated_at": pseo.now_iso()}})
            await _log({"slug": slug, "result": f"unpublished, 301 to {target}"})

        # links on any remaining post that still point at a merged/removed URL -> its replacement
        for post in await db.blog_posts.find({"published": True}, {"_id": 0, "slug": 1, "content": 1}).to_list(5000):
            new = retarget_links(post.get("content", ""), {**MERGED, **REMOVED})
            if new != post.get("content"):
                await db.blog_posts.update_one({"slug": post["slug"]}, {"$set": {"content": new}})

        await pseo.relink_all()

    summary = {}
    for r in results:
        summary[r["result"]] = summary.get(r["result"], 0) + 1
    await _status(state="done", finished_at=pseo.now_iso(), summary=summary)
    return {"run_id": RUN_ID, "summary": summary, "results": results}


async def restore(slug: str | None = None) -> list:
    """Put back the first backup taken in this run (the pre-refresh version) for one slug, or for every slug."""
    q = {"run_id": RUN_ID, **({"slug": slug} if slug else {})}
    rows = await db.blog_posts_backup.find(q, {"_id": 0}).sort("saved_at", 1).to_list(5000)
    done, seen = [], set()
    for b in rows:
        if b["slug"] in seen:
            continue
        seen.add(b["slug"])
        await db.blog_posts.replace_one({"slug": b["slug"]}, b["post"], upsert=True)
        done.append(b["slug"])
    if done:
        await pseo.relink_all()
    return done
