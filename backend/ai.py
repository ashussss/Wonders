"""
ShowUpAI — AI copy generation using Google Gemini
"""
import os
import json
import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger("showup.ai")

# ── Gemini client ─────────────────────────────────────
from google import genai as genai_sdk
from google.genai import types as genai_types
from groq import Groq

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3.5-flash-lite"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "openai/gpt-oss-20b"

# Init clients
try:
    gemini_client = genai_sdk.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    logger.info(f"Gemini client: {'ready' if gemini_client else 'not configured'}")
except Exception as e:
    logger.error(f"Gemini init error: {e}")
    gemini_client = None

try:
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
    logger.info(f"Groq client: {'ready' if groq_client else 'not configured'}")
except Exception as e:
    logger.error(f"Groq init error: {e}")
    groq_client = None

async def _call_llm(prompt: str, max_tokens: int = 1500) -> str:
    """Call LLM — Gemini primary, Groq fallback on rate limit."""
    
    def _clean_json(text):
        if "```" in text:
            for part in text.split("```"):
                p = part.strip()
                if p.startswith("json"): text = p[4:].strip(); break
                elif "{" in p: text = p; break
        s, e = text.find("{"), text.rfind("}") + 1
        return text[s:e] if s != -1 else "{}"

    # Try Gemini first
    if gemini_client:
        for attempt in range(2):
            try:
                def _gemini():
                    r = gemini_client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            max_output_tokens=min(max_tokens, 2000), temperature=0.7))
                    logger.info(f"Gemini OK: {len(r.text)} chars")
                    return r.text.strip()
                loop = asyncio.get_event_loop()
                text = await loop.run_in_executor(None, _gemini)
                return _clean_json(text)
            except Exception as ex:
                if "429" in str(ex) and attempt < 1:
                    logger.info("Gemini rate limit — trying Groq fallback")
                    break  # fall through to Groq
                logger.error(f"Gemini failed: {ex}")

    # Groq fallback
    if groq_client:
        for attempt in range(3):
            try:
                def _groq():
                    r = groq_client.chat.completions.create(
                        model=GROQ_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=min(max_tokens, 2000), temperature=0.7)
                    logger.info(f"Groq OK: {len(r.choices[0].message.content)} chars")
                    return r.choices[0].message.content.strip()
                loop = asyncio.get_event_loop()
                text = await loop.run_in_executor(None, _groq)
                return _clean_json(text)
            except Exception as ex:
                if "429" in str(ex) and attempt < 2:
                    await asyncio.sleep(15 * (attempt + 1))
                    continue
                logger.error(f"Groq failed: {ex}")
                break

    logger.error("Both Gemini and Groq failed")
    return "{}"

    def _sync_call():
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=min(max_tokens, 400),
            temperature=0.7,
        )
        text = response.choices[0].message.content.strip()
        logger.info(f"Groq OK: {len(text)} chars")
        return text

    try:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _sync_call)

        # Clean JSON
        if "```" in text:
            for part in text.split("```"):
                p = part.strip()
                if p.startswith("json"):
                    text = p[4:].strip()
                    break
                elif "{" in p:
                    text = p
                    break

        s = text.find("{")
        e = text.rfind("}") + 1
        if s == -1:
            logger.error(f"No JSON: {text[:100]}")
            return "{}"
        return text[s:e]

    except Exception as ex:
        logger.error(f"Groq failed: {ex}")
        return "{}"


# What each touch in config.TOUCH_DEFS has to do. Keyed by touch number, so the copy
# matches the moment it is sent (a "1 day before" message never reads like a recap).
TOUCH_CONTEXT = {
    1: "Registration confirmation, sent the second they sign up. Confirm the date and time, give the join link, "
       "ask them to add it to their calendar now, and ask them to hit reply with the one question they want answered.",
    2: "About 3 weeks out. Name the specific problem this session solves, in the words the audience uses. "
       "One concrete example of the problem. Say what they will be able to do after the session.",
    3: "About 19 days out. Share one genuinely useful tip or insight on the topic they can use today, "
       "then say the session goes deeper on it.",
    4: "About 2 weeks out. Ask the audience one direct question about how they handle this problem today, "
       "with 2 or 3 short options. Ask them to answer in the comments or by reply. Say you'll cover the results live.",
    5: "About 10 days out. Tell one short, realistic scenario of the problem playing out and what it costs. "
       "No invented names, companies or numbers. Then what the session will show them.",
    6: "About 8 days out. Tease the 3 things the session covers as a short plain list. Make each one specific.",
    7: "About 5 days out. Practical reminder: the date, the time, and the one outcome they get. "
       "Ask them to block the time in their calendar now.",
    8: "Day before, sent at the same time of day as the session. 'This time tomorrow'. Restate the one outcome, "
       "the time, and the join link. Mention they can send a question in advance by replying.",
    9: "1 hour before. Very short. 'We start in an hour.' The join link on its own line. Nothing else.",
    10: "Day after, to people who attended. Thank them in one line, give the one key takeaway to act on today, "
        "the recording link, and ask what they'll try first.",
    11: "Two days after, to people who registered but didn't come. No guilt. Say what was covered in one line, "
        "give the recording link, and offer to answer their question by reply.",
    12: "The moment the session starts, to everyone registered. 'We're live now.' The join link. One line saying "
        "they haven't missed anything important yet.",
}

