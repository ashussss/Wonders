"""Programmatic SEO pipeline for ShowUpAI.

Flow:  keyword queue (seo_candidates) -> AI long-form draft (blog_posts, published=False)
       -> human review -> publish -> appears on /blog and in /api/sitemap.xml

Everything lives in MongoDB (same MONGO_URL / DB_NAME as the rest of the app).
"""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

from database import db

logger = logging.getLogger("showup.pseo")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
PSEO_MODEL = os.environ.get("PSEO_MODEL", "openai/gpt-oss-120b")
PSEO_FALLBACK_MODEL = os.environ.get("PSEO_FALLBACK_MODEL", "openai/gpt-oss-20b")
PSEO_POSTS_PER_DAY = int(os.environ.get("PSEO_POSTS_PER_DAY", "1"))
PSEO_AUTO_TOPICS = os.environ.get("PSEO_AUTO_TOPICS", "false").lower() == "true"
# Auto-publishing: each new draft that passes the quality gate gets the next free publish slot (IST)
PSEO_AUTO_SCHEDULE = os.environ.get("PSEO_AUTO_SCHEDULE", "true").lower() == "true"
PSEO_PUBLISH_TIMES_IST = [t.strip() for t in os.environ.get("PSEO_PUBLISH_TIMES_IST", "10:00,13:00,16:00,19:00").split(",") if t.strip()]
# Publishing cadence: a steady, human-looking rhythm instead of bursts at identical clock times.
PSEO_MAX_PUBLISH_PER_DAY = int(os.environ.get("PSEO_MAX_PUBLISH_PER_DAY", "1"))
PSEO_PUBLISH_JITTER_MIN = int(os.environ.get("PSEO_PUBLISH_JITTER_MIN", "90"))  # random 0..N min added to a base time
PSEO_SCHEDULE_HORIZON_DAYS = int(os.environ.get("PSEO_SCHEDULE_HORIZON_DAYS", "14"))
# Topic dedup: skip queued keywords whose search intent an existing post already covers.
PSEO_DEDUP = os.environ.get("PSEO_DEDUP", "true").lower() == "true"
AUTHOR_NAME = os.environ.get("AUTHOR_NAME", "Ashutosh Kumar Singh")
AUTHOR_BIO = os.environ.get(
    "AUTHOR_BIO",
    "B2B marketer with 13+ years across SEO, content and demand generation. "
    "Builds ShowUpAI to help webinar hosts turn more registrants into live attendees.",
)
AUTHOR_URL = os.environ.get("AUTHOR_URL", "")  # e.g. LinkedIn profile

# Verified, sourced facts the writer may cite (with a link). Add more only after checking the primary source.
FACTS = [
    {
        "fact": "ON24's 2026 Digital Engagement Benchmarks (2025 platform data) report an average registration-to-attendee "
                "conversion of 60% and an average engagement time of 49 minutes; Q4 2025 averaged 254 attendees per "
                "webinar, up from 219 a year earlier.",
        "source": "ON24", "url": "https://www.on24.com/blog/key-takeaways-from-the-webinar-benchmarks-report/",
    },
    {
        "fact": "Livestorm reports an average webinar show-up rate of 51.3% across industries on its platform, and says "
                "browser-based webinar platforms showed a 53% higher attendance rate than traditional (download-based) ones.",
        "source": "Livestorm", "url": "https://livestorm.co/blog/boost-webinar-attendance-rate",
    },
    {
        "fact": "Demio (Banzai) reported that its customers saw an average live-session attendance rate of 38% in 2022, "
                "with February and March highest at 41%.",
        "source": "Banzai / Demio", "url": "https://www.banzai.io/2023-webinar-stats-for-marketers",
    },
    {
        "fact": "Banzai's analysis of about 800,000 webinars run on Demio found that attendance rate increases when brands "
                "use email notifications, regardless of company size.",
        "source": "Banzai", "url": "https://www.banzai.io/2024-webinar-statistics",
    },
    {
        "fact": "Zoom's webinar statistics roundup cites TwentyThree data: webinars average 307 sign-ups with a 58% "
                "attendance rate, and 42.6% of organisations increased their webinar frequency year over year.",
        "source": "Zoom (citing TwentyThree)", "url": "https://www.zoom.com/en/blog/webinar-statistics/",
    },
    {
        "fact": "Zoom's webinar statistics roundup cites BigMarker data: webinars during business hours see 50-55% response "
                "rates versus 25-30% outside business hours; the average webinar CTA click-through rate is about 8.74% "
                "(top performers 17.5%); high-performing webinars averaged 375 registrants and 214 attendees.",
        "source": "Zoom (citing BigMarker)", "url": "https://www.zoom.com/en/blog/webinar-statistics/",
    },
    {
        "fact": "TwentyThree's State of Webinars 2025 found that 35% of organisations have dedicated webinar program "
                "managers or teams.",
        "source": "TwentyThree", "url": "https://www.twentythree.com/state-of-webinars-2025",
    },
]
PSEO_AUTO_PUBLISH = os.environ.get("PSEO_AUTO_PUBLISH", "false").lower() == "true"
SITE_URL = "https://showupai.live"

