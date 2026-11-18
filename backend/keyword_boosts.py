"""Small, exact on-page changes for queries Search Console already shows us at positions 5-40 (pulled 2026-11-15).

Each boost adds a section, FAQ items and/or a clearer title to one existing post, aimed at a query that post already
gets impressions for. It is applied by the 10-minute publish job and is safe to run any number of times:

- a section is added only while its heading is missing from the post (so it comes back if a later rewrite drops it),
- an FAQ item is added only while no FAQ on the post has the same question,
- a title is set only while the post has a different one.

The post is backed up to `blog_posts_backup` (run_id "keyword-boosts") before its first change.
Write sections without statistics: anything with "%" must carry a source link (same rule as the pipeline).
"""

import logging

from database import db
import pseo

logger = logging.getLogger("showup.keyword_boosts")

RUN_ID = "keyword-boosts"
SITE = pseo.SITE_URL

BOOSTS = [
    {
        "slug": "ewebinar-vs-easywebinar",
        "query": "what is the difference between easywebinar, ewebinar and everwebinar? (#1)",
        "faq": [(
            "What is the difference between EasyWebinar, eWebinar and EverWebinar?",
            "eWebinar is built only for automated (pre-recorded) webinars that play on a schedule, with interactions "
            "and the option for a host to answer chat live. EasyWebinar runs both live and automated webinars from one "
            "account. EverWebinar is the automated-webinar product from the makers of WebinarJam, so it suits teams "
            "that already run live sessions on WebinarJam and want evergreen replays of them.",
        )],
    },
    {
        "slug": "webinar-lead-scoring",
        "query": "how to measure the value of content downloads or webinar signups? (#5)",
        "faq": [(
            "How do you measure the value of content downloads or webinar sign-ups?",
            "Follow each lead to pipeline instead of counting sign-ups: tag the source (download, webinar registration, "
            "webinar attendance) in your CRM, then compare how often each group becomes a sales opportunity within 90 "
            "days. Score attendance and in-session actions (questions, poll answers, CTA clicks) higher than a "
            "registration or a download, because they show more intent.",
        )],
    },
    {
        "slug": "how-to-measure-webinar-roi",
        "query": "how to measure webinar success (#5), webinar roi",
        "section": (
            "How to measure webinar success",
            "Success is more than ROI. Check these in order, because each one limits the next:\n\n"
            "1. **Registration rate**: landing-page visitors who register. Low means the title, date or page needs work.\n"
            "2. **Show-up rate**: registrants who attend live. Low means the reminder sequence needs work.\n"
            "3. **Watch time**: how long attendees stay, and where they drop off.\n"
            "4. **Engagement**: questions, poll answers and chat messages per attendee.\n"
            "5. **Next step taken**: CTA clicks, demo bookings or trial starts during and after the session.\n"
            "6. **Pipeline and revenue**: opportunities and deals from attendees within 90 days.\n\n"
            f"To put a money value on these numbers, try the free [webinar ROI calculator]({SITE}/tools/webinar-roi-calculator).",
        ),
        "faq": [(
            "How do you measure webinar success?",
            "Track the funnel in order: registration rate, show-up rate, watch time, engagement, the next step attendees "
            "take, and finally pipeline and revenue from attendees. A weak number early in that list caps every number "
            "after it, so fix the earliest weak step first.",
        )],
    },
    {
        "slug": "using-ai-to-predict-attendance-likelihood",
        "query": "ai attendee analytics (#4)",
        "section": (
            "AI attendee analytics: which signals to feed the model",
            "A prediction is only as good as the signals behind it. The useful ones are already in your tools:\n\n"
            "- **Confirmation email**: opened or not, and how fast.\n"
            "- **Calendar invite**: added to calendar or not.\n"
            "- **Reminder clicks**: which reminders, on which channel.\n"
            "- **Registration lead time**: days between sign-up and the event.\n"
            "- **History**: did this person attend or watch the replay of your last webinar?\n\n"
            "Use the score to decide who gets an extra nudge (a WhatsApp or SMS message on the day), not to stop "
            "reminding anyone. Tell registrants what you track in your privacy notice.",
        ),
    },
    {
        "slug": "webinar-cta-examples",
        "query": "webinar cta examples (#19.5), webinar cta (#25.7)",
        "title": "Webinar CTA Examples: Calls to Action That Get Attendees to Click",
        "faq": [(
            "What is a webinar CTA?",
            "A webinar CTA (call to action) is the one next step you ask attendees to take, such as booking a demo, "
            "starting a trial or downloading the slides. Give one main CTA, show it on screen and in chat, and repeat it "
            "in the follow-up email.",
        )],
    },
    {
        "slug": "webinarjam-alternatives",
        "query": "webinarjam alternatives (#23)",
        "section": (
            "Compare WebinarJam side by side",
            f"For a feature-by-feature view, see [WebinarJam compared with ShowUpAI]({SITE}/compare/webinarjam). If "
            f"you are choosing between two webinar platforms, [Demio vs WebinarJam]({SITE}/blog/demio-vs-webinarjam) "
            "covers the most common pairing.",
        ),
    },
    {
        "slug": "webinar-follow-up-email-for-no-shows",
        "query": "emails for webinar no shows (#24)",
        "section": (
            "Emails for webinar no-shows: 4 ready-to-send templates",
            "Send the first one within two hours of the session ending, while the topic is still fresh.\n\n"
            "```\nSubject: Sorry we missed you - here's the replay\n\n"
            "Hi {first_name},\n\nYou registered for {webinar_title} but couldn't make it live. No problem: the full "
            "replay is here: {replay_link}\n\nThe part most people asked about starts at {timestamp}.\n\n{host_name}\n```\n\n"
            "```\nSubject: The 3 takeaways from {webinar_title}\n\n"
            "Hi {first_name},\n\nShort on time? Here are the three things we covered:\n1. {takeaway_1}\n2. {takeaway_2}\n"
            "3. {takeaway_3}\n\nWatch the replay: {replay_link}\n```\n\n"
            "```\nSubject: Replay comes down on {date}\n\n"
            "Hi {first_name},\n\nQuick heads-up: the {webinar_title} replay is available until {date}. "
            "Watch it here: {replay_link}\n```\n\n"
            "```\nSubject: Want to join the next one live?\n\n"
            "Hi {first_name},\n\nOur next session, {next_webinar_title}, is on {next_date}. One click saves your seat: "
            "{registration_link}\n```",
        ),
    },
    {
        "slug": "goldcast-vs-on24",
        "query": "goldcast vs on24 (#24)",
        "section": (
            "Goldcast vs ON24 at a glance",
            "| | Goldcast | ON24 |\n|---|---|---|\n"
            "| Built for | B2B marketing teams running branded webinars and virtual events | Large enterprises running "
            "webinar programs at scale |\n"
            "| Strength | Modern event experience and turning sessions into short content | Deep engagement analytics and "
            "a long enterprise track record |\n"
            "| Pricing | Quote-based | Quote-based |\n"
            "| Best fit | Mid-size B2B teams that want polished events fast | Enterprises with many webinars and "
            "strict reporting needs |",
        ),
        "faq": [(
            "Is Goldcast or ON24 better?",
            "Goldcast usually fits mid-size B2B marketing teams that want polished events and content repurposing without "
            "a long setup. ON24 fits large enterprises that run many webinars and need deep analytics. Neither "
            "solves no-shows by itself, so plan your reminder sequence either way.",
        )],
    },
    {
        "slug": "demio-vs-webinarjam",
        "query": "demio vs webinarjam (#29.5-31), webinarjam vs demio",
        "lead_section": (
            "Quick verdict: Demio vs WebinarJam",
            "- **Pick Demio** for B2B webinars run by a marketing team: it runs in the browser, has a clean interface "
            "and connects well to marketing tools.\n"
            "- **Pick WebinarJam** for course creators and coaches who sell on the webinar: it has built-in offers and "
            "pairs with EverWebinar for automated replays.\n"
            "- **Either way**, the platform does not get people to show up; your reminder plan does.",
        ),
    },
    {
        "slug": "crowdcast-alternatives",
        "query": "best crowdcast alternative (#33), crowdcast competitors (#35.8)",
        "title": "Crowdcast Alternatives and Competitors: The Best Options Compared",
        "faq": [(
            "Who are Crowdcast's main competitors?",
            "Common Crowdcast competitors are Zoom Webinars, StreamYard, Livestorm, Demio and BigMarker. StreamYard suits "
            "multi-platform live streaming, Livestorm and Demio suit browser-based B2B webinars, and BigMarker suits "
            "larger virtual events.",
        )],
    },
    {
        "slug": "webinar-series-vs-single-webinar",
        "query": "webinar series (#38)",
        "section": (
            "What is a webinar series?",
            "A webinar series is a set of related sessions on a shared theme, run on a regular schedule (for example, "
            "every second Thursday) under one registration or one landing page. Each episode stands on its own, but "
            "together they build a habit: people who attend one session are easier to bring back to the next, so each "
            "episode should end by inviting attendees to the next date.",
        ),
    },
    {
        "slug": "how-to-write-a-webinar-description",
        "query": "webinar title (#19)",
        "section": (
            "Need a title too?",
            f"A good description needs a title that matches it. Try the free [webinar title generator]({SITE}/tools/webinar-title-generator) "
            "for options built from your topic and audience.",
        ),
    },
]

