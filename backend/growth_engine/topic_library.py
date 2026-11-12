"""Topic library for ShowUpAI's own social posts (original, non-blog campaigns).

Why this exists
---------------
The engine used to rotate through 14 fixed one-line angles and was told "no
statistics allowed", so original posts all sounded alike. This library gives it:

* five content pillars Ashu asked for (2026-11-02): show-up / attendance best
  practices, webinar lead generation, how mature B2B teams run webinar programs,
  current webinar + social trends, and follow-up / repurposing;
* 40+ specific briefs, ordered so consecutive posts change pillar;
* a small bank of benchmark numbers, each tied to the report it comes from, so a
  post may cite a real number (and stat_card posts become possible) without the
  model inventing one;
* rotating hook styles so two posts in a row never open the same way.

Every number below was checked against a public page on 2026-11-02. Sources are
benchmark reports from webinar vendors; the post names the report, never a
customer or a person. Edit freely: the engine reads these lists at run time.
"""

from datetime import datetime
from typing import Dict, List, Optional

# ── fact bank ────────────────────────────────────────────────────────────────
# key -> (claim, source). The source string is what the post must credit.
FACTS: Dict[str, tuple] = {
    "showup_avg": ("Average webinar show-up rate is 47.7%, across 33,786 sessions",
                   "Livestorm 2026 Webinar Benchmark Report"),
    "last_7_days": ("49.7% of webinar registrations come in the final 7 days before the event",
                    "Livestorm 2026 Webinar Benchmark Report"),
    "day_of": ("15% of registrations happen on the day of the webinar itself",
               "Livestorm 2026 Webinar Benchmark Report"),
    "top_challenge": ("54.2% of webinar teams say turning registrants into attendees is their top challenge, "
                      "more than the 43.6% who say getting registrations",
                      "Livestorm 2026 Webinar Benchmark Report"),
    "email_channel": ("86.3% of webinar teams name email a top-3 registration channel, about double "
                      "organic social at 43.3%",
                      "Livestorm 2026 Webinar Benchmark Report"),
    "best_day_tue": ("Tuesday has the highest show-up rate at 51.7%; August is the weakest month at 42.9%",
                     "Livestorm 2026 Webinar Benchmark Report"),
    "watch_time": ("Average watch time is 26 minutes, about 38% of the session's runtime",
                   "Livestorm 2026 Webinar Benchmark Report"),
    "on24_conversion": ("57% of webinar registrants converted to attendees in 2024",
                        "ON24 2025 Webinar Benchmarks Report"),
    "on24_on_demand": ("45% of webinar attendees watched on demand in 2024, and the share has grown every year since 2022",
                       "ON24 2025 Webinar Benchmarks Report"),
    "on24_minutes": ("The average webinar attendee stays engaged for 51 minutes",
                     "ON24 2025 Webinar Benchmarks Report"),
    "univid_live": ("49% of registrants attend live; 57% engage once replays are counted",
                    "Univid 2025, 1,000+ webinars"),
    "univid_cta": ("The average webinar CTA converts 22% of attendees; webinars with two CTAs reach 25%",
                   "Univid 2025, 1,000+ webinars"),
    "contrast_time": ("Webinars starting at 2 PM saw 55% live attendance, 11 AM saw 50%",
                      "Contrast, 500,000 registrants, 2025"),
    "thursday_64": ("Thursday webinars had the highest attendance rate at 64%",
                    "TwentyThree webinar benchmarks"),
    "leadgen_65": ("65% of organisations that run webinars use them for lead generation",
                   "TwentyThree webinar benchmarks"),
    "software_28": ("Software and services webinars average 28% attendance; pharma leads at 50%",
                    "Banzai webinar benchmarks"),
    "cost_per_lead": ("A webinar lead costs about $72, against $198 for a trade show and $811 for a conference",
                      "Cvent, 2025"),
    "length_45": ("Most high-performing webinars run about 45 minutes; under 30 loses engagement, over 60 loses people",
                  "BigMarker webinar benchmarks"),
}

