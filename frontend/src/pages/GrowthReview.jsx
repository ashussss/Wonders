import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Check, Loader2, RefreshCw, Send, Sparkles, X } from "@/components/Icons";

/**
 * Growth Engine — review queue (admin only).
 *
 * Lists growth_campaigns drafts so the admin can read the copy, see the
 * rendered visuals, edit captions and approve / reject / post. Every call
 * goes through /api/growth, which accepts an admin JWT.
 */

const STATUSES = [
  ["pending_review", "Pending"],
  ["approved", "Approved"],
  ["posted", "Posted"],
  ["partial", "Partial"],
  ["failed", "Failed"],
  ["rejected", "Rejected"],
  ["", "All"],
];

const KIND_LABEL = { blog: "Blog", news: "News", pain_point: "Pain point", engagement: "Engagement", competitor: "Competitor" };

const card = { background: "var(--bg-card)", border: "1px solid var(--border)" };
const muted = { color: "var(--text-muted)" };
const primary = { color: "var(--text-primary)" };

function errText(e, fallback) {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : fallback;
}

function Campaign({ c, onChanged, setError, setNotice }) {
  const platforms = c.platforms?.length ? c.platforms : Object.keys(c.platform_copy || {});
  const [drafts, setDrafts] = useState(() =>
    Object.fromEntries(platforms.map((p) => [p, c.platform_copy?.[p]?.caption || ""])));
  const [busy, setBusy] = useState("");
  const dirty = platforms.some((p) => (drafts[p] || "") !== (c.platform_copy?.[p]?.caption || ""));
  const editable = c.status === "pending_review" || c.status === "approved";

  const run = async (label, fn, ok) => {
    setBusy(label);
    setError("");
    try {
      await fn();
      if (ok) setNotice(ok);
      await onChanged();
    } catch (e) {
      setError(errText(e, `Could not ${label}.`));
    } finally {
      setBusy("");
    }
  };

  const save = () => run("save", () => {
    const platform_copy = { ...(c.platform_copy || {}) };
    platforms.forEach((p) => { platform_copy[p] = { ...(platform_copy[p] || {}), caption: drafts[p] || "" }; });
    return api.post(`/growth/edit/${c.id}`, { platform_copy });
  }, "Edits saved.");

  const approve = () => run("approve", async () => {
    if (dirty) await save();
    await api.post("/growth/approve", { id: c.id });
  }, "Approved.");
  const reject = () => run("reject", () => api.post("/growth/reject", { id: c.id }), "Rejected.");
  const postNow = () => {
    if (!window.confirm("Post this campaign to its platforms right now?")) return;
    run("post", async () => {
      const { data } = await api.post(`/growth/post-now/${c.id}`);
      if (data?.status !== "posted") {
        const why = Object.entries(data?.results || {})
          .filter(([, r]) => !r?.ok).map(([p, r]) => `${p}: ${r?.detail || "failed"}`).join(" · ");
        throw { response: { data: { detail: `Post ${data?.status || "failed"}. ${why}` } } };
      }
    }, "Posted.");
  };

  return (
    <div className="rounded-2xl p-5" style={card} data-testid={`growth-campaign-${c.id}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs mb-2" style={muted}>
        <span className="px-2 py-0.5 rounded-full font-semibold"
              style={{ background: "rgba(234,88,12,0.12)", color: "#EA580C" }}>
          {KIND_LABEL[c.kind] || c.kind}
        </span>
        <span>{c.status}</span>
        <span>· {fmtDate(c.scheduled_at)}</span>
        {c.link_url && (
          <a href={c.link_url} target="_blank" rel="noreferrer" className="underline truncate max-w-xs">
            {c.link_title || c.link_url}
          </a>
        )}
      </div>

      <div className="font-semibold mb-1" style={{ fontFamily: "Outfit", ...primary }}>
        {c.strategy?.hook || c.source_title || "Untitled campaign"}
      </div>
      {c.strategy?.content_angle && <p className="text-sm mb-4" style={muted}>{c.strategy.content_angle}</p>}

      {c.asset_urls?.length > 0 && (
        <div className="flex gap-2 overflow-x-auto mb-4 pb-1">
          {c.asset_urls.map((u) => (
            <a key={u} href={u} target="_blank" rel="noreferrer" className="shrink-0">
              <img src={u} alt="" loading="lazy" className="h-40 rounded-lg" style={{ border: "1px solid var(--border)" }} />
            </a>
          ))}
        </div>
      )}
      {c.review?.visual_error && (
        <p className="text-xs mb-3" style={{ color: "#b45309" }}>Visual failed to render: {c.review.visual_error}</p>
      )}

      <div className="space-y-3">
        {platforms.map((p) => (
          <div key={p}>
            <div className="text-xs font-semibold uppercase tracking-wide mb-1" style={muted}>{p}</div>
            <textarea
              data-testid={`growth-caption-${c.id}-${p}`}
              value={drafts[p] || ""}
              readOnly={!editable}
              onChange={(e) => setDrafts((d) => ({ ...d, [p]: e.target.value }))}
              rows={Math.min(12, Math.max(4, (drafts[p] || "").split("\n").length + 1))}
              className="w-full text-sm rounded-xl p-3"
              style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", ...primary }}
            />
            {c.results?.[p] && (
              <div className="text-xs mt-1" style={{ color: c.results[p].ok ? "#16a34a" : "#dc2626" }}>
                {c.results[p].ok ? "Posted" : `Failed: ${c.results[p].detail || "unknown error"}`}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-2 mt-4">
        {c.status === "pending_review" && (
          <>
            <button data-testid={`growth-approve-${c.id}`} onClick={approve} disabled={!!busy}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white disabled:opacity-50"
              style={{ background: "#16a34a" }}>
              {busy === "approve" ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
              {dirty ? "Save & approve" : "Approve"}
            </button>
            <button data-testid={`growth-reject-${c.id}`} onClick={reject} disabled={!!busy}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium disabled:opacity-50"
              style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", ...primary }}>
              {busy === "reject" ? <Loader2 size={15} className="animate-spin" /> : <X size={15} />}
              Reject
            </button>
          </>
        )}
        {editable && dirty && (
          <button data-testid={`growth-save-${c.id}`} onClick={save} disabled={!!busy}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium disabled:opacity-50"
            style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", ...primary }}>
            {busy === "save" && <Loader2 size={15} className="animate-spin" />}
            Save edits
          </button>
        )}
        {(c.status === "approved" || c.status === "partial" || c.status === "failed") && (
          <button data-testid={`growth-post-${c.id}`} onClick={postNow} disabled={!!busy}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white disabled:opacity-50"
            style={{ background: "#EA580C" }}>
            {busy === "post" ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
            {c.status === "approved" ? "Post now" : "Retry post"}
          </button>
        )}
      </div>
    </div>
  );
}

export default function GrowthReview() {
  const { user } = useAuth();
  const isAdmin = ["admin", "superadmin"].includes(user?.role);
  const [status, setStatus] = useState("pending_review");
  const [items, setItems] = useState([]);
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [q, s] = await Promise.all([
        api.get("/growth/queue", { params: status ? { status } : {} }),
        api.get("/growth/status"),
      ]);
      setItems(q.data || []);
      setInfo(s.data);
    } catch (e) {
      setError(errText(e, "Could not load the Growth queue."));
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => { if (isAdmin) load(); }, [isAdmin, load]);

  const generate = async () => {
    setGenerating(true);
    setError("");
    try {
      const { data } = await api.post("/growth/generate", {});
      setNotice(data?.note || `${data?.count || 0} draft(s) created.`);
      setStatus("pending_review");
      await load();
    } catch (e) {
      setError(errText(e, "Could not generate drafts."));
    } finally {
      setGenerating(false);
    }
  };

  if (!isAdmin) {
    return <div className="p-8 text-sm" style={muted}>This page is only available to admins.</div>;
  }

  return (
    <div className="p-6 md:p-8 max-w-4xl mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold" style={{ fontFamily: "Outfit", ...primary }}>Growth review</h1>
          <p className="text-sm mt-1" style={muted}>
            Read, edit and approve the Growth Engine's social drafts before anything goes out.
          </p>
        </div>
        <div className="flex gap-2">
          <button data-testid="growth-refresh" onClick={load} disabled={loading}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl text-sm disabled:opacity-50"
            style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", ...primary }}>
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
          <button data-testid="growth-generate" onClick={generate} disabled={generating}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium text-white disabled:opacity-50"
            style={{ background: "#EA580C" }}>
            {generating ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
            {generating ? "Generating…" : "Generate today's drafts"}
          </button>
        </div>
      </div>

      {info && (
        <div data-testid="growth-mode" className="mb-4 px-4 py-3 rounded-xl text-sm"
             style={info.publishing_blocked
               ? { background: "rgba(234,179,8,0.10)", color: "#b45309", border: "1px solid rgba(234,179,8,0.3)" }
               : { background: "rgba(34,197,94,0.12)", color: "#16a34a", border: "1px solid rgba(34,197,94,0.3)" }}>
          {info.publishing_blocked
            ? "Auto-publish is off. Approved posts only go out when you press Post now."
            : "Auto-publish is on. Approved posts go out automatically at their scheduled time."}
          {" "}{info.pending_review} waiting for review.
        </div>
      )}
      {notice && (
        <div data-testid="growth-notice" className="mb-4 px-4 py-3 rounded-xl text-sm"
             style={{ background: "rgba(34,197,94,0.12)", color: "#16a34a", border: "1px solid rgba(34,197,94,0.3)" }}>
          {notice}
        </div>
      )}
      {error && (
        <div data-testid="growth-error" className="mb-4 px-4 py-3 rounded-xl text-sm"
             style={{ background: "rgba(239,68,68,0.10)", color: "#dc2626", border: "1px solid rgba(239,68,68,0.3)" }}>
          {error}
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-5">
        {STATUSES.map(([value, label]) => (
          <button key={label} data-testid={`growth-filter-${value || "all"}`} onClick={() => setStatus(value)}
            className="px-3 py-1.5 rounded-full text-xs font-medium"
            style={status === value
              ? { background: "#EA580C", color: "#fff" }
              : { background: "var(--bg-secondary)", border: "1px solid var(--border)", ...muted }}>
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 size={20} className="animate-spin" style={muted} /></div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl p-8 text-center text-sm" style={{ ...card, ...muted }}>
          Nothing here. New drafts are created every day at 02:00 IST, or press "Generate today's drafts".
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((c) => (
            <Campaign key={`${c.id}-${c.updated_at}`} c={c} onChanged={load} setError={setError} setNotice={setNotice} />
          ))}
        </div>
      )}
    </div>
  );
}