TOUCH_TYPE = {
    1: "confirmation", 2: "problem", 3: "insight", 4: "poll", 5: "case_study", 6: "teaser",
    7: "reminder", 8: "day_before", 9: "one_hour", 10: "post_event_insight", 11: "no_show", 12: "live_now",
}

VOICE_RULES = """
VOICE (every channel):
- Write as the host, one real person, in the first person ("I", "we"). Not a brand. Not a marketer.
- Sound like a message a busy professional would actually send a colleague: plain words, contractions,
  specific details from the topic. Mix short and medium sentences.
- Never invent statistics, studies, customer names, companies or quotes.
- No em dashes or en dashes. No emojis except where the channel rule allows them.
- Banned words and phrases: in today's, fast-paced, landscape, dive in, deep dive, delve, game-changer,
  unlock, elevate, leverage, harness, supercharge, seamless, revolutionize, robust, navigate, realm,
  embark, level up, don't miss out, exciting opportunity, we are thrilled, we're excited to announce,
  join us for, valuable insights, take your X to the next level, I hope this finds you well.
"""

EMAIL_RULES = """
EMAIL RULES:
- Subject: 3 to 7 words, lowercase except names, like a person typed it. No clickbait, no ALL CAPS, no emojis.
- Body: 40 to 110 words. Start with "Hi {{first_name}}," on its own line. Short paragraphs, one idea each.
- Exactly one call to action. For pre-event emails that is the join link: {{join_link}}.
- Placeholders you may use: {{first_name}}, {{webinar_title}}, {{webinar_date}}, {{webinar_time}},
  {{join_link}}, {{calendar_link}}, {{recording_link}}, {{speaker}}. Never write a real link or date yourself.
- Sign off with just {{speaker}} on the last line.
"""

SOCIAL_RULES = """
SOCIAL POST RULES:
- First line is the hook, under 12 words, alone on its line. It must make someone stop scrolling:
  a specific problem, a surprising claim you can back up, or a direct question.
- Then 2 to 5 short lines. One idea per line. A blank line between ideas.
- Include the registration link exactly once, as {{join_link}}, on its own line near the end.
- End with one specific question about this topic that a reader can answer from experience,
  and ask them to answer in the comments. Never just "Thoughts?".
- Never use {{first_name}} in a social post.
"""

CHANNEL_RULES = {
    "email": "An email to one registrant.",
    "linkedin": "A LinkedIn post. 500 to 1200 characters. Exactly 3 relevant hashtags on the last line.",
    "linkedin_page": "A LinkedIn company Page post. 500 to 1200 characters. Exactly 3 relevant hashtags on the last line.",
    "linkedin_personal": "A personal LinkedIn post by the host, first person, a little more personal than a Page post. "
                         "500 to 1200 characters. Up to 3 hashtags on the last line.",
    "facebook": "A Facebook Page post. 150 to 450 characters. Conversational. No hashtags.",
    "facebook_page": "A Facebook Page post. 150 to 450 characters. Conversational. No hashtags.",
    "instagram": "An Instagram caption. 300 to 900 characters. Hook in the first 125 characters. "
                 "Write 'link in bio' instead of the link. One emoji at most. 3 to 5 specific hashtags on the last line.",
    "whatsapp": "A WhatsApp message to one registrant. 1 to 3 short sentences. Start with 'Hi {{first_name}},'. "
                "Include {{join_link}}. No hashtags. No sign-off.",
    "circle": "A post in the host's online community. 300 to 900 characters. Share something useful first, "
              "then the session, then a question to start discussion. No hashtags.",
}

