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
                            max_output_tokens=min(max_tokens, 400), temperature=0.7))
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
                        max_tokens=min(max_tokens, 400), temperature=0.7)
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


TOUCH_CONTEXT = {
    1: "Registration confirmation — confirm their spot, set expectations, one warm CTA. NOT a reminder.",
    2: "7 days before — share ONE provocative insight or uncomfortable truth related to the webinar topic. No 'join us'. Make them think. End with a soft teaser that the answer is in the webinar.",
    3: "3 days before — poll or question. Ask the audience something directly related to the problem this webinar solves. 2-3 poll options. Make it feel like a conversation, not a broadcast.",
    4: "1 day before — share a mini case study or stat that makes the cost of NOT attending feel real. One sentence reminder of the date at the end.",
    5: "Morning of — thought-provoking question or bold claim about the topic. Short. Punchy. No fluff. Join link at end.",
    6: "1 hour before — final reminder only. Join link front and centre. Nothing else. Max 3 sentences.",
    7: "Post-event attendees — share ONE key insight from the session. Not just 'thanks for joining'. Give them something to act on today. Recording link.",
    8: "Post-event no-shows — share what they missed as a teaser insight. Make them regret not attending. Recording link as CTA.",
}

TOUCH_TYPE = {
    1: "confirmation",
    2: "insight",
    3: "poll",
    4: "case_study",
    5: "thought_provoking",
    6: "reminder",
    7: "post_event_insight",
    8: "fomo",
}

EMAIL_RULES = """
EMAIL RULES (follow exactly):
- Max 4 sentences in body. Short. Direct.
- Use these placeholders: {{first_name}}, {{webinar_title}}, {{webinar_date}}, {{webinar_time}}, {{join_link}}, {{recording_link}}
- Subject line: under 8 words, curiosity-driven or benefit-driven
- One CTA only
- No fluff. No "I hope this finds you well". No filler.
- For insight/poll/case_study touches: lead with the insight or question FIRST, mention webinar at end
- Example confirmation: "Hi {{first_name}}, you are in for {{webinar_title}} on {{webinar_date}} at {{webinar_time}}. Add it now: {{join_link}}"
- Example insight touch: "Hi {{first_name}}, here is something most [audience] get wrong: [insight]. We are unpacking this live on {{webinar_date}}. {{join_link}}"
- Example poll touch: "Hi {{first_name}}, quick question before {{webinar_title}}: [poll question]? [option A] or [option B]? We will share results live. Join: {{join_link}}"
"""

SOCIAL_RULES = """
SOCIAL POST RULES (follow exactly):
- Max 3 sentences. Each hits hard.
- VARY the approach based on touch type:
  * insight: open with a bold claim or uncomfortable truth about the topic. No "join us" openers.
  * poll: ask a direct provocative question with 2 options. End with "Drop your answer below."
  * case_study: one specific scenario that makes the problem feel real and costly.
  * thought_provoking: one sentence that makes them stop scrolling. A tension or paradox.
  * reminder/confirmation: short, warm, practical. Join link prominent.
  * fomo: what they missed. Make it tangible. Recording link.
  * post_event_insight: one actionable takeaway from the session. Not "great webinar!".
- LinkedIn/Facebook: 1-2 hashtags at end
- WhatsApp: no hashtags, friendly tone
- Instagram: emoji ok, 3 hashtags max
- BANNED: "Don't miss out", "exciting opportunity", "we are thrilled", "join us for", "register now" as opening
"""


