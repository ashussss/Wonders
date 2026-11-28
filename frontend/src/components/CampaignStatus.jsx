import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Download, ExternalLink, Loader2, RefreshCcw, Search } from "@/components/Icons";
import { api } from "@/lib/api";
import { fmtInTz } from "@/lib/tz";
import { toast } from "sonner";

// One place for the host (or the agency's client) to see the whole campaign:
// who is on the list, what goes out when, how each send went, and the posts it made.

const STATE = {
  sent:            { label: "Sent",              color: "#10B981" },
  sending:         { label: "Sending now",       color: "#3B82F6" },
  limit_wait:      { label: "Daily limit, continues tomorrow", color: "#3B82F6" },
  failed:          { label: "Failed",            color: "#EF4444" },
  scheduled:       { label: "Scheduled",         color: "#8B5CF6" },
  manual:          { label: "Approved, send by hand", color: "#F59E0B" },
  queued:          { label: "Waiting for Send now", color: "#F59E0B" },
  needs_approval:  { label: "Needs approval",    color: "#F59E0B" },
  missed:          { label: "Time passed, not sent", color: "#9CA3AF" },
  rejected:        { label: "Skipped",           color: "#9CA3AF" },
  on_registration: { label: "On each sign-up",   color: "#06B6D4" },
};

const CH_LABEL = { email: "Email", linkedin: "LinkedIn", linkedin_personal: "LinkedIn", linkedin_page: "LinkedIn page",
  facebook: "Facebook", facebook_page: "Facebook", instagram: "Instagram", whatsapp: "WhatsApp", circle: "Circle" };

const card = { border: "1px solid var(--border)", background: "var(--bg-surface)", boxShadow: "var(--shadow-sm)" };

function Badge({ state }) {
  const s = STATE[state] || { label: state, color: "#9CA3AF" };
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap"
      style={{ color: s.color, background: `${s.color}1A` }} data-testid={`state-${state}`}>
      {state === "sending" ? <Loader2 size={11} className="animate-spin" /> : <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />}
      {s.label}
    </span>
  );
}

function Stat({ label, value, sub, tone }) {
  return (
    <div className="rounded-2xl p-4" style={card}>
      <div className="text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>{label}</div>
      <div className="text-2xl font-bold mt-1" style={{ color: tone || "var(--text-primary)", fontFamily: "Outfit" }}>{value}</div>
      {sub && <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{sub}</div>}
    </div>
  );
}

function EmailCell({ t }) {
  const e = t.email || {};
  const sent = (e.invite_sent || 0) + (e.reg_sent || 0);
  const failed = (e.invite_failed || 0) + (e.reg_failed || 0);
  if (t.state === "sending" && e.invite_total) {
    const pct = Math.round(((e.invite_sent + e.invite_failed) / e.invite_total) * 100);
    return (
      <div className="min-w-[140px]">
        <div className="text-xs" style={{ color: "var(--text-primary)" }}>{e.invite_sent} of {e.invite_total} sent{failed ? `, ${failed} failed` : ""}</div>
        <div className="h-1.5 rounded-full mt-1 overflow-hidden" style={{ background: "var(--bg-sunken)" }}>
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: "#3B82F6" }} />
        </div>
      </div>
    );
  }
  if (t.state === "limit_wait") {
    return (
      <div className="text-xs min-w-[140px]">
        <span style={{ color: "#10B981" }} className="font-semibold">{sent} sent</span>
        {failed > 0 && <span style={{ color: "#EF4444" }} className="font-semibold"> · {failed} failed</span>}
        <div style={{ color: "var(--text-muted)" }}>{(e.invite_held || 0).toLocaleString()} waiting for the next day's limit</div>
      </div>
    );
  }
  if (!t.channels.includes("email")) return <span className="text-xs" style={{ color: "var(--text-muted)" }}>No email</span>;
  if (t.state === "sent" || t.state === "failed" || sent || failed) {
    return (
      <div className="text-xs">
        <span style={{ color: "#10B981" }} className="font-semibold">{sent} sent</span>
        {failed > 0 && <span style={{ color: "#EF4444" }} className="font-semibold"> · {failed} failed</span>}
      </div>
    );
  }
  const n = (t.audience?.invitees || 0) + (t.audience?.registrants || 0);
  return <span className="text-xs" style={{ color: "var(--text-muted)" }}>{n ? `Will go to ${n.toLocaleString()}` : "No one to email yet"}</span>;
}