# New posts for queries no existing post answers. Queued ahead of everything else (oldest created_at is drafted first).
PRIORITY_KEYWORDS = [
    ("hopin alternatives", "commercial",
     "Search Console shows impressions for 'hopin alternatives'. Hopin sold its events business in 2023, so readers "
     "are looking for a replacement; compare options for virtual events and webinars."),
    ("how to plan a webinar series", "informational",
     "Search Console shows impressions for 'webinar series'. Cover planning a recurring series: theme, cadence, "
     "one registration for all episodes, and bringing attendees back to the next episode."),
]
_FIRST_AT = "2025-12-31T00:00:00+00:00"  # earlier than pseo._PRIORITY_AT, so these are drafted first


def _has_heading(content: str, heading: str) -> bool:
    h = heading.strip().lower()
    return any(line.lstrip("#").strip().lower() == h for line in content.splitlines() if line.startswith("#"))


def _insert_section(content: str, heading: str, body: str) -> str:
    """Add "## heading" before the post's own FAQ / closing section if it has one, else at the end."""
    block = f"## {heading}\n\n{body.strip()}\n"
    lines = content.rstrip().splitlines()
    for i, line in enumerate(lines):
        low = line.lower()
        if line.startswith("## ") and ("faq" in low or "frequently asked" in low or "conclusion" in low or "final thoughts" in low):
            return "\n".join(lines[:i]).rstrip() + "\n\n" + block + "\n" + "\n".join(lines[i:]) + "\n"
    return content.rstrip() + "\n\n" + block


