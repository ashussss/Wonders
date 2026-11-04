// Public SEO pages: /compare, /compare/:competitor, /tools, /tools/:tool and /webinar-attendance.
// Content lives in src/lib/seoPages.js, which scripts/prerender-blog.mjs also renders to static HTML for crawlers.
import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Zap, ArrowRight, Copy, Check } from "@/components/Icons";
import { parseMarkdown, splitInline, headingId } from "@/lib/markdown";
import { api } from "@/lib/api";
import {
  SITE, COMPARE, COMPARE_ROWS, SHOWUP, compareFaq, TOOLS, titleIdeas, GUIDE, BENCHMARKS, COMPARE_INDEX, TOOLS_INDEX,
} from "@/lib/seoPages";

function setMeta(name, content, attr = "name") {
  if (!content) return;
  let el = document.head.querySelector(`meta[${attr}="${name}"]`);
  if (!el) { el = document.createElement("meta"); el.setAttribute(attr, name); document.head.appendChild(el); }
  el.setAttribute("content", content);
}

function usePageMeta(title, description, path) {
  useEffect(() => {
    if (!title) return;
    document.title = title;
    setMeta("description", description);
    setMeta("og:title", title, "property");
    setMeta("og:description", description, "property");
    setMeta("og:url", SITE + path, "property");
    let el = document.head.querySelector('link[rel="canonical"]');
    if (!el) { el = document.createElement("link"); el.setAttribute("rel", "canonical"); document.head.appendChild(el); }
    el.setAttribute("href", SITE + path);
    window.scrollTo(0, 0);
  }, [title, description, path]);
}

function Shell({ children }) {
  return (
    <div className="min-h-screen text-white" style={{ background: "#05050F" }}>
      <nav className="border-b border-white/10 px-4 sm:px-6 py-4 flex items-center justify-between gap-3">
        <Link to="/" className="flex items-center gap-2 font-bold text-lg">
          <span className="w-8 h-8 rounded-lg bg-orange-600 flex items-center justify-center"><Zap size={16} color="white" /></span>
          ShowUp<span className="text-orange-500 -ml-2">AI</span>
        </Link>
        <div className="flex items-center gap-4 text-sm text-gray-400">
          <Link to="/webinar-attendance" className="hidden sm:inline hover:text-white">Guide</Link>
          <Link to="/tools" className="hover:text-white">Free tools</Link>
          <Link to="/compare" className="hidden sm:inline hover:text-white">Compare</Link>
          <Link to="/waitlist" className="bg-orange-600 hover:bg-orange-500 text-white font-bold px-4 py-2 rounded-lg">Start free</Link>
        </div>
      </nav>
      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-12">{children}</main>
      <footer className="border-t border-white/10 py-8 px-4 text-center text-gray-500 text-sm space-x-4">
        <Link to="/" className="text-orange-500">showupai.live</Link>
        <Link to="/webinar-attendance">Webinar attendance guide</Link>
        <Link to="/tools">Free tools</Link>
        <Link to="/compare">Comparisons</Link>
        <Link to="/blog">Blog</Link>
      </footer>
    </div>
  );
}

function Inline({ text }) {
  return splitInline(text).map((p, i) =>
    p.t === "b" ? <strong key={i} className="text-white">{p.v}</strong>
    : p.t === "code" ? <code key={i}>{p.v}</code>
    : p.t === "a" ? <a key={i} href={p.href.replace(SITE, "") || "/"} className="text-orange-400 underline">{p.v}</a>
    : <span key={i}>{p.v}</span>);
}

