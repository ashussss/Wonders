import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Check, Copy, ExternalLink, Loader2, RefreshCw, Shield, Sparkles, X } from "@/components/Icons";

/**
 * Link building — review queue (admin only).
 *
 * The backend drafts copy for trusted sites (Product Hunt, G2, Substack…) and
 * tracks each one. Nothing is submitted from here: the admin approves the copy,
 * submits it from their own account, then pastes the live URL so the weekly
 * checker can confirm the link exists.
 */

const STATUSES = [
  ["pending_review", "To review"],
  ["approved", "Approved"],
  ["submitted", "Submitted"],
  ["live", "Live"],
  ["lost", "Lost"],
  ["todo", "Not started"],
  ["skipped", "Skipped"],
  ["", "All"],
];

const CATEGORY_LABEL = {
  launch: "Launch", directory: "Directory", publishing: "Publishing", pr: "Expert quotes",
  community: "Community", guest_post: "Guest post",
};

const card = { background: "var(--bg-card)", border: "1px solid var(--border)" };
const muted = { color: "var(--text-muted)" };
const primary = { color: "var(--text-primary)" };
const btn = { background: "var(--bg-secondary)", border: "1px solid var(--border)", ...primary };

function errText(e, fallback) {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : fallback;
}

function label(k) {
  return k.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function asText(v) {
  if (Array.isArray(v)) {
    return v.map((x) => (typeof x === "object" && x
      ? `• ${x.title || ""}${x.angle ? ` — ${x.angle}` : ""}${x.outline ? `\n   ${x.outline.join("\n   ")}` : ""}`
      : `• ${x}`)).join("\n");
  }
  return typeof v === "string" ? v : JSON.stringify(v, null, 2);
}

function Item({ it, onChanged, setError, setNotice }) {
  const draft = it.draft || {};
  const [edits, setEdits] = useState(() =>
    Object.fromEntries(Object.entries(draft).filter(([, v]) => typeof v === "string")));
  const [liveUrl, setLiveUrl] = useState(it.live_url || "");
  const [busy, setBusy] = useState("");
  const dirty = Object.entries(edits).some(([k, v]) => v !== draft[k]);

  const run = async (name, fn, ok) => {
    setBusy(name);
    setError("");
    try {
      await fn();
      if (ok) setNotice(ok);
      await onChanged();
    } catch (e) {
      setError(errText(e, `Could not ${name}.`));
    } finally {
      setBusy("");
    }
  };

  const move = (status, extra = {}) => api.post(`/growth/links/${it.key}/status`, { status, ...extra });
  const redraft = () => run("draft", () => api.post(`/growth/links/${it.key}/draft`, {}), "New draft ready.");
  const approve = () => run("approve", () => move("approved", dirty ? { draft: edits } : {}), "Approved. Now submit it from your account.");
  const submitted = () => run("mark submitted", () => move("submitted", { live_url: liveUrl.trim() }),
    "Marked as submitted. The weekly check will confirm the link.");
  const skip = () => run("skip", () => move("skipped"), "Skipped.");
  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); setNotice("Copied."); } catch { setError("Copy failed."); }
  };

  return (
    <div data-testid={`link-${it.key}`} className="rounded-2xl p-5" style={card}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs" style={muted}>
            <span className="px-2 py-0.5 rounded-full" style={{ background: "rgba(234,88,12,0.1)", color: "#EA580C" }}>
              {CATEGORY_LABEL[it.category] || it.category}
            </span>
            <span>Priority {it.priority}</span>
            {it.cadence === "weekly" && <span>Every week</span>}
            <span>{label(it.status)}</span>
          </div>
          <h3 className="text-base font-semibold mt-1" style={primary}>{it.name}</h3>
          <p className="text-xs mt-1" style={muted}>{it.link}</p>
          {it.requirements && <p className="text-xs mt-1" style={muted}><b>You need:</b> {it.requirements}</p>}
          {it.input && <p className="text-xs mt-2 whitespace-pre-wrap" style={muted}><b>Your input:</b> {it.input}</p>}
        </div>
        {it.submit_url && (
          <a href={it.submit_url} target="_blank" rel="noreferrer"
             className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs" style={btn}>
            Open site <ExternalLink size={13} />
          </a>
        )}
      </div>

      {Object.keys(draft).length > 0 && (
        <div className="mt-4 space-y-3">
          {Object.entries(draft).map(([k, v]) => (
            <div key={k}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium" style={muted}>{label(k)}</span>
                <button onClick={() => copy(typeof v === "string" ? (edits[k] ?? v) : asText(v))}
                  className="inline-flex items-center gap-1 text-xs" style={muted}><Copy size={12} /> Copy</button>
              </div>
              {typeof v === "string" ? (
                <textarea value={edits[k] ?? v} onChange={(e) => setEdits({ ...edits, [k]: e.target.value })}
                  rows={Math.min(12, Math.max(1, Math.ceil((edits[k] ?? v).length / 90)))}
                  className="w-full text-sm rounded-xl p-2.5"
                  style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", ...primary }} />
              ) : (
                <pre className="text-sm whitespace-pre-wrap rounded-xl p-2.5"
                  style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", ...primary, fontFamily: "inherit" }}>
                  {asText(v)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}

      {it.check && (
        <p className="text-xs mt-3" style={muted}>
          Last check: {it.check.found ? `link found${it.check.follow ? " (followed)" : ` (${it.check.rel || "nofollow"})`}` : "no link found"}
          {it.live_url && <> on <a href={it.live_url} target="_blank" rel="noreferrer" className="underline">{it.live_url}</a></>}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 mt-4">
        {it.source === "catalog" && ["todo", "pending_review", "approved", "submitted", "live"].includes(it.status) && (
          <button onClick={redraft} disabled={!!busy} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs disabled:opacity-50" style={btn}>
            {busy === "draft" ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
            {it.draft ? "Redraft" : "Draft now"}
          </button>
        )}
        {it.status === "pending_review" && (
          <button onClick={approve} disabled={!!busy} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-white disabled:opacity-50" style={{ background: "#EA580C" }}>
            <Check size={13} /> Approve
          </button>
        )}
        {(it.status === "approved" || it.status === "pending_review") && (
          <>
            <input value={liveUrl} onChange={(e) => setLiveUrl(e.target.value)} placeholder="Live URL after you submit (optional)"
              className="flex-1 min-w-[200px] text-xs rounded-xl px-2.5 py-1.5"
              style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", ...primary }} />
            <button onClick={submitted} disabled={!!busy} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs disabled:opacity-50" style={btn}>
              <Check size={13} /> I submitted it
            </button>
          </>
        )}
        {it.status !== "skipped" && it.status !== "live" && (
          <button onClick={skip} disabled={!!busy} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs disabled:opacity-50" style={btn}>
            <X size={13} /> Skip
          </button>
        )}
      </div>
    </div>
  );
}

function OnDemand({ onDone, setError, setNotice }) {
  const [kind, setKind] = useState("pr_answer");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    setError("");
    try {
      await api.post("/growth/links/on-demand", { kind, text, url });
      setText(""); setUrl("");
      setNotice("Draft ready in To review.");
      await onDone();
    } catch (e) {
      setError(errText(e, "Could not draft."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="rounded-2xl p-5 mb-6" style={card}>
      <h2 className="text-sm font-semibold" style={primary}>Paste something to answer</h2>
      <p className="text-xs mt-1 mb-3" style={muted}>
        A journalist query (Qwoted, Featured), a Reddit or Quora question, or a blog you want to guest post on.
      </p>
      <div className="flex flex-wrap gap-2 mb-2">
        {[["pr_answer", "Journalist query"], ["answer", "Community question"], ["pitch", "Guest post pitch"]].map(([v, l]) => (
          <button key={v} onClick={() => setKind(v)} className="px-3 py-1.5 rounded-full text-xs"
            style={kind === v ? { background: "#EA580C", color: "#fff" } : btn}>{l}</button>
        ))}
      </div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} placeholder="Paste the query, question or notes about the site"
        className="w-full text-sm rounded-xl p-2.5 mb-2" style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", ...primary }} />
      <div className="flex flex-wrap gap-2">
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Link to it (optional)"
          className="flex-1 min-w-[200px] text-xs rounded-xl px-2.5 py-1.5" style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", ...primary }} />
        <button onClick={go} disabled={busy || !text.trim()} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-white disabled:opacity-50" style={{ background: "#EA580C" }}>
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} Draft
        </button>
      </div>
    </div>
  );
}

export default function LinkBuilding() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin" || user?.role === "superadmin";
  const [status, setStatus] = useState("pending_review");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get("/growth/links", { params: status ? { status } : {} });
      setData(d);
    } catch (e) {
      setError(errText(e, "Could not load link opportunities."));
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => { if (isAdmin) load(); }, [isAdmin, load]);

  const runWeek = async () => {
    setRunning(true);
    setError("");
    try {
      const { data: d } = await api.post("/growth/links/run");
      setNotice(`${d?.drafted?.length || 0} draft(s) ready.${d?.errors?.length ? ` ${d.errors.length} failed.` : ""}`);
      setStatus("pending_review");
      await load();
    } catch (e) {
      setError(errText(e, "Could not draft this week's links."));
    } finally {
      setRunning(false);
    }
  };

  if (!isAdmin) {
    return <div className="p-8 text-sm" style={muted}>This page is only available to admins.</div>;
  }

  const counts = data?.counts || {};
  return (
    <div className="p-6 md:p-8 max-w-4xl mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold" style={{ fontFamily: "Outfit", ...primary }}>Link building</h1>
          <p className="text-sm mt-1" style={muted}>
            Drafts for trusted sites. You approve, then submit from your own account. {data?.per_week ?? 3} new sites a week.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} disabled={loading} className="inline-flex items-center gap-2 px-3 py-2 rounded-xl text-sm disabled:opacity-50" style={btn}>
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
          <button data-testid="links-run" onClick={runWeek} disabled={running}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium text-white disabled:opacity-50" style={{ background: "#EA580C" }}>
            {running ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
            {running ? "Drafting…" : "Draft this week's links"}
          </button>
        </div>
      </div>

      {data?.guardrails && (
        <div className="mb-4 px-4 py-3 rounded-xl text-xs" style={{ background: "rgba(234,179,8,0.10)", color: "#b45309", border: "1px solid rgba(234,179,8,0.3)" }}>
          <div className="flex items-center gap-1.5 font-semibold mb-1"><Shield size={13} /> No-spam rules</div>
          <ul className="list-disc ml-5 space-y-0.5">{data.guardrails.map((g) => <li key={g}>{g}</li>)}</ul>
        </div>
      )}
      {notice && <div className="mb-4 px-4 py-3 rounded-xl text-sm" style={{ background: "rgba(34,197,94,0.12)", color: "#16a34a", border: "1px solid rgba(34,197,94,0.3)" }}>{notice}</div>}
      {error && <div className="mb-4 px-4 py-3 rounded-xl text-sm" style={{ background: "rgba(239,68,68,0.10)", color: "#dc2626", border: "1px solid rgba(239,68,68,0.3)" }}>{error}</div>}

      <OnDemand onDone={load} setError={setError} setNotice={setNotice} />

      <div className="flex flex-wrap gap-2 mb-5">
        {STATUSES.map(([value, l]) => (
          <button key={l} onClick={() => setStatus(value)} className="px-3 py-1.5 rounded-full text-xs font-medium"
            style={status === value ? { background: "#EA580C", color: "#fff" } : { ...btn, ...muted }}>
            {l}{value && counts[value] ? ` (${counts[value]})` : ""}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 size={20} className="animate-spin" style={muted} /></div>
      ) : !data?.items?.length ? (
        <div className="rounded-2xl p-8 text-center text-sm" style={{ ...card, ...muted }}>
          Nothing here. New drafts arrive every Monday, or press "Draft this week's links".
        </div>
      ) : (
        <div className="space-y-4">
          {data.items.map((it) => (
            <Item key={`${it.key}-${it.updated_at}`} it={it} onChanged={load} setError={setError} setNotice={setNotice} />
          ))}
        </div>
      )}
    </div>
  );
}