def _insert_after_intro(content: str, heading: str, body: str) -> str:
    """Add "## heading" right after the first paragraph (the post's quick answer)."""
    block = f"## {heading}\n\n{body.strip()}\n"
    parts = content.strip().split("\n\n", 1)
    if len(parts) < 2:
        return content.rstrip() + "\n\n" + block
    return parts[0] + "\n\n" + block + "\n" + parts[1] + ("\n" if not parts[1].endswith("\n") else "")


def apply_boost(post: dict, boost: dict) -> dict:
    """Return the fields to change on `post` for `boost` ({} when it is already applied)."""
    content = post.get("content") or ""
    changes = {}
    if boost.get("section") and not _has_heading(content, boost["section"][0]):
        content = _insert_section(content, *boost["section"])
        changes["content"] = content
    if boost.get("lead_section") and not _has_heading(content, boost["lead_section"][0]):
        content = _insert_after_intro(content, *boost["lead_section"])
        changes["content"] = content
    faqs = list(post.get("faq_items") or [])
    asked = {(f.get("question") or "").strip().lower() for f in faqs if isinstance(f, dict)}
    added = [{"question": q, "answer": a} for q, a in boost.get("faq", []) if q.strip().lower() not in asked]
    if added:
        changes["faq_items"] = faqs + added
    if boost.get("title") and post.get("title") != boost["title"]:
        changes["title"] = boost["title"]
        changes["seo_title"] = pseo.make_seo_title(boost["title"])
    return changes


async def queue_priority_keywords() -> int:
    added = 0
    for kw, intent, notes in PRIORITY_KEYWORDS:
        added += await pseo.add_keyword(kw, intent, notes=notes, created_at=_FIRST_AT)
    return added


async def apply_all() -> list:
    """Apply every boost that is not on its post yet. Returns the slugs changed."""
    changed = []
    for boost in BOOSTS:
        post = await db.blog_posts.find_one({"slug": boost["slug"], "published": True}, {"_id": 0})
        if not post:
            continue
        changes = apply_boost(post, boost)
        if not changes:
            continue
        if not await db.blog_posts_backup.find_one({"run_id": RUN_ID, "slug": post["slug"]}, {"_id": 1}):
            await db.blog_posts_backup.insert_one({"run_id": RUN_ID, "slug": post["slug"], "reason": "keyword boost",
                                                   "saved_at": pseo.now_iso(), "post": post})
        doc = {**post, **changes}
        pseo.clean_post_fields(doc)
        fields = list(changes) + (["word_count", "reading_time"] if "content" in changes else [])
        await db.blog_posts.update_one({"slug": post["slug"]}, {"$set": {
            **{k: doc[k] for k in fields}, "updated_at": pseo.now_iso()}})
        logger.info(f"keyword boost applied to {post['slug']}: {sorted(changes)}")
        changed.append(post["slug"])
    return changed


async def fix_seo_titles() -> list:
    """Re-make auto seo_titles that were cut mid-phrase ('... Registrants to') or are far too long. Idempotent."""
    changed = []
    async for post in db.blog_posts.find({"published": True}, {"_id": 0, "slug": 1, "title": 1, "seo_title": 1}):
        if not pseo.needs_new_seo_title(post):
            continue
        new = pseo.make_seo_title(post["title"])
        if new and new != post.get("seo_title"):
            await db.blog_posts.update_one({"slug": post["slug"]}, {"$set": {"seo_title": new}})
            changed.append(post["slug"])
    if changed:
        logger.info(f"seo_title fixed on {len(changed)} posts")
    return changed