# ── pillars ──────────────────────────────────────────────────────────────────
PILLAR_HINTS = {
    "attendance": ("PILLAR: show-up best practices. Give the reader one specific thing to change before "
                   "their next webinar that raises live attendance."),
    "lead_gen": ("PILLAR: webinar lead generation. Treat the webinar as a pipeline engine: who to invite, "
                 "what to capture, how fast sales follows up, what makes an attendee a qualified lead."),
    "playbook": ("PILLAR: how mature B2B teams run webinar programs. Describe practices that are standard in "
                 "well-run enterprise webinar programs (series cadence, run-of-show, producer roles, "
                 "segmented invites, sales handoff, content hubs). Do NOT claim that a specific named company "
                 "does something; say 'the best-run B2B webinar teams' or 'enterprise webinar teams'."),
    "trends": ("PILLAR: what is changing in webinars and B2B social right now. Take a side on the trend and "
               "tell the host what to do about it this quarter."),
    "follow_up": ("PILLAR: after the webinar. Replays, no-shows, repurposing and the follow-up that turns "
                  "a session into meetings."),
}

# Ordered so consecutive picks change pillar. Each brief is one specific idea.
TOPICS: List[Dict] = [
    {"pillar": "attendance", "brief": "Half of registrations arrive in the last week, so the reminder plan must "
     "work for people who sign up 2 days out, not just 3 weeks out", "facts": ["last_7_days", "day_of"]},
    {"pillar": "lead_gen", "brief": "Registrants are not leads. Score them by what they did: attended live, "
     "stayed past minute 30, asked a question, clicked the CTA", "facts": ["univid_cta"]},
    {"pillar": "playbook", "brief": "Enterprise webinar teams run a series, not one-offs: same day, same time, "
     "every month, so the audience builds a habit", "facts": []},
    {"pillar": "trends", "brief": "On-demand viewing keeps growing. Plan the replay as a product, not an "
     "afterthought", "facts": ["on24_on_demand"]},
    {"pillar": "follow_up", "brief": "The no-show email is the most ignored message in webinar marketing. "
     "Write it differently from the attendee email", "facts": []},

    {"pillar": "attendance", "brief": "The day-of reminders matter most: a 1 hour reminder and a 'we are live' "
     "message with the join link one click away", "facts": ["day_of"]},
    {"pillar": "lead_gen", "brief": "Webinars are one of the cheapest lead sources in B2B, but only if the "
     "follow-up happens within 24 hours", "facts": ["cost_per_lead"]},
    {"pillar": "playbook", "brief": "The run-of-show document big webinar teams use: minute-by-minute plan, "
     "producer, moderator, backup host, poll timing", "facts": []},
    {"pillar": "trends", "brief": "Email still drives registrations; social alone does not fill a webinar. "
     "Use social to remind, not just to announce", "facts": ["email_channel"]},
    {"pillar": "follow_up", "brief": "One webinar should become a month of content: clips, a carousel, a blog "
     "post, a quote card, an FAQ", "facts": []},

    {"pillar": "attendance", "brief": "Pick the day and time from data, then test your own audience", "facts":
     ["best_day_tue", "contrast_time"]},
    {"pillar": "lead_gen", "brief": "The registration form: ask for 3 fields, then one qualifying question "
     "that tells sales who to call first", "facts": []},
    {"pillar": "playbook", "brief": "Big teams co-host with a partner brand to borrow an audience and split "
     "the promotion", "facts": []},
    {"pillar": "trends", "brief": "Shorter webinars: 45 minutes beats 60, and the last 15 minutes is where "
     "people leave", "facts": ["length_45", "watch_time"]},
    {"pillar": "follow_up", "brief": "Gated vs public replays: gate the live seat, not the recording",
     "facts": []},

    {"pillar": "attendance", "brief": "Show-up is the real bottleneck, not registrations", "facts":
     ["top_challenge", "showup_avg"]},
    {"pillar": "lead_gen", "brief": "Put one clear CTA in the session, said out loud twice, with a reason to "
     "act today", "facts": ["univid_cta"]},
    {"pillar": "playbook", "brief": "Enterprise teams hand sales a hot list within an hour of the session: who "
     "attended, what they asked, what they clicked", "facts": []},
    {"pillar": "trends", "brief": "LinkedIn rewards saves and long reads now. Promote your webinar with a "
     "useful carousel, not a 'register now' banner", "facts": []},
    {"pillar": "follow_up", "brief": "Send attendees the one slide everyone screenshotted, not the full deck",
     "facts": []},

    {"pillar": "attendance", "brief": "Give a live-only reason to attend: a template, live Q&A, or a teardown "
     "shown only on the call. Say it in every reminder", "facts": []},
    {"pillar": "lead_gen", "brief": "Invite fewer, better people: segment the list and write one invite per "
     "segment", "facts": []},
    {"pillar": "playbook", "brief": "How a webinar team plans a quarter: theme, 3 sessions, guest list, "
     "promotion calendar, content repurposing plan", "facts": []},
    {"pillar": "trends", "brief": "Your industry's benchmark matters more than the average. Software webinars "
     "fill far fewer seats than pharma", "facts": ["software_28"]},
    {"pillar": "follow_up", "brief": "Ask no-shows one question instead of sending the replay blind", "facts": []},

    {"pillar": "attendance", "brief": "A calendar invite sent the moment someone registers is the cheapest "
     "attendance lever there is", "facts": []},
    {"pillar": "lead_gen", "brief": "Most organisations run webinars for leads, so stand out by teaching, not "
     "pitching: 75% teaching, 25% product", "facts": ["leadgen_65"]},
    {"pillar": "playbook", "brief": "The dry run big teams never skip: tech check, slides, polls, a backup "
     "presenter, 30 minutes before go-live", "facts": []},
    {"pillar": "trends", "brief": "Reminders that live where people already are: WhatsApp and LinkedIn messages "
     "get seen when emails get buried", "facts": []},
    {"pillar": "follow_up", "brief": "The 3-email follow-up after a webinar: thank you plus key slide, case "
     "study, then a meeting ask", "facts": []},

    {"pillar": "attendance", "brief": "The reminder sequence that works: confirmation, 7 days, 1 day, 1 hour, "
     "live now. What each one should say", "facts": ["on24_conversion"]},
    {"pillar": "lead_gen", "brief": "Polls are lead data: one poll question that tells you who is buying this "
     "quarter", "facts": []},
    {"pillar": "playbook", "brief": "Big webinar teams measure show-up rate, average watch time and meetings "
     "booked, not registrations", "facts": ["watch_time", "on24_minutes"]},
    {"pillar": "trends", "brief": "Benchmarks disagree on the best webinar day. That tells you to test your "
     "own audience", "facts": ["best_day_tue", "thursday_64"]},
    {"pillar": "follow_up", "brief": "Replays count: plan for the people who watch later, they are still "
     "engaged leads", "facts": ["univid_live"]},

    {"pillar": "attendance", "brief": "The subject line of the reminder email decides attendance more than the "
     "webinar title", "facts": []},
    {"pillar": "lead_gen", "brief": "Turn webinar questions into sales talk tracks and FAQ pages", "facts": []},
    {"pillar": "playbook", "brief": "The moderator role: why every serious webinar team has someone who is not "
     "the speaker running chat and Q&A", "facts": []},
    {"pillar": "trends", "brief": "AI writes the reminders now, but the host still has to approve them. Speed "
     "without sounding like a robot", "facts": []},
    {"pillar": "follow_up", "brief": "Retarget no-shows with a short clip of the best 60 seconds", "facts": []},
]