async def _generate_single_channel(webinar: dict, touch_num: int, channel: str, context: str, touch_type: str = "reminder", custom_instructions: str = "") -> tuple:
    """Generate copy for a single channel — runs in parallel."""
    is_email = channel == "email"
    rules = EMAIL_RULES if is_email else SOCIAL_RULES
    schema = '{"subject": "...", "body": "..."}' if is_email else '{"body": "..."}'

    # Build speaker line
    speakers = webinar.get('speakers') or webinar.get('speaker') or ''
    speaker_line = f"Speaker(s): {speakers}" if speakers else ""
    topics = webinar.get('key_topics', '') or ''
    topic_line = f"Key topics: {topics}" if topics else ""
    custom_ctx = webinar.get('custom_context', '') or ''
    custom_block = f"\nSPECIAL INSTRUCTIONS (follow exactly):\n{custom_ctx}" if custom_ctx else ""
    extra = f"\nADDITIONAL INSTRUCTIONS:\n{custom_instructions}" if custom_instructions else ""

    channel_rules = {
        "email": "Write a compelling EMAIL. Subject: 8 words max, curiosity-driven. Body: 3-4 short punchy sentences. Use {{first_name}}, {{webinar_title}}, {{webinar_date}}, {{webinar_time}}, {{join_link}}. No fluff.",
        "linkedin_page": "Write a LINKEDIN POST. Open with a bold stat or question (NOT 'join us'). 3-4 sentences. End with relevant insight. 2 hashtags. Professional but engaging.",
        "linkedin_personal": "Write a personal LINKEDIN POST from the speaker. First-person, authentic, story-driven. 3-4 sentences. Conversational. 1-2 hashtags.",
        "facebook_page": "Write a FACEBOOK POST. Conversational and warm. 2-3 sentences. Include an emoji. Ask a question to boost engagement.",
        "instagram": "Write an INSTAGRAM CAPTION. Hook first line. 3-4 sentences. 3-5 relevant hashtags. Include a call to action.",
        "whatsapp": "Write a WHATSAPP message. Friendly and personal. 2-3 sentences max. No hashtags. Include join link naturally.",
        "circle": "Write a CIRCLE COMMUNITY post. Community-first tone. Share value first. 3-4 sentences. Encourage discussion.",
    }
    ch_rule = channel_rules.get(channel, "Write engaging social copy. 3 sentences. Platform-appropriate.")
    
    prompt = f"""You are writing pre-webinar campaign content for ShowUpAI.

WEBINAR: {webinar.get('title', '')}
DATE: {webinar.get('starts_at', '')}  
AUDIENCE: {webinar.get('target_audience', '')}
DESCRIPTION: {(webinar.get('description') or '')[:200]}

TOUCH #{touch_num} — {touch_type.upper()}
GOAL: {context[:150]}
{f"SPECIAL INSTRUCTIONS: {custom_block[:150]}" if custom_block else ""}

CHANNEL RULES: {ch_rule}

Write 2 variants — safe (professional) and casual (conversational/urgent).
Make it genuinely engaging — NOT generic. Reference the actual topic.
Return ONLY valid JSON: {{"safe": {schema}, "casual": {schema}}}"""

    try:
        raw = await _call_llm(prompt, max_tokens=600)
        return channel, json.loads(raw)
    except Exception as e:
        fallback_body = f"Hi {{{{first_name}}}}, {{{{webinar_title}}}} is on {{{{webinar_date}}}} at {{{{webinar_time}}}}. Join here: {{{{join_link}}}}"
        if is_email:
            return channel, {"safe": {"subject": "Your spot is confirmed", "body": fallback_body}, "casual": {"subject": "See you there!", "body": fallback_body}}
        return channel, {"safe": {"body": fallback_body}, "casual": {"body": fallback_body}}


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
Channel: {channel.upper()}

{SOCIAL_RULES}

Return ONLY valid JSON:
{{
  "content": "the post",
  "subject": "email subject if email channel else empty string",
  "hashtags": ["#tag1", "#tag2"],
  "image_prompt": "brief description for a promotional square image"
}}"""

    try:
        raw = await _call_llm(user_msg, max_tokens=600)
        return json.loads(raw)
    except Exception:
        return {"content": f"{{{{webinar_title}}}} — {{{{webinar_date}}}}. Register: {{{{join_link}}}}", "hashtags": [], "image_prompt": ""}



async def compute_dynamic_schedule(webinar_starts_at: str, touch_num: int, total_touches: int = 11) -> str | None:
    """
    Dynamically calculate touch send time based on days available before webinar.
    
    Strategy:
    - Touch 1: Immediate (on registration)
    - Touches 2-9: Spread evenly across available days (1 per day gap)
    - Touch 10: 1 day after event
    - Touch 11: 3 days after event
    
    If webinar is < 3 days away: compress schedule, send 1-2 touches/day
    If webinar is > 21 days away: use full 3-week warmup schedule
    """
    from datetime import datetime, timezone, timedelta
    
    if not webinar_starts_at:
        return None
    
    try:
        now = datetime.now(timezone.utc)
        webinar_dt = datetime.fromisoformat(webinar_starts_at.replace("Z", "+00:00"))
        days_available = max(0, (webinar_dt - now).days)
        
        # Post-event touches
        if touch_num == 10:
            return (webinar_dt + timedelta(days=1)).replace(hour=10, minute=0, second=0).isoformat()
        if touch_num == 11:
            return (webinar_dt + timedelta(days=3)).replace(hour=10, minute=0, second=0).isoformat()
        
        # Touch 1 = immediate (no schedule)
        if touch_num == 1:
            return None
        
        # Touches 2-9 = pre-event sequence
        pre_touches = 8  # touches 2-9
        touch_index = touch_num - 2  # 0-indexed
        
        if days_available <= 0:
            return None
        elif days_available >= 21:
            # Full 3-week schedule
            ideal_days = [21, 19, 14, 10, 8, 5, 1, 0.04]  # 0.04 = 1 hour before
        elif days_available >= 14:
            # 2-week schedule
            ratio = days_available / 21
            ideal_days = [int(d * ratio) for d in [21, 19, 14, 10, 8, 5, 1, 0.04]]
        elif days_available >= 7:
            # 1-week schedule — compress
            spread = days_available / pre_touches
            ideal_days = [days_available - int(i * spread) for i in range(pre_touches)]
            ideal_days[-1] = 0.04  # last one = 1 hour before
        else:
            # Less than 7 days — daily touches
            spread = max(1, days_available / pre_touches)
            ideal_days = [max(0.04, days_available - int(i * spread)) for i in range(pre_touches)]
        
        if touch_index >= len(ideal_days):
            return None
            
        days_before = ideal_days[touch_index]
        
        if days_before < 1:
            # Hours before
            hours_before = int(days_before * 24)
            send_dt = webinar_dt - timedelta(hours=max(1, hours_before))
        else:
            send_dt = webinar_dt - timedelta(days=int(days_before))
            send_dt = send_dt.replace(hour=9, minute=0, second=0, microsecond=0)
        
        return send_dt.isoformat()
        
    except Exception as e:
        logger.error(f"Dynamic schedule error: {e}")
        return None

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