function Markdown({ md }) {
  return parseMarkdown(md).map((b, i) => {
    if (b.type === "h") return b.level === 2
      ? <h2 key={i} id={headingId(b.text)} className="text-white text-2xl font-bold mt-10 mb-4">{b.text}</h2>
      : <h3 key={i} id={headingId(b.text)} className="text-white text-xl font-bold mt-6 mb-3">{b.text}</h3>;
    if (b.type === "p") return <p key={i} className="text-gray-300 leading-relaxed mb-4"><Inline text={b.text} /></p>;
    if (b.type === "table") return (
      <div key={i} className="overflow-x-auto mb-6"><table className="w-full text-sm border border-white/10">
        <thead><tr>{b.head.map((c, j) => <th key={j} className="text-left p-3 bg-white/5">{c}</th>)}</tr></thead>
        <tbody>{b.rows.map((r, j) => <tr key={j} className="border-t border-white/5">{r.map((c, k) => <td key={k} className="p-3 text-gray-300">{c}</td>)}</tr>)}</tbody>
      </table></div>);
    if (b.type === "ol" || b.type === "ul") {
      const Tag = b.type;
      return <Tag key={i} className={`${b.type === "ol" ? "list-decimal" : "list-disc"} pl-6 space-y-2 text-gray-300 mb-6`}>
        {b.items.map((it, j) => <li key={j}><Inline text={it.text} /></li>)}</Tag>;
    }
    return null;
  });
}

function Faq({ items }) {
  return (
    <section className="mt-12">
      <h2 className="text-white text-2xl font-bold mb-6">Frequently asked questions</h2>
      {items.map(([q, a]) => (
        <div key={q} className="mb-5"><h3 className="text-white font-bold text-white mb-1">{q}</h3><p className="text-gray-400">{a}</p></div>
      ))}
    </section>
  );
}

function Cta() {
  return (
    <div className="rounded-2xl p-8 text-center border border-orange-500/30 mt-12" style={{ background: "rgba(234,88,12,0.06)" }}>
      <h2 className="text-white text-2xl font-bold mb-3">Get more registrants to show up</h2>
      <p className="text-gray-400 mb-6">ShowUpAI writes and sends your whole reminder sequence. You approve every message. 14-day free trial, no card.</p>
      <Link to="/waitlist" className="inline-flex items-center gap-2 bg-orange-600 hover:bg-orange-500 text-white font-bold px-6 py-3 rounded-xl">
        Start free <ArrowRight size={18} />
      </Link>
    </div>
  );
}

