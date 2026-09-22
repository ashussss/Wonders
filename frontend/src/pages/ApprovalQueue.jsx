import { useEffect, useState, useMemo } from "react";
import { AlertTriangle, Check, ChevronDown, Copy, Filter, Inbox, X } from "@/components/Icons";
import { motion, AnimatePresence } from "framer-motion";
import { api, fmtDate, CHANNEL_META } from "@/lib/api";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { useTheme } from "@/lib/theme";

export default function ApprovalQueue() {
  const { isDark } = useTheme();
  const [touches, setTouches] = useState([]);
  const [webinars, setWebinars] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterWebinar, setFilterWebinar] = useState("all");
  const [total, setTotal] = useState(0);

  const load = async (wid = "all") => {
    try {
      const url = wid === "all" ? "/approval-queue" : `/approval-queue?webinar_id=${wid}`;
      const r = await api.get(url);
      if (Array.isArray(r.data)) {
        setTouches(r.data);
      } else {
        setTouches(r.data.touches || []);
        setWebinars(r.data.webinars || []);
        setTotal(r.data.total || 0);
      }
    } catch(e) {
      console.error("Approval queue load failed:", e);
      toast.error("Could not load approval queue");
      setTouches([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleFilter = (wid) => {
    setFilterWebinar(wid);
    setLoading(true);
    load(wid);
  };

    const approve = async (t, variant) => {
    try {
      await api.patch(`/touches/${t.id}`, { approval_status: "approved", selected_variant: variant });
      toast.success("Approved ✓");
      setTouches(prev => prev.filter(x => x.id !== t.id));
    } catch(e) {
      toast.error("Failed to approve");
    }
  };

  const reject = async (t) => {
    try {
      await api.patch(`/touches/${t.id}`, { approval_status: "rejected" });
      toast.success("Rejected");
      setTouches(prev => prev.filter(x => x.id !== t.id));
    } catch(e) {
      toast.error("Failed to reject");
    }
  };

  // Group touches by webinar
  const grouped = useMemo(() => {
    const groups = {};
    touches.forEach(t => {
      const key = t.webinar_id;
      if (!groups[key]) groups[key] = { title: t.webinar_title, starts_at: t.webinar_starts_at, touches: [] };
      groups[key].touches.push(t);
    });
    return Object.entries(groups);
  }, [touches]);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
      className="min-h-screen p-4 sm:p-8" style={{ background: "var(--bg-base)" }}>
      <div className="max-w-7xl mx-auto">

        {/* Header */}
        <div className="flex items-center gap-2 mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
          <span className="text-[10px] font-bold uppercase tracking-[0.25em] text-white">Workflow</span>
        </div>
        <div className="flex flex-wrap items-end justify-between gap-4 mb-5">
          <div>
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
              Approval Queue
            </h1>
            <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
              Review AI-drafted copy before it goes out. Archived webinars are excluded.
            </p>
          </div>
          {touches.length > 0 && (
            <div className="text-sm font-bold px-3 py-1.5 rounded-xl" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
              {touches.length} pending
            </div>
          )}
        </div>

        {/* Warning */}
        <div className="flex items-start gap-3 px-4 py-3 rounded-xl mb-5" style={{ border: "1px solid rgba(245,158,11,0.3)", background: "rgba(245,158,11,0.06)" }}>
          <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
          <div className="text-xs text-amber-400/90">AI-generated content — verify specific stats and company names before approving.</div>
        </div>

        {/* Webinar filter dropdown */}
        {webinars.length > 1 && (
          <div className="flex items-center gap-2 mb-6">
            <Filter size={14} style={{ color: "var(--text-muted)" }} />
            <div className="relative">
              <select value={filterWebinar} onChange={e => handleFilter(e.target.value)}
                className="text-sm pl-3 pr-8 py-2 rounded-xl appearance-none cursor-pointer transition-colors"
                style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-primary)" }}>
                <option value="all">All active webinars ({touches.length})</option>
                {webinars.map(w => (
                  <option key={w.id} value={w.id}>{w.title.slice(0, 50)}</option>
                ))}
              </select>
              <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--text-muted)" }} />
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="w-7 h-7 border-2 border-white border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {/* Empty */}
        {!loading && touches.length === 0 && (
          <div className="rounded-2xl p-16 text-center" style={{ border: "1px solid var(--border)", background: "var(--bg-surface)" }}>
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4" style={{ background: "var(--bg-sunken)" }}>
              <Inbox size={24} style={{ color: "var(--text-muted)" }} />
            </div>
            <div className="font-medium mb-1" style={{ color: "var(--text-secondary)" }}>
              {filterWebinar === "all" ? "Queue is empty" : "No pending touches for this webinar"}
            </div>
            <div className="text-sm" style={{ color: "var(--text-muted)" }}>
              {filterWebinar === "all" ? "All touches approved or archived." : "Switch to another webinar or check approvals."}
            </div>
          </div>
        )}

        {/* Grouped by webinar */}
        {!loading && grouped.map(([wid, group]) => (
          <div key={wid} className="mb-8">
            {/* Webinar header */}
            <div className="flex items-center gap-3 mb-3">
              <div className="h-px flex-1" style={{ background: "var(--border)" }} />
              <Link to={`/app/webinars/${wid}`}
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold hover:text-white transition-colors"
                style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                {group.title}
                {group.starts_at && <span style={{ color: "var(--text-muted)" }}>· {fmtDate(group.starts_at)}</span>}
                <span className="ml-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-white/15 text-white">
                  {group.touches.length}
                </span>
              </Link>
              <div className="h-px flex-1" style={{ background: "var(--border)" }} />
            </div>

            <div className="space-y-4">
              <AnimatePresence>
                {group.touches.map((t, i) => (
                  <motion.div key={t.id}
                    initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, x: 30, scale: 0.97 }}
                    transition={{ delay: i * 0.04, duration: 0.3 }}>
                    <QueueCard t={t} onApprove={approve} onReject={reject} />
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

function QueueCard({ t, onApprove, onReject }) {
  const [variant, setVariant] = useState(0);
  const variantKey = variant === 0 ? "safe" : "casual";
  const aiCh = t.ai_copy?.channels || {};
  const emailCopy = aiCh.email?.[variantKey];
  const socialChannels = (t.channels || []).filter(c => c !== "email");

  return (
    <div className="rounded-2xl overflow-hidden" data-testid={`queue-card-${t.id}`}
      style={{ border: "1px solid var(--border)", background: "var(--bg-surface)" }}>

      {/* Header */}
      <div className="px-5 py-4 flex items-center justify-between flex-wrap gap-3"
        style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-white text-black font-bold text-sm flex items-center justify-center shrink-0" style={{ fontFamily: "Outfit" }}>
            {t.touch_num}
          </div>
          <div>
            <div className="font-semibold text-sm" style={{ color: "var(--text-primary)", fontWeight: 700 }}>{t.name}</div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              {t.scheduled_at ? fmtDate(t.scheduled_at) : "On registration"}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {["Safe", "Casual"].map((label, idx) => (
            <button key={label} onClick={() => setVariant(idx)}
              data-testid={`q-${t.id}-${label.toLowerCase()}`}
              className="text-xs px-3 py-1.5 rounded-full transition-all font-bold"
              style={variant === idx
                ? { background: "#FFFFFF", color: "#000000" }
                : { color: "var(--text-muted)" }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="grid lg:grid-cols-2" style={{ borderTop: "1px solid var(--border)" }}>
        {/* Email */}
        <div className="p-5" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: "var(--text-muted)" }}>Email</div>
          {emailCopy ? (
            <>
              <div className="text-xs font-semibold mb-2 border-l-2 border-orange-500 pl-2" style={{ color: "var(--text-primary)" }}>
                {emailCopy.subject}
              </div>
              <div className="text-sm whitespace-pre-wrap leading-relaxed" style={{ color: "var(--text-primary)" }}>
                {emailCopy.body}
              </div>
            </>
          ) : <div className="text-sm italic" style={{ color: "var(--text-muted)" }}>No email copy yet.</div>}
        </div>

        {/* Social */}
        <div className="p-5">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: "var(--text-muted)" }}>
            Social ({socialChannels.length})
          </div>
          {socialChannels.length === 0
            ? <div className="text-xs italic" style={{ color: "var(--text-muted)" }}>No social channels.</div>
            : <div className="space-y-3">
                {socialChannels.map(ch => {
                  const copy = aiCh[ch]?.[variantKey];
                  const isManual = CHANNEL_META[ch]?.manualOnly;
                  return (
                    <div key={ch} className="rounded-xl p-3"
                      style={isManual
                        ? { border: "1px solid rgba(245,158,11,0.3)", background: "rgba(245,158,11,0.06)" }
                        : { border: "1px solid var(--border)", background: "var(--bg-sunken)" }}>
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="text-[10px] font-bold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                          {CHANNEL_META[ch]?.label || ch}
                        </div>
                        {isManual && <span className="text-[9px] bg-amber-500/20 text-amber-400 font-bold px-2 py-0.5 rounded-full">Manual</span>}
                      </div>
                      {copy ? (
                        <>
                          <div className="text-sm whitespace-pre-wrap leading-relaxed" style={{ color: "var(--text-primary)" }}>
                            {copy.body}
                          </div>
                          <button onClick={() => { navigator.clipboard.writeText(copy.body); toast.success("Copied!"); }}
                            className="mt-2 text-xs px-2.5 py-1 rounded-lg flex items-center gap-1 transition-colors"
                            style={{ background: isManual ? "#D97706" : "var(--bg-elevated)", color: isManual ? "#fff" : "var(--text-secondary)", fontWeight: isManual ? 700 : 400 }}>
                            <Copy size={10} /> {isManual ? "Copy for manual post" : "Copy"}
                          </button>
                        </>
                      ) : <div className="text-xs italic" style={{ color: "var(--text-muted)" }}>No copy yet.</div>}
                    </div>
                  );
                })}
              </div>
          }
        </div>
      </div>

      {/* Actions */}
      <div className="px-5 py-3.5 flex justify-end gap-2" style={{ borderTop: "1px solid var(--border)" }}>
        <button data-testid={`q-reject-${t.id}`} onClick={() => onReject(t)}
          className="text-sm px-3 py-1.5 text-red-400 hover:bg-red-500/10 rounded-xl flex items-center gap-1.5 transition-colors">
          <X size={13} /> Reject
        </button>
        <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          data-testid={`q-approve-${t.id}`} onClick={() => onApprove(t, variant === 0 ? "safe" : "casual")}
          className="text-sm px-5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl flex items-center gap-1.5 transition-colors">
          <Check size={13} /> Approve {variantKey === "safe" ? "Safe" : "Casual"}
        </motion.button>
      </div>
    </div>
  );
}
