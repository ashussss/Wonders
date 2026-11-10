import React, { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";

/**
 * Free "reminder kit" lead magnet, used on blog posts, the blog index, free tools and compare pages.
 * Step 1: the visitor types their webinar title + date (low effort, builds commitment).
 * Step 2: they see the six messages waiting (blurred) and give name + email to unlock them.
 * Step 3: six reminders written for their webinar, with copy buttons, a calendar file that holds
 * each message at its send time, and a CTA to let ShowUpAI send them automatically.
 */

const PREVIEW = [
  ["Registration confirmation", "Email"],
  ["Host's LinkedIn post, 2 days before", "LinkedIn post"],
  ["24 hours before", "Email"],
  ["1 hour before", "WhatsApp"],
  ["At start time", "SMS"],
  ["No-show replay, next morning", "Email"],
];

// A headline that fits the page the visitor is reading.
export function kitPitch(source = "", competitor = "") {
  const s = String(source).toLowerCase();
  if (competitor) return {
    title: `Running your next webinar on ${competitor}? Get your reminders written for you`,
    sub: `Type your webinar title and date. We'll write the 6 reminder messages that get registrants to show up, ready to paste into ${competitor}, email and WhatsApp.`,
  };
  if (s.includes("whatsapp")) return {
    title: "Get these WhatsApp reminders written for your webinar",
    sub: "Type your webinar title and date. In 30 seconds you get WhatsApp, email, SMS and LinkedIn reminders written for it, with the exact time to send each one.",
  };
  if (s.includes("linkedin")) return {
    title: "Get your LinkedIn post and reminders written for your webinar",
    sub: "Type your webinar title and date. You get a LinkedIn post plus the email, WhatsApp and SMS reminders, each with its send time.",
  };
  if (s.includes("sms") || s.includes("text-message")) return {
    title: "Get your SMS and email reminders written for your webinar",
    sub: "Type your webinar title and date. You get 6 ready-to-send reminders, each with the exact time to send it.",
  };
  if (/(email|subject|confirmation|follow-?up|replay|thank-you)/.test(s)) return {
    title: "Get your reminder emails written for your webinar",
    sub: "Type your webinar title and date. You get the confirmation, day-before and replay emails (plus WhatsApp and SMS nudges), written for your topic.",
  };
  return {
    title: "Get 6 reminder messages written for your webinar, free",
    sub: "Type your webinar title and date. In 30 seconds you get the email, WhatsApp, SMS and LinkedIn messages that get registrants to actually show up, with the time to send each one.",
  };
}

function defaultStart() {
  const d = new Date(Date.now() + 14 * 864e5);
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T11:00`;
}

// send_at comes back as the typed local time with a +00:00 suffix: read the wall-clock part only.
const wall = (iso) => (iso ? String(iso).slice(0, 16) : "");
function fmtWhen(iso) {
  if (!iso) return "As soon as they register";
  const d = new Date(wall(iso));
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

const icsEscape = (s) => String(s || "").replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
function kitToIcs(items, title) {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ShowUpAI//Reminder kit//EN", "CALSCALE:GREGORIAN"];
  items.filter((i) => i.send_at).forEach((i, n) => {
    const t = wall(i.send_at).replace(/[-:]/g, "") + "00";
    const body = (i.subject ? `Subject: ${i.subject}\n\n` : "") + i.body;
    lines.push("BEGIN:VEVENT", `UID:kit-${n}-${t}@showupai.live`, `DTSTAMP:${stamp}`, `DTSTART:${t}`,
      "DURATION:PT15M", `SUMMARY:${icsEscape(`Send: ${i.label} (${i.channel}) - ${title}`)}`,
      `DESCRIPTION:${icsEscape(body + "\n\nAutomate this: https://showupai.live/register")}`, "END:VEVENT");
  });
  lines.push("END:VCALENDAR");
  return lines.join("\r\n");
}
function kitToText(items, title) {
  return `Reminder messages for: ${title}\n\n` + items.map((i, n) =>
    `${n + 1}. ${i.label} (${i.channel}) - send: ${fmtWhen(i.send_at)}\n` + (i.subject ? `Subject: ${i.subject}\n` : "") + `${i.body}\n`
  ).join("\n") + "\nLet ShowUpAI send these automatically: https://showupai.live/register\n";
}
function download(name, text, type) {
  try {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = document.createElement("a");
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) { /* ignore */ }
}

const input = "w-full min-w-0 px-4 py-2.5 rounded-xl border border-white/15 bg-white/5 text-white text-sm placeholder:text-gray-500 outline-none focus:ring-2 focus:ring-orange-500";
const btn = "px-5 py-3 rounded-xl bg-orange-600 hover:bg-orange-500 text-white text-sm font-bold disabled:opacity-60";

export default function ReminderKit({ source = "", placement = "kit", competitor = "", defaultTitle = "", id = "reminder-kit" }) {
  const pitch = kitPitch(source, competitor);
  const [step, setStep] = useState("details"); // details | unlock | loading | done
  const [title, setTitle] = useState(defaultTitle);
  const [start, setStart] = useState(defaultStart());
  const [audience, setAudience] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [items, setItems] = useState([]);
  const [emailed, setEmailed] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState("");

  const next = (e) => { e.preventDefault(); setErr(""); setStep("unlock"); };
  const unlock = async (e) => {
    e.preventDefault();
    if (step === "loading") return;
    setStep("loading"); setErr("");
    try {
      const r = await api.post("/leads/reminder-kit", { name, email, title, starts_at: start, audience, slug: source, placement, website });
      setItems(r.data?.items || []);
      setEmailed(!!r.data?.emailed);
      setStep("done");
      try { localStorage.setItem("showup_subscribed", "1"); } catch (e2) { /* ignore */ }
      try { if (window.gtag) window.gtag("event", "generate_lead", { lead_source: `kit:${placement}`, page: source }); } catch (e3) { /* ignore */ }
    } catch (e4) {
      setStep("unlock");
      setErr(e4?.response?.data?.detail || (e4?.response?.status === 429 ? "Too many tries, please wait a minute." : "Something went wrong. Please try again."));
    }
  };
  const copy = (key, text) => {
    try { navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(""), 1500); } catch (e) { /* ignore */ }
  };

  return (
    <section id={id} className="not-prose my-10 p-5 sm:p-7 rounded-2xl bg-[#0F0F12] text-white border border-orange-500/30 scroll-mt-6">
      <p className="text-[11px] font-bold uppercase tracking-[0.25em] text-orange-500 mb-2">Free tool</p>

      {step === "details" && (
        <form onSubmit={next}>
          <h2 className="text-xl md:text-2xl font-bold mb-2" style={{ fontFamily: "Outfit", color: "#fff" }}>{pitch.title}</h2>
          <p className="text-sm text-gray-300 mb-5">{pitch.sub}</p>
          <div className="grid sm:grid-cols-2 gap-3">
            <label className="sm:col-span-2 text-xs text-gray-400">Webinar title
              <input className={input + " mt-1"} required minLength={3} maxLength={140} value={title} onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. How to price your SaaS for 2027" />
            </label>
            <label className="text-xs text-gray-400">Date and time
              <input className={input + " mt-1"} type="datetime-local" required value={start} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label className="text-xs text-gray-400">Who is it for? (optional)
              <input className={input + " mt-1"} maxLength={100} value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="e.g. SaaS founders" />
            </label>
          </div>
          <button type="submit" className={btn + " mt-4 w-full sm:w-auto"}>Write my 6 reminders →</button>
        </form>
      )}

      {(step === "unlock" || step === "loading") && (
        <form onSubmit={unlock}>
          <h2 className="text-xl md:text-2xl font-bold mb-1" style={{ fontFamily: "Outfit", color: "#fff" }}>Your 6 reminders for "{title}" are one step away</h2>
          <p className="text-sm text-gray-300 mb-4">Tell us where to send a copy, and they'll appear right here.</p>
          <ol className="grid sm:grid-cols-2 gap-2 mb-5" aria-hidden="true">
            {PREVIEW.map(([label, ch]) => (
              <li key={label} className="rounded-xl border border-white/10 px-3 py-2">
                <div className="text-xs text-orange-300">{ch}</div>
                <div className="text-sm font-semibold">{label}</div>
                <div className="text-xs text-gray-500 select-none" style={{ filter: "blur(4px)" }}>Hi {"{first_name}"}, your seat for {title} is saved…</div>
              </li>
            ))}
          </ol>
          <div className="flex flex-col sm:flex-row gap-2">
            <input type="text" value={website} onChange={(e) => setWebsite(e.target.value)} tabIndex={-1} autoComplete="off" aria-hidden="true"
              style={{ position: "absolute", left: "-9999px", width: 1, height: 1, opacity: 0 }} name="website" />
            <label className="sr-only" htmlFor={`${id}-name`}>First name</label>
            <input id={`${id}-name`} className={input + " sm:flex-1"} required value={name} onChange={(e) => setName(e.target.value)} placeholder="First name" autoComplete="given-name" />
            <label className="sr-only" htmlFor={`${id}-email`}>Work email</label>
            <input id={`${id}-email`} className={input + " sm:flex-[1.4]"} required type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Work email" autoComplete="email" />
            <button type="submit" disabled={step === "loading"} className={btn + " whitespace-nowrap"}>
              {step === "loading" ? "Writing your reminders…" : "Show my reminders"}
            </button>
          </div>
          {err && <p className="text-red-400 text-sm mt-2" role="alert">{err}</p>}
          <p className="text-[11px] text-gray-500 mt-2">
            Free. We'll also send occasional webinar attendance tips. Unsubscribe any time.{" "}
            <button type="button" className="underline" onClick={() => setStep("details")}>Edit webinar details</button>
          </p>
        </form>
      )}

      {step === "done" && (
        <div role="status">
          <h2 className="text-xl md:text-2xl font-bold mb-1" style={{ fontFamily: "Outfit", color: "#fff" }}>Your reminders for "{title}"</h2>
          <p className="text-sm text-gray-300 mb-4">
            {emailed ? "We've also emailed you a copy. " : ""}Replace [join link] and {"{first_name}"}, then send each one at its time.
          </p>
          <div className="flex flex-wrap gap-2 mb-5">
            <button type="button" onClick={() => download("webinar-reminders.ics", kitToIcs(items, title), "text/calendar")} className="px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-sm font-bold">
              Add send times to my calendar (.ics)
            </button>
            <button type="button" onClick={() => copy("all", kitToText(items, title))} className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-sm">
              {copied === "all" ? "Copied!" : "Copy all"}
            </button>
            <button type="button" onClick={() => download("webinar-reminders.txt", kitToText(items, title), "text/plain")} className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-sm">
              Download (.txt)
            </button>
          </div>
          <ol className="space-y-3">
            {items.map((i, n) => (
              <li key={i.key} className="rounded-xl border border-white/10 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <span className="font-semibold">{n + 1}. {i.label} <span className="text-orange-300 font-normal">· {i.channel}</span></span>
                  <span className="text-xs text-gray-400">Send: {fmtWhen(i.send_at)}</span>
                </div>
                {i.subject && <p className="text-sm mb-1"><span className="text-gray-400">Subject:</span> {i.subject}</p>}
                <pre className="whitespace-pre-wrap font-sans text-sm text-gray-200 bg-white/5 rounded-lg p-3">{i.body}</pre>
                <button type="button" onClick={() => copy(i.key, (i.subject ? `Subject: ${i.subject}\n\n` : "") + i.body)} className="mt-2 text-xs text-orange-300 hover:text-orange-200">
                  {copied === i.key ? "Copied!" : "Copy"}
                </button>
              </li>
            ))}
          </ol>
          <div className="mt-6 rounded-xl p-4 border border-orange-500/40 bg-orange-500/10 flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
            <p className="text-sm"><strong>Don't want to send these by hand?</strong> ShowUpAI sends them for you, to each registrant, at the right time, on email, WhatsApp, SMS and LinkedIn.</p>
            <Link to="/register" className={btn + " text-center whitespace-nowrap"}>Start free trial</Link>
          </div>
        </div>
      )}
    </section>
  );
}

// Slim sticky bar for blog posts: points readers at the kit instead of asking for a bare newsletter signup.
export function KitBar({ target = "reminder-kit" }) {
  const [hidden, setHidden] = useState(true);
  React.useEffect(() => {
    let off = false;
    try { off = localStorage.getItem("showup_kit_bar") === "closed" || localStorage.getItem("showup_subscribed") === "1"; } catch (e) { /* ignore */ }
    if (off) return undefined;
    const onScroll = () => {
      const h = document.documentElement;
      const kit = document.getElementById(target);
      const kitVisible = kit && kit.getBoundingClientRect().top < window.innerHeight && kit.getBoundingClientRect().bottom > 0;
      setHidden(kitVisible || (h.scrollTop + window.innerHeight) / h.scrollHeight < 0.3);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [target]);
  if (hidden) return null;
  const close = () => { setHidden(true); try { localStorage.setItem("showup_kit_bar", "closed"); } catch (e) { /* ignore */ } };
  return (
    <div className="fixed bottom-0 inset-x-0 z-40 border-t bg-white/95 backdrop-blur shadow-[0_-4px_20px_rgba(0,0,0,0.06)]" style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}>
      <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3 text-black">
        <p className="text-sm font-semibold flex-1">Free: get your webinar's 6 reminder messages written in 30 seconds</p>
        <a href={`#${target}`} className="px-4 py-2 rounded-full bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold whitespace-nowrap">Write mine</a>
        <button onClick={close} aria-label="Close" className="text-xl leading-none opacity-60 hover:opacity-100">×</button>
      </div>
    </div>
  );
}