// ── /compare/:competitor ─────────────────────────────────────────────────────
export default function Compare() {
  const { competitor } = useParams();
  const key = (competitor || "").toLowerCase();
  const c = COMPARE[key];
  usePageMeta(c && `${c.title} | ShowUpAI`, c && c.description, `/compare/${key}`);
  if (!c) return <Shell><h1 className="text-white text-3xl font-bold mb-4">Comparison not found</h1><Link to="/compare" className="text-orange-500">See all comparisons</Link></Shell>;
  return (
    <Shell>
      <p className="text-orange-500 text-sm font-bold uppercase tracking-widest mb-3">ShowUpAI vs {c.name}</p>
      <h1 className="text-white text-3xl md:text-5xl font-bold mb-6">{c.title}</h1>
      <p className="text-lg text-gray-300 mb-4"><strong className="text-white">Short answer:</strong> {c.name} is a {c.kind}. ShowUpAI is webinar attendance software that works alongside it. {c.together}</p>
      <p className="text-gray-400 mb-10">{c.intro}</p>
      <h2 className="text-white text-2xl font-bold mb-4">ShowUpAI vs {c.name} at a glance</h2>
      <div className="overflow-x-auto rounded-2xl border border-white/10 mb-10">
        <table className="w-full text-sm">
          <thead><tr className="bg-white/5"><th className="text-left p-3">Feature</th><th className="text-left p-3 text-orange-400">ShowUpAI</th><th className="text-left p-3">{c.name}</th></tr></thead>
          <tbody>{COMPARE_ROWS.map(([k, label]) => (
            <tr key={k} className="border-t border-white/5"><td className="p-3 text-gray-400">{label}</td><td className="p-3">{SHOWUP[k]}</td><td className="p-3 text-gray-300">{c.them[k]}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <div className="grid md:grid-cols-2 gap-4 mb-6">
        <div className="rounded-2xl p-5 border border-white/10"><h3 className="text-white font-bold mb-2">Choose {c.name} if</h3><p className="text-gray-400">{c.chooseThem}</p></div>
        <div className="rounded-2xl p-5 border border-orange-500/30"><h3 className="text-white font-bold mb-2">Choose ShowUpAI if</h3><p className="text-gray-400">{c.chooseUs}</p></div>
      </div>
      <h2 className="text-white text-2xl font-bold mt-10 mb-3">Using {c.name} and ShowUpAI together</h2>
      <p className="text-gray-300">{c.together}</p>
      <Faq items={compareFaq(c)} />
      <Cta />
      <div className="mt-12 flex flex-wrap gap-3">
        {Object.entries(COMPARE).filter(([k]) => k !== key).map(([k, v]) => (
          <Link key={k} to={`/compare/${k}`} className="text-sm px-4 py-2 rounded-lg border border-white/10 text-gray-400 hover:text-white">ShowUpAI vs {v.name}</Link>
        ))}
      </div>
    </Shell>
  );
}

export function CompareIndex() {
  usePageMeta(`${COMPARE_INDEX.title} | ShowUpAI`, COMPARE_INDEX.description, "/compare");
  return (
    <Shell>
      <h1 className="text-white text-3xl md:text-5xl font-bold mb-6">{COMPARE_INDEX.title}</h1>
      <p className="text-gray-300 mb-10">ShowUpAI doesn't host webinars. It works alongside your webinar platform and handles what happens between registration and start time. Here's how it compares with the tools people usually use for that.</p>
      <div className="grid sm:grid-cols-2 gap-4">
        {Object.entries(COMPARE).map(([k, v]) => (
          <Link key={k} to={`/compare/${k}`} className="rounded-2xl p-5 border border-white/10 hover:border-orange-500/50">
            <h2 className="text-white font-bold text-lg mb-1">ShowUpAI vs {v.name}</h2><p className="text-gray-400 text-sm">{v.description}</p>
          </Link>
        ))}
      </div>
      <Cta />
    </Shell>
  );
}

// ── /tools and /tools/:tool ──────────────────────────────────────────────────
const inputCls = "w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white";
function Field({ label, value, onChange, type = "number", step }) {
  return (
    <label className="block text-sm text-gray-400">{label}
      <input className={inputCls + " mt-1"} type={type} step={step} min={type === "number" ? 0 : undefined} value={value}
        onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
const num = (v) => Math.max(0, Number(v) || 0);
const fmt = (v, d = 0) => Number.isFinite(v) ? v.toLocaleString("en-US", { maximumFractionDigits: d }) : "–";
function Stat({ label, value }) {
  return <div className="rounded-xl p-4 border border-white/10 bg-white/[0.03]"><div className="text-xs text-gray-400 mb-1">{label}</div><div className="text-2xl font-bold text-orange-400">{value}</div></div>;
}

function NoShowCalculator() {
  const [reg, setReg] = useState(200), [att, setAtt] = useState(70), [leadPct, setLeadPct] = useState(20), [value, setValue] = useState(100);
  const r = num(reg), a = Math.min(num(att), r);
  const show = r ? (a / r) * 100 : 0;
  const noShows = r - a;
  const lost = noShows * (num(leadPct) / 100) * num(value);
  const plus10 = r * 0.1 * (num(leadPct) / 100) * num(value);
  return (
    <div>
      <div className="grid sm:grid-cols-2 gap-4 mb-6">
        <Field label="Registrants" value={reg} onChange={setReg} />
        <Field label="Attendees (joined live)" value={att} onChange={setAtt} />
        <Field label="% of attendees who become a lead" value={leadPct} onChange={setLeadPct} />
        <Field label="Value of one lead ($)" value={value} onChange={setValue} />
      </div>
      <div className="grid sm:grid-cols-3 gap-4 mb-4">
        <Stat label="Show-up rate" value={`${fmt(show, 1)}%`} />
        <Stat label="No-shows" value={fmt(noShows)} />
        <Stat label="Pipeline lost to no-shows" value={`$${fmt(lost)}`} />
      </div>
      <p className="text-gray-300 mb-2">Every 10 points of show-up rate on this webinar is worth about <strong className="text-white">${fmt(plus10)}</strong> in pipeline.</p>
      <ul className="text-sm text-gray-400 list-disc pl-5">{BENCHMARKS.map((b) => (
        <li key={b.source}>{b.source} ({b.year}): {b.rate}%, {b.note}. You are {show >= b.rate ? "above" : "below"} it.</li>
      ))}</ul>
    </div>
  );
}

function RoiCalculator() {
  const [cost, setCost] = useState(1500), [reg, setReg] = useState(300), [show, setShow] = useState(40), [conv, setConv] = useState(3), [deal, setDeal] = useState(1000);
  const attendees = num(reg) * num(show) / 100;
  const customers = attendees * num(conv) / 100;
  const revenue = customers * num(deal);
  const roi = num(cost) ? ((revenue - num(cost)) / num(cost)) * 100 : 0;
  const revenue10 = num(reg) * (Math.min(100, num(show) + 10) / 100) * num(conv) / 100 * num(deal);
  return (
    <div>
      <div className="grid sm:grid-cols-2 gap-4 mb-6">
        <Field label="Total cost of the webinar ($)" value={cost} onChange={setCost} />
        <Field label="Registrants" value={reg} onChange={setReg} />
        <Field label="Show-up rate (%)" value={show} onChange={setShow} />
        <Field label="Attendees who become customers (%)" value={conv} onChange={setConv} step="0.1" />
        <Field label="Average deal value ($)" value={deal} onChange={setDeal} />
      </div>
      <div className="grid sm:grid-cols-3 gap-4 mb-4">
        <Stat label="Attendees" value={fmt(attendees)} />
        <Stat label="Customers" value={fmt(customers, 1)} />
        <Stat label="Revenue" value={`$${fmt(revenue)}`} />
        <Stat label="ROI" value={`${fmt(roi)}%`} />
        <Stat label="Cost per attendee" value={attendees ? `$${fmt(num(cost) / attendees, 2)}` : "–"} />
        <Stat label="Revenue at +10 pts show-up" value={`$${fmt(revenue10)}`} />
      </div>
    </div>
  );
}

function TitleGenerator() {
  const [topic, setTopic] = useState("Webinar Promotion"), [audience, setAudience] = useState("B2B Marketers"), [outcome, setOutcome] = useState("double demo bookings"), [n, setN] = useState(5);
  const [copied, setCopied] = useState(-1);
  const ideas = useMemo(() => titleIdeas({ topic, audience, outcome, number: n }), [topic, audience, outcome, n]);
  const copy = (t, i) => { try { navigator.clipboard.writeText(t); setCopied(i); setTimeout(() => setCopied(-1), 1500); } catch (e) { /* ignore */ } };
  return (
    <div>
      <div className="grid sm:grid-cols-2 gap-4 mb-6">
        <Field label="Topic" type="text" value={topic} onChange={setTopic} />
        <Field label="Audience" type="text" value={audience} onChange={setAudience} />
        <Field label="Outcome they want" type="text" value={outcome} onChange={setOutcome} />
        <Field label="Number for list titles" value={n} onChange={setN} />
      </div>
      <ol className="space-y-2">{ideas.map((t, i) => (
        <li key={i} className="flex items-center justify-between gap-3 rounded-lg border border-white/10 px-4 py-3">
          <span>{t}</span>
          <button type="button" onClick={() => copy(t, i)} className="text-gray-400 hover:text-white shrink-0" aria-label="Copy title">
            {copied === i ? <Check size={16} /> : <Copy size={16} />}
          </button>
        </li>
      ))}</ol>
    </div>
  );
}

export const WIDGETS = {
  "webinar-no-show-calculator": NoShowCalculator,
  "webinar-roi-calculator": RoiCalculator,
  "webinar-title-generator": TitleGenerator,
};

export function ToolPage() {
  const { tool } = useParams();
  const t = TOOLS[tool];
  const Widget = WIDGETS[tool];
  usePageMeta(t && `${t.title} | ShowUpAI`, t && t.description, `/tools/${tool}`);
  if (!t) return <Shell><h1 className="text-white text-3xl font-bold mb-4">Tool not found</h1><Link to="/tools" className="text-orange-500">See all free tools</Link></Shell>;
  return (
    <Shell>
      <p className="text-orange-500 text-sm font-bold uppercase tracking-widest mb-3">Free tool</p>
      <h1 className="text-white text-3xl md:text-5xl font-bold mb-4">{t.title}</h1>
      <p className="text-lg text-gray-300 mb-8">{t.intro}</p>
      <div className="rounded-2xl p-5 sm:p-6 border border-white/10 bg-white/[0.02] mb-10"><Widget /></div>
      <EmbedBox tool={tool} name={t.name} />
      <h2 className="text-white text-2xl font-bold mb-3">How it works</h2>
      <ul className="list-disc pl-6 text-gray-300 space-y-1">{t.how.map((h) => <li key={h}>{h}</li>)}</ul>
      <Faq items={t.faq} />
      <p className="mt-8 text-gray-400">Read next: <Link to="/webinar-attendance" className="text-orange-400 underline">How to increase webinar attendance</Link>.</p>
      <Cta />
      <div className="mt-10 flex flex-wrap gap-3">{Object.entries(TOOLS).filter(([k]) => k !== tool).map(([k, v]) => (
        <Link key={k} to={`/tools/${k}`} className="text-sm px-4 py-2 rounded-lg border border-white/10 text-gray-400 hover:text-white">{v.name}</Link>
      ))}</div>
    </Shell>
  );
}

export function ToolsIndex() {
  usePageMeta(`${TOOLS_INDEX.title} | ShowUpAI`, TOOLS_INDEX.description, "/tools");
  return (
    <Shell>
      <h1 className="text-white text-3xl md:text-5xl font-bold mb-6">Free webinar tools</h1>
      <p className="text-gray-300 mb-10">{TOOLS_INDEX.description}</p>
      <div className="grid sm:grid-cols-3 gap-4">{Object.entries(TOOLS).map(([k, v]) => (
        <Link key={k} to={`/tools/${k}`} className="rounded-2xl p-5 border border-white/10 hover:border-orange-500/50">
          <h2 className="text-white font-bold mb-2">{v.name}</h2><p className="text-gray-400 text-sm">{v.description}</p>
        </Link>
      ))}</div>
      <Cta />
    </Shell>
  );
}

// ── /webinar-attendance (pillar guide) ───────────────────────────────────────
export function Guide() {
  usePageMeta(GUIDE.seoTitle, GUIDE.description, `/${GUIDE.slug}`);
  const [posts, setPosts] = useState([]);
  useEffect(() => {
    api.get("/blog").then((r) => {
      const list = Array.isArray(r.data) ? r.data : [];
      setPosts(list.filter((p) => GUIDE.clusterWords.some((w) => (p.slug || "").includes(w))).slice(0, 20));
    }).catch(() => {});
  }, []);
  return (
    <Shell>
      <h1 className="text-white text-3xl md:text-5xl font-bold mb-4">{GUIDE.title}</h1>
      <p className="text-sm text-gray-500 mb-6">Updated {GUIDE.updated}</p>
      <p className="text-lg text-gray-300 mb-8 border-l-4 border-orange-600 pl-4"><strong className="text-white">Quick answer:</strong> {GUIDE.faq[0][1]}</p>
      <Markdown md={GUIDE.markdown} />
      <Faq items={GUIDE.faq} />
      {posts.length > 0 && (
        <section className="mt-12"><h2 className="text-white text-2xl font-bold mb-4">More on webinar attendance</h2>
          <ul className="list-disc pl-6 space-y-1">{posts.map((p) => <li key={p.slug}><Link to={`/blog/${p.slug}`} className="text-orange-400 hover:underline">{p.title}</Link></li>)}</ul>
        </section>
      )}
      <Cta />
    </Shell>
  );
}

// ── Embeds: any site can put a tool on its page; the credit link under the iframe points back here ──
export function embedCode(tool, name) {
  return `<iframe src="${SITE}/embed/${tool}" title="${name}" width="100%" height="680" style="border:0;border-radius:12px;max-width:760px" loading="lazy"></iframe>\n<p style="font-size:13px"><a href="${SITE}/tools/${tool}">${name}</a> by <a href="${SITE}">ShowUpAI</a></p>`;
}

function EmbedBox({ tool, name }) {
  const [done, setDone] = useState(false);
  const code = embedCode(tool, name);
  const copy = () => { try { navigator.clipboard.writeText(code); setDone(true); setTimeout(() => setDone(false), 1500); } catch (e) { /* ignore */ } };
  return (
    <section className="rounded-2xl p-5 border border-white/10 mb-10">
      <h2 className="text-white text-xl font-bold mb-2">Add this tool to your website</h2>
      <p className="text-gray-400 text-sm mb-3">Free for blogs, agencies and course sites. Paste this code where you want the {name.toLowerCase()} to appear.</p>
      <pre className="text-xs bg-black/40 border border-white/10 rounded-lg p-3 whitespace-pre-wrap break-all text-gray-300">{code}</pre>
      <button type="button" onClick={copy} className="mt-3 inline-flex items-center gap-2 text-sm bg-white/10 hover:bg-white/20 px-4 py-2 rounded-lg">
        {done ? <Check size={14} /> : <Copy size={14} />} {done ? "Copied" : "Copy embed code"}
      </button>
    </section>
  );
}

export function EmbedTool() {
  const { tool } = useParams();
  const t = TOOLS[tool];
  const Widget = WIDGETS[tool];
  useEffect(() => {
    if (!t) return;
    document.title = `${t.name} | ShowUpAI`;
    setMeta("robots", "noindex, follow");
  }, [t]);
  if (!t) return <div className="p-6 text-white" style={{ background: "#05050F" }}>Tool not found</div>;
  return (
    <div className="min-h-screen text-white p-4 sm:p-6" style={{ background: "#05050F" }}>
      <h1 className="text-white text-xl font-bold mb-4">{t.name}</h1>
      <Widget />
      <p className="mt-6 text-xs text-gray-500">
        Free tool by <a href={`${SITE}/tools/${tool}`} target="_blank" rel="noopener" className="text-orange-400 underline">ShowUpAI</a>, webinar attendance software.
      </p>
    </div>
  );
}

// Home page block: the three tools, usable right there
export function FreeToolsSection() {
  const keys = Object.keys(TOOLS);
  const [active, setActive] = useState(keys[0]);
  const Widget = WIDGETS[active];
  return (
    <section id="free-tools" className="py-24 px-4 sm:px-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-10">
          <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-orange-500 mb-4">Free tools</div>
          <h2 className="text-white text-4xl sm:text-5xl font-bold" style={{ fontFamily: "Outfit" }}>Free webinar tools. No sign-up.</h2>
          <p className="text-gray-400 mt-4">Work out what no-shows cost you, what a webinar returns, or get title ideas.</p>
        </div>
        <div className="flex flex-wrap justify-center gap-2 mb-6" role="tablist">
          {keys.map((k) => (
            <button key={k} type="button" role="tab" aria-selected={active === k} onClick={() => setActive(k)}
              className={`text-sm px-4 py-2 rounded-full border ${active === k ? "bg-orange-600 border-orange-600 text-white" : "border-white/15 text-gray-300 hover:text-white"}`}>
              {TOOLS[k].name.replace("Webinar ", "")}
            </button>
          ))}
        </div>
        <div className="rounded-2xl p-5 sm:p-6 border border-white/10 bg-white/[0.02]"><Widget /></div>
        <p className="text-center mt-6 text-sm text-gray-400">
          <Link to={`/tools/${active}`} className="text-orange-400 underline">Open the full {TOOLS[active].name.toLowerCase()}</Link>
          {" "}· <Link to="/tools" className="text-orange-400 underline">All free tools</Link> · Embed any tool on your own site
        </p>
      </div>
    </section>
  );
}

export const MENU_TOOLS = Object.entries(TOOLS).map(([k, v]) => [`/tools/${k}`, v.name]);
export const MENU_COMPARE = Object.entries(COMPARE).map(([k, v]) => [`/compare/${k}`, `vs ${v.name}`]);