# Starter keyword bank. Seeded once; add more via POST /api/seo/research.
SEED_KEYWORDS = [
    ("how to increase webinar attendance", "informational"),
    ("average webinar attendance rate", "informational"),
    ("webinar reminder email sequence", "informational"),
    ("why people register for webinars but don't attend", "informational"),
    ("best time to send webinar reminder emails", "informational"),
    ("webinar no-show rate", "informational"),
    ("webinar reminder sms", "informational"),
    ("how many webinar reminders to send", "informational"),
    ("webinar attendance software", "commercial"),
    ("zoom webinar attendance tips", "informational"),
    ("linkedin posts to promote a webinar", "informational"),
    ("webinar follow up email for no shows", "informational"),
    ("b2b webinar marketing strategy", "informational"),
    ("webinar registration to attendance ratio", "informational"),
    ("how to reduce webinar drop off", "informational"),
    ("automated webinar reminders", "commercial"),
    ("webinar promotion checklist", "informational"),
    ("edtech webinar attendance", "informational"),
    ("webinar reminder whatsapp message", "informational"),
    ("calendar invite for webinar attendance", "informational"),
    # long-tail / niche angles with less competition
    ("webinar reminder whatsapp template", "informational"),
    ("how to get people to attend a free webinar", "informational"),
    ("webinar attendance for edtech companies", "informational"),
    ("how agencies run webinars for clients", "informational"),
    ("circle community event attendance", "informational"),
    ("linkedin event reminder message", "informational"),
    ("webinar reminder sms examples", "informational"),
    ("webinar replay email for no shows", "informational"),
    ("how far in advance to promote a webinar", "informational"),
    ("webinar attendance benchmarks by industry", "informational"),
    ("webinar poll ideas to boost engagement", "informational"),
    ("how to write a webinar confirmation email", "informational"),
    ("live vs on demand webinar attendance", "informational"),
    ("webinar reminder cadence for b2b saas", "informational"),
    ("how to reduce zoom webinar no shows", "informational"),
    ("webinar attendance tracking", "informational"),
    # batch 3 (2026-10-06): the first 36 were all used by 5 Oct, which stopped daily posts
    # competitor "alternative" searches first (high buying intent)
    ("best tools to reduce webinar no shows", "commercial"),
    ("demio alternatives", "commercial"),
    ("livestorm alternatives", "commercial"),
    ("webinarjam alternatives", "commercial"),
    ("zoom webinar alternatives", "commercial"),
    ("gotowebinar alternatives", "commercial"),
    ("on24 alternatives", "commercial"),
    ("ewebinar alternatives", "commercial"),
    ("easywebinar alternatives", "commercial"),
    ("airmeet alternatives", "commercial"),
    ("webinarninja alternatives", "commercial"),
    ("bigmarker alternatives", "commercial"),
    ("webinar late joiner email", "informational"),
    ("last minute webinar reminder message", "informational"),
    ("webinar countdown email", "informational"),
    ("webinar email subject lines", "informational"),
    ("webinar invitation email for b2b", "informational"),
    ("webinar thank you email for attendees", "informational"),
    ("webinar lead nurturing sequence", "informational"),
    ("how to qualify webinar leads", "informational"),
    ("webinar to sales pipeline conversion", "informational"),
    ("how to measure webinar roi", "informational"),
    ("webinar kpis to track", "informational"),
    ("webinar landing page conversion tips", "informational"),
    ("webinar registration form best practices", "informational"),
    ("webinar title ideas that get registrations", "informational"),
    ("best day of the week to host a webinar", "informational"),
    ("best time of day to host a webinar", "informational"),
    ("how long should a webinar be", "informational"),
    ("webinar timezone strategy for global audiences", "informational"),
    ("recurring webinar series attendance", "informational"),
    ("webinar q&a best practices", "informational"),
    ("product demo webinar best practices", "informational"),
    ("customer onboarding webinars for saas", "informational"),
    ("webinar co-marketing with partners", "informational"),
    ("how to repurpose a webinar recording", "informational"),
    ("webinar speaker prep checklist", "informational"),
    ("webinar attendance incentives", "informational"),
    ("online workshop attendance for course creators", "informational"),
    ("masterclass attendance for coaches", "informational"),
    ("webinar confirmation page ideas", "informational"),
    ("webinar reminder automation for small teams", "commercial"),
]


BRAND = os.environ.get("BRAND_NAME", "ShowUpAI")
# "ShowUp.ai", "Showup.ai", "SHOWUP.AI", "ShowUp AI" ... -> BRAND (never touches showupai.live or emails)
_OLD_BRAND = re.compile(r"(?<![@/\w.])show\s?up\.ai\b(?!\.live)", re.I)


def rebrand(t):
    if not isinstance(t, str):
        return t
    return _OLD_BRAND.sub(BRAND, t)


_CHAR_MAP = {
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u00ad": "",
    "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u200b": "",
}


def normalize_text(t: str) -> str:
    if not isinstance(t, str):
        return t
    for k, v in _CHAR_MAP.items():
        t = t.replace(k, v)
    return rebrand(t)


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u20E3]")


def clean_content(content: str, has_faq: bool) -> str:
    c = _EMOJI.sub("", normalize_text(content or "")).strip()
    # drop a leading "Direct answer" / "Quick answer" heading, keep the paragraph
    c = re.sub(r"^#{1,4}\s*(direct|quick|short)\s+answer\s*\n+", "", c, flags=re.I)
    if has_faq:
        # FAQs are rendered separately from faq_items; remove an in-body FAQ section at the end
        c = re.sub(r"\n(?:-{3,}\s*\n)?\s*#{1,4}\s*(faqs?|frequently asked questions)\b[\s\S]*$", "", c, flags=re.I)
    c = re.sub(r"\n-{3,}\s*$", "", c).strip()
    return c


def make_seo_title(title: str, limit: int = 60) -> str:
    """'<title> | ShowUpAI' when it fits, else the title alone, cut at a word boundary only if still too long."""
    title = (title or "").strip()
    branded = f"{title} | {BRAND}"
    if len(branded) <= limit:
        return branded
    if len(title) <= 70:
        return title
    return title[:70].rsplit(" ", 1)[0].rstrip(" :-,|")


_BLOG_LINK = re.compile(r"\[([^\]]+)\]\((?:https?://(?:www\.)?showupai\.live)?/blog/([a-z0-9-]+)/?\)")


def strip_unknown_blog_links(content: str, known_slugs: set) -> str:
    """Unwrap markdown links to /blog/<slug> pages that don't exist (the writer sometimes invents slugs)."""
    return _BLOG_LINK.sub(lambda m: m.group(0) if m.group(2) in known_slugs else m.group(1), content or "")


_EXAMPLE_WORDS = re.compile(r"\b(example|e\.g\.|assume|assuming|hypothetical|illustrative|say you|if you|suppose)\b", re.I)


def unsourced_numbers(content: str) -> list:
    """Lines that state a percentage without one of the verified FACTS links and without being labelled an example."""
    urls = [f["url"] for f in FACTS]
    out, in_code = [], False
    for line in (content or "").split("\n"):
        t = line.strip()
        if t.startswith("```"):
            in_code = not in_code
            continue
        if in_code or "%" not in t or any(u in t for u in urls) or _EXAMPLE_WORDS.search(t):
            continue
        out.append(t[:160])
    return out


_NUM = r"(\d[\d,]*(?:\.\d+)?)"
_SUM = re.compile(_NUM + r"\s*(%?)\s*([x\u00d7*+/-])\s*" + _NUM + r"\s*(%?)\s*=\s*" + _NUM + r"\s*(%?)")