# Conversation starters: take a side people will argue with.
ENGAGEMENT_TOPICS: List[Dict] = [
    {"brief": "Should webinar replays be gated or free for anyone?", "facts": []},
    {"brief": "45 minutes or 60? What is the right webinar length", "facts": ["length_45"]},
    {"brief": "Is a 40% show-up rate good or bad?", "facts": ["showup_avg", "software_28"]},
    {"brief": "Unpopular opinion: most webinars should be 20 minutes shorter", "facts": ["watch_time"]},
    {"brief": "Which reminder matters most: 1 day before, 1 hour before, or 'we are live'?", "facts": []},
    {"brief": "Camera on or off for the host's opening slide?", "facts": []},
    {"brief": "Do you pitch your product on a webinar, or only teach?", "facts": []},
    {"brief": "Registrations or attendees: which number goes in your report to the boss?", "facts":
     ["top_challenge"]},
    {"brief": "Tuesday, Wednesday or Thursday: when does your audience actually show up?", "facts":
     ["best_day_tue", "thursday_64"]},
    {"brief": "The most common mistake new webinar hosts make", "facts": []},
]

# Approach vs approach. Never a named product other than ShowUpAI.
COMPARISON_TOPICS: List[str] = [
    "Your webinar platform's built-in reminder emails vs a multi-channel reminder sequence",
    "Manual reminder emails from your marketing tool vs an automated pre-event sequence",
    "Email-only reminders vs email plus LinkedIn, WhatsApp and calendar",
    "Sending the replay to everyone vs a separate follow-up for attendees and no-shows",
    "One-off webinars vs a monthly webinar series",
    "Gated replay vs public replay",
    "A 60-minute webinar with 45 minutes of slides vs a 40-minute session with live Q&A",
    "Promoting a webinar with 'register now' banners vs useful content posts that lead to the signup",
    "Counting registrations vs counting live attendees and meetings booked",
]

