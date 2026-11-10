// Content for the public SEO pages: /compare/*, /tools/* and the /webinar-attendance pillar guide.
// Shared by the React pages and scripts/prerender-blog.mjs (which loads this file through a temp .mjs copy),
// so keep it import-free and plain data.
//
// Rules for this file:
// - Only claims we can stand behind. ShowUpAI facts match public/index.html (JSON-LD + FAQ).
// - Competitor rows describe what their product is built for, not prices (prices change; we would go stale).
// - Benchmarks are quoted with their source and year, never as our own result.
// - Links inside markdown must be absolute https:// URLs (splitInline only links those).

export const SITE = "https://showupai.live";

export const BENCHMARKS = [
  { source: "ON24", year: 2025, rate: 60, note: "average registrant-to-attendee conversion on ON24's platform" },
  { source: "Livestorm", year: 2025, rate: 51.3, note: "average attendance rate on Livestorm's platform" },
  { source: "Demio (Banzai)", year: 2022, rate: 38, note: "average live-session attendance on Demio" },
];

const SHOWUP_ROWS = {
  what: "Webinar attendance software: it gets registrants to show up",
  hosting: "No. Works alongside your webinar platform",
  sequence: "11 touches, from 21 days before to 2 days after",
  copy: "AI writes each touch per channel, in two variants",
  channels: "Email, LinkedIn, Facebook, Instagram, WhatsApp/SMS, Circle.so, calendar invites",
  approval: "Yes. Nothing sends until you approve it",
  noshow: "Separate follow-ups for attendees and no-shows",
  analytics: "Attendance by channel",
  price: "From $29/month, 14-day free trial, no card",
};

const ROW_LABELS = [
  ["what", "What it is"],
  ["hosting", "Hosts the live webinar"],
  ["sequence", "Reminder sequence"],
  ["copy", "Who writes the reminders"],
  ["channels", "Reminder channels"],
  ["approval", "Approve messages before sending"],
  ["noshow", "No-show follow-up"],
  ["analytics", "Attendance reporting"],
  ["price", "Pricing"],
];

