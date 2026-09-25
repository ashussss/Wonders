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
PSEO_POSTS_PER_DAY = int(os.environ.get("PSEO_POSTS_PER_DAY", "4"))
PSEO_AUTO_TOPICS = os.environ.get("PSEO_AUTO_TOPICS", "false").lower() == "true"
# Auto-publishing: each new draft that passes the quality gate gets the next free publish slot (IST)
PSEO_AUTO_SCHEDULE = os.environ.get("PSEO_AUTO_SCHEDULE", "true").lower() == "true"
PSEO_PUBLISH_TIMES_IST = [t.strip() for t in os.environ.get("PSEO_PUBLISH_TIMES_IST", "10:00,13:00,16:00,19:00").split(",") if t.strip()]
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
    doc["content"] = clean_content(doc.get("content", ""), bool(faqs))
    if doc.get("author") in (None, "", f"{BRAND} Team"):
        doc["author"], doc["author_bio"], doc["author_url"] = AUTHOR_NAME, AUTHOR_BIO, AUTHOR_URL
    doc["word_count"] = len(doc["content"].split())
    doc["reading_time"] = max(1, round(doc["word_count"] / 200))
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
    c = content or ""
    home = SITE_URL
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


PROMPT = """You are a senior B2B marketer who has run hundreds of webinars. Write an in-depth blog article.

Target keyword: "{keyword}"
Search intent: {intent}
Product context: ShowUpAI (showupai.live) helps webinar hosts get more registrants to actually attend, using an
AI-written, multi-channel reminder sequence (email, LinkedIn, WhatsApp/SMS, calendar) timed around the event.
Mention ShowUpAI naturally at most twice, near the end. The article must be genuinely useful without the product.
Only describe ShowUpAI with these true facts: it generates an 11-touch reminder sequence timed from about three weeks
before the event to after it; channels are email, LinkedIn, Facebook, Instagram, WhatsApp/SMS, Circle.so and calendar
invites; the host reviews and approves messages before they send; it tracks attendance by channel. Do NOT claim it adapts
timing to engagement, personalises send times per person, matches brand tone, or anything else not listed.

Author: {author}. {author_bio}
{notes_block}
Published articles on the same site you can link to (title - URL):
{related}

Verified facts you SHOULD use where relevant (2 to 5 per article, each with its markdown link, phrased as
"<Source> reports ..."; point out that platform benchmarks differ because each reflects one vendor's customers):
{facts}

Rules:
- 1300 to 1800 words. Markdown only: "## " and "### " headings, "- " bullets, "1. " numbered lists, plain paragraphs.
  Simple markdown tables and ``` code blocks (for email templates) are allowed.
- No H1 (the title is shown separately). No images, no emojis. Use plain ASCII hyphens "-".
- Links (markdown [text](url)) allowed ONLY to: the fact URLs above, https://showupai.live, and the published
  articles listed below. Link the first natural mention of ShowUpAI to https://showupai.live.
- Where it genuinely fits, link 2-3 of the related articles below inside sentences, using descriptive anchor text
  (never "click here"). Do not invent other URLs.
- Write from a practitioner's point of view: concrete examples, specific message wording, trade-offs and when NOT to
  do something. Add one short "Key takeaways" list near the end.
- Make it number-rich and insight-led, without inventing data:
  * a "## By the numbers" section early on: a markdown table or bullets using ONLY the verified facts, with links;
  * where useful, compare benchmarks side by side and explain why they differ;
  * at least one worked example with simple arithmetic, clearly labelled as an example
    (e.g. "Example: 400 registrants x 40% = 160 attendees; lifting that to 50% adds 40 people"),
    plus exact timings (e.g. "send at T-24h and T-1h") and concrete counts (e.g. "3 emails, 1 SMS").
- Start with a 2-3 sentence direct answer to the keyword as a plain paragraph (no heading above it).
- Do NOT include an FAQ section inside "content"; FAQs go only in "faq_items".
- Do NOT invent statistics, percentages, benchmarks, studies, quotes or customer names. The ONLY numbers you may
  present as facts are the verified facts above. Otherwise tell readers to measure their own baseline.
- Tone: direct, practical, skeptical of hype. Avoid: "unlock", "revolutionary", "game-changer", "in today's fast-paced".
- Include concrete steps, examples of message timing, and common mistakes.

Return ONLY a JSON object with these keys:
{{
  "title": "compelling title, max 65 chars, includes the keyword naturally",
  "meta_description": "max 155 chars",
  "excerpt": "1-2 sentence summary, max 200 chars",
  "content": "the full markdown article",
  "faq_items": [{{"question": "...", "answer": "2-3 sentence answer"}}],   // 4 to 6 items
  "entities": ["key concepts/tools mentioned"],
  "related_topics": ["3-5 related topics to write about next"]
}}"""


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
        "seo_title": f"{title} | ShowUpAI"[:70],
        "meta_description": (data.get("meta_description") or "")[:160],
        "seo_description": (data.get("meta_description") or "")[:160],
        "excerpt": (data.get("excerpt") or "")[:220],
        "content": content,
        "faq_items": faqs[:6],
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
    """Earliest future IST slot (today or the next 7 days) that no other post is scheduled for. UTC ISO."""
    from datetime import timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    taken = {d.get("publish_at") for d in await db.blog_posts.find(
        {"published": {"$ne": True}, "publish_at": {"$ne": None}}, {"_id": 0, "publish_at": 1}).to_list(500)}
    now = datetime.now(ist)
    for day in range(8):
        date = (now + timedelta(days=day)).date()
        for t in PSEO_PUBLISH_TIMES_IST:
            hh, mm = (int(x) for x in t.split(":"))
            slot = datetime(date.year, date.month, date.day, hh, mm, tzinfo=ist)
            if slot <= now + timedelta(minutes=10):
                continue
            iso = slot.astimezone(timezone.utc).isoformat()
            if iso not in taken:
                return iso
    return None