def bad_math(content: str) -> list:
    """Simple 'A op B = C' sums (x, *, +, -, /, with % on B meaning a rate) whose result is wrong."""
    out = []
    for m in _SUM.finditer(content or ""):
        a, ap, op, b, bp, c, cp = m.groups()
        try:
            a, b, c = (float(v.replace(",", "")) for v in (a, b, c))
        except ValueError:
            continue
        if op in "x\u00d7*":
            want = a * b / 100 if (bp and not ap and not cp) else a * b
        elif op == "+":
            want = a + b
        elif op == "-":
            want = a - b
        else:
            if b == 0:
                continue
            want = a / b * 100 if (cp and not ap and not bp) else a / b
        if abs(want - c) > max(1.0, abs(want) * 0.02):
            out.append(m.group(0).strip())
    return out


def empty_tables(content: str) -> int:
    """Count markdown tables whose body cells are mostly blank or dashes (a hollow table)."""
    n, rows = 0, []
    for line in (content or "").split("\n") + [""]:
        if line.strip().startswith("|"):
            rows.append(line)
            continue
        if rows:
            body = [r for r in rows[1:] if not re.match(r"^\s*\|?\s*:?-{2,}", r)]
            cells = [c.strip() for r in body for c in r.strip().strip("|").split("|")[1:]]
            if cells and sum(c in ("", "-", "--", "\u2014", "\u2013", "n/a", "N/A") for c in cells) / len(cells) > 0.5:
                n += 1
            rows = []
    return n


def clean_post_fields(doc: dict) -> dict:
    """Normalise every text field of a post in place and return it."""
    for k in ("title", "seo_title", "meta_description", "seo_description", "excerpt", "author", "author_bio"):
        if isinstance(doc.get(k), str):
            doc[k] = normalize_text(doc[k]).strip()
    faqs = [
        {"question": normalize_text(f.get("question", "")), "answer": normalize_text(f.get("answer", ""))}
        for f in (doc.get("faq_items") or []) if isinstance(f, dict) and f.get("question")
    ]
    doc["faq_items"] = faqs
    t = doc.get("title") or ""
    if t and doc.get("seo_title") in (None, "", f"{t} | {BRAND}"[:70], f"{t} | ShowUpAI"[:70], t):
        doc["seo_title"] = make_seo_title(t)
    doc["content"] = clean_content(doc.get("content", ""), bool(faqs))
    if doc.get("author") in (None, "", f"{BRAND} Team"):
        doc["author"], doc["author_bio"], doc["author_url"] = AUTHOR_NAME, AUTHOR_BIO, AUTHOR_URL
    doc["word_count"] = len(doc["content"].split())
    doc["reading_time"] = max(1, round(doc["word_count"] / 200))
    seen, srcs = set(), []
    for f in FACTS:  # list only sources actually linked in the article
        if f["url"] in doc["content"] and f["url"] not in seen:
            seen.add(f["url"])
            srcs.append({"source": f["source"], "url": f["url"]})
    doc["sources"] = srcs
    return doc


_INLINE_SPLIT = re.compile(r"(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`)")
_LEAD_WORDS = re.compile(r"^(how (to|many|far in advance to|do i|can i)|why|what is( the)?|what are|best|when to|the)\s+", re.I)


def _anchor_candidates(keyword: str, title: str):
    c = []
    k = (keyword or "").strip().lower()
    if k:
        c.append(k)
        stripped = _LEAD_WORDS.sub("", k).strip()
        if stripped != k and len(stripped.split()) >= 2:
            c.append(stripped)
    t = (title or "").split(":")[0].strip().lower()
    if t and len(t.split()) >= 3:
        c.append(t)
    seen, out = set(), []
    for x in sorted(c, key=len, reverse=True):
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _link_first(content: str, phrase: str, url: str) -> tuple:
    """Link the first plain-text occurrence of phrase (in paragraphs/list items only). Returns (content, done)."""
    pat = re.compile(r"(?<![\w/])(" + re.escape(phrase) + r")(?![\w])", re.I)
    lines = content.split("\n")
    in_code = False
    for li, line in enumerate(lines):
        t = line.strip()
        if t.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not t or t.startswith("#") or t.startswith("|"):
            continue
        parts = _INLINE_SPLIT.split(line)
        for pi, part in enumerate(parts):
            if pi % 2 == 1:  # existing link / bold / code
                continue
            m = pat.search(part)
            if m:
                parts[pi] = part[:m.start()] + f"[{m.group(1)}]({url})" + part[m.end():]
                lines[li] = "".join(parts)
                return "\n".join(lines), True
    return content, False


def autolink(content: str, slug: str, others: list, max_internal: int = 4) -> str:
    """Guarantee a link to showupai.live and contextual links to other published posts.
    others: [{"slug", "title", "keyword"}] of published posts (self excluded here). Idempotent."""
    home = SITE_URL
    c = strip_unknown_blog_links(content or "", {o["slug"] for o in others if o.get("slug")} | {slug})
    # 1) ShowUpAI -> homepage
    if not re.search(r"\]\(" + re.escape(home) + r"/?\)", c):
        c, done = _link_first(c, BRAND, home)
        if not done:
            c = c.rstrip() + f"\n\nWant more of your registrants to actually show up? [Try {BRAND}]({home})."
    # 2) contextual internal links
    others = [o for o in others if o.get("slug") and o["slug"] != slug]
    linked = {o["slug"] for o in others if f"/blog/{o['slug']})" in c}
    for o in others:
        if len(linked) >= max_internal:
            break
        if o["slug"] in linked:
            continue
        url = f"{home}/blog/{o['slug']}"
        for phrase in _anchor_candidates(o.get("keyword", ""), o.get("title", "")):
            c, done = _link_first(c, phrase, url)
            if done:
                linked.add(o["slug"])
                break
    # 3) fallback: guarantee at least 2 internal links with a "Related reading" line after the 2nd section
    if len(linked) < 2 and others:
        words = set(re.findall(r"[a-z]{4,}", (slug or "").replace("-", " ")))
        ranked = sorted(
            [o for o in others if o["slug"] not in linked],
            key=lambda o: -len(words & set(re.findall(r"[a-z]{4,}", (o.get("keyword") or o.get("title") or "").lower()))),
        )[: 2 - len(linked)]
        if ranked and "**Related reading:**" not in c:
            line = "**Related reading:** " + " · ".join(f"[{o['title']}]({home}/blog/{o['slug']})" for o in ranked)
            heads = [m.start() for m in re.finditer(r"^## ", c, re.M)]
            if len(heads) >= 3:
                c = c[:heads[2]] + line + "\n\n" + c[heads[2]:]
            else:
                c = c.rstrip() + "\n\n" + line
    return c