// key = URL slug. Keep the old slugs (demio, zoom, webinarjam, activecampaign, buffer) so existing links still work.
export const COMPARE = {
  zoom: {
    name: "Zoom Webinars",
    kind: "webinar platform",
    title: "ShowUpAI vs Zoom Webinars: Get More Registrants to Show Up",
    description: "Zoom Webinars hosts the event and sends email reminders. ShowUpAI adds an 11-touch, multi-channel attendance sequence on top. How they differ and when to use both.",
    intro: "Zoom Webinars is the webinar add-on to Zoom's video platform. It handles registration, the live room, Q&A, polls and recordings, and it can send a registration confirmation, reminder emails and a follow-up email to attendees and absentees.",
    them: {
      what: "Video webinar platform",
      hosting: "Yes",
      sequence: "Confirmation plus configurable reminder emails",
      copy: "You write them (templates provided)",
      channels: "Email",
      approval: "Not applicable: you set the emails up yourself",
      noshow: "Follow-up email to absentees",
      analytics: "Registration and attendee reports",
      price: "See Zoom's pricing page",
    },
    chooseThem: "you need a reliable room for the live session, breakout rooms and recordings, and your audience already reads email reminders.",
    chooseUs: "people register on Zoom but a large share never join, and you want reminders on LinkedIn, WhatsApp and social as well as email, without writing every message yourself.",
    together: "Keep hosting on Zoom. Paste the Zoom join link into ShowUpAI, and it runs the reminder sequence and no-show follow-up around your Zoom event.",
    faq: [
      ["Does ShowUpAI replace Zoom Webinars?", "No. ShowUpAI doesn't host the live session. You keep Zoom for the event, and ShowUpAI handles the messages that get registrants into the room."],
      ["Can I send Zoom webinar reminders on WhatsApp?", "Not from Zoom itself, which sends email. ShowUpAI can send the join link on WhatsApp, with SMS as a fallback, alongside the email reminders."],
    ],
  },
  demio: {
    name: "Demio",
    kind: "webinar platform",
    title: "ShowUpAI vs Demio: Webinar Platform vs Attendance Engine",
    description: "Demio is a webinar platform for marketing teams, with built-in email reminders. ShowUpAI is a multi-channel attendance sequence that works with any platform. Here's the difference.",
    intro: "Demio (part of Banzai) is a browser-based webinar platform for marketing teams. It runs live, automated and series webinars and sends registration, reminder and follow-up emails from inside the product.",
    them: {
      what: "Webinar platform for marketing teams",
      hosting: "Yes",
      sequence: "Built-in reminder and follow-up emails",
      copy: "You write them (defaults provided)",
      channels: "Email (other channels through integrations)",
      approval: "Not applicable: you set the emails up yourself",
      noshow: "Follow-up emails",
      analytics: "Attendance and engagement analytics",
      price: "See Demio's pricing page",
    },
    chooseThem: "you want one tool for hosting, registration pages and replays, and email reminders are enough for your audience.",
    chooseUs: "you already have a webinar platform, or your audience lives on LinkedIn, WhatsApp or a community, and you want a longer, value-led warm-up instead of a few reminder emails.",
    together: "Host on Demio and point ShowUpAI at the event. ShowUpAI covers the channels and the three-week warm-up that Demio's emails don't.",
    faq: [
      ["What attendance rate does Demio report?", "Demio (Banzai) reported 38% average attendance for live sessions in 2022. That's their platform average, not a ShowUpAI result."],
      ["Is ShowUpAI a Demio alternative?", "Only for the reminder part. If you want to stop paying for a host, you need another platform for the live room. ShowUpAI works with Zoom, Teams, Google Meet, Livestorm, Luma and others."],
    ],
  },
  livestorm: {
    name: "Livestorm",
    kind: "webinar platform",
    title: "ShowUpAI vs Livestorm: Which One Raises Webinar Attendance?",
    description: "Livestorm is a browser-based webinar and video engagement platform with email reminders. ShowUpAI runs an 11-touch attendance sequence across 7 channels. A side-by-side comparison.",
    intro: "Livestorm is a browser-based platform for webinars, demos and virtual events. Registration, email reminders, the live room, recordings and analytics are all in one product, with integrations for CRMs and marketing tools.",
    them: {
      what: "Browser-based webinar and video engagement platform",
      hosting: "Yes",
      sequence: "Customisable reminder emails",
      copy: "You write them (templates provided)",
      channels: "Email (others through integrations)",
      approval: "Not applicable: you set the emails up yourself",
      noshow: "Follow-up emails, replay links",
      analytics: "Event and attendee analytics",
      price: "See Livestorm's pricing page",
    },
    chooseThem: "you want an all-in-one, browser-based event platform with CRM integrations.",
    chooseUs: "you want attendance worked on across social, WhatsApp and community channels, with AI-written copy you approve.",
    together: "Run the event on Livestorm. ShowUpAI uses the Livestorm event link and handles the multi-channel reminders.",
    faq: [
      ["What attendance rate does Livestorm report?", "Livestorm reports a 51.3% average attendance rate on its platform. Use it as a reference point, then compare your own webinars against your own baseline."],
      ["Does ShowUpAI work with Livestorm?", "Yes. Any platform with a join link works, including Livestorm."],
    ],
  },
  webinarjam: {
    name: "WebinarJam",
    kind: "webinar platform",
    title: "ShowUpAI vs WebinarJam: Reminders Built for Attendance",
    description: "WebinarJam is an all-in-one webinar platform with email and SMS reminders. ShowUpAI adds a value-led, multi-channel sequence with AI-written copy. How to choose.",
    intro: "WebinarJam is an all-in-one webinar platform popular with course creators and marketers. It covers registration pages, the live room, offers during the webinar, replays, and email and SMS reminders.",
    them: {
      what: "All-in-one webinar and sales platform",
      hosting: "Yes",
      sequence: "Email and SMS reminders you configure",
      copy: "You write them (templates provided)",
      channels: "Email, SMS",
      approval: "Not applicable: you set the messages up yourself",
      noshow: "Replay and follow-up messages",
      analytics: "Registration, attendance and sales stats",
      price: "See WebinarJam's pricing page",
    },
    chooseThem: "you sell from the webinar and want hosting, offers and replays in one product.",
    chooseUs: "your reminders feel generic, you want touches that build interest for three weeks (an insight, a poll, a case study), and you want LinkedIn, Instagram and community posts as well.",
    together: "Keep WebinarJam for the live room and offers. ShowUpAI runs the warm-up and reminder touches around it.",
    faq: [
      ["Doesn't WebinarJam already send reminders?", "Yes, by email and SMS. ShowUpAI starts earlier, adds social and community channels, and writes each touch for its channel."],
    ],
  },
  on24: {
    name: "ON24",
    kind: "enterprise webinar platform",
    title: "ShowUpAI vs ON24: Attendance Without an Enterprise Contract",
    description: "ON24 is an enterprise webinar and digital events platform. ShowUpAI is a lightweight attendance engine for any platform, from $29/month. When each one fits.",
    intro: "ON24 is an enterprise platform for webinars, virtual events and content experiences, used by large B2B marketing teams. It includes registration, email reminders, engagement tools and deep analytics connected to marketing automation.",
    them: {
      what: "Enterprise webinar and digital events platform",
      hosting: "Yes",
      sequence: "Configurable reminder emails",
      copy: "Your team writes them",
      channels: "Email (plus your marketing automation)",
      approval: "Through your own team's process",
      noshow: "Follow-up emails, on-demand replays",
      analytics: "Deep engagement analytics",
      price: "Enterprise contract (ask ON24)",
    },
    chooseThem: "you're a large B2B team that needs enterprise analytics, integrations and event programs.",
    chooseUs: "you're a smaller team, agency or creator, you host on Zoom, Teams or Meet, and you want the attendance work done without an enterprise budget.",
    together: "Enterprise teams on ON24 can still use ShowUpAI for channels their email program doesn't reach, like WhatsApp, Instagram and communities.",
    faq: [
      ["What attendance rate does ON24 report?", "ON24 reports a 60% average registrant-to-attendee conversion on its platform (2025). That's an ON24 platform average."],
    ],
  },
  gotowebinar: {
    name: "GoTo Webinar",
    kind: "webinar platform",
    title: "ShowUpAI vs GoTo Webinar: More Show-Ups From the Same Signups",
    description: "GoTo Webinar hosts webinars and sends reminder emails. ShowUpAI adds an 11-touch sequence across email, social, WhatsApp and community channels. Compare them here.",
    intro: "GoTo Webinar (formerly GoToWebinar) is a long-standing webinar platform with registration, reminder and follow-up emails, polls, recordings and reporting.",
    them: {
      what: "Webinar platform",
      hosting: "Yes",
      sequence: "Confirmation, reminder and follow-up emails",
      copy: "You write them (templates provided)",
      channels: "Email",
      approval: "Not applicable: you set the emails up yourself",
      noshow: "Follow-up email to absentees",
      analytics: "Registration and attendance reports",
      price: "See GoTo's pricing page",
    },
    chooseThem: "you need a dependable host with classic webinar features.",
    chooseUs: "your registrants ignore email and you want to reach them on the channels they actually check.",
    together: "Host on GoTo Webinar and run ShowUpAI's sequence with the GoTo join link.",
    faq: [
      ["Can ShowUpAI send GoTo Webinar join links?", "Yes. Add the event's join link and ShowUpAI sends it one hour before, along with the rest of the sequence."],
    ],
  },
  activecampaign: {
    name: "ActiveCampaign",
    kind: "email marketing automation",
    title: "ShowUpAI vs ActiveCampaign for Webinar Reminders",
    description: "You can build webinar reminders in ActiveCampaign, but you design and write every step yourself. ShowUpAI plans and writes the whole attendance sequence for you.",
    intro: "ActiveCampaign is a marketing automation and CRM platform. Many webinar hosts build their reminder sequences there as automations triggered by a registration tag or form.",
    them: {
      what: "Email marketing automation and CRM",
      hosting: "No",
      sequence: "Whatever automation you build",
      copy: "You write every email",
      channels: "Email (SMS on some plans)",
      approval: "You control it, because you build it",
      noshow: "Possible if you build the branch",
      analytics: "Email opens and clicks",
      price: "See ActiveCampaign's pricing page",
    },
    chooseThem: "you have the time to design, write and maintain automations for every event, and email is your main channel.",
    chooseUs: "you run webinars often and want the timing, copy and channels planned for each event automatically, with your approval at the end.",
    together: "Keep ActiveCampaign as your CRM and newsletter tool. Let ShowUpAI run the event-specific sequence, including the social and WhatsApp touches.",
    faq: [
      ["Does ShowUpAI send email through ActiveCampaign?", "Not at the moment. Email goes through your Brevo, Mailchimp, SendGrid or Buzz.ai account."],
    ],
  },
  buffer: {
    name: "Buffer",
    kind: "social media scheduler",
    title: "ShowUpAI vs Buffer for Promoting Webinars",
    description: "Buffer schedules social posts you write. ShowUpAI writes and times webinar-specific posts and reminders across social, email and WhatsApp. Here's the difference.",
    intro: "Buffer is a social media scheduling tool. You write posts, queue them and publish across your social accounts, with an AI assistant for drafting.",
    them: {
      what: "Social media scheduler",
      hosting: "No",
      sequence: "None: it doesn't know your event date",
      copy: "You write the posts (AI assistant available)",
      channels: "Social networks",
      approval: "You approve, because you schedule it",
      noshow: "No",
      analytics: "Social post analytics",
      price: "See Buffer's pricing page",
    },
    chooseThem: "you need a general social calendar for all your content.",
    chooseUs: "you want posts and reminders tied to a webinar date: awareness three weeks out, a poll, a case study, urgency, the join link and a no-show follow-up.",
    together: "Keep Buffer for everyday social posting. Use ShowUpAI for the webinar campaign.",
    faq: [
      ["Can Buffer send webinar reminders?", "Buffer publishes social posts. It doesn't send emails, WhatsApp messages or calendar invites to registrants, which is what ShowUpAI adds."],
    ],
  },
};