function PostsCell({ t }) {
  const social = t.channels.filter(c => c !== "email" && c !== "whatsapp");
  if (!t.posts.length) {
    if (!social.length) return <span className="text-xs" style={{ color: "var(--text-muted)" }}>—</span>;
    return <span className="text-xs" style={{ color: "var(--text-muted)" }}>{[...new Set(social.map(c => CH_LABEL[c] || c))].join(", ")}</span>;
  }
  const stats = t.linkedin_stats?.posts || {};
  return (
    <div className="space-y-1">
      {t.posts.map((p, i) => {
        const s = stats[p.external_id];
        return (
          <div key={i} className="text-xs flex items-center gap-1.5 flex-wrap">
            {p.ok ? <CheckCircle2 size={12} style={{ color: "#10B981" }} /> : <AlertTriangle size={12} style={{ color: "#EF4444" }} />}
            <span style={{ color: "var(--text-primary)" }}>{CH_LABEL[p.channel] || p.channel}</span>
            {p.url && <a href={p.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 underline" style={{ color: "#3B82F6" }}>view <ExternalLink size={10} /></a>}
            {s?.available && <span style={{ color: "var(--text-muted)" }}>· {s.likes} likes · {s.comments} comments</span>}
            {!p.ok && p.detail && <span style={{ color: "var(--text-muted)" }} title={p.detail}>· {p.detail.slice(0, 60)}</span>}
          </div>
        );
      })}
    </div>
  );
}

export function CampaignStatus({ webinar }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    try { const r = await api.get(`/webinars/${webinar.id}/campaign-status`); setData(r.data); }
    catch { /* keep last */ }
  };
  useEffect(() => { load(); }, [webinar.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const live = data?.touches?.some(t => t.state === "sending");
  useEffect(() => {
    if (!live) return undefined;
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [live]); // eslint-disable-line react-hooks/exhaustive-deps

  const refreshLinkedIn = async () => {
    setBusy(true);
    try { await api.post(`/webinars/${webinar.id}/linkedin-stats/refresh`); await load(); }
    catch { toast.error("Couldn't reach LinkedIn"); }
    finally { setBusy(false); }
  };

  if (!data) return <div className="p-10 text-center text-sm" style={{ color: "var(--text-muted)" }}>Loading campaign status…</div>;
  const tz = data.webinar.timezone;
  const localTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const c = data.contacts;
  const anyLiStats = data.touches.some(t => Object.keys(t.linkedin_stats?.posts || {}).length);
  const liNote = data.touches.flatMap(t => Object.values(t.linkedin_stats?.posts || {})).find(s => !s.available)?.reason;

  return (
    <div className="space-y-5" data-testid="campaign-status">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Contacts" value={(c.total + c.registrants).toLocaleString()}
          sub={`${c.reachable.toLocaleString()} invited · ${c.registrants} registered${c.unsubscribed ? ` · ${c.unsubscribed} unsubscribed` : ""}`} />
        <Stat label="Emails sent" value={data.totals.emails_sent.toLocaleString()} tone="#10B981" sub={`via ${data.email_provider}`} />
        <Stat label="Emails failed" value={data.totals.emails_failed.toLocaleString()} tone={data.totals.emails_failed ? "#EF4444" : undefined}
          sub={data.totals.emails_failed ? "see the reason per send below" : "none"} />
        <Stat label="Posts live" value={data.totals.posts_live}
          sub={`LinkedIn ${data.linkedin_connected ? "connected" : "not connected"} · Facebook ${data.facebook_connected ? "connected" : "not connected"}`} />
        <Stat label="Next send" value={data.next_send ? `#${data.next_send.touch_num}` : "—"}
          sub={data.next_send ? fmtInTz(data.next_send.at, tz) : `${data.totals.touches_sent} sent · ${data.totals.touches_left} left`} />
      </div>

      <div className="rounded-2xl overflow-hidden" style={card}>
        <div className="flex justify-between items-center px-5 py-3.5 border-b gap-3 flex-wrap" style={{ borderColor: "var(--border)" }}>
          <div>
            <div className="font-semibold" style={{ color: "var(--text-primary)" }}>Send schedule and results</div>
            <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
              Times in the webinar's time zone ({tz}){localTz && localTz !== tz ? `, with your time (${localTz}) below` : ""}.
              {live ? " Updating every 15 seconds while a send is going out." : ""}
            </div>
          </div>
          <div className="flex gap-3">
            {data.linkedin_connected && (
              <button onClick={refreshLinkedIn} disabled={busy} data-testid="refresh-linkedin-stats"
                className="text-xs font-semibold flex items-center gap-1.5" style={{ color: "var(--text-secondary)" }}>
                {busy ? <Loader2 size={12} className="animate-spin" /> : <RefreshCcw size={12} />} LinkedIn stats
              </button>
            )}
            <button onClick={load} data-testid="refresh-status" className="text-xs font-semibold flex items-center gap-1.5" style={{ color: "var(--text-secondary)" }}>
              <RefreshCcw size={12} /> Refresh
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] font-bold uppercase tracking-[0.15em] text-left" style={{ color: "var(--text-muted)" }}>
                <th className="px-5 py-3">#</th><th className="px-3 py-3">Touch</th><th className="px-3 py-3">When</th>
                <th className="px-3 py-3">Status</th><th className="px-3 py-3">Email</th><th className="px-3 py-3">Posts</th>
              </tr>
            </thead>
            <tbody>
              {data.touches.map(t => (
                <tr key={t.id} className="border-t align-top" style={{ borderColor: "var(--border)" }} data-testid={`status-row-${t.touch_num}`}>
                  <td className="px-5 py-3 font-semibold" style={{ color: "var(--text-muted)" }}>{t.touch_num}</td>
                  <td className="px-3 py-3">
                    <div style={{ color: "var(--text-primary)" }} className="font-medium">{t.name}</div>
                    <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>{[...new Set(t.channels.map(ch => CH_LABEL[ch] || ch))].join(" · ")}</div>
                    {t.errors.length > 0 && t.state !== "scheduled" && (
                      <div className="text-[11px] mt-1 space-y-0.5" style={{ color: "#EF4444" }}>
                        {t.errors.map((e, i) => <div key={i} title={e}>{e.slice(0, 110)}</div>)}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3 text-xs whitespace-nowrap">
                    {t.scheduled_at ? (
                      <>
                        <div style={{ color: "var(--text-primary)" }}>{fmtInTz(t.sent_at && t.state === "sent" ? t.sent_at : t.scheduled_at, tz)}</div>
                        {localTz && localTz !== tz && <div style={{ color: "var(--text-muted)" }}>{fmtInTz(t.sent_at && t.state === "sent" ? t.sent_at : t.scheduled_at, localTz)}</div>}
                        {t.state === "sent" && <div style={{ color: "var(--text-muted)" }}>sent</div>}
                        {t.state === "limit_wait" && t.resume_at && <div style={{ color: "#3B82F6" }}>continues {fmtInTz(t.resume_at, tz)}</div>}
                      </>
                    ) : <span style={{ color: "var(--text-muted)" }}>when someone registers</span>}
                  </td>
                  <td className="px-3 py-3"><Badge state={t.state} /></td>
                  <td className="px-3 py-3"><EmailCell t={t} /></td>
                  <td className="px-3 py-3"><PostsCell t={t} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(anyLiStats && liNote) && (
          <div className="px-5 py-3 text-xs border-t" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>{liNote}</div>
        )}
      </div>
    </div>
  );
}

const PAGE = 100;
const FILTERS = [["all", "Everyone"], ["emailed", "Emailed"], ["failed", "Last email failed"], ["not_yet", "Not emailed yet"],
  ["registered", "Registered"], ["unsubscribed", "Unsubscribed"]];

function contactStatus(p) {
  if (p.unsubscribed) return ["Unsubscribed", "#9CA3AF"];
  if (p.registered_at) return ["Registered", "#10B981"];
  if (p.last_error) return ["Last email failed", "#EF4444"];
  if (p.sends) return [`Emailed ${p.sends}×`, "#3B82F6"];
  return ["Not emailed yet", "#9CA3AF"];
}

export function InviteContacts({ webinar }) {
  const [items, setItems] = useState(null);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(0);
  useEffect(() => {
    api.get(`/webinars/${webinar.id}/invitees`).then(r => setItems(r.data.items || [])).catch(() => setItems([]));
  }, [webinar.id]);

  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (items || []).filter(p => {
      if (s && !`${p.name || ""} ${p.email}`.toLowerCase().includes(s)) return false;
      if (filter === "emailed") return (p.sends || 0) > 0;
      if (filter === "failed") return !!p.last_error;
      if (filter === "not_yet") return !p.sends && !p.unsubscribed && !p.registered_at;
      if (filter === "registered") return !!p.registered_at;
      if (filter === "unsubscribed") return !!p.unsubscribed;
      return true;
    });
  }, [items, q, filter]);
  useEffect(() => { setPage(0); }, [q, filter]);

  const download = () => {
    const esc = v => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [["Name", "Email", "Status", "Emails sent", "Last sent", "Last error"].join(",")];
    rows.forEach(p => lines.push([p.name, p.email, contactStatus(p)[0], p.sends || 0, p.last_sent_at || "", p.last_error || ""].map(esc).join(",")));
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    const a = document.createElement("a"); a.href = url; a.download = `contacts-${webinar.id.slice(0, 8)}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  if (items === null) return <div className="text-xs py-4" style={{ color: "var(--text-muted)" }}>Loading contacts…</div>;
  const shown = rows.slice(page * PAGE, (page + 1) * PAGE);
  return (
    <div className="mt-4" data-testid="invite-contacts">
      <div className="flex gap-2 flex-wrap items-center mb-3">
        <div className="flex items-center gap-2 rounded-lg px-3 py-1.5 flex-1 min-w-[200px]" style={{ border: "1px solid var(--border)", background: "var(--bg-sunken)" }}>
          <Search size={13} style={{ color: "var(--text-muted)" }} />
          <input data-testid="contacts-search" value={q} onChange={e => setQ(e.target.value)} placeholder="Search name or email"
            className="bg-transparent outline-none text-sm flex-1" style={{ color: "var(--text-primary)" }} />
        </div>
        <select data-testid="contacts-filter" value={filter} onChange={e => setFilter(e.target.value)}
          className="text-sm rounded-lg px-2 py-1.5" style={{ border: "1px solid var(--border)", background: "var(--bg-sunken)", color: "var(--text-primary)" }}>
          {FILTERS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <button data-testid="contacts-download" onClick={download} className="text-xs font-semibold flex items-center gap-1.5 px-2" style={{ color: "var(--text-secondary)" }}>
          <Download size={13} /> CSV
        </button>
      </div>
      <div className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>{rows.length.toLocaleString()} of {items.length.toLocaleString()} contacts</div>
      <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
        <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0" style={{ background: "var(--bg-surface)" }}>
              <tr className="text-[10px] font-bold uppercase tracking-[0.15em] text-left" style={{ color: "var(--text-muted)" }}>
                <th className="px-4 py-2.5">Name</th><th className="px-3 py-2.5">Email</th><th className="px-3 py-2.5">Status</th><th className="px-3 py-2.5">Last email</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(p => {
                const [label, color] = contactStatus(p);
                return (
                  <tr key={p.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="px-4 py-2" style={{ color: "var(--text-primary)" }}>{p.name || "—"}</td>
                    <td className="px-3 py-2" style={{ color: "var(--text-secondary)" }}>{p.email}</td>
                    <td className="px-3 py-2"><span className="text-xs font-semibold" style={{ color }} title={p.last_error || ""}>{label}</span></td>
                    <td className="px-3 py-2 text-xs" style={{ color: "var(--text-muted)" }}>
                      {p.last_error ? <span title={p.last_error}>{p.last_error.slice(0, 50)}</span>
                        : p.last_sent_at ? new Date(p.last_sent_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "—"}
                    </td>
                  </tr>
                );
              })}
              {!shown.length && <tr><td colSpan={4} className="px-4 py-6 text-center text-xs" style={{ color: "var(--text-muted)" }}>No contacts match.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {rows.length > PAGE && (
        <div className="flex justify-between items-center mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
          <button disabled={page === 0} onClick={() => setPage(p => p - 1)} className="disabled:opacity-30" data-testid="contacts-prev">← Previous</button>
          <span>Page {page + 1} of {Math.ceil(rows.length / PAGE)}</span>
          <button disabled={(page + 1) * PAGE >= rows.length} onClick={() => setPage(p => p + 1)} className="disabled:opacity-30" data-testid="contacts-next">Next →</button>
        </div>
      )}
    </div>
  );
}