BANNED_PHRASES = (
    "in today's", "fast-paced", "landscape", "dive in", "deep dive", "delve", "game-changer", "game changer",
    "unlock", "elevate", "leverage", "harness", "supercharge", "seamless", "revolutioniz", "robust",
    "navigate", "realm", "embark", "level up", "don't miss out", "exciting opportunity", "we are thrilled",
    "excited to announce", "join us for", "valuable insights", "next level", "hope this finds you",
)

# Used when the model is unavailable or returns nothing usable. Human, specific to the
# moment, and built only from placeholders so they are always correct.
FALLBACK_COPY = {
    "confirmation": ("you're in: {{webinar_title}}",
                     "Hi {{first_name}},\n\nYou're registered for {{webinar_title}} on {{webinar_date}} at {{webinar_time}}.\n\n"
                     "Your link to join: {{join_link}}\n\nPut it in your calendar now so it doesn't get buried: {{calendar_link}}\n\n"
                     "Hit reply and tell me the one question you want answered. I'll try to cover it live.\n\n{{speaker}}"),
    "day_before": ("this time tomorrow",
                   "Hi {{first_name}},\n\nQuick one: {{webinar_title}} is tomorrow at {{webinar_time}}.\n\n"
                   "Here's your link so you don't have to dig for it: {{join_link}}\n\n"
                   "If there's something you want me to cover, reply and tell me.\n\n{{speaker}}"),
    "one_hour": ("we start in an hour",
                 "Hi {{first_name}},\n\nWe start in an hour.\n\n{{join_link}}\n\nSee you there,\n{{speaker}}"),
    "live_now": ("we're live",
                 "Hi {{first_name}},\n\nWe've just started. Jump in here: {{join_link}}\n\n"
                 "You haven't missed anything important yet.\n\n{{speaker}}"),
    "post_event_insight": ("thanks for coming",
                           "Hi {{first_name}},\n\nThanks for spending the time with us.\n\n"
                           "Here's the recording if you want to rewatch any part: {{recording_link}}\n\n"
                           "What's the one thing you'll try first? Reply and tell me.\n\n{{speaker}}"),
    "no_show": ("sorry we missed you",
                "Hi {{first_name}},\n\nWe missed you at {{webinar_title}}. It happens.\n\n"
                "Here's the recording: {{recording_link}}\n\n"
                "If you had a question you wanted answered, reply and I'll answer it myself.\n\n{{speaker}}"),
}
_DEFAULT_FALLBACK = ("{{webinar_title}} on {{webinar_date}}",
                     "Hi {{first_name}},\n\nA reminder that {{webinar_title}} is on {{webinar_date}} at {{webinar_time}}.\n\n"
                     "Your link to join: {{join_link}}\n\n{{speaker}}")
_SOCIAL_FALLBACK = ("{{webinar_title}}\n\n{{webinar_date}}, {{webinar_time}}.\n\n"
                    "Save your spot: {{join_link}}\n\nWhat's the one question you'd want answered on this? Tell me below.")


def fallback_copy(channel: str, touch_type: str) -> dict:
    if channel in ("email", "whatsapp"):
        subject, body = FALLBACK_COPY.get(touch_type, _DEFAULT_FALLBACK)
        if channel == "whatsapp":
            body = body.split("\n\n{{speaker}}")[0].replace("\n\n", " ")
        block = {"subject": subject, "body": body} if channel == "email" else {"body": body}
    else:
        block = {"body": _SOCIAL_FALLBACK}
    return {"safe": block, "casual": dict(block)}


def banned_hits(copy: dict) -> list:
    text = json.dumps(copy).lower()
    return [p for p in BANNED_PHRASES if p in text]


def _usable(copy: Any, is_email: bool) -> bool:
    if not isinstance(copy, dict):
        return False
    for v in ("safe", "casual"):
        block = copy.get(v)
        if not isinstance(block, dict) or not str(block.get("body") or "").strip():
            return False
        if is_email and not str(block.get("subject") or "").strip():
            return False
    return True