export const COMPARE_ROWS = ROW_LABELS;
export const SHOWUP = SHOWUP_ROWS;

export function compareFaq(c) {
  return [
    [`What is the difference between ShowUpAI and ${c.name}?`,
      `${c.name} is a ${c.kind}. ShowUpAI is webinar attendance software: it writes, schedules and sends an 11-touch reminder sequence across email, LinkedIn, Facebook, Instagram, WhatsApp/SMS, Circle.so and calendar invites, and you approve every message before it goes out.`],
    [`Should I use ShowUpAI or ${c.name}?`, `Choose ${c.name} if ${c.chooseThem} Choose ShowUpAI if ${c.chooseUs}`],
    ...c.faq,
  ];
}

// ── Free tools ───────────────────────────────────────────────────────────────
export const TOOLS = {
  "webinar-no-show-calculator": {
    name: "Webinar No-Show Calculator",
    title: "Webinar Attendance Rate & No-Show Calculator (Free)",
    description: "Free webinar attendance rate calculator: see your show-up rate, no-show rate and the pipeline lost to no-shows, compare with published benchmarks, and get a dated 11-touch reminder plan.",
    intro: "Enter how many people registered and how many joined. The calculator shows your show-up and no-show rates, compares them with published platform averages, and estimates what the no-shows cost you.",
    how: [
      "Show-up rate = attendees ÷ registrants × 100.",
      "No-show rate = 100 − show-up rate.",
      "Lost value = no-shows × the share of attendees who become leads × value per lead.",
    ],
    faq: [
      ["What is a good webinar show-up rate?", "Published platform averages range from about 38% (Demio/Banzai, live sessions, 2022) to 51.3% (Livestorm) and 60% (ON24, 2025). Compare each webinar against your own previous ones first."],
      ["Why do people register for webinars and not show up?", "Common reasons are forgetting, a clash with work, losing the join link, or the topic feeling less urgent on the day. A reminder plan that builds interest and sends the join link at the right time addresses most of them."],
      ["How do I calculate my webinar attendance rate?", "Divide the number of people who joined live by the number who registered, then multiply by 100. 70 attendees from 200 registrants is a 35% attendance rate and a 65% no-show rate."],
      ["How do I reduce webinar no-shows?", "Start reminders earlier, use more than one channel, send the join link an hour before, add a calendar invite on registration, and follow up with no-shows with the replay."],
    ],
  },
  "webinar-roi-calculator": {
    name: "Webinar ROI Calculator",
    title: "Webinar ROI Calculator: Cost per Attendee, Leads and Return",
    description: "Free webinar ROI calculator: enter your costs, registrants, attendance and conversion rates to get cost per attendee, customers won, revenue and ROI.",
    intro: "Enter what the webinar costs and how your funnel converts. The calculator works out attendees, customers, revenue, cost per attendee and return on investment, and shows how much a better show-up rate is worth.",
    how: [
      "Attendees = registrants × show-up rate.",
      "Customers = attendees × attendee-to-customer rate.",
      "Revenue = customers × average deal value.",
      "ROI = (revenue − cost) ÷ cost × 100.",
    ],
    faq: [
      ["How do you measure webinar ROI?", "Add up every cost (ads, tools, the hours your team spent), then track the revenue from customers who attended. ROI is revenue minus cost, divided by cost."],
      ["What costs should I include?", "Paid promotion, webinar and email tools, speaker fees, design, and the time your team spent planning, promoting and running the event."],
    ],
  },
  "webinar-title-generator": {
    name: "Webinar Title Generator",
    title: "Free Webinar Title Generator: 12 Title Ideas in Seconds",
    description: "Free webinar title generator: enter your topic, audience and outcome to get 12 clear, benefit-led webinar title ideas you can copy. No sign-up needed.",
    intro: "Enter your topic, who it's for and the result they'll get. You get 12 title ideas in proven formats: how-to, numbered, mistakes, case study and live workshop. Edit the one that sounds most like you.",
    how: [
      "Lead with the outcome the audience wants, not the product.",
      "Name the audience so the right people recognise themselves.",
      "Keep it under about 70 characters so it fits in emails and calendar invites.",
    ],
    faq: [
      ["What makes a good webinar title?", "A specific outcome, a clear audience and a reason to attend live. 'How B2B marketers can double demo bookings from webinars' beats 'Q3 product webinar'."],
      ["How long should a webinar title be?", "Aim for 40–70 characters. Longer titles get cut off in email subject lines, calendar invites and social previews."],
    ],
  },
};