async def relink_all(changed_slug: str = "") -> int:
    """Clean + rebrand every post, and re-run autolink on published ones so older posts also link to newer ones.
    Returns number of posts changed."""
    docs = await db.blog_posts.find({}, {"_id": 0}).to_list(5000)
    pubs = [d for d in docs if d.get("published")]
    meta = [{"slug": p["slug"], "title": rebrand(p.get("title", "")), "keyword": p.get("keyword", "")} for p in pubs]
    n = 0
    for d in docs:
        before = {k: d.get(k) for k in d}
        clean_post_fields(d)
        if d.get("published"):
            d["content"] = autolink(d.get("content", ""), d["slug"], meta)
        changed = {k: v for k, v in d.items() if before.get(k) != v and k not in ("word_count", "reading_time")}
        if changed:
            await db.blog_posts.update_one({"slug": d["slug"]}, {"$set": d})
            n += 1
    return n


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:80] or "post"


async def _unique_slug(base: str) -> str:
    slug, n = base, 2
    while await db.blog_posts.find_one({"slug": slug}, {"_id": 1}):
        slug = f"{base}-{n}"
        n += 1
    return slug


async def ensure_indexes():
    await db.blog_posts.create_index("slug", unique=True)
    await db.blog_posts.create_index([("published", 1), ("published_at", -1)])
    await db.seo_candidates.create_index("keyword", unique=True)


async def seed_keywords() -> int:
    added = 0
    for kw, intent in SEED_KEYWORDS:
        added += await add_keyword(kw, intent)
    return added


async def add_keyword(keyword: str, intent: str = "informational", notes: str = "") -> int:
    keyword = normalize_text(keyword).strip().lower()
    if not keyword:
        return 0
    res = await db.seo_candidates.update_one(
        {"keyword": keyword},
        {"$setOnInsert": {"keyword": keyword, "intent": intent, "status": "pending", "created_at": now_iso()}},
        upsert=True,
    )
    if notes:
        await db.seo_candidates.update_one({"keyword": keyword}, {"$set": {"notes": notes}})
    return 1 if res.upserted_id else 0


PROMPT = """You are a senior B2B Growth Lead specializing in webinar distribution, retention, and event marketing.
Write a comprehensive, highly tactical B2B blog article on the TARGET TOPIC below.

TARGET TOPIC (target keyword): "{keyword}"
Search intent: {intent}
Author: {author}. {author_bio}
{notes_block}
STRICT WRITING GUIDELINES

1. No AI cliches or filler.
   - NEVER use these words/phrases (or variants): "In today's fast-paced digital landscape", "game-changer", "tapestry",
     "delve", "mastering", "unlock", "revolutionize", "let's dive in", "look no further".
   - Skip introductory fluff. Sentence 1 leads directly with a strong data point (only from the verified facts below,
     or clearly labelled example arithmetic), a counter-intuitive insight, or a direct operational reality.
   - The first paragraph is shown to readers as the "Quick answer" box, so it must also answer the topic directly
     in 2-4 sentences.

2. Structure variation.
   - Choose H2/H3 headings that fit THIS topic. Do NOT use the stock template (Introduction -> What is X -> 5 Steps
     -> Conclusion), and do not reuse the heading pattern of the published articles listed below.
   - Include at least two concrete visual elements: an ASCII flowchart inside a ``` code block, a timed bulleted
     sequence, a comparison table, and/or a callout line written exactly as "> **Key Takeaway:** ...".

3. Specificity over generality.
   - Never just say "send a reminder email". Give exact timing (e.g. "24 hours before + 15 minutes before"), the
     channel mix (e.g. Email + WhatsApp + Calendar invite), and exact subject lines / message copy templates
     (put templates in ``` code blocks).
   - Include at least one worked example with simple arithmetic, labelled as an example
     (format: "Example: <registrants> x <rate>% = <attendees>; lifting that to <rate2>% adds <n> people", with numbers
     that fit this topic's scenario).
   - Write as a practitioner: trade-offs, and when NOT to do something.

4. Deliver exactly what the topic promises, and be different from the other posts.
   - Every H2 must serve this exact topic. If the topic names a platform (Circle, LinkedIn, Zoom), an audience
     (EdTech, agencies) or a format (SMS examples, subject lines), the article must be specific to it throughout,
     not a generic attendance post with the name swapped in.
   - Template/example topics ("examples", "template", "message", "subject lines", "email") need 15 to 25 distinct,
     ready-to-paste examples grouped by situation, not 2 or 3.
   - Avoid the skeleton every other post on this site already uses: do NOT include the full 11-touch reminder table,
     do NOT use "400 registrants" as the example (pick numbers that fit this topic's scenario), and cite the ON24 60%
     figure only if the topic is about benchmarks or rates.
   - Worked examples must show every step with real numbers and correct arithmetic, and must be complete (never cut
     off or left with blank steps). Check each sum before you return.

5. Native product placement (ShowUpAI).
   - Mention ShowUpAI exactly ONCE, in the middle or toward the end, as a logical tool recommendation that solves a
     specific technical barrier (e.g. running a multi-channel 11-touch automated reminder sequence across WhatsApp,
     SMS and Email without manual effort). Not a sales pitch. Link that mention to https://showupai.live.
   - Only describe ShowUpAI with these true facts: it generates an 11-touch reminder sequence timed from about three
     weeks before the event to after it; channels are email, LinkedIn, Facebook, Instagram, WhatsApp/SMS, Circle.so
     and calendar invites; the host reviews and approves messages before they send; it tracks attendance by channel.
     Do NOT claim it adapts timing to engagement, personalises send times per person, detects who has joined live,
     matches brand tone, or anything else not listed.

Verified facts you MAY use (only the 1-3 most relevant, each with its markdown link, phrased as "<Source> reports ...";
if you compare benchmarks, note they differ because each reflects one vendor's customers). Any other number must be
clearly labelled example arithmetic, never presented as a statistic. Every line that contains a "%" must either
carry the matching fact link on that same line or say "Example" on that line. Never put an empty or "-" placeholder in a
table cell; leave a table out if you have no real values for it:
{facts}

Published articles on the same site (title - URL). Your article must cover an angle NONE of these already covers;
link 2-3 of them inside sentences where they genuinely fit, with descriptive anchor text:
{related}

Format rules:
- 1400 to 2200 words. Markdown only: "## " and "### " headings, "- " bullets, "1. " numbered lists, plain
  paragraphs, simple markdown tables, ``` code blocks, and "> **Key Takeaway:** ..." callout lines.
- No H1 (the title is shown separately). No images, no emojis, no YAML frontmatter inside "content".
  Use plain ASCII hyphens "-", never em-dashes.
- Links ONLY to: the fact URLs above, https://showupai.live, and the published articles listed, copied exactly.
  Do not invent or guess URLs; unknown /blog/ links are removed.
- Do NOT add a "By the numbers" section or a table listing all the facts. Only if the topic itself is about rates,
  benchmarks or statistics may you add one comparison table of the relevant facts.

Return ONLY a JSON object with these keys (title/summary/tags map to the post's frontmatter):
{{
  "title": "specific title, max 65 chars, includes the topic naturally",
  "meta_description": "max 155 chars",
  "excerpt": "1-2 sentence summary, max 200 chars",
  "tags": ["3-6 short topic tags"],
  "content": "the full markdown article",
  "faq_items": [{{"question": "...", "answer": "2-3 sentence answer"}}],   // 4 to 6 items
  "entities": ["key concepts/tools mentioned"],
  "related_topics": ["3-5 related topics to write about next, each clearly different from the published articles"]
}}"""