async def _generate_single_channel(webinar: dict, touch_num: int, channel: str, context: str, touch_type: str = "reminder", custom_instructions: str = "") -> tuple:
    """Generate copy for a single channel — runs in parallel."""
    is_email = channel == "email"
    rules = EMAIL_RULES if is_email else ("" if channel == "whatsapp" else SOCIAL_RULES)
    schema = '{"subject": "...", "body": "..."}' if is_email else '{"body": "..."}'

    speakers = webinar.get('speakers') or webinar.get('speaker') or ''
    facts = "\n".join(line for line in [
        f"WEBINAR: {webinar.get('title', '')}",
        f"HOST / SPEAKER: {speakers}" if speakers else "",
        f"AUDIENCE: {webinar.get('target_audience', '')}" if webinar.get('target_audience') else "",
        f"WHAT IT'S ABOUT: {(webinar.get('description') or '')[:600]}",
        f"KEY TOPICS / OUTCOMES: {webinar.get('key_topics')}" if webinar.get('key_topics') else "",
        f"HOST'S SPECIAL INSTRUCTIONS (follow exactly): {webinar.get('custom_context')}" if webinar.get('custom_context') else "",
        f"BRAND RULES: {custom_instructions}" if custom_instructions else "",
    ] if line)

    prompt = f"""You write the messages that get people who registered for a webinar to actually show up.

{facts}

THIS MESSAGE: touch #{touch_num} ({touch_type})
JOB: {context}

CHANNEL: {CHANNEL_RULES.get(channel, "A short social post.")}
{VOICE_RULES}
{rules}
Write 2 variants of the same message:
- "safe": warm and professional.
- "casual": more relaxed and direct, like a quick note.
Use the real topic. Nothing generic that could be about any webinar.
Return ONLY valid JSON: {{"safe": {schema}, "casual": {schema}}}"""

    copy = None
    for attempt in range(2):
        try:
            raw = await _call_llm(prompt, max_tokens=1400)
            cand = json.loads(raw)
        except Exception:
            continue
        if not _usable(cand, is_email):
            continue
        copy = cand
        hits = banned_hits(cand)
        if not hits:
            break
        prompt += f"\n\nYour last draft used these banned phrases: {', '.join(hits)}. Rewrite without them."
    if copy is None:
        return channel, fallback_copy(channel, touch_type)
    from touch_render import clean
    for v in ("safe", "casual"):
        for k in ("subject", "body"):
            if isinstance(copy[v].get(k), str):
                copy[v][k] = clean(copy[v][k], channel)
    return channel, copy


async def generate_touch_copy(webinar: dict, touch_num: int, channels: list, custom_instructions: str = "") -> dict:
    """Generate copy for ALL channels in parallel — much faster."""
    context = TOUCH_CONTEXT.get(touch_num, f"Touch {touch_num}")

    touch_type = TOUCH_TYPE.get(touch_num, "reminder")
    
    # Semaphore to limit concurrent calls (avoid rate limits but stay fast)
    sem = asyncio.Semaphore(3)
    
    async def _gen_with_limit(ch):
        async with sem:
            await asyncio.sleep(0.3)  # small stagger
            for attempt in range(3):
                try:
                    r = await _generate_single_channel(webinar, touch_num, ch, context, touch_type, custom_instructions)
                    return r
                except Exception as e:
                    if "429" in str(e) and attempt < 2:
                        wait = 10 * (attempt + 1)
                        await asyncio.sleep(wait)
                        continue
                    return e
            return Exception("max retries")
    
    # Run all channels concurrently (with semaphore limiting)
    results = await asyncio.gather(*[_gen_with_limit(ch) for ch in channels], return_exceptions=True)

    channel_copy = {}
    for result in results:
        if isinstance(result, Exception):
            continue
        ch, copy = result
        channel_copy[ch] = copy

    return {
        "angle": context,
        "touch_type": touch_type,
        "channels": channel_copy,
        "reasoning": f"Touch {touch_num} ({touch_type}) — {context}"
    }


async def generate_lead_magnets(webinar: dict) -> dict:
    prompt = f"""Webinar: {webinar.get('title', '')}
Description: {webinar.get('description', '')}
Audience: {webinar.get('target_audience', '')}

Write supporting content. No fabricated company names or fake statistics.

Return ONLY valid JSON:
{{
  "case_study": "150 word illustrative scenario showing value of this topic",
  "snippets": ["sharp insight 1", "sharp insight 2", "sharp insight 3", "sharp insight 4"],
  "one_pager": {{
    "title": "...",
    "outline": ["section 1", "section 2", "section 3", "section 4", "section 5"]
  }}
}}"""

    try:
        raw = await _call_llm(prompt, max_tokens=1000)
        return json.loads(raw)
    except Exception:
        return {"case_study": "", "snippets": [], "one_pager": {"title": "", "outline": []}}