export function titleIdeas({ topic = "", audience = "", outcome = "", number = 5 }) {
  const t = topic.trim() || "Webinar Promotion";
  const a = audience.trim() || "Marketers";
  const o = outcome.trim() || "get more results";
  const n = Math.max(3, Math.min(12, Number(number) || 5));
  const cap = (s) => s.replace(/\b([a-z])/g, (m) => m.toUpperCase());
  return [
    `How ${a} Can ${cap(o)} With ${t}`,
    `${n} ${t} Strategies That Help ${a} ${cap(o)}`,
    `${t} for ${a}: A Live Step-by-Step Workshop`,
    `The ${t} Playbook: How to ${cap(o)} in 30 Days`,
    `${n} ${t} Mistakes ${a} Make (and How to Fix Them)`,
    `From Zero to Results: ${t} for ${a}`,
    `Live Q&A: Your ${t} Questions, Answered`,
    `How We Used ${t} to ${cap(o)} (Case Study)`,
    `${t} in 2026: What's Working for ${a} Right Now`,
    `Stop Guessing: A Simple ${t} Framework for ${a}`,
    `${cap(o)} Faster: ${n} ${t} Tactics You Can Use Today`,
    `${t}, Explained: A Practical Guide for ${a}`,
  ];
}

// ── Pillar guide ─────────────────────────────────────────────────────────────
export const GUIDE = {
  slug: "webinar-attendance",
  title: "How to Increase Webinar Attendance: The Complete Guide (2026)",
  seoTitle: "How to Increase Webinar Attendance (2026 Guide) | ShowUpAI",
  description: "A practical guide to raising webinar attendance: benchmarks, why registrants no-show, an 11-touch reminder timeline, channels, copy examples and how to measure it.",
  updated: "2026-11-04",
  // blog posts whose slug contains one of these words are listed under "More on webinar attendance"
  clusterWords: ["attendance", "no-show", "noshow", "reminder", "show-up", "follow-up", "registration", "promotion"],
  markdown: `## What webinar attendance rate should you expect?

Most hosts lose between 40% and 60% of registrants before the event starts. Published platform averages give you a reference point:

| Source | Year | Average attendance |
| --- | --- | --- |
| ON24 | 2025 | 60% |
| Livestorm | 2025 | 51.3% |
| Demio (Banzai), live sessions | 2022 | 38% |

These are platform averages, and each platform measures a little differently. Your own previous webinars are a better baseline. Work out your current rate with the free [webinar no-show calculator](https://showupai.live/tools/webinar-no-show-calculator).

## Why registrants don't show up

People rarely skip a webinar on purpose. The usual reasons are:

- **They forgot.** They registered two weeks ago and nothing reminded them on the day.
- **They lost the join link.** It's buried in an email from three weeks back.
- **Something else came up.** A meeting landed on top of it, and the webinar wasn't in their calendar.
- **The urgency faded.** The topic felt important when they signed up, but not on the day.
- **They planned to watch the replay.** If nothing gives them a reason to join live, many won't.

Each of these has a fix, and almost all of the fixes happen between registration and start time.

## The 11-touch attendance timeline

One reminder the day before isn't enough. A sequence that builds interest for three weeks, then turns to urgency, works much better:

1. **On registration:** confirmation plus a calendar invite (.ics), so the slot is held.
2. **21 days before:** an awareness post that explains why the topic matters now.
3. **19 days before:** an insight or newsletter-style touch that teaches one useful thing.
4. **14 days before:** an engagement poll, so registrants commit to a question they want answered.
5. **10 days before:** a short case study that shows the result the webinar promises.
6. **8 days before:** an infographic teaser of one idea from the session.
7. **5 days before:** an urgency message: what they miss if they only watch the replay.
8. **1 day before:** a final warm-up with the agenda.
9. **1 hour before:** the join link, on its own, in the channel they check most.
10. **After the event:** a thank-you for attendees with the next step.
11. **2 days after:** a no-show follow-up with the replay and one reason to book a call.

## Use more than one channel

Email alone misses people who don't check their inbox before a meeting. Spread the touches across the channels your audience actually uses:

- **Email** for the confirmation, the agenda and the replay.
- **Calendar invite** on registration. It's the single most useful touch.
- **WhatsApp or SMS** for the join link an hour before. It gets seen.
- **LinkedIn, Facebook and Instagram** for awareness, the poll and the case study.
- **Community spaces** like Circle.so if your audience lives there.

For copy you can reuse, see the [WhatsApp reminder templates](https://showupai.live/blog/webinar-reminder-whatsapp-template) and the [no-show follow-up email guide](https://showupai.live/blog/webinar-follow-up-email-for-no-shows).

## Write each touch for its channel

The same text pasted into every channel reads like spam. Keep each message short and specific to where it lands:

- **Email subject one day before:** "Tomorrow, 11am: the 3 questions you asked us"
- **WhatsApp one hour before:** "We go live in 60 minutes. Here's your link: …"
- **LinkedIn post two weeks before:** a poll about the problem the webinar solves.

## Get more of the right registrants

Attendance starts with who registers. A clear, benefit-led title attracts people who care about the outcome. Try the free [webinar title generator](https://showupai.live/tools/webinar-title-generator), and work through the [webinar promotion checklist](https://showupai.live/blog/webinar-promotion-checklist) and [how to increase webinar registrations](https://showupai.live/blog/how-to-increase-webinar-registrations).

## Follow up with attendees and no-shows separately

Attendees and no-shows need different messages. Thank attendees and give them the next step while the session is fresh. Send no-shows the replay with one highlight that makes them want to watch, and invite them to the next live session. See [post-webinar follow-up best practices](https://showupai.live/blog/best-practices-for-post-webinar-followup).

## Measure what works

Track the show-up rate for every webinar, and if you can, which channel the attendee came through. Then change one thing at a time: the day, the time, the first touch, the join-link channel. Put a number on what each improvement is worth with the [webinar ROI calculator](https://showupai.live/tools/webinar-roi-calculator). For more industry numbers, see the [webinar statistics roundup](https://showupai.live/blog/webinar-statistics).

## Do it without writing 11 messages per webinar

ShowUpAI plans this timeline for each webinar, writes every touch for its channel in two variants, and sends it on schedule after you approve it. It works with Zoom, Microsoft Teams, Google Meet, Livestorm, Luma and any other platform with a join link. See how it compares with [Zoom Webinars](https://showupai.live/compare/zoom), [Demio](https://showupai.live/compare/demio) and [Livestorm](https://showupai.live/compare/livestorm).`,
  faq: [
    ["How do I increase webinar attendance?", "Send a calendar invite on registration, start reminders up to three weeks before with value-led touches, use more than one channel, send the join link one hour before, and follow up with no-shows with the replay."],
    ["What is a good webinar attendance rate?", "Published platform averages range from 38% (Demio/Banzai, live sessions, 2022) to 51.3% (Livestorm) and 60% (ON24, 2025). Your own previous webinars are the best baseline."],
    ["When should I send webinar reminders?", "On registration, then on a timeline that ends with a reminder one day before and the join link one hour before. Earlier touches should give value, not just repeat the date."],
  ],
};

