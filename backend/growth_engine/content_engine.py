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

from . import BRAND_NAME, FUNNEL_STAGES, GROWTH_PLATFORMS, SITE_URL, VISUAL_FORMATS
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

# Brand + hard guardrails. Same anti-fabrication rules the blog pipeline uses:
# we may only cite numbers that are handed to the model.
BRAND_RULES = f"""Brand: {BRAND_NAME} ({SITE_URL}) helps webinar and event hosts get registrants to actually show up,
using an AI-written reminder sequence across email, LinkedIn, Facebook, Instagram, WhatsApp and calendar, plus
calendar invites. The host approves every message.

ABSOLUTE RULES (violating these fails the campaign):
- Never write "ShowUp.ai". Always "{BRAND_NAME}".
- Never invent statistics, customer names, quotes, logos or study findings. Use ONLY numbers and sources provided
  to you below. If you have no number, write a practical tip instead of a stat.
- No hype words: unlock, game-changer, revolutionary, disrupt, seamless, cutting-edge.
- Do not fabricate a study or attribute a number to a source that is not given.
- Speak to one specific person, not "businesses" or "teams" in the abstract."""

# How the copy should sound. The goal is a post a real person at ShowUpAI could have
# written, built to get comments (reach) and clicks to the site (leads).
VOICE_RULES = """
VOICE (applies to every platform):
- Sound like one experienced person talking to a peer. Not a brand, not a press release.
- Assertive. Take a clear position. No hedging ("might", "could potentially", "in some cases").
- Short sentences. Most under 12 words. One sentence per line. A blank line between ideas.
- Concrete over clever: a specific situation, a specific step, a specific mistake.
- No emojis. No decorative symbols or arrows. No em dashes. Plain "1." "2." "3." for lists.
- Banned words and phrases: in today's, fast-paced, landscape, dive in, let's dive, delve,
  game-changer, game changer, unlock, elevate, leverage, harness, supercharge, seamless,
  revolutionize, robust, navigate, realm, tapestry, embark, buckle up, level up,
  "here's the thing", "the truth is", "it's not just X, it's Y", "let that sink in".
- End with ONE question about this exact subject that a reader can answer from their own
  experience, then ask them to answer in the comments. Vary the wording; never a bare
  "Thoughts?" or "What do you think?". The question is always the last line before hashtags.
"""

PLATFORM_RULES = """
PLATFORM COPY RULES (LinkedIn and Meta best practice; return each as a separate object):
- linkedin: 700-1300 characters. Line 1 is the hook, under 12 words, alone on its line, and
  must make someone click "see more". Line 2 adds tension or a stake. Then the substance as
  short lines or a plain numbered list. If the visual is a carousel, say what they get by
  swiping. Always one plain line pointing to showupai.live (domain only, no https, no
  "link in bio"). Then the question and the comment ask. Exactly 3 hashtags on the last line.
- facebook: 150-450 characters. Hook line, 2-4 short lines, one line mentioning showupai.live,
  the question and the comment ask. 0-2 hashtags.
- instagram: 400-1100 characters. Hook in the first 125 characters. Short lines. Ask them
  to save or share the post if it is useful, one line "More at showupai.live (link in bio)",
  then the question and the comment ask. 3-5 specific hashtags on the last line.
- Put the hashtags inside the caption text and also list them in "hashtags".
"""