async def generate_adhoc_post(webinar: dict, channel: str = "linkedin", prompt: str = "",
                               audience: str = "", with_poll: bool = False, custom_brief: str = "") -> dict:
    brief = custom_brief or f"Webinar: {webinar.get('title', '')}. Audience: {webinar.get('target_audience', '')}."

    user_msg = f"""{brief}
Channel: {CHANNEL_RULES.get(channel, channel.upper())}
{VOICE_RULES}
{SOCIAL_RULES}

Return ONLY valid JSON:
{{
  "content": "the post",
  "subject": "email subject if email channel else empty string",
  "hashtags": ["#tag1", "#tag2"],
  "image_prompt": "brief description for a promotional square image"
}}"""

    try:
        raw = await _call_llm(user_msg, max_tokens=1200)
        return json.loads(raw)
    except Exception:
        return {"content": _SOCIAL_FALLBACK, "hashtags": [], "image_prompt": ""}



# Days before the session for the warm-up touches when there are 3+ weeks of lead time.
NOMINAL_DAYS_BEFORE = {2: 21, 3: 19, 4: 14, 5: 10, 6: 8, 7: 5}
SEND_HOUR_LOCAL = 9          # pre-event emails land at the start of the reader's day
POST_EVENT_HOUR_LOCAL = 10


def _warmup_days(lead_days: float) -> Dict[int, int]:
    """Whole days before the session for touches 2-7, scaled to the lead time.

    Each touch gets its own day (no two warm-ups on one day) and the last one is at
    least 2 days out, because day-before, 1-hour and live-now have their own touches.
    """
    scale = min(1.0, lead_days / 21)
    nums = sorted(NOMINAL_DAYS_BEFORE)
    days = {n: int(NOMINAL_DAYS_BEFORE[n] * scale) for n in nums}
    floor = 2
    for n in reversed(nums):
        days[n] = max(days[n], floor)
        floor = days[n] + 1
    return days


async def compute_dynamic_schedule(webinar_starts_at: str, touch_num: int, total_touches: int = 12,
                                   tz: str = "") -> str | None:
    """Send time (UTC ISO) for a touch, or None when it has no fixed time.

    Day-before goes out exactly 24 hours ahead ("this time tomorrow"), then 1 hour
    before, then at the start ("we're live"). Warm-ups go at 9am in the webinar's own
    timezone. A touch whose time has already passed (short lead time) is not
    scheduled rather than fired late in a burst.
    """
    from datetime import datetime, timezone, timedelta
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    if not webinar_starts_at or touch_num == 1:
        return None
    try:
        start = datetime.fromisoformat(webinar_starts_at.replace("Z", "+00:00"))
    except ValueError as e:
        logger.error(f"Dynamic schedule error: {e}")
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo((tz or "UTC").strip())
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    now = datetime.now(timezone.utc)
    local_start = start.astimezone(zone)

    def at_local(day_offset: int, hour: int) -> datetime:
        d = (local_start + timedelta(days=day_offset)).replace(hour=hour, minute=0, second=0, microsecond=0)
        return d.astimezone(timezone.utc)

    if touch_num == 10:
        send = at_local(1, POST_EVENT_HOUR_LOCAL)
    elif touch_num == 11:
        send = at_local(2, POST_EVENT_HOUR_LOCAL)
    elif touch_num == 12:
        send = start
    elif touch_num == 9:
        send = start - timedelta(hours=1)
    elif touch_num == 8:
        send = start - timedelta(hours=24)
    elif touch_num in NOMINAL_DAYS_BEFORE:
        lead_days = (start - now).total_seconds() / 86400
        send = at_local(-_warmup_days(lead_days)[touch_num], SEND_HOUR_LOCAL)
    else:
        return None

    if touch_num <= 9 and send <= now:
        return None
    return send.astimezone(timezone.utc).isoformat()


async def compute_send_time(starts_at: str, offset_minutes: int):
    if not starts_at or offset_minutes is None:
        return starts_at
    try:
        from datetime import datetime, timedelta
        dt = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        return (dt + timedelta(minutes=offset_minutes)).isoformat()
    except Exception:
        return starts_at


async def touch_reasoning(touch_num: int, channels: list) -> str:
    context = TOUCH_CONTEXT.get(touch_num, f"Touch {touch_num}")
    return f"{context}. Channels: {', '.join(channels)}."