export const COMPARE_INDEX = {
  title: "ShowUpAI Comparisons: Webinar Platforms and Reminder Tools",
  description: "How ShowUpAI compares with Zoom Webinars, Demio, Livestorm, WebinarJam, ON24, GoTo Webinar, ActiveCampaign and Buffer for getting webinar registrants to show up.",
};

export const TOOLS_INDEX = {
  title: "Free Webinar Tools: No-Show Calculator, ROI Calculator, Title Generator",
  description: "Free webinar tools from ShowUpAI: calculate no-show cost and webinar ROI, and generate webinar title ideas. No sign-up needed.",
};

// ── Lead magnet: a dated 11-touch attendance plan for the visitor's own webinar ──────────────
// offsetH = hours relative to the webinar start (negative = before). "On registration" has no fixed time.
export const PLAN_TOUCHES = [
  { offsetH: null, channel: "Email + calendar invite", title: "Confirmation + calendar invite", tip: "Send the .ics on registration so the slot is held in their calendar." },
  { offsetH: -21 * 24, channel: "LinkedIn / social", title: "Awareness post", tip: "Why the topic matters now. One problem, one promise." },
  { offsetH: -19 * 24, channel: "Email", title: "Insight / newsletter touch", tip: "Teach one useful thing from the session. No hard sell." },
  { offsetH: -14 * 24, channel: "LinkedIn poll / email", title: "Engagement poll", tip: "Ask which question they want answered. People show up for their own question." },
  { offsetH: -10 * 24, channel: "Email / social", title: "Case study", tip: "A short before/after that shows the result the webinar promises." },
  { offsetH: -8 * 24, channel: "Instagram / LinkedIn", title: "Infographic teaser", tip: "One idea from the session as a visual." },
  { offsetH: -5 * 24, channel: "Email", title: "Urgency message", tip: "What they miss if they only wait for the replay (live Q&A, bonus)." },
  { offsetH: -24, channel: "Email", title: "Final warm-up + agenda", tip: "Subject with the time: 'Tomorrow, 11am: ...'." },
  { offsetH: -1, channel: "WhatsApp / SMS", title: "Join link", tip: "Just the link and the start time, in the channel they check most." },
  { offsetH: 3, channel: "Email", title: "Thank-you for attendees", tip: "Slides, replay and the one next step." },
  { offsetH: 48, channel: "Email", title: "No-show follow-up", tip: "Replay + one highlight + invite to the next live session." },
];