# The first line decides reach. Rotate how it opens.
HOOK_STYLES = [
    "Open with a contrarian claim the reader half-believes the opposite of.",
    "Open with the costly mistake the reader is making right now, stated plainly.",
    "Open with a sharp before/after in one line.",
    "Open with the number from the sourced facts and what it means for the reader.",
    "Open with a 1-line scene from the host's day (the empty room at minute five, the replay nobody opens).",
    "Open with 'Steal this' plus the exact playbook the post gives away.",
]


def _index(seed: str) -> int:
    day, _, n = seed.rpartition("-")
    try:
        return datetime.fromisoformat(day).date().toordinal() * 2 + int(n)
    except ValueError:
        return sum(seed.encode())


def pick_topic(seed: str, need_fact: bool = False) -> Dict:
    pool = [t for t in TOPICS if t["facts"]] if need_fact else TOPICS
    return pool[_index(seed) % len(pool)]


def pick_engagement(seed: str, need_fact: bool = False) -> Dict:
    pool = [t for t in ENGAGEMENT_TOPICS if t["facts"]] if need_fact else ENGAGEMENT_TOPICS
    return pool[_index(seed) % len(pool)]


def pick_comparison(seed: str) -> str:
    return COMPARISON_TOPICS[_index(seed) % len(COMPARISON_TOPICS)]


def pick_hook(seed: str, has_facts: bool) -> str:
    styles = HOOK_STYLES if has_facts else [h for h in HOOK_STYLES if "number" not in h]
    # Offset by 3 so the hook does not move in lockstep with the topic.
    return styles[(_index(seed) * 5 + 3) % len(styles)]


def fact_block(keys: Optional[List[str]]) -> str:
    """The facts a post may cite. With none, the post must not state any statistic."""
    rows = [FACTS[k] for k in (keys or []) if k in FACTS]
    if not rows:
        return ("SOURCED FACTS: none. Do not state any statistic or study finding. "
                "Write practical, experience-based advice only.")
    lines = "\n".join(f"- {claim} (source: {src})" for claim, src in rows)
    return ("SOURCED FACTS (the only numbers you may use; name the source in the caption when you cite "
            "one, e.g. 'per the Livestorm 2026 Webinar Benchmark Report'):\n" + lines)


__all__ = ["FACTS", "TOPICS", "ENGAGEMENT_TOPICS", "COMPARISON_TOPICS", "HOOK_STYLES", "PILLAR_HINTS",
           "pick_topic", "pick_engagement", "pick_comparison", "pick_hook", "fact_block"]