# Phrases the writing prompt forbids; drafts that still contain them after the style pass are held back.
BANNED_PHRASES = [
    "in today's fast-paced", "digital landscape", "game-changer", "game changer", "tapestry", "delve",
    "mastering", "unlock", "revolutionize", "revolutionise", "let's dive in", "dive in", "look no further",
]


def banned_phrases_in(text: str) -> list:
    t = (text or "").replace("\u2019", "'").lower()
    return [p for p in BANNED_PHRASES if re.search(r"(?<![a-z])" + re.escape(p), t)]


def brand_mentions(text: str) -> int:
    return len(re.findall(r"(?<![\w/.])" + re.escape(BRAND) + r"(?!\w|\.\w)", text or "", re.I))


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("No JSON object in model output")
        return json.loads(text[start:end + 1])


def _groq_json(prompt: str) -> dict:
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    last_err = None
    for model in (PSEO_MODEL, PSEO_FALLBACK_MODEL):
        # Try strict JSON mode first, then plain mode with JSON extraction.
        for json_mode in (True, False):
            try:
                kwargs = dict(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=16000,  # gpt-oss spends part of this on reasoning
                    temperature=0.6,
                    extra_body={"reasoning_effort": "low"},
                )
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                r = client.chat.completions.create(**kwargs)
                return _parse_json(r.choices[0].message.content)
            except Exception as e:
                last_err = e
                logger.warning(f"pSEO model {model} (json_mode={json_mode}) failed: {e}")
                if "model_not_found" in str(e) or "does not exist" in str(e):
                    break  # no point retrying this model without JSON mode
    raise RuntimeError(f"All pSEO models failed: {last_err}")


PRODUCT_FACTS = (
    f"{BRAND} (showupai.live): generates an 11-touch reminder sequence per webinar: confirmation + calendar invite on "
    "registration, awareness post (21 days before), insight (19 days), poll (14 days), case study (10 days), infographic "
    "(8 days), urgency (5 days), final warm-up (1 day), join link (1 hour before), thank-you to attendees (after), "
    "no-show follow-up (2 days after). Channels: email (Brevo/Mailchimp/SendGrid/Buzz.ai), LinkedIn page, Facebook, "
    "Instagram, WhatsApp with SMS fallback, Circle.so, calendar invites. AI writes two variants per message; the host "
    "approves every message; attendance analytics by channel. Plans $29/$79/$199 per month, 14-day free trial."
)

FACTCHECK_PROMPT = """You are a strict fact-checker for a B2B blog. Today's year is 2026.

ALLOWED FACTS (the only statistics that may be stated as facts, each only with its own source):
{facts}

TRUE PRODUCT FACTS about the brand (anything else claimed about the product is false):
{product}

ARTICLE (markdown):
<<<
{article}
>>>

Find EVERY sentence, bullet or table cell that:
1. states a number, percentage, rate, multiplier or benchmark as a fact that is not in ALLOWED FACTS
   (clearly labelled hypothetical arithmetic like "Example: 400 x 40% = 160" or "assume" is fine);
2. attributes a finding, number or cause to a source (ON24, Livestorm, Banzai, Demio, Zoom, TwentyThree, BigMarker,
   "research", "studies", "data") that the ALLOWED FACTS do not say, or mixes up which source said what;
3. speculates about why a vendor's numbers are what they are, stated as fact;
4. claims something about the brand that is not in TRUE PRODUCT FACTS (e.g. "mirrors the brand's sequence" when timings differ);
5. is factually wrong or outdated (e.g. LinkedIn SlideShare, dates in 2024/2025 used as upcoming examples);
6. recommends fake scarcity ("only 20 seats left") or fake social proof.

For each, give an edit: "find" must be an EXACT substring copied from the article (a whole sentence or table cell),
"replace" is a corrected version that keeps the useful point without the unsupported claim (or "" to delete a
sentence that has no other value). Do not touch correct content. Keep markdown formatting intact.

Return ONLY JSON: {{"edits": [{{"find": "...", "replace": "...", "reason": "short"}}]}}"""


async def fact_check(content: str) -> tuple:
    """Second AI pass: remove invented stats, wrong attributions and false product claims. Returns (content, edits)."""
    facts = "\n".join(f"- {f['fact']} (Source: {f['source']})" for f in FACTS)
    prompt = FACTCHECK_PROMPT.format(facts=facts, product=PRODUCT_FACTS, article=content)
    try:
        data = await asyncio.get_running_loop().run_in_executor(None, _groq_json, prompt)
    except Exception as e:
        logger.warning(f"fact-check failed: {e}")
        return content, None  # None = fact-check did not run
    applied = []
    for e in (data.get("edits") or [])[:40]:
        find, repl = (e.get("find") or ""), (e.get("replace") or "")
        if len(find) < 8 or find == repl:
            continue
        find_n = normalize_text(find)
        if find_n in content:
            content = content.replace(find_n, normalize_text(repl), 1)
            applied.append({"find": find_n[:160], "replace": normalize_text(repl)[:160], "reason": e.get("reason", "")[:80]})
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content, applied


