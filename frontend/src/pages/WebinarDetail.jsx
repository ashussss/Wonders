import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, CalendarDays, Check, Clock, Copy, FileDown, Link, Plus, RefreshCcw, Send, Share2, Star, Trash2, Upload, User, X, Zap } from "@/components/Icons";
import { useParams, useNavigate } from "react-router-dom";
import { api, fmtDate, CHANNEL_META, API_BASE } from "@/lib/api";
import { useTheme } from "@/lib/theme";
import { motion, AnimatePresence } from "framer-motion";
import AdHocPostDialog from "@/components/AdHocPostDialog";
import { toast } from "sonner";

const CHANNELS = ["email","linkedin","linkedin_personal","facebook","instagram","whatsapp","circle"];

export default function WebinarDetail() {
  const { isDark } = useTheme();
  const { id } = useParams();
  const nav = useNavigate();
  const [tab, setTab] = useState("plan");
  const [w, setW] = useState(null);
  const [touches, setTouches] = useState([]);
  const [registrants, setRegistrants] = useState([]);
  const [lm, setLm] = useState(null);
  const [adhocOpen, setAdhocOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [regenAllBusy, setRegenAllBusy] = useState(false);
  const [insights, setInsights] = useState(null);
  const [editOpen, setEditOpen] = useState(false);
  const [bannerUploading, setBannerUploading] = useState(false);
  const [goingLive, setGoingLive] = useState(false);
  const [postWebinarOpen, setPostWebinarOpen] = useState(false);

  const goLive = async () => {
    if (!window.confirm("Send 'We are live!' email to all registrants now?")) return;
    setGoingLive(true);
    try {
      const r = await api.post(`/webinars/${id}/go-live`);
      toast.success(`Sent to ${r.data.sent} registrants! 🔴`);
    } catch(e) {
      toast.error(e?.response?.data?.detail || "Failed to send");
    } finally { setGoingLive(false); }
  };

  const uploadBanner = async (file) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) { toast.error("Only image files allowed"); return; }
    if (file.size > 5 * 1024 * 1024) { toast.error("Max 5MB"); return; }
    setBannerUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api.post(`/webinars/${id}/banner`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Banner uploaded!");
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Upload failed"); }
    finally { setBannerUploading(false); }
  };

  const deleteBanner = async () => {
    try { await api.delete(`/webinars/${id}/banner`); toast.success("Banner removed"); reload(); }
    catch(e) { toast.error("Failed to remove banner"); }
  };

  const reload = async () => {
    const [wr, tr, rr, lr, ir] = await Promise.all([
      api.get(`/webinars/${id}`),
      api.get(`/webinars/${id}/touches`),
      api.get(`/webinars/${id}/registrants`),
      api.get(`/webinars/${id}/lead-magnets`),
      api.get(`/webinars/${id}/ai-insights`).catch(() => ({ data: null })),
    ]);
    setW(wr.data);
    setTouches(tr.data);
    setRegistrants(rr.data);
    setLm(lr.data);
    if (ir?.data) setInsights(ir.data);
  };
  useEffect(() => { reload(); }, [id]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await api.delete(`/webinars/${id}`);
      toast.success("Webinar deleted");
      nav("/");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delete failed");
      setDeleting(false);
    }
  };

  const handleRegenAll = async () => {
    setRegenAllBusy(true);
    try {
      const r = await api.post(`/webinars/${id}/regenerate-all`);
      toast.success(`Regenerating ${r.data.regenerated} touches — refresh in a moment`);
      setTimeout(() => reload(), 3000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Regeneration failed");
    } finally {
      setRegenAllBusy(false);
    }
  };

  if (!w) return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg-base)" }}>
      <div className="w-8 h-8 border-2 border-white border-t-transparent rounded-full animate-spin" />
    </div>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="min-h-screen p-4 sm:p-8" style={{ background: "var(--bg-base)" }}
    >
      <div className="max-w-7xl mx-auto">

        {/* Back */}
        <button onClick={() => nav("/app")} className={`text-sm flex items-center gap-1.5 mb-6 transition-colors ${isDark ? "text-gray-600 hover:text-gray-300" : "text-gray-400 hover:text-gray-700"}`} data-testid="back-btn">
          <ArrowLeft size={15} /> Back to dashboard
        </button>

        {/* Header */}
        <header className="rounded-2xl p-6 mb-6" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }}>
          {/* Top row — status + actions */}
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest ${w.status === "completed" ? "bg-gray-800 text-gray-400" : "bg-white/15 text-white"}`}>
                {w.status}
              </span>
              <a href={`${API_BASE}/webinars/${w.id}/calendar.ics`} data-testid="dl-ics"
                className={`text-xs inline-flex items-center gap-1 transition-colors ${isDark ? "text-gray-500 hover:text-orange-400" : "text-gray-400 hover:text-orange-500"}`}>
                <CalendarDays size={12} /> Add to calendar
              </a>
              <a href={`${API_BASE}/webinars/${w.id}/one-pager.pdf`} target="_blank" rel="noreferrer" data-testid="dl-pdf"
                className={`text-xs inline-flex items-center gap-1 transition-colors ${isDark ? "text-gray-500 hover:text-orange-400" : "text-gray-400 hover:text-orange-500"}`}>
                <FileDown size={12} /> One-pager PDF
              </a>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <motion.button
                whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
                onClick={() => setEditOpen(true)}
                className="text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 rounded-lg inline-flex items-center gap-1.5 transition-all"
                style={{ background: "var(--bg-sunken)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                Edit
              </motion.button>
              {w.status !== "archived" && (
                <motion.button
                  whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
                  onClick={goLive} disabled={goingLive}
                  className="text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 rounded-lg inline-flex items-center gap-1.5 transition-all disabled:opacity-50"
                  style={{ background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.4)", color: "#EF4444" }}>
                  {goingLive ? <span className="w-3 h-3 border-2 border-red-400 border-t-transparent rounded-full animate-spin" /> : "🔴"}
                  {goingLive ? "Sending..." : "We're Live!"}
                </motion.button>
              )}
              <motion.button
                whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
                onClick={() => setAdhocOpen(true)}
                data-testid="open-adhoc-btn"
                style={{ background: "linear-gradient(90deg, #EA580C 0%, #DC4A06 100%)", boxShadow: "0 0 12px rgba(234,88,12,0.3)" }}
                className="text-white text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 rounded-lg inline-flex items-center gap-1.5"
              >
                <Zap size={11} /> AI Quick Post
              </motion.button>
              <motion.button
                whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
                onClick={handleRegenAll}
                disabled={regenAllBusy}
                data-testid="regen-all-btn"
                className={`text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 rounded-lg inline-flex items-center gap-1.5 transition-all disabled:opacity-50 ${isDark ? "text-orange-400 bg-orange-500/10 hover:bg-orange-500/20" : "text-orange-600 bg-orange-50 hover:bg-orange-100 border border-orange-200"}`}
              >
                {regenAllBusy ? <span className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" /> : <RefreshCcw size={11} />}
                {regenAllBusy ? "Generating…" : "Regen All"}
              </motion.button>
              <motion.button
                whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
                onClick={() => setDeleteConfirm(true)}
                data-testid="delete-webinar-btn"
                className="text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 rounded-lg inline-flex items-center gap-1.5 transition-all text-red-500 bg-red-500/10 hover:bg-red-500/20"
              >
                <Trash2 size={11} /> Delete
              </motion.button>
            </div>
          </div>

          {/* Title */}
          <h1 className={`text-2xl sm:text-3xl font-bold tracking-tight mb-4 leading-snug ${isDark ? "text-white" : "text-gray-900"}`} style={{ fontFamily: "Outfit" }}>
            {w.title}
          </h1>

          {/* Meta pills row */}
          <div className="flex flex-wrap gap-3 mb-5">
            <div className={`flex items-center gap-2 text-sm px-3 py-2 rounded-xl border ${isDark ? "bg-white/[0.03] border-white/[0.06] text-gray-300" : "bg-gray-50 border-gray-200 text-gray-700"}`}>
              <Clock size={14} className="text-white shrink-0" />
              <div>
                <div className={`text-[10px] font-bold uppercase tracking-wider mb-0.5 ${isDark ? "text-gray-600" : "text-gray-400"}`}>Date & Time</div>
                <div className="font-semibold text-sm">{fmtDate(w.starts_at)}</div>
              </div>
            </div>
            {w.speaker && (
              <div className={`flex items-center gap-2 text-sm px-3 py-2 rounded-xl border ${isDark ? "bg-white/[0.03] border-white/[0.06] text-gray-300" : "bg-gray-50 border-gray-200 text-gray-700"}`}>
                <User size={14} className="text-orange-500 shrink-0" />
                <div>
                  <div className={`text-[10px] font-bold uppercase tracking-wider mb-0.5 ${isDark ? "text-gray-600" : "text-gray-400"}`}>Speaker</div>
                  <div className="font-semibold text-sm">{w.speaker}</div>
                </div>
              </div>
            )}
            {w.target_audience && (
              <div className={`flex items-center gap-2 text-sm px-3 py-2 rounded-xl border ${isDark ? "bg-white/[0.03] border-white/[0.06] text-gray-300" : "bg-gray-50 border-gray-200 text-gray-700"}`}>
                <User size={14} className="text-orange-500 shrink-0" />
                <div>
                  <div className={`text-[10px] font-bold uppercase tracking-wider mb-0.5 ${isDark ? "text-gray-600" : "text-gray-400"}`}>Audience</div>
                  <div className="font-semibold text-sm">{w.target_audience}</div>
                </div>
              </div>
            )}
            <div className={`flex items-center gap-2 text-sm px-3 py-2 rounded-xl border ${isDark ? "bg-white/[0.03] border-white/[0.06] text-gray-300" : "bg-gray-50 border-gray-200 text-gray-700"}`}>
              <Link size={14} className="text-white shrink-0" />
              <div>
                <div className={`text-[10px] font-bold uppercase tracking-wider mb-0.5 ${isDark ? "text-gray-600" : "text-gray-400"}`}>Reg. Link</div>
                <button
                  className="font-semibold text-sm text-white hover:text-gray-300 transition-colors"
                  data-testid="copy-public-link"
                  onClick={() => { navigator.clipboard.writeText(`${window.location.origin}/r/${w.id}`); toast.success("Copied!"); }}
                >
                  Copy link ↗
                </button>
              </div>
            </div>
          </div>

          {/* Banner */}
          <div className="mb-4">
            {w.banner_url ? (
              <div className="relative rounded-xl overflow-hidden" style={{ maxHeight: "220px" }}>
                <img src={`${API_BASE}${w.banner_url.replace("/api","")}`} alt="Webinar banner"
                  className="w-full object-cover rounded-xl" style={{ maxHeight: "220px" }} />
                <button onClick={deleteBanner}
                  className="absolute top-2 right-2 w-7 h-7 rounded-lg bg-black/60 hover:bg-black/80 flex items-center justify-center text-white transition-colors"
                  title="Remove banner">
                  <X size={13} />
                </button>
              </div>
            ) : (
              <label className="flex items-center gap-2 cursor-pointer group">
                <div className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold transition-all"
                  style={{ border: "1px dashed var(--border)", color: "var(--text-muted)", background: "var(--bg-sunken)" }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = "#FFFFFF"}
                  onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border)"}>
                  {bannerUploading
                    ? <><span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" /> Uploading…</>
                    : <><Upload size={13} /> Upload webinar banner (recommended: 1200×630px, max 5MB)</>}
                </div>
                <input type="file" accept="image/*" className="hidden" onChange={e => uploadBanner(e.target.files?.[0])} />
              </label>
            )}
          </div>

          {/* Description */}
          {w.description && (
            <div className={`rounded-xl p-4 border text-sm leading-relaxed ${isDark ? "bg-black/20 border-white/[0.05] text-gray-400" : "bg-gray-50 border-gray-100 text-gray-600"}`}>
              <div className={`text-[10px] font-bold uppercase tracking-wider mb-2 ${isDark ? "text-gray-600" : "text-gray-400"}`}>About this webinar</div>
              {w.description}
            </div>
          )}
        </header>

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6">
          <StatBox label="Registrants" value={w.registrant_count} />
          <StatBox label="Attended" value={w.attendee_count} />
          <StatBox label="Attendance Rate" value={`${w.attendance_rate}%`} highlight />
          <StatBox label="Public Reg. Link" value={
            <button
              className="text-xs text-orange-500 hover:text-orange-400 truncate block w-full text-left transition-colors"
              data-testid="copy-public-link"
              onClick={() => { navigator.clipboard.writeText(`${window.location.origin}/r/${w.id}`); toast.success("Copied"); }}
            >
              {window.location.origin}/r/{w.id.slice(0, 8)}…
            </button>
          } />
        </div>


          {/* ── AI Health Score ── */}
          {insights && (
            <div className="rounded-2xl p-5 mb-5" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
              <div className="flex flex-wrap items-center justify-between gap-4 mb-3">
                <div className="flex items-center gap-3">
                  <div className="text-2xl font-black" style={{ fontFamily: "Outfit", color: insights.health_score >= 80 ? "#10B981" : insights.health_score >= 60 ? "#F59E0B" : "#EF4444" }}>
                    {insights.health_score}<span className="text-sm font-bold" style={{ color: "var(--text-muted)" }}>/100</span>
                  </div>
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>AI Health Score</div>
                    <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>{insights.health_label}</div>
                  </div>
                </div>
                {insights.prediction && insights.prediction.rate > 0 && (
                  <div className="flex items-center gap-5">
                    <div className="text-center">
                      <div className="text-xl font-black text-white" style={{ fontFamily: "Outfit" }}>{insights.prediction.rate}%</div>
                      <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>{insights.prediction.label}</div>
                    </div>
                    {insights.prediction.no_show_pct != null && (
                      <div className="text-center">
                        <div className="text-xl font-black" style={{ fontFamily: "Outfit", color: "var(--text-secondary)" }}>{insights.prediction.no_show_pct}%</div>
                        <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>No-Show Risk</div>
                      </div>
                    )}
                    <span className="text-[9px] px-2 py-0.5 rounded-full font-bold uppercase" style={{
                      background: insights.prediction.confidence === "high" ? "rgba(16,185,129,0.15)" : "rgba(245,158,11,0.15)",
                      color: insights.prediction.confidence === "high" ? "#10B981" : "#F59E0B"
                    }}>{insights.prediction.confidence}</span>
                  </div>
                )}
              </div>
              <div className="h-1.5 rounded-full mb-3 overflow-hidden" style={{ background: "var(--bg-sunken)" }}>
                <div className="h-full rounded-full" style={{ width: `${insights.health_score}%`, background: insights.health_score >= 80 ? "#10B981" : insights.health_score >= 60 ? "#F59E0B" : "#EF4444" }} />
              </div>
              <div className="space-y-1.5">
                {(insights.recommendations || []).slice(0, 3).map((r, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg" style={{
                    background: r.priority === "high" ? "rgba(239,68,68,0.06)" : r.priority === "medium" ? "rgba(245,158,11,0.06)" : "rgba(16,185,129,0.06)",
                    border: `1px solid ${r.priority === "high" ? "rgba(239,68,68,0.2)" : r.priority === "medium" ? "rgba(245,158,11,0.2)" : "rgba(16,185,129,0.2)"}`
                  }}>
                    <span>{r.priority === "high" ? "⚡" : r.priority === "medium" ? "💡" : "✓"}</span>
                    <span className="font-medium" style={{ color: "var(--text-primary)" }}>{r.action}</span>
                    <span style={{ color: "var(--text-muted)" }}>— {r.impact}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

        {/* Tabs */}
        <div className={`border-b mb-7 flex gap-6 ${isDark ? "border-white/[0.06]" : "border-gray-200"}`}>
          {[["plan","Send Plan"], ["content","Content"], ["registrants","Registrants"], ["leadmagnets","Lead Magnets"]].map(([k, l]) => (
            <button key={k} data-testid={`tab-${k}`} onClick={() => setTab(k)}
              className={`pb-3 -mb-px text-sm font-semibold border-b-2 transition-all ${tab === k ? "border-white text-white" : isDark ? "border-transparent text-gray-600 hover:text-gray-300" : "border-transparent text-gray-400 hover:text-gray-700"}`}>
              {l}
            </button>
          ))}
        </div>

        {tab === "plan" && <PlanTab webinar={w} touches={touches} onChange={(signal) => { reload(); if(signal === "approved") setTab("content"); }} />}
        {tab === "registrants" && <RegistrantsTab webinar={w} regs={registrants} onChange={reload} />}
        {tab === "leadmagnets" && <LeadMagnetsTab webinar={w} lm={lm} onChange={reload} />}
        {w.attendee_count > 0 && tab === "plan" && <ShowUpScoreCard webinar={w} />}
        {tab === "content" && <ContentTab webinar={w} touches={touches} onChange={reload} />}
        {editOpen && <EditWebinarModal webinar={w} onClose={() => setEditOpen(false)} onSaved={reload} />}
        <AdHocPostDialog open={adhocOpen} onClose={() => setAdhocOpen(false)} webinar={w} />

        {/* Delete Confirm Modal */}
        <AnimatePresence>
          {deleteConfirm && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
              onClick={() => setDeleteConfirm(false)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.93, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.93, y: 10 }}
                transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                className="rounded-2xl p-6 w-full max-w-md" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", boxShadow: "var(--shadow-lg)" }}
                onClick={e => e.stopPropagation()}
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="w-10 h-10 rounded-xl bg-red-500/15 flex items-center justify-center">
                    <Trash2 size={18} className="text-red-400" />
                  </div>
                  <button onClick={() => setDeleteConfirm(false)} className="text-gray-600 hover:text-gray-300 transition-colors">
                    <X size={18} />
                  </button>
                </div>
                <h3 className="text-lg font-bold text-white mb-1" style={{ fontFamily: 'Outfit' }}>Delete webinar?</h3>
                <p className="text-sm text-gray-500 mb-1">
                  <span className="text-gray-300 font-medium">"{w.title}"</span> and all its touches, registrants, and lead magnets will be permanently deleted.
                </p>
                <p className="text-xs text-red-400/80 mb-6">This action cannot be undone.</p>
                <div className="flex gap-3">
                  <button
                    onClick={() => setDeleteConfirm(false)}
                    className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-gray-400 border border-white/[0.08] hover:bg-white/[0.04] transition-colors"
                  >
                    Cancel
                  </button>
                  <motion.button
                    whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                    onClick={handleDelete}
                    disabled={deleting}
                    data-testid="confirm-delete-btn"
                    className="flex-1 px-4 py-2.5 rounded-xl text-sm font-bold text-white bg-red-600 hover:bg-red-500 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
                  >
                    {deleting ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <Trash2 size={14} />}
                    {deleting ? "Deleting…" : "Yes, delete"}
                  </motion.button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

function StatBox({ label, value, highlight }) {
  return (
    <div className="rounded-xl p-4"
      style={highlight
        ? { background: "rgba(234,88,12,0.08)", border: "1px solid rgba(234,88,12,0.25)" }
        : { background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] mb-2" style={{ color: "var(--text-muted)" }}>{label}</div>
      <div className="text-2xl font-bold" style={{ fontFamily: "Outfit", color: highlight ? "#FFFFFF" : "var(--text-primary)" }}>{value}</div>
    </div>
  );
}

function ShowUpScoreCard({ webinar }) {
  const { isDark } = useTheme();
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState(`${API_BASE}/webinars/${webinar.id}/showup-score.png?v=${Date.now()}`);
  const regen = async () => {
    setBusy(true);
    try { await api.post(`/webinars/${webinar.id}/showup-score/generate`); setUrl(`${API_BASE}/webinars/${webinar.id}/showup-score.png?v=${Date.now()}`); toast.success("ShowUp Score refreshed"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };
  const shareText = `We hit a ${webinar.attendance_rate}% attendance rate on "${webinar.title}" with ShowUpAI — beating the 30% industry baseline.`;
  const li = `https://www.linkedin.com/feed/?shareActive=true&text=${encodeURIComponent(shareText + " " + window.location.origin + "/api/webinars/" + webinar.id + "/showup-score.png")}`;
  return (
    <div className="mt-8 rounded-2xl overflow-hidden border border-white/20 bg-gradient-to-br from-white/5 to-transparent" data-testid="showup-score-card">
      <div className="flex flex-col lg:flex-row gap-6 p-6">
        <a href={url} target="_blank" rel="noreferrer" className="block shrink-0">
          {/* eslint-disable-next-line */}
          <img src={url} alt="ShowUp Score" className="w-52 h-52 object-cover rounded-xl border border-white/20" data-testid="showup-score-image" />
        </a>
        <div className="flex-1">
          <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-white flex items-center gap-1.5 mb-1"><Star size={12} /> ShowUp Score</div>
          <h3 className="text-2xl font-bold text-white mt-1 mb-2" style={{ fontFamily: 'Outfit' }}>
            Attendance rate: <span className="text-gray-300">{webinar.attendance_rate}%</span>
          </h3>
          <p className="text-sm text-gray-500 max-w-xl">Auto-attached to touch #7. Drop it on LinkedIn to turn one webinar into proof for the next.</p>
          <div className="flex flex-wrap gap-2 mt-4">
            <a href={li} target="_blank" rel="noreferrer" data-testid="score-share-linkedin"
              className="px-3 py-1.5 bg-white hover:bg-gray-100 text-black text-sm font-semibold rounded-lg inline-flex items-center gap-1.5 transition-colors">
              <Share2 size={13} /> Share2 on LinkedIn
            </a>
            <a href={url} download={`${webinar.id}-showup-score.png`} data-testid="score-download"
              className="px-3 py-1.5 border border-white/[0.1] bg-white/[0.04] text-gray-300 text-sm font-semibold rounded-lg inline-flex items-center gap-1.5 hover:bg-white/[0.08] transition-colors">
              <FileDown size={13} /> FileDown
            </a>
            <button onClick={regen} disabled={busy} data-testid="score-regen"
              className="px-3 py-1.5 border border-white/[0.1] bg-white/[0.04] text-gray-400 text-sm rounded-lg inline-flex items-center gap-1.5 disabled:opacity-50 hover:bg-white/[0.08] transition-colors">
              <RefreshCcw size={13} /> {busy ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function PlanTab({ webinar, touches, onChange }) {
  const { isDark } = useTheme();
  return (
    <div className="space-y-4" data-testid="plan-timeline">
      {touches.map((t, idx) => <TouchCard key={t.id} touch={t} idx={idx} onChange={onChange} webinar={webinar} />)}
    </div>
  );
}

function TouchCard({ touch, onChange }) {
  const { isDark } = useTheme();
  const [channels, setChannels] = useState(touch.channels);
  const [variant, setVariant] = useState(touch.selected_variant ?? 0);
  const [regenPrompt, setRegenPrompt] = useState("");
  const [showPrompt, setShowPrompt] = useState(false);

  const generating = !touch.ai_copy || Object.keys(touch.ai_copy).length === 0;
  const aiCh = touch.ai_copy?.channels || {};
  const variantKey = variant === 0 ? "safe" : "casual";

  const toggleChannel = async (ch) => {
    const next = channels.includes(ch) ? channels.filter(c => c !== ch) : [...channels, ch];
    setChannels(next);
    await api.patch(`/touches/${touch.id}`, { channels: next });
    toast.success("Channels updated — regenerating copy…");
    onChange();
  };
  const approve = async () => { await api.patch(`/touches/${touch.id}`, { approval_status: "approved", selected_variant: variant }); toast.success("Approved ✓ — view in Content tab"); onChange("approved"); };
  const reject = async () => { await api.patch(`/touches/${touch.id}`, { approval_status: "rejected" }); onChange(); };
  const regen = async () => {
    toast.message("Regenerating with Claude…");
    await api.post(`/touches/${touch.id}/regenerate`, { custom_instructions: regenPrompt });
    setRegenPrompt("");
    setShowPrompt(false);
    onChange();
  };

  const statusColor = touch.approval_status === "approved" ? "bg-emerald-500/15 text-emerald-400" :
    touch.approval_status === "rejected" ? "bg-red-500/15 text-red-400" : "bg-amber-500/15 text-amber-400";

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl overflow-hidden" style={{ border: "1px solid var(--border)", background: "var(--bg-surface)", boxShadow: "var(--shadow-sm)" }}
      data-testid={`touch-card-${touch.touch_num}`}
    >
      {/* Touch Header */}
      <div className={`flex items-start justify-between gap-4 px-5 py-4 border-b ${isDark ? "border-white/[0.06]" : "border-gray-100"}`}>
        <div className="flex gap-3.5 items-start">
          <div className="w-9 h-9 rounded-xl bg-white text-black font-bold text-sm flex items-center justify-center shrink-0" style={{ fontFamily: 'Outfit' }}>
            {touch.touch_num}
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <div className={`font-semibold text-sm ${isDark ? "text-white" : "text-gray-900"}`}>{touch.name}</div>
              {touch.ai_copy?.touch_type && (
                <span className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                  touch.ai_copy.touch_type === "insight" ? "bg-purple-500/15 text-purple-400" :
                  touch.ai_copy.touch_type === "poll" ? "bg-pink-500/15 text-pink-400" :
                  touch.ai_copy.touch_type === "case_study" ? "bg-cyan-500/15 text-cyan-400" :
                  touch.ai_copy.touch_type === "thought_provoking" ? "bg-amber-500/15 text-amber-400" :
                  touch.ai_copy.touch_type === "confirmation" ? "bg-blue-500/15 text-blue-400" :
                  touch.ai_copy.touch_type === "post_event_insight" ? "bg-emerald-500/15 text-emerald-400" :
                  touch.ai_copy.touch_type === "fomo" ? "bg-red-500/15 text-red-400" :
                  "bg-gray-500/15 text-gray-400"
                }`}>
                  {touch.ai_copy.touch_type.replace(/_/g, " ")}
                </span>
              )}
            </div>
            <div className={`text-xs font-mono mt-0.5 ${isDark ? "text-gray-600" : "text-gray-400"}`}>{touch.scheduled_at ? fmtDate(touch.scheduled_at) : "On registration"}</div>
            {touch.ai_reasoning && (
              <div className={`text-xs mt-1 max-w-xl italic ${isDark ? "text-gray-600" : "text-gray-500"}`}>💡 {touch.ai_reasoning.slice(0, 120)}…</div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide ${statusColor}`}>
            {touch.approval_status}
          </span>
          {touch.sent_status !== "planned" && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide bg-blue-500/15 text-blue-400">
              {touch.sent_status}
            </span>
          )}
        </div>
      </div>

      {/* Channels */}
      <div className="px-5 py-3 border-b border-white/[0.04] flex flex-wrap gap-2 items-center">
        <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-gray-600 mr-1">Channels:</span>
        {CHANNELS.map(ch => (
          <button key={ch} data-testid={`touch-${touch.touch_num}-ch-${ch}`} onClick={() => toggleChannel(ch)}
            className={`text-xs px-2.5 py-1 rounded-full border transition-all ${channels.includes(ch)
              ? "bg-orange-600 border-orange-600 text-white"
              : isDark ? "bg-transparent border-white/[0.1] text-gray-500 hover:border-white/50 hover:text-gray-300" : "bg-transparent border-gray-200 text-gray-500 hover:border-gray-400 hover:text-gray-700"}`}>
            {CHANNEL_META[ch].label}
          </button>
        ))}
      </div>

      {/* Variant */}
      <div className={`px-5 py-3 border-b flex gap-2 items-center ${isDark ? "border-white/[0.04]" : "border-gray-100"}`}>
        <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-gray-600">Variant:</span>
        <button data-testid={`touch-${touch.touch_num}-safe`} onClick={() => setVariant(0)}
          className="text-xs px-3 py-1 rounded-full transition-all font-bold" style={variant === 0 ? { background: "#FFFFFF", color: "#000000" } : { color: "var(--text-muted)" }}>
          Safe / Professional
        </button>
        <button data-testid={`touch-${touch.touch_num}-casual`} onClick={() => setVariant(1)}
          className="text-xs px-3 py-1 rounded-full transition-all font-bold" style={variant === 1 ? { background: "#FFFFFF", color: "#000000" } : { color: "var(--text-muted)" }}>
          Casual / Urgent
        </button>
        <div className="flex-1" />
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-2">
            <button onClick={() => setShowPrompt(p => !p)} data-testid={`touch-${touch.touch_num}-regen`}
              className={`text-xs flex items-center gap-1 transition-colors ${isDark ? "text-gray-600 hover:text-gray-300" : "text-gray-400 hover:text-gray-600"}`}>
              <RefreshCcw size={12} /> Regenerate
            </button>
          </div>
          {showPrompt && (
            <div className="flex items-center gap-1.5 w-full mt-1">
              <input value={regenPrompt} onChange={e => setRegenPrompt(e.target.value)}
                placeholder="Add instructions (optional)… e.g. more urgent, mention Martyn's Law"
                className="text-xs px-2 py-1 rounded-lg flex-1 focus:outline-none"
                style={{ background: "var(--bg-sunken)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                onKeyDown={e => e.key === "Enter" && regen()} />
              <button onClick={regen} className="text-xs px-2.5 py-1 rounded-lg bg-white text-black font-semibold">Go</button>
            </div>
          )}
        </div>
      </div>

      {/* Copy Content */}
      {generating ? (
        <div className="px-5 py-10 text-center text-sm text-gray-600">
          <div className="inline-block w-5 h-5 border-2 border-orange-500 border-t-transparent rounded-full animate-spin mr-2" />
          AI drafting copy…
        </div>
      ) : (
        <div className={`grid lg:grid-cols-2 divide-x ${isDark ? "divide-white/[0.04]" : "divide-gray-100"}`}>
          {channels.map(ch => {
            const channelCopy = aiCh[ch]?.[variantKey];
            const isManual = CHANNEL_META[ch].manualOnly;
            return (
              <div key={ch} className={`p-5 ${isManual ? "bg-amber-500/5" : ""}`}>
                <div className="flex items-center justify-between mb-2.5">
                  <div className={`text-[10px] font-bold uppercase tracking-[0.18em] ${isDark ? "text-gray-500" : "text-gray-400"}`}>{CHANNEL_META[ch].label}</div>
                  {isManual && (
                    <span className="text-[9px] bg-amber-500/20 text-amber-400 font-bold px-2 py-0.5 rounded-full uppercase tracking-wide">⚠ Manual</span>
                  )}
                </div>
                {channelCopy ? (
                  <>
                    {channelCopy.subject && (
                      <div className={`text-xs font-semibold mb-1.5 border-l-2 border-white pl-2 ${isDark ? "text-gray-300" : "text-gray-700"}`}>
                        {channelCopy.subject}
                      </div>
                    )}
                    <div className={`text-sm whitespace-pre-wrap leading-relaxed ${isDark ? "text-gray-400" : "text-gray-600"}`}>{channelCopy.body}</div>
                    <div className="flex gap-2 mt-3">
                      <button
                        onClick={() => { navigator.clipboard.writeText(`${channelCopy.subject ? channelCopy.subject + '\n\n' : ''}${channelCopy.body}`); toast.success("Copied!"); }}
                        data-testid={`copy-${touch.touch_num}-${ch}`}
                        className={`text-xs px-2.5 py-1 rounded-lg font-semibold inline-flex items-center gap-1 transition-colors ${isManual ? "bg-amber-600 hover:bg-amber-500 text-white" : "bg-white/[0.06] hover:bg-white/[0.1] text-gray-300"}`}>
                        <Copy size={11} /> {isManual ? "Copy for LinkedIn" : "Copy"}
                      </button>
                      {isManual && (
                        <a href="https://www.linkedin.com/feed/?shareActive=true" target="_blank" rel="noreferrer"
                          data-testid={`open-linkedin-${touch.touch_num}`}
                          className="text-xs px-2.5 py-1 rounded-lg text-amber-400 border border-amber-500/30 hover:bg-amber-500/10 inline-flex items-center gap-1 transition-colors">
                          Open LinkedIn ↗
                        </a>
                      )}
                    </div>
                  </>
                ) : (
                  <div className={`text-sm italic ${isDark ? "text-gray-700" : "text-gray-400"}`}>No copy generated yet.</div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Actions */}
      <div className={`px-5 py-3.5 flex justify-end gap-2 border-t ${isDark ? "border-white/[0.04]" : "border-gray-100"}`}>
        <button onClick={reject} data-testid={`reject-${touch.touch_num}`}
          className="text-sm px-3 py-1.5 text-red-400 hover:bg-red-500/10 rounded-lg transition-colors">
          Reject
        </button>
        <button onClick={approve} data-testid={`approve-${touch.touch_num}`}
          className="text-sm px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-lg flex items-center gap-1.5 transition-colors">
          <Check size={13} /> Approve {variantKey === "safe" ? "Safe" : "Casual"}
        </button>
        {touch.approval_status === "approved" && touch.sent_status !== "sent" && (
          <button data-testid={`send-now-${touch.touch_num}`} onClick={async () => {
            toast.message("Delivering…");
            try { const r = await api.post(`/touches/${touch.id}/send-now`); toast[r.data.ok ? "success" : "error"](r.data.ok ? "Delivered" : "Delivery failed — check Settings"); onChange(); }
            catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
          }} className="text-sm px-4 py-1.5 bg-white hover:bg-gray-100 text-black font-semibold rounded-lg flex items-center gap-1.5 transition-colors">
            <Send size={13} /> Send now
          </button>
        )}
      </div>

      {(touch.delivery_log && touch.delivery_log.length > 0) && (
        <div className={`px-5 py-2.5 border-t text-xs space-y-1 ${isDark ? "border-white/[0.04]" : "border-gray-100"}`}>
          <div className={`font-semibold ${isDark ? "text-gray-600" : "text-gray-400"}`}>Delivery log ({touch.delivery_log.length}):</div>
          {touch.delivery_log.slice(0, 6).map((d, i) => (
            <div key={i} className={`font-mono ${d.ok ? "text-emerald-400" : "text-red-400"}`}>
              {d.ok ? "✓" : "✗"} [{d.channel}] {d.recipient || ""} {!d.ok && d.detail ? `— ${d.detail.slice(0, 80)}` : ""}
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

function RegistrantsTab({ webinar, regs, onChange }) {
  const { isDark } = useTheme();
  const [importing, setImporting] = useState(false);
  const [csv, setCsv] = useState("");

  const toggleAttended = async (r) => { await api.patch(`/registrants/${r.id}`, { attended: !r.attended }); onChange(); };
  const toggleCommunityJoined = async (r) => { await api.patch(`/registrants/${r.id}`, { community_joined: !r.community_joined }); onChange(); };
  const doImport = async () => {
    const items = csv.split("\n").map(l => l.trim()).filter(Boolean).map(l => {
      const [name, email, phone] = l.split(",").map(x => x?.trim());
      return { name: name || email, email, phone, source: "linkedin_manual" };
    }).filter(it => it.email);
    if (!items.length) return toast.error("Provide name,email per line");
    const r = await api.post(`/webinars/${webinar.id}/registrants/import`, items);
    toast.success(`Imported ${r.data.inserted}, deduped ${r.data.deduped}`);
    setImporting(false); setCsv(""); onChange();
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <div className="text-sm text-gray-500">{regs.length} registrants · {regs.filter(r => r.attended).length} attended</div>
        <button data-testid="open-import" onClick={() => setImporting(true)}
          className="text-sm text-white font-semibold hover:text-gray-200 flex items-center gap-1.5 transition-colors">
          <Upload size={13} /> Import CSV
        </button>
      </div>

      <div className="rounded-2xl overflow-hidden" style={{ border: "1px solid var(--border)", background: "var(--bg-surface)", boxShadow: "var(--shadow-sm)" }}>
        <div className={`hidden md:grid grid-cols-12 gap-2 px-6 py-3.5 border-b text-[10px] font-bold uppercase tracking-[0.18em] ${isDark ? "border-white/[0.06] text-gray-600" : "border-gray-100 text-gray-400"}`}>
          <div className="col-span-3">Name</div>
          <div className="col-span-4">Email</div>
          <div className="col-span-2">Source</div>
          <div className="col-span-1 text-right">Attended</div>
          <div className="col-span-2 text-right">Community</div>
        </div>
        {regs.length === 0 && (
          <div className={`p-10 text-center text-sm ${isDark ? "text-gray-600" : "text-gray-400"}`}>No registrants yet. Share2 your public registration link.</div>
        )}
        {regs.map(r => (
          <div key={r.id} className={`grid grid-cols-12 gap-2 px-6 py-3.5 border-b text-sm items-center transition-colors ${isDark ? "border-white/[0.04] hover:bg-white/[0.02]" : "border-gray-100 hover:bg-white/[0.02]"}`} data-testid={`reg-row-${r.id}`}>
            <div className={`col-span-3 font-medium ${isDark ? "text-white" : "text-gray-900"}`}>{r.name}</div>
            <div className={`col-span-4 font-mono text-xs ${isDark ? "text-gray-500" : "text-gray-500"}`}>{r.email}</div>
            <div className="col-span-2">
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/[0.05] text-gray-500">{r.source}</span>
            </div>
            <div className="col-span-1 text-right">
              <button data-testid={`toggle-attended-${r.id}`} onClick={() => toggleAttended(r)}
                className={`text-xs px-2.5 py-1 rounded-full font-medium transition-colors ${r.attended ? "bg-emerald-500/20 text-emerald-400" : "bg-white/[0.05] text-gray-600 hover:text-gray-300"}`}>
                {r.attended ? "✓" : "Mark"}
              </button>
            </div>
            <div className="col-span-2 text-right">
              <button data-testid={`toggle-community-${r.id}`} onClick={() => toggleCommunityJoined(r)}
                className={`text-xs px-2.5 py-1 rounded-full font-medium transition-colors ${r.community_joined ? "bg-white/20 text-white" : "bg-white/[0.05] text-gray-600 hover:text-gray-300"}`}>
                {r.community_joined ? "Joined ✓" : "Mark"}
              </button>
            </div>
          </div>
        ))}
      </div>

      <AnimatePresence>
        {importing && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.93 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.93 }}
              className="rounded-2xl p-6 w-full max-w-lg" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", boxShadow: "var(--shadow-lg)" }}
            >
              <h3 className={`font-bold text-lg mb-2 ${isDark ? "text-white" : "text-gray-900"}`} style={{ fontFamily: 'Outfit' }}>Import LinkedIn / CSV</h3>
              <p className={`text-sm mb-3 ${isDark ? "text-gray-500" : "text-gray-500"}`}>One per line: <code className="text-white">Name, email, phone (optional)</code></p>
              <textarea data-testid="import-csv" rows={6} value={csv} onChange={e => setCsv(e.target.value)}
                className={`w-full rounded-xl p-3 text-sm font-mono focus:outline-none focus:border-orange-500/50 ${isDark ? "bg-black/40 border border-white/[0.1] text-gray-300" : "bg-gray-50 border border-gray-200 text-gray-700"}`}
                placeholder="Jane Doe, jane@school.uk" />
              <div className="flex justify-end gap-2 mt-3">
                <button onClick={() => setImporting(false)} className="px-4 py-2 text-sm text-gray-500 border border-white/[0.08] rounded-xl hover:bg-white/[0.04] transition-colors">Cancel</button>
                <button data-testid="do-import" onClick={doImport} className="px-4 py-2 bg-white hover:bg-gray-100 text-black text-sm rounded-xl font-semibold transition-colors">Import</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function LeadMagnetsTab({ webinar, lm, onChange }) {
  const { isDark } = useTheme();
  const content = lm?.ai_content || {};
  const generating = !content || !content.case_study;
  const [edited, setEdited] = useState({ case_study: "", snippets: "", one_pager: "" });
  const [approved, setApproved] = useState(lm?.approval_status === "approved");
  const [imgBusy, setImgBusy] = useState(false);
  const [imgUrl, setImgUrl] = useState(`${API_BASE}/webinars/${webinar.id}/social-image.png?v=${Date.now()}`);
  const [imgType, setImgType] = useState("carousel");
  const [imgChannel, setImgChannel] = useState("instagram");
  const [generatedImages, setGeneratedImages] = useState({});

  const regen = async () => { toast.message("Regenerating lead magnets…"); await api.post(`/webinars/${webinar.id}/lead-magnets/regenerate`); onChange(); };
  const approve = async () => { await api.patch(`/lead-magnets/${lm.id}`, { approval_status: "approved", edited_content: edited }); setApproved(true); toast.success("Lead magnets approved"); };
  const CHANNEL_SIZES = {
    instagram:  { label: "Instagram",  size: "1080×1080", icon: "📸" },
    linkedin:   { label: "LinkedIn",   size: "1200×627",  icon: "💼" },
    facebook:   { label: "Facebook",   size: "1200×630",  icon: "👥" },
    twitter:    { label: "Twitter/X",  size: "1600×900",  icon: "🐦" },
    stories:    { label: "Stories",    size: "1080×1920", icon: "📱" },
    whatsapp:   { label: "WhatsApp",   size: "800×800",   icon: "💬" },
  };

  const downloadCarousel = async () => {
    setImgBusy(true);
    try {
      const r = await api.post(`/webinars/${webinar.id}/carousel/generate`);
      if (r.data?.base64) {
        const a = document.createElement("a");
        a.href = r.data.base64;
        a.download = r.data.filename || "carousel.zip";
        a.click();
        toast.success(`${r.data.slides} slides downloaded as ZIP!`);
      }
    } catch(e) { toast.error("Carousel generation failed"); }
    finally { setImgBusy(false); }
  };

  const genImg = async () => {
    setImgBusy(true);
    try {
      const r = await api.post(`/webinars/${webinar.id}/social-image/generate`, {
        image_type: imgType || "carousel",
        channel: imgChannel,
      });
      // Use base64 directly if available (avoids URL fetch issues)
      const url = r.data?.base64 || (r.data?.url
        ? `${API_BASE.replace("/api","")}${r.data.url}`
        : `${API_BASE}/webinars/${webinar.id}/social-image.png?v=${Date.now()}`);
      setImgUrl(url);
      setGeneratedImages(prev => ({ ...prev, [imgChannel]: { url, type: imgType } }));
      toast.success(`${CHANNEL_SIZES[imgChannel]?.label || imgChannel} image generated!`);
    }
    catch (e) { toast.error(e?.response?.data?.detail || "ImageIcon generation failed"); }
    finally { setImgBusy(false); }
  };

  return (
    <div className="space-y-4" data-testid="lead-magnets-tab">
      <div className="flex items-start gap-3 px-4 py-3.5 rounded-xl border border-amber-500/20 bg-amber-500/5" data-testid="lm-warning">
        <AlertTriangle size={16} className="text-amber-400 shrink-0 mt-0.5" />
        <div>
          <div className="text-sm font-semibold text-amber-300">AI-generated — verify before sending</div>
          <div className="text-xs text-amber-400/70 mt-0.5">Replace fabricated examples with real case studies and verified statistics before publishing.</div>
        </div>
      </div>

      <div className="flex justify-between items-center">
        <h3 className="text-lg font-bold text-white" style={{ fontFamily: 'Outfit' }}>Supporting content</h3>
        <button data-testid="regen-lm" onClick={regen} className="text-sm text-white hover:text-gray-200 font-semibold flex items-center gap-1.5 transition-colors">
          <RefreshCcw size={13} /> Regenerate all
        </button>
      </div>

      {generating ? (
        <div className="rounded-2xl p-14 text-center" style={{ border: "1px solid var(--border)", background: "var(--bg-surface)", color: "var(--text-muted)", boxShadow: "var(--shadow-sm)" }}>
          <div className="inline-block w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin mr-3" />
          Claude is drafting your case study, snippets, and one-pager…
        </div>
      ) : (
        <>
          <Section title="Mini Case Study" tag="case-study">
            <textarea defaultValue={content.case_study} onChange={e => setEdited({ ...edited, case_study: e.target.value })}
              data-testid="lm-case-study" rows={8}
              className={`w-full rounded-xl p-3 text-sm leading-relaxed focus:outline-none focus:border-white/50 resize-none ${isDark ? "bg-black/30 border border-white/[0.08] text-gray-300" : "bg-gray-50 border border-gray-200 text-gray-700"}`} />
          </Section>
          <Section title="Insight Snippets" tag="snippets">
            <ol className={`list-decimal pl-5 space-y-1.5 text-sm ${isDark ? "text-gray-400" : "text-gray-600"}`}>
              {(content.snippets || []).map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          </Section>
          <Section title="One-Pager Outline" tag="one-pager">
            <div className={`font-semibold mb-2 ${isDark ? "text-gray-300" : "text-gray-700"}`}>{content.one_pager?.title}</div>
            <ul className={`list-disc pl-5 space-y-1 text-sm ${isDark ? "text-gray-500" : "text-gray-600"}`}>
              {(content.one_pager?.outline || []).map((o, i) => <li key={i}>{o}</li>)}
            </ul>
          </Section>
          <Section title="Social Media Images" tag="social-image">
            <div className="space-y-4">
              {/* Channel selector */}
              <div>
                <div className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>Platform</div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(CHANNEL_SIZES).map(([key, ch]) => (
                    <button key={key} onClick={() => { setImgChannel(key); if(generatedImages[key]) setImgUrl(generatedImages[key].url); }}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all"
                      style={imgChannel === key
                        ? { background: "#EA580C", color: "#fff" }
                        : { background: "var(--bg-sunken)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                      <span>{ch.icon}</span>
                      <span>{ch.label}</span>
                      <span className="opacity-60">{ch.size}</span>
                      {generatedImages[key] && <span className="w-1.5 h-1.5 rounded-full bg-green-400 ml-1" />}
                    </button>
                  ))}
                </div>
              </div>

              {/* ImageIcon type selector */}
              <div>
                <div className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>Format</div>
                <div className="flex gap-2">
                  {[
                    { key: "carousel", label: "🎠 Carousel", desc: "6 slides" },
                    { key: "infographic", label: "📊 Infographic", desc: "Topic insights" },
                    { key: "quote_card", label: "💬 Quote Card", desc: "Bold statement" },
                  ].map(t => (
                    <button key={t.key} onClick={() => setImgType(t.key)}
                      className="flex-1 py-2 px-3 rounded-xl text-xs font-bold transition-all text-center"
                      style={imgType === t.key
                        ? { background: "rgba(234,88,12,0.15)", border: "1px solid #EA580C", color: "#EA580C" }
                        : { background: "var(--bg-sunken)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
                      <div>{t.label}</div>
                      <div className="opacity-60 font-normal mt-0.5">{t.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Preview + Generate */}
              <div className="flex gap-4 items-start">
                <div className="rounded-xl overflow-hidden shrink-0" style={{
                  width: imgChannel === "stories" ? "60px" : "120px",
                  height: imgChannel === "stories" ? "120px" : imgChannel === "twitter" || imgChannel === "linkedin" || imgChannel === "facebook" ? "63px" : "120px",
                  border: "1px solid var(--border)", background: "var(--bg-sunken)"
                }}>
                  <img src={imgUrl} onError={e => e.target.style.display="none"}
                    alt="Preview" className="w-full h-full object-cover" />
                </div>
                <div className="flex-1 space-y-3">
                  <div className="text-sm" style={{ color: "var(--text-muted)" }}>
                    Generating for <strong style={{ color: "var(--text-primary)" }}>{CHANNEL_SIZES[imgChannel]?.label}</strong> at {CHANNEL_SIZES[imgChannel]?.size}px
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    <button onClick={genImg} disabled={imgBusy}
                      className="px-5 py-2.5 bg-orange-600 hover:bg-orange-500 text-white text-sm font-bold rounded-xl disabled:opacity-50 transition-colors flex items-center gap-2">
                      {imgBusy
                        ? <><span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Generating…</>
                        : <>🎨 Generate {CHANNEL_SIZES[imgChannel]?.label} Image</>}
                    </button>
                    {imgType === "carousel" && (
                      <button onClick={downloadCarousel} disabled={imgBusy}
                        className="px-4 py-2.5 text-sm font-bold rounded-xl disabled:opacity-50 transition-colors flex items-center gap-2"
                        style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                        📦 FileDown All 6 Slides
                      </button>
                    )}
                    {imgUrl && imgUrl.startsWith("data:image") && (
                      <a href={imgUrl} download={`showup-${imgChannel}-${imgType}.png`}
                        className="px-4 py-2.5 text-sm font-bold rounded-xl transition-colors flex items-center gap-2"
                        style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                        ⬇️ FileDown PNG
                      </a>
                    )}
                  </div>
                  {Object.keys(generatedImages).length > 0 && (
                    <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                      Generated: {Object.keys(generatedImages).map(k => CHANNEL_SIZES[k]?.icon).join(" ")}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </Section>
          <div className="flex justify-end">
            <button onClick={approve} disabled={approved} data-testid="lm-approve"
              className={`px-5 py-2.5 rounded-xl font-semibold text-sm transition-colors ${approved ? "bg-emerald-500/20 text-emerald-400" : "bg-emerald-600 hover:bg-emerald-500 text-white"}`}>
              {approved ? "✓ Approved" : "Approve all (verified)"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Section({ title, tag, children }) {
  const { isDark } = useTheme();
  return (
    <div className="rounded-2xl p-5" style={{ border: "1px solid var(--border)", background: "var(--bg-surface)", boxShadow: "var(--shadow-sm)" }} data-testid={`lm-section-${tag}`}>
      <div className={`text-[10px] font-bold uppercase tracking-[0.18em] mb-3 ${isDark ? "text-gray-600" : "text-gray-400"}`}>{title}</div>
      {children}
    </div>
  );
}

// ══════════════════════════════════════════════
// CONTENT TAB — approved touches + images
// ══════════════════════════════════════════════
function ContentTab({ webinar, touches, onChange }) {
  const { isDark } = useTheme();
  const approved = touches.filter(t => t.approval_status === "approved");
  const pending  = touches.filter(t => t.approval_status === "pending");

  return (
    <div className="space-y-5" data-testid="content-tab">
      {/* Summary bar */}
      <div className="flex flex-wrap gap-3">
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold"
          style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.25)", color: "#10B981" }}>
          ✓ {approved.length} approved
        </div>
        {pending.length > 0 && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold"
            style={{ background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.25)", color: "#F59E0B" }}>
            ⏳ {pending.length} pending — go to Send Plan to approve
          </div>
        )}
      </div>

      {approved.length === 0 && (
        <div className="rounded-2xl p-14 text-center" style={{ border: "1px solid var(--border)", background: "var(--bg-surface)" }}>
          <div className="text-4xl mb-3">📭</div>
          <div className="font-semibold mb-1" style={{ color: "var(--text-primary)" }}>No approved content yet</div>
          <div className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>Go to Send Plan tab to review and approve touches.</div>
          <button className="text-sm px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white font-semibold rounded-xl transition-colors">
            View Send Plan →
          </button>
        </div>
      )}

      {approved.map(touch => (
        <ContentCard key={touch.id} touch={touch} webinar={webinar} onChange={onChange} />
      ))}
    </div>
  );
}

function ContentCard({ touch, webinar, onChange }) {
  const { isDark } = useTheme();
  const [imgType, setImgType] = useState("carousel");
  const [imgChannel, setImgChannel] = useState("instagram");
  const [generatedImages, setGeneratedImages] = useState({});
  const [imgBusy, setImgBusy] = useState(false);
  const [imgUrl, setImgUrl] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [expandChannel, setExpandChannel] = useState(touch.channels?.[0] || "email");

  const variantKey = touch.selected_variant === 1 ? "casual" : "safe";
  const aiCh = touch.ai_copy?.channels || {};

  const generateImageIcon = async () => {
    setImgBusy(true);
    try {
      const r = await api.post(`/webinars/${webinar.id}/social-image/generate`, { image_type: imgType });
      const url = r.data?.url
        ? `${window.location.origin.replace(':3000','')}/api${r.data.url.replace('/api','')}`
        : `${API_BASE}/webinars/${webinar.id}/social-image.png?v=${Date.now()}`;
      setImgUrl(`${API_BASE}/webinars/${webinar.id}/social-image.png?v=${Date.now()}`);
      toast.success(`${imgType} image generated!`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "ImageIcon generation failed");
      console.error(e?.response?.data);
    } finally { setImgBusy(false); }
  };

  const deleteContent = async () => {
    setDeleteBusy(true);
    try {
      // Reset touch to pending — clears approval so it goes back to queue
      await api.patch(`/touches/${touch.id}`, { approval_status: "pending", ai_copy: {} });
      toast.success("Content deleted — touch moved back to Send Plan");
      setShowDeleteConfirm(false);
      onChange();
    } catch (e) {
      toast.error("Delete failed");
    } finally { setDeleteBusy(false); }
  };

  const TYPE_COLORS = {
    confirmation: "bg-blue-500/15 text-blue-400",
    insight: "bg-purple-500/15 text-purple-400",
    poll: "bg-pink-500/15 text-pink-400",
    case_study: "bg-cyan-500/15 text-cyan-400",
    thought_provoking: "bg-amber-500/15 text-amber-400",
    reminder: "bg-gray-500/15 text-gray-400",
    post_event_insight: "bg-emerald-500/15 text-emerald-400",
    fomo: "bg-red-500/15 text-red-400",
  };

  return (
    <div className="rounded-2xl overflow-hidden" style={{ border: "1px solid var(--border)", background: "var(--bg-surface)", boxShadow: "var(--shadow-sm)" }}>
      {/* Header */}
      <div className="px-5 py-4 flex items-center justify-between gap-3 flex-wrap"
        style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-orange-600 text-white font-bold text-sm flex items-center justify-center shrink-0"
            style={{ fontFamily: "Outfit" }}>
            {touch.touch_num}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>{touch.name}</span>
              {touch.ai_copy?.touch_type && (
                <span className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${TYPE_COLORS[touch.ai_copy.touch_type] || "bg-gray-500/15 text-gray-400"}`}>
                  {touch.ai_copy.touch_type.replace(/_/g, " ")}
                </span>
              )}
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              {touch.scheduled_at ? fmtDate(touch.scheduled_at) : "On registration"} ·{" "}
              <span className="font-semibold capitalize">{variantKey}</span> variant
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-emerald-500/15 text-emerald-400">✓ Approved</span>
          {touch.sent_status === "sent"
            ? <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-blue-500/15 text-blue-400">Sent</span>
            : <button onClick={() => setShowDeleteConfirm(true)}
                className="text-[10px] px-2.5 py-1 rounded-lg flex items-center gap-1 text-red-400 hover:bg-red-500/10 transition-colors font-semibold">
                <Trash2 size={10} /> Delete
              </button>
          }
        </div>
      </div>

      {/* Channel tabs */}
      <div className="flex gap-1 px-4 py-2.5 overflow-x-auto" style={{ borderBottom: "1px solid var(--border)" }}>
        {touch.channels?.map(ch => (
          <button key={ch} onClick={() => setExpandChannel(ch)}
            className="text-[10px] px-2.5 py-1 rounded-full font-semibold shrink-0 transition-all"
            style={expandChannel === ch
              ? { background: "#EA580C", color: "#fff" }
              : { background: "var(--bg-sunken)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
            {CHANNEL_META[ch]?.label || ch}
          </button>
        ))}
      </div>

      {/* Selected channel copy */}
      <div className="p-5">
        {(() => {
          const copy = aiCh[expandChannel]?.[variantKey];
          if (!copy) return <div className="text-sm italic" style={{ color: "var(--text-muted)" }}>No copy for this channel.</div>;
          return (
            <div>
              {copy.subject && (
                <div className="text-xs font-semibold mb-2 border-l-2 border-orange-500 pl-2" style={{ color: "var(--text-secondary)" }}>
                  {copy.subject}
                </div>
              )}
              <div className="text-sm leading-relaxed whitespace-pre-wrap mb-3" style={{ color: "var(--text-secondary)" }}>
                {copy.body}
              </div>
              <div className="flex gap-2 flex-wrap">
                <button onClick={() => { navigator.clipboard.writeText((copy.subject ? copy.subject + "\n\n" : "") + copy.body); toast.success("Copied!"); }}
                  className="text-xs px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1 transition-colors"
                  style={{ background: "#EA580C", color: "#fff" }}>
                  <Copy size={11} /> Copy
                </button>
                {CHANNEL_META[expandChannel]?.manualOnly && (
                  <a href="https://www.linkedin.com/feed/?shareActive=true" target="_blank" rel="noreferrer"
                    className="text-xs px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1 transition-colors"
                    style={{ border: "1px solid rgba(245,158,11,0.4)", color: "#F59E0B" }}>
                    Open LinkedIn ↗
                  </a>
                )}
                {touch.sent_status !== "sent" && (
                  <button onClick={async () => {
                    try { const r = await api.post(`/touches/${touch.id}/send-now`); toast[r.data.ok ? "success" : "error"](r.data.ok ? "Sent!" : "Failed"); onChange(); }
                    catch(e) { toast.error("Send failed"); }
                  }} className="text-xs px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1 transition-colors"
                    style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                    <Send size={11} /> Send now
                  </button>
                )}
              </div>
            </div>
          );
        })()}
      </div>

      {/* ImageIcon generation */}
      <div className="px-5 pb-5" style={{ borderTop: "1px solid var(--border)", paddingTop: "16px" }}>
        <div className="text-[10px] font-bold uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
          Visual Content
        </div>
        <div className="flex flex-wrap gap-3 items-start">
          {/* ImageIcon preview */}
          <div className="w-28 h-28 rounded-xl overflow-hidden shrink-0 flex items-center justify-center"
            style={{ background: "var(--bg-sunken)", border: "1px solid var(--border)" }}>
            {imgUrl
              ? <img src={imgUrl} alt="Generated" className="w-full h-full object-cover"
                  onError={() => setImgUrl(null)} />
              : <div className="text-[10px] text-center px-2" style={{ color: "var(--text-muted)" }}>No image<br/>generated</div>
            }
          </div>
          <div className="flex-1">
            <div className="flex gap-1.5 mb-2 flex-wrap">
              {["carousel","infographic","quote_card"].map(t => (
                <button key={t} type="button" onClick={() => setImgType(t)}
                  className="text-[9px] px-2 py-1 rounded-full font-bold uppercase tracking-wide transition-all"
                  style={imgType === t
                    ? { background: "#EA580C", color: "#fff" }
                    : { background: "var(--bg-sunken)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                  {t === "quote_card" ? "Quote" : t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
            <button onClick={generateImageIcon} disabled={imgBusy}
              className="text-xs px-3 py-2 rounded-xl font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50"
              style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
              {imgBusy
                ? <><span className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" /> Generating…</>
                : <><Zap size={11} /> Generate image</>}
            </button>
            {imgUrl && (
              <a href={imgUrl} download={`touch-${touch.touch_num}-${imgType}.png`}
                className="mt-1.5 text-[10px] flex items-center gap-1 transition-colors"
                style={{ color: "var(--text-muted)" }}>
                <FileDown size={10} /> FileDown
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Delete confirm */}
      <AnimatePresence>
        {showDeleteConfirm && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setShowDeleteConfirm(false)}>
            <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }} exit={{ scale: 0.95 }}
              className="rounded-2xl p-6 w-full max-w-sm"
              style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", boxShadow: "var(--shadow-lg)" }}
              onClick={e => e.stopPropagation()}>
              <div className="font-bold text-lg mb-1" style={{ color: "var(--text-primary)", fontFamily: "Outfit" }}>Delete content?</div>
              <div className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
                This will clear the approved copy for <strong>Touch {touch.touch_num}</strong> and move it back to pending. You can regenerate it from Send Plan.
              </div>
              <div className="flex gap-2">
                <button onClick={() => setShowDeleteConfirm(false)}
                  className="flex-1 py-2 rounded-xl text-sm transition-colors"
                  style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                  Cancel
                </button>
                <button onClick={deleteContent} disabled={deleteBusy}
                  className="flex-1 py-2 rounded-xl text-sm font-bold text-white bg-red-600 hover:bg-red-500 transition-colors disabled:opacity-50 flex items-center justify-center gap-1">
                  {deleteBusy ? <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <Trash2 size={13} />}
                  {deleteBusy ? "Deleting…" : "Delete"}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ══════════════════════════════════════════════
// EDIT WEBINAR MODAL
// ══════════════════════════════════════════════
function EditWebinarModal({ webinar, onClose, onSaved }) {
  const { isDark } = useTheme();
  const [form, setForm] = useState({
    title:          webinar.title || "",
    speaker:        webinar.speaker || "",
    speakers:       webinar.speakers || "",
    description:    webinar.description || "",
    target_audience:webinar.target_audience || "",
    starts_at:      webinar.starts_at ? webinar.starts_at.slice(0,16) : "",
    timezone:       webinar.timezone || "Europe/London",
    join_link:      webinar.join_link || "",
    key_topics:     webinar.key_topics || "",
    custom_context: webinar.custom_context || "",
  });
  const [saving, setSaving] = useState(false);

  const upd = k => e => setForm(f => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/webinars/${webinar.id}`, {
        ...form,
        starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : webinar.starts_at,
      });
      toast.success("Webinar updated!");
      onSaved();
      onClose();
    } catch(e) {
      toast.error(e?.response?.data?.detail || "Update failed");
    } finally { setSaving(false); }
  };

  const inputStyle = {
    width: "100%", padding: "8px 12px", borderRadius: "8px", fontSize: "14px",
    background: "var(--bg-sunken)", border: "1px solid var(--border)",
    color: "var(--text-primary)", outline: "none",
  };
  const labelStyle = {
    display: "block", fontSize: "11px", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.1em",
    color: "var(--text-muted)", marginBottom: "4px",
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}>
      <motion.div initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }}
        className="rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", boxShadow: "var(--shadow-lg)" }}
        onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 sticky top-0"
          style={{ background: "var(--bg-elevated)", borderBottom: "1px solid var(--border)" }}>
          <h3 className="font-bold text-lg" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
            Edit Webinar
          </h3>
          <button onClick={onClose} style={{ color: "var(--text-muted)" }}>
            <X size={18} />
          </button>
        </div>

        {/* Form */}
        <div className="px-6 py-5 space-y-4">
          <div>
            <label style={labelStyle}>Title *</label>
            <input value={form.title} onChange={upd("title")} style={inputStyle} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={labelStyle}>Main Speaker</label>
              <input value={form.speaker} onChange={upd("speaker")} style={inputStyle} placeholder="Richard Clarke" />
            </div>
            <div>
              <label style={labelStyle}>Additional Speakers</label>
              <input value={form.speakers} onChange={upd("speakers")} style={inputStyle} placeholder="Jane, John (comma separated)" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={labelStyle}>Date & Time</label>
              <input type="datetime-local" value={form.starts_at} onChange={upd("starts_at")} style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Timezone</label>
              <select value={form.timezone} onChange={upd("timezone")} style={inputStyle}>
                {["Europe/London","Europe/Paris","America/New_York","America/Chicago","America/Los_Angeles","Asia/Kolkata","Asia/Singapore","Australia/Sydney"].map(tz => (
                  <option key={tz} value={tz}>{tz}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label style={labelStyle}>Target Audience</label>
            <input value={form.target_audience} onChange={upd("target_audience")} style={inputStyle} placeholder="UK school business managers" />
          </div>

          <div>
            <label style={labelStyle}>Join Link</label>
            <input value={form.join_link} onChange={upd("join_link")} style={inputStyle} placeholder="https://zoom.us/j/..." />
          </div>

          <div>
            <label style={labelStyle}>Description</label>
            <textarea value={form.description} onChange={upd("description")} rows={3}
              style={{ ...inputStyle, resize: "vertical" }} />
          </div>

          <div>
            <label style={labelStyle}>Key Topics / Outcomes</label>
            <input value={form.key_topics} onChange={upd("key_topics")} style={inputStyle}
              placeholder="Martyn's Law compliance, duty of care, practical checklists" />
          </div>

          <div>
            <label style={labelStyle}>AI Instructions</label>
            <textarea value={form.custom_context} onChange={upd("custom_context")} rows={3}
              style={{ ...inputStyle, resize: "vertical" }}
              placeholder="Extra context for AI — e.g. Always mention compliance deadline, reference speaker's background, use urgent professional tone" />
          </div>

          <div className="flex gap-3 pt-2">
            <button onClick={onClose}
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold transition-colors"
              style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
              Cancel
            </button>
            <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
              onClick={save} disabled={saving}
              className="flex-1 py-2.5 rounded-xl text-sm font-bold text-white bg-orange-600 hover:bg-orange-500 transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
              {saving ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : null}
              {saving ? "Saving…" : "Save Changes"}
            </motion.button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
