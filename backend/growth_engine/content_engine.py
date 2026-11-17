"""Content engine — turns a source (blog / news / original idea) into a full campaign.

Responsibilities
----------------
* Decide target audience, pain point, intent, funnel stage, angle, hook.
* Write platform-native copy for LinkedIn / Facebook / Instagram.
* Declare the visual format and supply its *content* (never image bytes).
* Return a validated ``CampaignDraft`` — nothing is persisted here.

Reuses the repo's existing Groq JSON helper (``pseo._groq_json``) so there is no
second AI client, no new dependency, and no new key to manage. The blocking SDK
call is pushed onto a thread executor by the caller (``ai_json``).
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, cast

import pseo

from . import BRAND_NAME, FUNNEL_STAGES, GROWTH_LINKEDIN_VOICE, GROWTH_PLATFORMS, SITE_URL, VISUAL_FORMATS
from .models import (
    CampaignDraft,
    CampaignKind,
    FunnelStage,
    Platform,
    PlatformCopy,
    Strategy,
    VisualFormat,
    VisualSpec,
)

logger = logging.getLogger("showup.growth.content")

SITE_DOMAIN_TEXT = "showupai.live"

# Brand + hard guardrails. Product facts come from Ashu's master prompt (2026-11-17).
# Same anti-fabrication rules the blog pipeline uses: only numbers handed to the model.
BRAND_RULES = f"""Brand: {BRAND_NAME} ({SITE_DOMAIN_TEXT}). It gets more webinar registrants to actually show up live.
How it works: the host pastes their event link (Zoom, Microsoft Teams, Google Meet or any event page). {BRAND_NAME} then
plans up to 11 reminder touches, from 3 weeks before to 2 days after the event; writes the messages for email,
WhatsApp, LinkedIn and calendar; creates promo posts and creatives in every platform size; sends only what the host
approves, with the join link landing 1 hour before going live; shows who actually attended, and follows up with
everyone who didn't.
Tagline: "Fuller rooms. Fewer no-shows. Zero extra hours."
Current offer: free for the first 100 webinar teams.
Reader: people who run webinars at B2B companies (webinar managers, virtual events managers, field and event
marketers, demand gen managers, heads of marketing) in the US, UK, Europe and Australia/New Zealand.

ABSOLUTE RULES (violating these fails the campaign):
- The brand is always written "{BRAND_NAME}". Never "ShowUp AI", "ShowUp.ai" or "Showupai.Live". The website is
  written showupai.live, lower case.
- Never invent numbers, results, clients, quotes, studies or personal stories. Use ONLY the numbers and sources
  provided below. To illustrate with a number you were not given, make it an obvious hypothetical
  ("Say 400 people register..."), never a claim about a real webinar.