STYLE_FIX_PROMPT = """You are a copy editor. The article below contains banned filler phrases: {phrases}.

ARTICLE (markdown):
<<<
{article}
>>>

For EVERY sentence, heading or bullet containing a banned phrase, give an edit: "find" must be an EXACT substring
copied from the article (the whole sentence or heading), "replace" is the same point rewritten plainly and directly
without any banned phrase. Change nothing else. Keep markdown formatting intact.

Return ONLY JSON: {{"edits": [{{"find": "...", "replace": "..."}}]}}"""


async def style_fix(content: str) -> str:
    """Rewrite sentences that still contain banned filler phrases. Best effort; the quality gate re-checks."""
    found = banned_phrases_in(content)
    if not found:
        return content
    prompt = STYLE_FIX_PROMPT.format(phrases=", ".join(f'"{p}"' for p in found), article=content)
    try:
        data = await asyncio.get_running_loop().run_in_executor(None, _groq_json, prompt)
    except Exception as e:
        logger.warning(f"style-fix failed: {e}")
        return content
    for e in (data.get("edits") or [])[:40]:
        find, repl = normalize_text(e.get("find") or ""), normalize_text(e.get("replace") or "")
        if len(find) >= 4 and find != repl and find in content:
            content = content.replace(find, repl, 1)
    return content


_DEDUP_STOP = set(
    "a an the to for of in on and or with via how what why when is are do does your you best practice practices tip "
    "tips guide using use leveraging effective compelling write writing create creating boost increase get people "
    "b2b webinar webinars event events".split()
)
_DEDUP_SYN = {
    "signup": "registration", "signups": "registration", "registrations": "registration", "registrants": "registration",
    "registrant": "registration", "register": "registration", "promote": "promotion", "promoting": "promotion",
    "marketing": "promotion", "emails": "email", "messages": "message", "templates": "template",
    "reminders": "reminder", "attend": "attendance", "companies": "company", "postevent": "post",
}


def topic_tokens(text: str) -> set:
    t = normalize_text(text or "").lower().replace("\u2011", "-")
    for a, b in (("no-show", "noshow"), ("no show", "noshow"), ("follow-up", "followup"), ("follow up", "followup"),
                 ("post-event", "postevent"), ("post-webinar", "postevent"), ("sign-up", "signup"), ("sign up", "signup")):
        t = t.replace(a, b)
    out = set()
    for w in re.findall(r"[a-z0-9]+", t):
        w = _DEDUP_SYN.get(w, w)
        if w in _DEDUP_STOP:
            continue
        if len(w) > 4 and w.endswith("s"):
            w = w[:-1]
        out.add(w)
    return out


def topic_similarity(a: str, b: str) -> float:
    ta, tb = topic_tokens(a), topic_tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


OVERLAP_PROMPT = """You are an SEO editor preventing keyword cannibalisation on a small B2B blog.

Candidate topic: "{keyword}"

Existing posts (slug - keyword - title):
{existing}

Would a post on the candidate topic target the SAME search intent as one of the existing posts (a searcher would be
satisfied by either, so the two would compete in Google)? Different channel, audience, or stage of the funnel counts
as a different intent. Synonyms and rephrasings of the same thing count as the same intent.

Return ONLY JSON: {{"duplicate_of": "<existing slug, or empty string>", "reason": "short"}}"""


async def find_overlap(keyword: str) -> dict | None:
    """Return {"slug", "reason"} of an existing post (published, scheduled or draft) covering the same intent, else None."""
    rows = await db.blog_posts.find(
        {}, {"_id": 0, "slug": 1, "title": 1, "keyword": 1}).to_list(5000)
    if not rows:
        return None
    scored = sorted(((max(topic_similarity(keyword, r.get("keyword") or ""), topic_similarity(keyword, r.get("title") or "")), r)
                     for r in rows), key=lambda x: -x[0])
    best, top = scored[0]
    if best >= 0.75:
        return {"slug": top["slug"], "reason": f"near-identical keyword ({best:.2f})"}
    if not GROQ_API_KEY:
        return {"slug": top["slug"], "reason": f"similar keyword ({best:.2f})"} if best >= 0.6 else None
    existing = "\n".join(f"- {r['slug']} - {r.get('keyword', '')} - {r.get('title', '')}" for r in rows)
    try:
        data = await asyncio.get_running_loop().run_in_executor(
            None, _groq_json, OVERLAP_PROMPT.format(keyword=keyword, existing=existing))
    except Exception as e:
        logger.warning(f"overlap check failed: {e}")
        return {"slug": top["slug"], "reason": f"similar keyword ({best:.2f})"} if best >= 0.6 else None
    dup = (data.get("duplicate_of") or "").strip().strip("/").split("/")[-1]
    if dup and dup in {r["slug"] for r in rows}:
        return {"slug": dup, "reason": str(data.get("reason") or "same search intent")[:200]}
    return None