VISUAL_RULES = """
VISUAL RULES — you describe the image, a renderer draws it in the flat ShowUpAI brand style
(no stock photos, no illustrations, no AI art). Text on the image must be short and readable
on a phone. One idea per slide or row.
Pick the format you are told to use, or the best fit if none is given, and fill only the
fields that format uses:
- carousel:      {"format":"carousel","title":"cover headline, a bold claim or promise (<=10 words)","slides":[{"title":"<=8 words","body":"<=25 words, one actionable point"}],"cta":"last slide: the comment question or a save prompt (<=14 words)"}  (4-6 slides)
- infographic:   {"format":"infographic","title":"<=9 words","rows":["<=12 words each, 4-6 rows, an insight or step per row"]}
- stat_card:     {"format":"stat_card","title":"short label","number":"e.g. 51.3%","label":"what it means, <=22 words","source":"the exact source name provided"}   (needs a number you were GIVEN)
- checklist:     {"format":"checklist","title":"<=9 words","rows":["<=12 words each, 5-6 checklist items"]}
- comparison:    {"format":"comparison","title":"<=9 words","left":{"title":"<=5 words","rows":["<=10 words, 3-4"]},"right":{"title":"<=5 words","rows":["<=10 words, 3-4"]}}   (left = the usual way, right = the better way)
- quote:         {"format":"quote","quote":"<=28 words, a strong opinion the reader will recognise","attribution":"role or team, not a real person's name"}
- poll:          {"format":"poll","title":"the poll question, <=120 characters","rows":["option, <=30 characters", "2-4 options"]}
                 A real choice people disagree on, every option a fair answer. On LinkedIn it becomes a native
                 poll; on Facebook and Instagram the image shows options A-D, so those captions must ask
                 readers to comment their letter (A, B, C or D) and why.
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
}

# Fallback visual rotation when the model returns an unknown format.
FORMAT_PREFERENCE = {
    "blog": ["carousel", "infographic", "checklist", "stat_card"],
    "news": ["stat_card", "quote", "comparison", "carousel"],
    "pain_point": ["checklist", "comparison", "carousel", "infographic"],
    "engagement": ["quote", "poll", "carousel"],
    "competitor": ["comparison", "carousel", "infographic"],
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
            out[k] = humanize(pseo.rebrand(pseo.normalize_text(v)))
        elif isinstance(v, list):
            out[k] = [humanize(pseo.rebrand(pseo.normalize_text(x))) if isinstance(x, str)
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
            spec.items.append({"label": str(it.get("label") or "")[:60], "value": str(it.get("value") or "")[:120]})

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
        spec.rows = [r[:30].strip() for r in spec.rows if r.strip()][:4]

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
    rows = [r[:120] for r in rows][:6]

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


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u20E3\u2190-\u21FF]")
_DASH = re.compile(r"\s*[\u2014\u2013]\s*")

BANNED_PHRASES = (
    "in today's", "fast-paced", "landscape", "dive in", "let's dive", "delve", "game-changer",
    "game changer", "unlock", "elevate", "leverage", "harness", "supercharge", "seamless",
    "revolutioniz", "robust", "navigate", "realm", "tapestry", "embark", "buckle up",
    "level up", "here's the thing", "the truth is", "let that sink in",
)


def humanize(text: str) -> str:
    """Strip the tells that make a caption read as machine-written: emojis, arrows,
    em/en dashes and runs of blank lines. Wording problems are caught by copy_issues."""
    if not isinstance(text, str):
        return text
    t = _EMOJI.sub("", text)
    t = _DASH.sub(", ", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


SITE_DOMAIN = "showupai.live"


def ensure_site(caption: str) -> str:
    """Every caption carries showupai.live once. If the model left it out, add it as
    its own line just above the hashtag line (or at the end when there are none)."""
    if SITE_DOMAIN in caption.lower():
        return caption
    lines = caption.rstrip().split("\n")
    if lines and lines[-1].strip().startswith("#"):
        return "\n".join(lines[:-1]).rstrip() + f"\n\n{SITE_DOMAIN}\n\n" + lines[-1].strip()
    return caption.rstrip() + f"\n\n{SITE_DOMAIN}"


def copy_issues(copy: Dict[str, PlatformCopy]) -> List[str]:
    """Rule checks a reviewer would otherwise do by hand. Empty list = good."""
    issues: List[str] = []
    for platform, block in copy.items():
        cap = block.caption or ""
        low = cap.lower()
        hits = [p for p in BANNED_PHRASES if p in low]
        if hits:
            issues.append(f"{platform}: remove the phrases {', '.join(hits)}")
        if "?" not in cap:
            issues.append(f"{platform}: end with a question that asks readers to comment")
        first = cap.strip().split("\n", 1)[0]
        if platform == "linkedin" and len(first.split()) > 14:
            issues.append("linkedin: the first line must be a hook under 12 words")
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
SOURCE EXCERNS/BODY (excerpt):
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

{VOICE_RULES}
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
  "visual": {{...one of the six formats above...}}
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
        for block in copy.values():
            block.caption = ensure_site(humanize(block.caption))
        issues = copy_issues(copy) if copy else ["no captions returned"]
        if not issues:
            break
        logger.info(f"content_engine: rewrite {kind}/{seed}: {issues}")
        feedback = ("\n\nYOUR PREVIOUS DRAFT BROKE THESE RULES. Rewrite everything and fix them:\n- "
                    + "\n- ".join(issues))

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


def stage_hint_for(kind: str) -> str:
    stage = KIND_STAGE.get(kind, "awareness")
    return f"Aim for '{stage}' — {STAGE_HINTS[stage]}."


def source_type_default(kind: str) -> str:
    return {"blog": "blog", "news": "news", "pain_point": "original",
            "engagement": "original", "competitor": "original"}.get(kind, "original")


__all__ = [
    "ai_json",
    "build_campaign",
    "FORMAT_PREFERENCE",
    "BRAND_RULES",
    "VOICE_RULES",
    "humanize",
    "copy_issues",
    "ensure_site",
    "STAGE_HINTS",
    "stage_hint_for",
]