- Never claim {BRAND_NAME} customers, users or results. There are none you may cite yet.
- Do not attribute a number to a source that is not given.
- If a line only works with a fact you were not given and cannot be made a hypothetical, cut it. As a last
  resort keep it and end it with "[CONFIRM WITH ASHU]" so a human checks it before it goes out."""

# Who is speaking, per platform. LinkedIn may be Archana's personal profile; the Facebook
# Page and Instagram account are always the brand.
PERSONA_ARCHANA = f"""SPEAKER: Archana Singh, Growth Manager at {BRAND_NAME} (joined in 2026). Write in her first person ("I").
The ONLY personal facts you may use: she has run 100+ webinars for audiences across the US, UK, Australia and
New Zealand, and she joined {BRAND_NAME} in 2026. No past employers, no specific webinar results, no dated
anecdotes, no named companies. A story is built from what she believed vs what she learned about attendance in
general, or from what she sees teams do every week, never from an invented event.
When she mentions {BRAND_NAME}, it is "we" ("So we built {BRAND_NAME}")."""

PERSONA_BRAND = f"""SPEAKER: the {BRAND_NAME} team, writing as "we" to one webinar host ("you"). Do not write as a named person and
do not claim personal experience (no "I've run 100 webinars"). Same tone and structure as everywhere else:
confident, a bit cheeky, simple words."""

# How the copy should sound: Lara Acosta's LinkedIn style, per Ashu's master prompt
# (2026-11-17). Applies to every platform; PLATFORM_RULES only changes the length.
VOICE_RULES = """
VOICE (Lara Acosta's style, applies to every platform):
- Conversational, confident, a bit cheeky. Talk to ONE person. Simple words, no jargon, no corporate filler.
- Every post is about webinar attendance. One topic, many angles.

STRUCTURE of every caption:
1. Hook in the first 1-2 lines. Use one of:
   - a contrarian take: '"Send more reminders" is the worst webinar advice I've heard.'
   - a specific number (a sourced one, or an obvious hypothetical): "400 registered. 140 showed up."
   - a confession or turning point: "For years I thought the fix was more promotion."
   - a direct call-out: "If your webinar show-up rate is under 40%, read this:"
   Never open with a greeting, "Did you know", a hashtag or the brand name.
2. Short lines. One idea per line, a blank line between beats. Most lines under 12 words.
   Paragraphs of 1-3 lines at most.
3. Rhythm through repetition: "More emails. More posts. More 'don't forget!'" and "Not because... Because...".
4. The meat (see POST TYPE below for which shape to use).
5. A plain, honest punchline on its own lines: "It's boring. But boring fills rooms." or
   "That's not a content problem. That's a timing problem."
6. ALWAYS a PS line: "PS: " followed by one question that is easy to answer in a few words in the
   comments ("PS: Which of these 8 are you not sending right now?", "PS: What's the lowest show-up
   rate you've ever seen? Be honest 👀"). Never a bare "Thoughts?".
7. Optional repost line after the PS: "Save this ♻️ for your next webinar." or
   "Repost ♻️ if you know someone whose webinar deserves a fuller room."
8. Optional CTA block after a line containing only "---": the lead magnet or the offer, plus the
   showupai.live line.

RULES:
- Emoji: at most 2 per caption, and only 👀 😂 or ♻️. Never emoji bullets, arrows, checkmarks, rockets
  or decorative symbols. Plain "1." "2." "3." for lists.
- Never use em dashes or en dashes. Use a full stop or a comma.
- Never use: "In today's fast-paced world", game-changer, unlock, leverage, delve, elevate, seamless,
  revolutionize, "Here's the thing:", "Let that sink in", landscape, harness, supercharge, robust,
  navigate, realm, embark, "level up", "dive in".
- Hashtags: none, or at most 2 at the very end. Never a block of hashtags.
- When you use a sourced number, name the report in plain words. Never round it up or apply it to a
  different situation.
- Nothing should look AI-generated.

REFERENCE EXAMPLES (match this tone exactly; do not copy them word for word):

STORY:
Most webinars don't fail because of the content.

They fail at 9:58am.

Two minutes before you go live.
When hundreds registered.
And the room is a third full.

I've run 100+ webinars across the US, UK and ANZ.

For years I thought the fix was more promotion.
More emails. More posts. More "don't forget!"

It wasn't.

The people who registered already wanted to come.
They just forgot. Or the link was buried. Or the reminder landed at the wrong time.

That's not a content problem.
That's a timing problem.

PS: What's the lowest show-up rate you've ever seen? Be honest 👀

EDUCATE with lead magnet:
If your webinar show-up rate is under 40%, read this:

After 100+ webinars, this is the reminder sequence I'd use if I started from zero.

The quick summary? Of course:

1. Instant confirmation. With a calendar link that actually works.
2. 7 days before: what they'll walk away with.
3. 3 days before: a speaker teaser.
4. 1 day before: one question you'll answer live.
5. Morning of: "today at [time]."
6. 1 hour before: the join link. Nothing else.
7. 10 minutes before: "we're starting."
8. After: the replay + a reason to come live next time.

It's boring. But boring fills rooms.

PS: Which of these 8 are you not sending right now?

Save this ♻️ for your next webinar.

---

Want the full sequence written for your next webinar? Comment "SEQUENCE" and I'll send it over.

EDUCATE, contrarian:
"Send more reminders" is the worst webinar advice I've heard.

More reminders don't fix low attendance.
They train people to ignore you.

What actually works:

1. Fewer messages, better timing.
2. Different channels, not the same email 5 times.
3. One clear action per message.
4. A reason to show up live.

And the biggest killer?

"Don't worry, we'll send the recording."

The second you say that, half the room decides to watch later.
(They won't.)

PS: Do you send the replay to everyone, or only to people who showed up?

SELL:
Every webinar I ran, I lost days to the same work.

Writing reminders. Timing them.
Making promo graphics in 6 sizes.
Chasing no-shows after.

So we built ShowUpAI.

You paste your event link.
It plans up to 11 touches, from 3 weeks before to 2 days after.
Writes them for email, WhatsApp, LinkedIn and calendar.
Makes the promo posts.
Sends only what you approve.
Then shows you who actually turned up.

Fuller rooms. Fewer no-shows. Zero extra hours.

For the first 100 webinar teams, it's free.

Got a webinar coming up? Comment "SHOW" and I'll set it up with you.

PS: What's the one part of webinar promo you'd happily never do again?
"""

# The shape of "the meat" for each campaign kind.
KIND_STRUCTURE = {
    "pain_point": ('EDUCATE post. Hook, one line of context, then "The quick summary? Of course:" and a numbered '
                   "list (1. 2. 3.), each item short and concrete, then the punchline and the PS question."),
    "engagement": ("EDUCATE, contrarian post. Take a clear side people will argue with, give 3-4 numbered points on "
                   "what actually works, a sharp twist line, then the PS question."),
    "story": ("STORY post. What happened (or what she sees every week) > what I believed > what I learned > what "
              "changed. Built only on the allowed facts. No pitch beyond one light mention at most. Up to 300 words."),
    "sell": ('SELL post. The pain in 3-4 short lines > "So we built ShowUpAI." > how it works in 5-6 short lines '
             "> the tagline > the offer (free for the first 100 webinar teams) > the comment-keyword CTA > PS."),
    "blog": ("EDUCATE post built from our article. Hook from the article's single most useful idea, then "
             '"The quick summary? Of course:" with 3-6 numbered takeaways the article actually states, the '
             "punchline, the PS question, and after the --- line: \"Full breakdown on our blog:\" (the link is added "
             "for you)."),
    "competitor": ("EDUCATE post comparing two approaches. The usual way vs the better way as two short numbered "
                   "lists or paired lines, honest about where the usual way is fine, then the punchline and PS."),
    "news": ("EDUCATE post reacting to the news item. One line on what happened, then what it means for someone "
             "running webinars next month as a short numbered list, the punchline and the PS question."),
}

PLATFORM_RULES = """
PLATFORM COPY (return each as a separate object; same voice and structure everywhere, only the length changes):
- linkedin: 120-250 words (STORY posts up to 300). The hook (lines 1-2) stays under 150 characters, since
  that is all LinkedIn shows before "see more". Include one line with the link https://showupai.live,
  inside the CTA block after "---". 0-2 hashtags on the last line.
- facebook: 60-150 words. Hook, the meat in short lines, the punchline, the PS question, and a
  line with https://showupai.live. 0-2 hashtags.
- instagram: 100-220 words. Hook in the first 125 characters. Short lines. The PS question, a save or
  "send this to a teammate who runs webinars" line, and "More at showupai.live (link in bio)". 0-2 hashtags.
- Put any hashtags inside the caption text and also list them in "hashtags".
"""

VISUAL_RULES = """
VISUAL RULES — you describe the image, a renderer draws it in the flat ShowUpAI brand style
(no stock photos, no illustrations, no AI art). Text on the image must be short and readable
on a phone. One idea per slide or row.
Highlight: in every headline, title, quote and stat label on the image, wrap the 1-3 words
that carry the point in *asterisks*; the renderer highlights them in the brand colour. Use
asterisks ONLY inside "visual", never in captions. Slide titles are punchy statements, not
labels ("One email is not a sequence", not "Email strategy").
Pick the format you are told to use, or the best fit if none is given, and fill only the
fields that format uses:
- carousel:      {"format":"carousel","title":"cover headline, a bold claim (<=10 words)","subtitle":"the promise of swiping, <=12 words, e.g. 4 fixes that lift live attendance","slides":[{"title":"<=8 words","body":"<=25 words, one actionable point"}],"cta":"last slide: the comment question or a save prompt (<=14 words)"}  (4-6 slides)
- infographic:   {"format":"infographic","title":"<=9 words","rows":["<=12 words each, 4-6 rows, an insight or step per row"]}
- stat_card:     {"format":"stat_card","title":"short label","number":"e.g. 51.3%","label":"what it means, <=22 words","source":"the exact source name provided"}   (needs a number you were GIVEN)
- checklist:     {"format":"checklist","title":"<=9 words","rows":["<=12 words each, 5-6 checklist items"]}
- comparison:    {"format":"comparison","title":"<=9 words","left":{"title":"<=5 words","rows":["<=10 words, 3-4"]},"right":{"title":"<=5 words","rows":["<=10 words, 3-4"]}}   (left = the usual way, right = the better way)
- quote:         {"format":"quote","quote":"<=28 words, a strong opinion the reader will recognise","attribution":"role or team, not a real person's name"}
- poll:          {"format":"poll","title":"the poll question, <=120 characters","rows":["option, <=30 characters", "2-4 options"]}
                 A real choice people disagree on, every option a fair answer. On LinkedIn it becomes a native
                 poll; on Facebook and Instagram the image shows options A-D, so those captions must ask
                 readers to comment their letter (A, B, C or D) and why.
- myth_fact:     {"format":"myth_fact","title":"<=8 words","items":[{"myth":"<=12 words, a belief hosts really hold","fact":"<=16 words, what actually works"}]}   (2-3 pairs)
- timeline:      {"format":"timeline","title":"<=9 words","items":[{"time":"<=4 words, e.g. 7 days before","what":"<=12 words, what to send or do"}]}   (4-6 steps, in time order)
- text_card:     {"format":"text_card","title":"the post's hook, 1-3 short sentences, <=28 words, exactly as the caption opens"}
                 A plain text card that looks like the opening of a post. Best for story and opinion posts.
- hot_take:      {"format":"hot_take","title":"the opinion itself, <=12 words, a clear side","subtitle":"one line on why, <=20 words"}
Carousels are the best-performing format on LinkedIn and Instagram: prefer them for how-to.
stat_card only when you were given a citable number.
"""

STAGE_HINTS = {
    "awareness": "reach people who have not thought about this problem yet",
    "consideration": "help someone already aware compare options/approaches",
    "intent": "target someone actively trying to solve this in the next few weeks",
    "conversion": "target someone evaluating a tool or vendor right now",
    "retention": "target existing users/customers who need a next step",
}

# Campaign kind -> the funnel stage that kind usually aims for. NOTE: a kind is
# not always a stage ("engagement" is a kind with no matching stage) — engagement
# posts aim at awareness to start a conversation, so it maps explicitly here.
KIND_STAGE = {
    "blog": "awareness",
    "news": "awareness",
    "pain_point": "consideration",
    "engagement": "awareness",
    "competitor": "consideration",
    "story": "awareness",
    "sell": "conversion",
}

# Fallback visual rotation when the model returns an unknown format.
FORMAT_PREFERENCE = {
    "blog": ["carousel", "infographic", "checklist", "stat_card"],
    "news": ["stat_card", "quote", "comparison", "carousel"],
    "pain_point": ["checklist", "comparison", "carousel", "infographic"],
    "engagement": ["quote", "poll", "hot_take", "carousel"],
    "competitor": ["comparison", "carousel", "infographic"],
    "story": ["text_card", "quote", "hot_take"],
    "sell": ["checklist", "timeline", "infographic"],
}


def _ai(prompt: str) -> Dict[str, Any]:
    """Blocking Groq JSON call (delegated to pseo's configured model)."""
    return pseo._groq_json(prompt)


async def ai_json(prompt: str) -> Dict[str, Any]:
    """Async wrapper — the SDK call is blocking, so run it off the event loop."""
    return await asyncio.get_running_loop().run_in_executor(None, _ai, prompt)


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the repo's brand + text normalisation (and humanize) to every string in the payload."""
    out: Dict[str, Any] = {}
    for k, v in (d or {}).items():
        if isinstance(v, str):
            out[k] = humanize(fix_brand(pseo.rebrand(pseo.normalize_text(v))))
        elif isinstance(v, list):
            out[k] = [humanize(fix_brand(pseo.rebrand(pseo.normalize_text(x)))) if isinstance(x, str)
                      else _clean(x) if isinstance(x, dict) else x for x in v]
        elif isinstance(v, dict):
            out[k] = _clean(v)
        else:
            out[k] = v
    return out


def _strategy(d: Optional[Dict[str, Any]], kind: str) -> Strategy:
    """Build + validate the strategy block, coercing unknown values safely."""
    d = d if isinstance(d, dict) else {}
    stage = str(d.get("funnel_stage", "")).strip().lower()
    if stage not in FUNNEL_STAGES:
        stage = KIND_STAGE.get(kind, "awareness")
    fields = {
        "target_audience": d.get("target_audience"),
        "pain_point": d.get("pain_point"),
        "intent": d.get("intent"),
        "content_angle": d.get("content_angle"),
        "hook": d.get("hook"),
    }
    cleaned = {}
    for name, val in fields.items():
        text = (val if isinstance(val, str) else "").strip()
        if len(text) < 3:
            text = _fallback_strategy_text(name, kind)
        cleaned[name] = text
    keywords = d.get("keywords")
    return Strategy(
        funnel_stage=cast(FunnelStage, stage),
        cta=str(d.get("cta") or "").strip(),
        rationale=str(d.get("rationale") or "").strip(),
        keywords=[str(k) for k in keywords] if isinstance(keywords, list) else [],
        **cleaned,
    )


def _fallback_strategy_text(name: str, kind: str) -> str:
    """Deterministic, honest fallback — never a fabricated insight, just structure."""
    return {
        "target_audience": "Webinar and event hosts responsible for attendance",
        "pain_point": "Registrations are healthy but the room stays empty",
        "intent": "Find a practical fix they can apply to their next event",
        "content_angle": f"A {kind.replace('_', ' ')} angle on getting registrants to show up",
        "hook": "Registered but not showing up? Start here.",
    }[name]


def _platform_copy(d: Dict[str, Any], platforms: List[str]) -> Dict[str, PlatformCopy]:
    raw = d.get("platform_copy") or d.get("copy") or {}
    if not isinstance(raw, dict):
        raw = {}
    out: Dict[str, PlatformCopy] = {}
    for p in platforms:
        block = raw.get(p) or {}
        if isinstance(block, str):          # model returned a bare string
            block = {"caption": block}
        if not isinstance(block, dict):
            continue
        caption = str(block.get("caption") or block.get("body") or "").strip()
        if not caption:
            continue
        tags = block.get("hashtags")
        out[p] = PlatformCopy(
            caption=caption,
            hashtags=[str(t) for t in tags] if isinstance(tags, list) else [],
            cta=str(block.get("cta") or "").strip(),
        )
    return out


def _visual(d: Dict[str, Any], kind: str, seed: str, preferred: str = "") -> VisualSpec:
    """Validate the AI's visual declaration, falling back to a safe, renderable spec."""
    raw = d.get("visual") or {}
    if not isinstance(raw, dict):
        raw = {}
    fmt = str(raw.get("format") or "").strip().lower().replace(" ", "_").replace("-", "_")
    if fmt not in VISUAL_FORMATS:
        pool = FORMAT_PREFERENCE.get(kind) or list(VISUAL_FORMATS)
        fmt = preferred if preferred in VISUAL_FORMATS else pool[int(hashlib8(seed)) % len(pool)]

    spec = VisualSpec(format=cast(VisualFormat, fmt))
    spec.title = str(raw.get("title") or "").strip()[:200]
    spec.subtitle = str(raw.get("subtitle") or "").strip()[:300]

    for s in (raw.get("slides") or [])[:8]:
        if isinstance(s, dict) and s.get("title"):
            spec.slides.append({"title": str(s["title"])[:120], "body": str(s.get("body") or "")[:300]})

    spec.rows = [str(r)[:160] for r in (raw.get("rows") or []) if isinstance(r, (str, int))][:6]

    for it in (raw.get("items") or [])[:8]:
        if isinstance(it, dict):
            label = it.get("label") or it.get("myth") or it.get("time") or ""
            value = it.get("value") or it.get("fact") or it.get("what") or ""
            if str(label).strip() and str(value).strip():
                spec.items.append({"label": str(label).strip()[:90], "value": str(value).strip()[:160]})

    spec.number = str(raw.get("number") or "").strip()[:20]
    spec.label = str(raw.get("label") or "").strip()[:300]
    spec.source = str(raw.get("source") or "").strip()[:120]
    spec.cta = str(raw.get("cta") or "").strip()[:200]
    spec.quote = str(raw.get("quote") or "").strip()[:300]
    spec.attribution = str(raw.get("attribution") or "").strip()[:120]
    for side in ("left", "right"):
        blk = raw.get(side)
        if isinstance(blk, dict):
            setattr(spec, side, {
                "title": str(blk.get("title") or "")[:80],
                "rows": [str(r)[:120] for r in (blk.get("rows") or []) if isinstance(r, (str, int))][:5],
            })

    if spec.format == "poll":
        # LinkedIn's limits: question 140 characters, 2-4 options of 30 characters.
        spec.title = spec.title[:140]
        spec.rows = [r.replace("*", "")[:30].strip() for r in spec.rows if r.strip()][:4]

    # Normalise an unusable format into one that can actually be drawn.
    # Order matters: each branch is guarded on renderability so a format can never
    # bounce back to the one it just left (that loop previously ended unrenderable).
    if not is_renderable(spec):
        spec.format = "carousel"
        if not is_renderable(spec):
            spec.format = "checklist"
            if not is_renderable(spec):
                spec.format = "quote"
                if not is_renderable(spec):
                    spec.format = "comparison"
                    if not is_renderable(spec):
                        spec.format = "infographic"
                        if not is_renderable(spec):
                            spec.format = "stat_card"

    # Final guarantee: never hand the renderer a spec it cannot draw.
    if not is_renderable(spec):
        spec = _synthesize_spec(spec, fmt)
    return spec


def is_renderable(spec: VisualSpec) -> bool:
    """True when spec has the content its chosen format requires."""
    f = spec.format
    if f == "stat_card":
        return bool(spec.number and spec.label)
    if f == "carousel":
        return len(spec.slides) >= 3
    if f in ("infographic", "checklist"):
        return len(spec.rows) >= 3
    if f == "comparison":
        return bool(spec.left.get("rows")) and bool(spec.right.get("rows"))
    if f == "quote":
        return bool(spec.quote)
    if f == "poll":
        return bool(spec.title) and 2 <= len(spec.rows) <= 4
    if f == "myth_fact":
        return len(spec.items) >= 2
    if f == "timeline":
        return len(spec.items) >= 3
    if f in ("hot_take", "text_card"):
        return bool(spec.title)
    return False


def _synthesize_spec(spec: VisualSpec, original_fmt: str) -> VisualSpec:
    """Last-resort rebuild so a campaign is never queued with an undrawable visual.

    Salvages whatever the model DID return (title, rows, slides, quote, number)
    into a checklist/stat-card that the renderer can always draw.
    """
    rows = [r for r in spec.rows if r.strip()]
    for s in spec.slides:
        if s.get("title"):
            rows.append(s["title"] if not s.get("body") else f"{s['title']} — {s['body']}"[:120])
    for side in ("left", "right"):
        rows.extend(getattr(spec, side, {}).get("rows") or [])
    for it in spec.items:
        rows.append(f"{it.get('label', '')}: {it.get('value', '')}".strip(": "))
    rows = [r[:120] for r in rows if r][:6]

    if spec.number and spec.label:
        spec.format = "stat_card"
        return spec
    if len(rows) >= 3:
        spec.format = "checklist"
        spec.rows = rows
        if not spec.title:
            spec.title = f"{original_fmt.replace('_', ' ').title()} checklist"
        return spec
    if spec.quote:
        spec.format = "quote"
        return spec
    # Too thin to draw any list format — pad with clearly-labelled placeholders so the
    # reviewer sees an obviously-incomplete draft rather than a silently wrong card.
    while len(rows) < 3:
        rows.append("Add this point")
    spec.format = "checklist"
    spec.rows = rows
    spec.title = spec.title or "Review needed"
    return spec


_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️⃣←-⇿]")
_DASH = re.compile(r"\s*[—–]\s*")
# The only emoji the voice allows (Ashu's master prompt): 👀 😂 ♻️, at most two per caption.
ALLOWED_EMOJI = ("\U0001F440", "\U0001F602", "♻️", "♻")
MAX_EMOJI = 2

BANNED_PHRASES = (
    "in today's", "fast-paced", "landscape", "dive in", "let's dive", "delve", "game-changer",
    "game changer", "unlock", "elevate", "leverage", "harness", "supercharge", "seamless",
    "revolutioniz", "revolutionis", "robust", "navigate", "realm", "tapestry", "embark", "buckle up",
    "level up", "here's the thing", "the truth is", "let that sink in",
)

_BRAND_VARIANTS = re.compile(r"(?<![@/\w.])show\s?up[\s.-]?ai(?!\w)(?!\.live)", re.I)
_DOMAIN = re.compile(r"(?<![@/\w])showupai\.live\b", re.I)


def fix_brand(text: str) -> str:
    """'ShowUp AI' / 'Showup ai' / 'ShowUp.ai' -> 'ShowUpAI'; 'Showupai.Live' -> 'showupai.live'."""
    if not isinstance(text, str):
        return text
    t = _DOMAIN.sub("showupai.live", text)
    return _BRAND_VARIANTS.sub(BRAND_NAME, t)


def humanize(text: str) -> str:
    """Strip the tells that make a caption read as machine-written: emojis other than the
    allowed 👀 😂 ♻️ (max two), arrows, em/en dashes and runs of blank lines. Wording
    problems are caught by copy_issues."""
    if not isinstance(text, str):
        return text
    kept: List[str] = []

    def _keep(m: "re.Match[str]") -> str:
        kept.append(m.group(0))
        return f"\x00{len(kept) - 1}\x00"

    t = re.sub("|".join(re.escape(e) for e in ALLOWED_EMOJI), _keep, text)
    t = _EMOJI.sub("", t)
    t = re.sub("\x00(\\d+)\x00", lambda m: ("♻️" if kept[int(m.group(1))].startswith("♻")
                                            else kept[int(m.group(1))]) if int(m.group(1)) < MAX_EMOJI else "", t)
    t = _DASH.sub(", ", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


SITE_DOMAIN = "showupai.live"


SITE_LINK = "https://showupai.live"
_BARE_DOMAIN = re.compile(r"(?<![/\w.@-])showupai\.live(?![/\w])", re.I)


def ensure_site(caption: str, platform: str = "linkedin") -> str:
    """Every caption carries the ShowUpAI link once (Ashu, 2026-11-17: "showup ka link bhi").
    LinkedIn and Facebook get the clickable https://showupai.live; Instagram captions cannot
    hold a clickable link, so they keep "showupai.live (link in bio)". If the model left it
    out, add it as its own line just above the hashtag line (or at the end)."""
    if platform != "instagram" and SITE_LINK not in caption.lower():
        caption = _BARE_DOMAIN.sub(SITE_LINK, caption, count=1)
    if SITE_DOMAIN in caption.lower():
        return caption
    line = f"Try it free: {SITE_LINK}" if platform != "instagram" else f"{SITE_DOMAIN} (link in bio)"
    lines = caption.rstrip().split("\n")
    if lines and lines[-1].strip().startswith("#"):
        return "\n".join(lines[:-1]).rstrip() + f"\n\n{line}\n\n" + lines[-1].strip()
    return caption.rstrip() + f"\n\n{line}"


def ensure_link(caption: str, url: str) -> str:
    """Put the exact blog URL in the caption once, above the hashtag line, so readers
    can open the post itself. LinkedIn image posts and Instagram carry no link card."""
    if not url or url.lower() in caption.lower():
        return caption
    line = f"Read it here: {url}"
    lines = caption.rstrip().split("\n")
    if lines and lines[-1].strip().startswith("#"):
        return "\n".join(lines[:-1]).rstrip() + f"\n\n{line}\n\n" + lines[-1].strip()
    return caption.rstrip() + f"\n\n{line}"


def is_blog_link(url: str) -> bool:
    from . import SITE_URL
    return bool(url) and url.startswith(SITE_URL.rstrip("/") + "/blog/")


# Word ranges per platform (the master prompt's 120-250, story up to 300). A little slack on
# each side so a good post is not rewritten for being three words short.
WORD_RANGE = {"linkedin": (110, 265), "facebook": (50, 170), "instagram": (90, 240)}
STORY_MAX_WORDS = 320


def _words(caption: str) -> int:
    body = caption.split("\n---", 1)[0]  # the CTA block does not count toward length
    return len(re.findall(r"[A-Za-z0-9'%$]+", body))


def copy_issues(copy: Dict[str, PlatformCopy], kind: str = "") -> List[str]:
    """Rule checks a reviewer would otherwise do by hand. Empty list = good."""
    issues: List[str] = []
    for platform, block in copy.items():
        cap = block.caption or ""
        low = cap.lower()
        hits = [p for p in BANNED_PHRASES if p in low]
        if hits:
            issues.append(f"{platform}: remove the phrases {', '.join(hits)}")
        if not re.search(r"(?im)^\s*PS:.*\?", cap):
            issues.append(f"{platform}: add a 'PS:' line with one easy question readers can answer in the comments")
        elif "?" not in cap:
            issues.append(f"{platform}: end with a question that asks readers to comment")
        first = cap.strip().split("\n", 1)[0]
        if platform == "linkedin" and len(first.split()) > 14:
            issues.append("linkedin: the first line must be a hook under 12 words")
        lo, hi = WORD_RANGE.get(platform, (0, 10_000))
        if kind == "story":
            hi = max(hi, STORY_MAX_WORDS) if platform == "linkedin" else hi
        n = _words(cap)
        if n < lo or n > hi:
            issues.append(f"{platform}: {n} words, keep it between {lo} and {hi}")
        tags = re.findall(r"(?<![\w&])#\w+", cap)
        if len(tags) > 2:
            issues.append(f"{platform}: at most 2 hashtags, at the very end")
        if re.search(r"show\s?up[\s.]ai(?!\.live)", cap, re.I):
            issues.append(f"{platform}: write the brand as {BRAND_NAME}")
    return issues


def hashlib8(seed: str) -> int:
    """Stable small-int hash (no hashlib import needed in hot path)."""
    h = 2166136261
    for ch in str(seed):
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


async def build_campaign(
    kind: CampaignKind,
    *,
    source_title: str = "",
    source_body: str = "",
    source_url: str = "",
    source_slug: str = "",
    source_type: str = "",
    link_url: str = "",
    link_title: str = "",
    fact_block: str = "",
    seed: str = "",
    platforms: Optional[List[str]] = None,
    angle_hint: str = "",
    visual_format: str = "",
) -> Optional[CampaignDraft]:
    """Generate one validated campaign. Returns None if the AI output is unusable."""
    platforms = [p for p in (platforms or GROWTH_PLATFORMS) if p in GROWTH_PLATFORMS] or ["linkedin"]
    seed = seed or f"{kind}:{source_slug or source_title}"
    visual_format = visual_format if visual_format in VISUAL_FORMATS else ""
    format_line = (f"VISUAL FORMAT: use \"{visual_format}\"." if visual_format
                   else "VISUAL FORMAT: pick the best fit.")

    prompt = f"""{BRAND_RULES}

You are the content strategist for {BRAND_NAME}'s own social channels. Create ONE campaign.

CAMPAIGN TYPE: {kind}
{angle_hint}

SOURCE TITLE: {source_title or "(none — original idea, invent a specific topic in the webinar/event-marketing space)"}
SOURCE URL: {source_url or "(none)"}
SOURCE BODY (excerpt):
{(source_body or "(none)")[:6000]}
{fact_block}

FIRST decide the strategy, then write the copy and describe the visual.

Strategy fields:
- target_audience: one specific person with a job title and context (not "businesses").
- pain_point: the concrete, felt problem in their day.
- intent: what they are trying to do, and how soon.
- funnel_stage: exactly one of {", ".join(FUNNEL_STAGES)}. {stage_hint_for(kind)}
- content_angle: the specific, non-generic point of view.
- hook: the first line — must earn the next line, no clickbait lies.
- cta: what the reader should do next.
- rationale: 1-2 sentences on why this angle suits this audience at this stage.

{speaker_block(platforms)}
{VOICE_RULES}
POST TYPE: {KIND_STRUCTURE.get(kind, KIND_STRUCTURE["pain_point"])}
{PLATFORM_RULES}
{VISUAL_RULES}
{format_line}

Return ONLY a JSON object with exactly this shape:
{{
  "strategy": {{
    "target_audience": "...", "pain_point": "...", "intent": "...", "funnel_stage": "...",
    "content_angle": "...", "hook": "...", "cta": "...", "rationale": "...",
    "keywords": ["..."]
  }},
  "platform_copy": {{
    "linkedin": {{"caption": "...", "hashtags": ["..."], "cta": "..."}},
    "facebook": {{"caption": "...", "hashtags": ["..."], "cta": "..."}},
    "instagram": {{"caption": "...", "hashtags": ["..."], "cta": "..."}}
  }},
  (only include the platforms in this list: {", ".join(platforms)})
  "visual": {{...one of the formats above...}}
}}"""

    raw: Dict[str, Any] = {}
    copy: Dict[str, PlatformCopy] = {}
    feedback = ""
    # One rewrite pass: if the first draft breaks the voice rules, send the exact
    # problems back once. A second miss is kept and left to the human reviewer.
    for attempt in range(2):
        try:
            raw = _clean(await ai_json(prompt + feedback))
        except Exception as e:                              # noqa: BLE001
            logger.error(f"content_engine: AI failed for {kind}/{seed}: {e}")
            return None
        copy = _platform_copy(raw, platforms)
        for plat, block in copy.items():
            block.caption = ensure_site(humanize(fix_brand(block.caption.replace("*", ""))), plat)
        issues = copy_issues(copy, kind) if copy else ["no captions returned"]
        if not issues:
            break
        logger.info(f"content_engine: rewrite {kind}/{seed}: {issues}")
        feedback = ("\n\nYOUR PREVIOUS DRAFT BROKE THESE RULES. Rewrite everything and fix them:\n- "
                    + "\n- ".join(issues))

    blog_link = link_url or source_url
    if is_blog_link(blog_link):
        for block in copy.values():
            block.caption = ensure_link(block.caption, blog_link)

    strategy = _strategy(raw.get("strategy"), kind)
    if not copy:
        logger.error(f"content_engine: no usable platform copy for {kind}/{seed}")
        return None
    visual = _visual(raw, kind, seed, visual_format)

    return CampaignDraft(
        kind=cast(CampaignKind, kind),
        source_type=source_type or source_type_default(kind),
        source_slug=source_slug,
        source_url=source_url,
        source_title=source_title,
        strategy=strategy,
        platform_copy=copy,
        platforms=[cast(Platform, p) for p in copy.keys()],
        visual=visual,
        link_url=link_url or source_url,
        link_title=link_title or source_title,
    )


def speaker_block(platforms: List[str]) -> str:
    """Who writes which caption. Facebook and Instagram are always the brand page."""
    li_archana = GROWTH_LINKEDIN_VOICE == "archana" and "linkedin" in platforms
    if not li_archana:
        return PERSONA_BRAND
    return ("LINKEDIN CAPTION " + PERSONA_ARCHANA +
            "\n\nFACEBOOK AND INSTAGRAM CAPTIONS (the brand page) " + PERSONA_BRAND +
            "\nThe brand captions make the same point as the LinkedIn caption, rewritten in the team's voice.")


def stage_hint_for(kind: str) -> str:
    stage = KIND_STAGE.get(kind, "awareness")
    return f"Aim for '{stage}' — {STAGE_HINTS[stage]}."


def source_type_default(kind: str) -> str:
    return {"blog": "blog", "news": "news", "pain_point": "original",
            "engagement": "original", "competitor": "original",
            "story": "original", "sell": "original"}.get(kind, "original")


__all__ = [
    "ai_json",
    "build_campaign",
    "FORMAT_PREFERENCE",
    "BRAND_RULES",
    "VOICE_RULES",
    "humanize",
    "copy_issues",
    "fix_brand",
    "KIND_STRUCTURE",
    "ensure_site",
    "STAGE_HINTS",
    "stage_hint_for",
]