async def generate_post(keyword: str, intent: str = "informational") -> dict:
    """Generate one long-form draft and save it to blog_posts (unpublished unless auto-publish)."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")

    facts = "\n".join(f"- {f['fact']} Source: {f['source']} {f['url']}" for f in FACTS)
    cand = await db.seo_candidates.find_one({"keyword": keyword}, {"notes": 1}) or {}
    notes = (cand.get("notes") or "").strip()
    notes_block = (
        f"The author's own first-hand notes on this topic (weave them in, attributed to the author's experience):\n{notes}\n"
        if notes else ""
    )
    pubs = await db.blog_posts.find({"published": True}, {"_id": 0, "slug": 1, "title": 1}).sort(
        "published_at", -1).to_list(30)
    related = "\n".join(f"- {p['title']} - {SITE_URL}/blog/{p['slug']}" for p in pubs) or "(none yet)"
    prompt = PROMPT.format(keyword=keyword, intent=intent, author=AUTHOR_NAME, author_bio=AUTHOR_BIO,
                           notes_block=notes_block, facts=facts, related=related)
    data = await asyncio.get_running_loop().run_in_executor(None, _groq_json, prompt)
    content = clean_content((data.get("content") or "").strip(), bool(data.get("faq_items")))
    content, fixes = await fact_check(content)
    content = await style_fix(content)
    words = len(content.split())
    if words < 600:
        raise RuntimeError(f"Draft too short ({words} words)")

    title = (data.get("title") or keyword.title()).strip()
    slug = await _unique_slug(slugify(keyword))
    faqs = [f for f in (data.get("faq_items") or []) if isinstance(f, dict) and f.get("question")]
    doc = {
        "id": str(uuid.uuid4()),
        "slug": slug,
        "keyword": keyword,
        "intent": intent,
        "title": title,
        "seo_title": make_seo_title(title),
        "meta_description": (data.get("meta_description") or "")[:160],
        "seo_description": (data.get("meta_description") or "")[:160],
        "excerpt": (data.get("excerpt") or "")[:220],
        "content": content,
        "faq_items": faqs[:6],
        "tags": [normalize_text(t).strip() for t in (data.get("tags") or []) if isinstance(t, str)][:6],
        "entities": data.get("entities") or [],
        "related_topics": data.get("related_topics") or [],
        "reading_time": max(1, round(words / 200)),
        "word_count": words,
        "author": AUTHOR_NAME,
        "author_bio": AUTHOR_BIO,
        "author_url": AUTHOR_URL,
        "sources": [{"source": f["source"], "url": f["url"]} for f in FACTS if f["url"] in content],
        "source": "pseo",
        "fact_check_edits": fixes or [],
        "fact_check_ok": fixes is not None,
        "banned_phrases": banned_phrases_in(content),
        "brand_mentions": brand_mentions(content),
        "unsourced_numbers": unsourced_numbers(content),
        "bad_math": bad_math(content),
        "status": "published" if PSEO_AUTO_PUBLISH else "draft",
        "published": PSEO_AUTO_PUBLISH,
        "published_at": now_iso() if PSEO_AUTO_PUBLISH else None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    clean_post_fields(doc)
    await db.blog_posts.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def next_publish_slot() -> str | None:
    """Earliest future IST slot within the horizon on a day that has fewer than PSEO_MAX_PUBLISH_PER_DAY posts
    published or scheduled. The time is a random base time plus random jitter, so posts don't all land on the same
    clock minute. Returns UTC ISO."""
    import random
    from collections import Counter
    from datetime import timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    rows = await db.blog_posts.find(
        {"$or": [{"published": {"$ne": True}, "publish_at": {"$ne": None}}, {"published": True}]},
        {"_id": 0, "publish_at": 1, "published_at": 1, "published": 1}).to_list(5000)
    per_day = Counter()
    for r in rows:
        ts = r.get("published_at") if r.get("published") else r.get("publish_at")
        try:
            per_day[datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(ist).date()] += 1
        except Exception:
            continue
    now = datetime.now(ist)
    for day in range(PSEO_SCHEDULE_HORIZON_DAYS + 1):
        date = (now + timedelta(days=day)).date()
        if per_day[date] >= PSEO_MAX_PUBLISH_PER_DAY:
            continue
        bases = list(PSEO_PUBLISH_TIMES_IST)
        random.shuffle(bases)
        for t in bases:
            hh, mm = (int(x) for x in t.split(":"))
            slot = datetime(date.year, date.month, date.day, hh, mm, tzinfo=ist)
            slot += timedelta(minutes=random.randint(0, max(PSEO_PUBLISH_JITTER_MIN, 0)), seconds=random.randint(0, 59))
            if slot > now + timedelta(minutes=10):
                return slot.astimezone(timezone.utc).isoformat()
    return None


def passes_quality_gate(post: dict) -> tuple:
    if not post.get("fact_check_ok"):
        return False, "fact-check did not run"
    if (post.get("word_count") or 0) < 1200:
        return False, f"too short ({post.get('word_count')} words)"
    if banned_phrases_in(post.get("content")):
        return False, f"banned phrases: {', '.join(banned_phrases_in(post.get('content')))}"
    loose = unsourced_numbers(post.get("content"))
    if loose:
        return False, f"unsourced numbers: {loose[0][:80]}"
    wrong = bad_math(post.get("content"))
    if wrong:
        return False, f"wrong arithmetic: {wrong[0]}"
    if empty_tables(post.get("content")):
        return False, "table with empty cells"
    if brand_mentions(post.get("content")) > 2:
        return False, f"{BRAND} mentioned {brand_mentions(post.get('content'))} times"
    if "](https://showupai.live" not in (post.get("content") or ""):
        pass  # autolink adds it at publish time
    if not post.get("title") or not post.get("meta_description"):
        return False, "missing title/meta"
    return True, ""


async def auto_schedule(post: dict) -> dict:
    """If auto-scheduling is on and the draft passes the gate, give it the next free slot."""
    if not PSEO_AUTO_SCHEDULE or post.get("published"):
        return {}
    ok, why = passes_quality_gate(post)
    slot = await next_publish_slot() if ok else None
    if slot:
        await db.blog_posts.update_one({"slug": post["slug"]}, {"$set": {"publish_at": slot, "status": "scheduled"}})
        return {"status": "scheduled", "publish_at_utc": slot}
    return {"held": why or "no free slot"}


async def run_pipeline(count: int | None = None) -> dict:
    """Take `count` pending keywords, generate drafts. Safe to call from cron or manually."""
    count = count or PSEO_POSTS_PER_DAY
    await ensure_indexes()
    await seed_keywords()  # idempotent: only adds seeds that aren't queued yet

    backlog = await db.blog_posts.count_documents({"published": {"$ne": True}, "publish_at": {"$ne": None}})
    if PSEO_AUTO_SCHEDULE and backlog >= PSEO_SCHEDULE_HORIZON_DAYS * PSEO_MAX_PUBLISH_PER_DAY:
        return {"ok": True, "processed": 0, "results": [], "skipped": f"{backlog} posts already scheduled"}

    results, drafted, attempts = [], 0, 0
    while drafted < count and attempts < count * 5:
        attempts += 1
        cand = await db.seo_candidates.find_one_and_update(
            {"status": "pending"},
            {"$set": {"status": "processing", "started_at": now_iso()}},
            sort=[("created_at", 1)],
        )
        if not cand:
            logger.warning("pSEO keyword queue is empty: no new blog drafts until keywords are added")
            break
        if PSEO_DEDUP:
            overlap = await find_overlap(cand["keyword"])
            if overlap:
                await db.seo_candidates.update_one({"_id": cand["_id"]}, {"$set": {
                    "status": "duplicate", "duplicate_of": overlap["slug"], "error": overlap["reason"], "done_at": now_iso()}})
                results.append({"keyword": cand["keyword"], "skipped": f"duplicate of {overlap['slug']}: {overlap['reason']}"})
                logger.info(f"pSEO skipped '{cand['keyword']}' (duplicate of {overlap['slug']})")
                continue
        drafted += 1
        kw = cand["keyword"]
        try:
            post = await generate_post(kw, cand.get("intent", "informational"))
            await db.seo_candidates.update_one(
                {"_id": cand["_id"]}, {"$set": {"status": "drafted", "slug": post["slug"], "done_at": now_iso()}}
            )
            # Optionally queue suggested follow-up topics (off by default: keyword choice stays human)
            if PSEO_AUTO_TOPICS:
                for t in post.get("related_topics", [])[:3]:
                    if isinstance(t, str):
                        await add_keyword(t, "informational")
            item = {"keyword": kw, "slug": post["slug"], "status": post["status"]}
            item.update(await auto_schedule(post))
            results.append(item)
            logger.info(f"pSEO drafted '{kw}' -> {post['slug']}")
        except Exception as e:
            await db.seo_candidates.update_one(
                {"_id": cand["_id"]}, {"$set": {"status": "failed", "error": str(e)[:300]}}
            )
            results.append({"keyword": kw, "error": str(e)[:300]})
            logger.error(f"pSEO failed '{kw}': {e}")
    return {"ok": True, "processed": len(results), "results": results}


async def catch_up() -> dict:
    """On startup: if no pipeline post was drafted today (UTC), e.g. the 03:30 run found an empty queue or the
    server was asleep, draft one now so the day still gets a post."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if await db.blog_posts.find_one({"keyword": {"$exists": True}, "created_at": {"$gte": today}}, {"_id": 1}):
        return {"ok": True, "skipped": "already drafted today"}
    return await run_pipeline(1)