def passes_quality_gate(post: dict) -> tuple:
    if not post.get("fact_check_ok"):
        return False, "fact-check did not run"
    if (post.get("word_count") or 0) < 900:
        return False, f"too short ({post.get('word_count')} words)"
    if "](https://showupai.live" not in (post.get("content") or ""):
        pass  # autolink adds it at publish time
    if not post.get("title") or not post.get("meta_description"):
        return False, "missing title/meta"
    return True, ""


async def run_pipeline(count: int | None = None) -> dict:
    """Take `count` pending keywords, generate drafts. Safe to call from cron or manually."""
    count = count or PSEO_POSTS_PER_DAY
    await ensure_indexes()
    await seed_keywords()  # idempotent: only adds seeds that aren't queued yet

    results = []
    for _ in range(count):
        cand = await db.seo_candidates.find_one_and_update(
            {"status": "pending"},
            {"$set": {"status": "processing", "started_at": now_iso()}},
            sort=[("created_at", 1)],
        )
        if not cand:
            break
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
            if PSEO_AUTO_SCHEDULE and not post.get("published"):
                ok, why = passes_quality_gate(post)
                slot = await next_publish_slot() if ok else None
                if slot:
                    await db.blog_posts.update_one({"slug": post["slug"]}, {"$set": {"publish_at": slot, "status": "scheduled"}})
                    item.update({"status": "scheduled", "publish_at_utc": slot})
                else:
                    item["held"] = why or "no free slot"
            results.append(item)
            logger.info(f"pSEO drafted '{kw}' -> {post['slug']}")
        except Exception as e:
            await db.seo_candidates.update_one(
                {"_id": cand["_id"]}, {"$set": {"status": "failed", "error": str(e)[:300]}}
            )
            results.append({"keyword": kw, "error": str(e)[:300]})
            logger.error(f"pSEO failed '{kw}': {e}")
    return {"ok": True, "processed": len(results), "results": results}


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
        doc = {
            "id": str(uuid.uuid4()), "slug": slug, "keyword": m.get("keyword", ""), "intent": "product",
            "title": title, "seo_title": title if len(title) > 55 else f"{title} | {BRAND}",
            "meta_description": m.get("meta_description", "")[:160], "seo_description": m.get("meta_description", "")[:160],
            "excerpt": m.get("excerpt", ""), "content": m["content"], "faq_items": m["faq_items"],
            "author": AUTHOR_NAME, "author_bio": AUTHOR_BIO, "author_url": AUTHOR_URL,
            "sources": [{"source": f["source"], "url": f["url"]} for f in FACTS if f["url"] in m["content"]],
            "source": "content", "status": "scheduled" if m.get("publish_at") else "draft", "published": False,
            "publish_at": m.get("publish_at") or None, "published_at": None,
            "created_at": now_iso(), "updated_at": now_iso(),
        }
        clean_post_fields(doc)
        await db.blog_posts.insert_one(doc)
        added += 1
    return added


async def build_sitemap() -> str:
    static = [("/", "1.0", "weekly"), ("/blog", "0.8", "daily"), ("/about", "0.6", "monthly"), ("/waitlist", "0.7", "monthly")]
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