export function buildPlan(startIso) {
  const start = new Date(startIso);
  if (Number.isNaN(start.getTime())) return [];
  return PLAN_TOUCHES.map((t, i) => ({
    n: i + 1, ...t,
    at: t.offsetH === null ? null : new Date(start.getTime() + t.offsetH * 3600 * 1000),
  }));
}

const icsDate = (d) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
const icsText = (s) => String(s).replace(/[\\,;]/g, (m) => "\\" + m).replace(/\n/g, "\\n");

export function planToIcs(plan, webinarName = "My webinar") {
  const stamp = icsDate(new Date());
  const ev = plan.filter((p) => p.at).map((p) => [
    "BEGIN:VEVENT",
    `UID:showupai-plan-${p.n}-${p.at.getTime()}@showupai.live`,
    `DTSTAMP:${stamp}`,
    `DTSTART:${icsDate(p.at)}`,
    `DTEND:${icsDate(new Date(p.at.getTime() + 15 * 60 * 1000))}`,
    `SUMMARY:${icsText(`Touch ${p.n}: ${p.title} (${webinarName})`)}`,
    `DESCRIPTION:${icsText(`${p.channel}. ${p.tip} Plan by ShowUpAI: https://showupai.live/webinar-attendance`)}`,
    "END:VEVENT",
  ].join("\r\n"));
  return ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ShowUpAI//Attendance plan//EN", "CALSCALE:GREGORIAN", ...ev, "END:VCALENDAR"].join("\r\n");
}

export function planToText(plan, webinarName = "My webinar") {
  const f = (d) => d ? d.toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "On registration";
  return [`11-touch attendance plan for: ${webinarName}`, "", ...plan.map((p) => `${p.n}. ${f(p.at)} | ${p.channel} | ${p.title}\n   ${p.tip}`), "",
    "Made with the free ShowUpAI planner: https://showupai.live/tools/webinar-no-show-calculator",
    "Want this written and sent for you? https://showupai.live/waitlist"].join("\n");
}