async def retry_failed() -> int:
    """Put failed keywords back in the queue."""
    res = await db.seo_candidates.update_many(
        {"status": {"$in": ["failed", "processing"]}}, {"$set": {"status": "pending"}, "$unset": {"error": ""}}
    )
    return res.modified_count


CONTENT_DIR = os.path.join(os.path.dirname(__file__), "content")


def _parse_content_file(path: str) -> dict:
    raw = open(path, encoding="utf-8").read()
    meta, body = {}, raw
    if raw.startswith("---"):
        _, fm, body = raw.split("---", 2)
        for line in fm.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    body = body.strip()
    faqs = []
    m = re.search(r"^## FAQ\s*$", body, re.M)
    if m:
        faq_md, body = body[m.end():], body[:m.start()].rstrip()
        for q in re.split(r"^### ", faq_md, flags=re.M)[1:]:
            q_line, _, ans = q.partition("\n")
            if q_line.strip() and ans.strip():
                faqs.append({"question": q_line.strip(), "answer": " ".join(ans.split())})
    meta["content"], meta["faq_items"] = body, faqs
    return meta


async def seed_content_posts() -> int:
    """Hand-written posts in backend/content/*.md become drafts (scheduled via publish_at) if not in the DB yet."""
    if not os.path.isdir(CONTENT_DIR):
        return 0
    added = 0
    for name in sorted(os.listdir(CONTENT_DIR)):
        if not name.endswith(".md"):
            continue
        m = _parse_content_file(os.path.join(CONTENT_DIR, name))
        slug = m.get("slug") or slugify(m.get("title", name[:-3]))
        if await db.blog_posts.find_one({"slug": slug}, {"_id": 1}):
            continue
        title = m.get("title", slug)
        pub_at = m.get("publish_at") or None
        if pub_at:  # store in UTC so string comparison with now_iso() is correct
            pub_at = datetime.fromisoformat(pub_at.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        doc = {
            "id": str(uuid.uuid4()), "slug": slug, "keyword": m.get("keyword", ""), "intent": "product",
            "title": title, "seo_title": make_seo_title(title),
            "meta_description": m.get("meta_description", "")[:160], "seo_description": m.get("meta_description", "")[:160],
            "excerpt": m.get("excerpt", ""), "content": m["content"], "faq_items": m["faq_items"],
            "author": AUTHOR_NAME, "author_bio": AUTHOR_BIO, "author_url": AUTHOR_URL,
            "sources": [{"source": f["source"], "url": f["url"]} for f in FACTS if f["url"] in m["content"]],
            "source": "content", "status": "scheduled" if m.get("publish_at") else "draft", "published": False,
            "publish_at": pub_at, "published_at": None,
            "created_at": now_iso(), "updated_at": now_iso(),
        }
        clean_post_fields(doc)
        await db.blog_posts.insert_one(doc)
        added += 1
    return added


async def build_sitemap() -> str:
    static = [("/", "1.0", "weekly"), ("/blog", "0.8", "daily"), ("/about", "0.6", "monthly"), ("/waitlist", "0.7", "monthly"), ("/privacy", "0.3", "yearly")]
    urls = [
        f"<url><loc>{SITE_URL}{p}</loc><changefreq>{f}</changefreq><priority>{pr}</priority></url>"
        for p, pr, f in static
    ]
    rows = await db.blog_posts.find(
        {"published": True}, {"_id": 0, "slug": 1, "title": 1, "published_at": 1, "updated_at": 1}
    ).sort("published_at", -1).to_list(5000)
    for r in rows:
        last = (r.get("updated_at") or r.get("published_at") or "")[:10]
        lastmod = f"<lastmod>{last}</lastmod>" if last else ""
        from xml.sax.saxutils import escape as _x
        cover = f"https://showup-backend-2bfj.onrender.com/api/blog/{r['slug']}/cover.png"
        urls.append(
            f"<url><loc>{SITE_URL}/blog/{r['slug']}</loc>{lastmod}"
            f"<changefreq>monthly</changefreq><priority>0.7</priority>"
            f"<image:image><image:loc>{cover}</image:loc><image:title>{_x(r.get('title') or '')}</image:title></image:image></url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n' + "\n".join(urls) + "\n</urlset>\n"
    )
