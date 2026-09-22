import { useEffect, useState } from "react";
import { Activity, ArrowRight, CalendarDays, Moon, Plus, Sun, Trash2, TrendingUp, Users, X, Zap } from "@/components/Icons";
import { motion, AnimatePresence } from "framer-motion";
import CinematicBackground from "@/components/CinematicBackground";
import { api, fmtDate, daysUntil } from "@/lib/api";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import CreateWebinarDialog from "@/components/CreateWebinarDialog";
import FetchWebinarDialog from "@/components/FetchWebinarDialog";
import OnboardingTour from "@/components/OnboardingTour";
import StarField from "@/components/StarField";
import { useTheme } from "@/lib/theme";

const stagger = { animate: { transition: { staggerChildren: 0.07 } } };
const fadeUp = { initial: { opacity: 0, y: 18 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] } };

export default function Dashboard() {
  const { isDark, toggle } = useTheme();
  const [webinars, setWebinars] = useState([]);
  const [registrants, setRegistrants] = useState([]);
  const [dashTab, setDashTab] = useState("webinars");
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [fetchOpen, setFetchOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const nav = useNavigate();

  const load = async () => {
    const [wr] = await Promise.all([
      api.get("/webinars"),
    ]);
    setWebinars(wr.data);
    // Load all registrants across webinars
    const allRegs = [];
    for (const w of wr.data.slice(0, 10)) {
      try {
        const rr = await api.get(`/webinars/${w.id}/registrants`);
        rr.data.forEach(r => allRegs.push({ ...r, webinar_title: w.title, webinar_id: w.id }));
      } catch(e) {}
    }
    setRegistrants(allRegs);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/webinars/${deleteTarget.id}`);
      toast.success("Webinar deleted");
      setDeleteTarget(null);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  const stats = {
    total: webinars.length,
    upcoming: webinars.filter(w => w.status !== "completed").length,
    avgRate: webinars.filter(w => w.registrant_count > 0).length
      ? (webinars.filter(w => w.registrant_count > 0).reduce((s, w) => s + w.attendance_rate, 0) /
        webinars.filter(w => w.registrant_count > 0).length).toFixed(1)
      : "—",
    registrants: webinars.reduce((s, w) => s + w.registrant_count, 0)
  };

  return (
    <div className="min-h-screen relative p-4 sm:p-8" style={{ background: "var(--bg-base)" }}>
      {isDark && <StarField count={120} speed={0.25} />}
      <div className="max-w-7xl mx-auto relative z-10">

        {/* Header */}
        <motion.header
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-10"
        >
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
              <span className="text-[10px] font-bold uppercase tracking-[0.25em] text-white">Control Room</span>
            </div>
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
              Webinars
            </h1>
            <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>Orchestrate touches. Convert registrants. Ship more show-ups.</p>
          </div>
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <motion.button
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
              onClick={() => setFetchOpen(true)}
              className="text-sm font-semibold px-4 py-2.5 rounded-xl flex items-center gap-1.5 transition-colors"
              style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
              🔗 Add from Link
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.03, boxShadow: "0 0 32px rgba(255,255,255,0.3)" }}
              whileTap={{ scale: 0.97 }}
              data-testid="create-webinar-btn"
              onClick={() => setOpen(true)}
              className="bg-white hover:bg-gray-100 text-black font-semibold px-5 py-2.5 rounded-xl flex items-center gap-2 shadow-lg transition-colors"
            >
              <Plus size={17} /> New Webinar
            </motion.button>
          </div>
        </motion.header>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 p-1 rounded-xl w-fit" style={{ background: "var(--bg-sunken)" }}>
          {[["webinars","Webinars"], ["registrants","Registrants"]].map(([k, l]) => (
            <button key={k} onClick={() => setDashTab(k)}
              className="px-4 py-1.5 rounded-lg text-sm font-semibold transition-all"
              style={{
                background: dashTab === k ? "var(--bg-surface)" : "transparent",
                color: dashTab === k ? "var(--text-primary)" : "var(--text-muted)",
                boxShadow: dashTab === k ? "var(--shadow-sm)" : "none",
              }}>
              {l} {k === "registrants" && registrants.length > 0 && (
                <span className="ml-1 text-[10px] bg-white/15 text-white px-1.5 py-0.5 rounded-full font-bold">
                  {registrants.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {dashTab === "webinars" && <>
        {/* KPI Row */}
        <motion.div
          variants={stagger}
          initial="initial"
          animate="animate"
          className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-8"
          data-testid="kpi-row"
        >
          <KPI label="Total Webinars" value={stats.total} icon={CalendarDays} isDark={isDark} />
          <KPI label="Upcoming" value={stats.upcoming} icon={Activity} isDark={isDark} />
          <KPI label="Total Registrants" value={stats.registrants} icon={Users} isDark={isDark} />
          <KPI label="Avg Attendance" value={stats.avgRate === "—" ? "—" : `${stats.avgRate}%`} icon={TrendingUp} highlight isDark={isDark} />
        </motion.div>

        {/* Webinars Table */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25, duration: 0.45 }}
          className="rounded-2xl overflow-hidden" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }}
          data-testid="webinars-table"
        >
          {/* Table Header */}
          <div className="hidden md:grid grid-cols-12 gap-2 px-6 py-3.5 border-b" style={{ borderColor: "var(--border)" }}>
            <div className="col-span-5 text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>Title</div>
            <div className="col-span-2 text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>Starts</div>
            <div className="col-span-1 text-right text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>Days</div>
            <div className="col-span-1 text-right text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>Reg.</div>
            <div className="col-span-2 text-right text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>Attendance</div>
            <div className="col-span-1 text-right text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>Status</div>
          </div>

          {loading && (
            <div className="p-10 text-center">
              <div className="inline-block w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {!loading && webinars.length === 0 && (
            <div className="p-16 text-center">
              <div className="w-14 h-14 rounded-2xl bg-white/10 flex items-center justify-center mx-auto mb-4">
                <Zap size={26} className="text-white" />
              </div>
              <div className="mb-1 font-medium" style={{ color: "var(--text-secondary)" }}>No webinars yet</div>
              <div className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>Create your first and let AI do the heavy lifting.</div>
              <button
                data-testid="empty-create-btn"
                onClick={() => setOpen(true)}
                className="text-sm text-white font-semibold hover:text-gray-300 flex items-center gap-1.5 mx-auto"
              >
                Create your first webinar <ArrowRight size={14} />
              </button>
            </div>
          )}

          <AnimatePresence>
            {webinars.map((w, i) => {
              const d = daysUntil(w.starts_at);
              const daysColor = d === null ? "text-gray-400" : d === 0 ? "text-white font-black" : d <= 3 ? "text-gray-300" : d <= 7 ? "text-gray-400" : "";
              return (
                <motion.div
                  key={w.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ delay: 0.04 * i, duration: 0.3 }}
                >
                  <Link
                    to={`/app/webinars/${w.id}`}
                    data-testid={`webinar-row-${w.id}`}
                    className="group block md:grid md:grid-cols-12 gap-2 px-4 sm:px-6 py-4 border-b transition-all items-center hover:bg-white/[0.02]" style={{ borderColor: "var(--border)" }}
                  >
                    <div className="md:col-span-4 flex items-center gap-3">
                      <div className="w-2 h-2 rounded-full shrink-0 mt-0.5" style={{ background: w.status === "completed" ? "#4B5563" : "#FFFFFF" }} />
                      <div>
                        <div className="font-semibold group-hover:text-white transition-colors text-sm" style={{ color: "var(--text-primary)" }}>{w.title}</div>
                        <div className="text-xs truncate max-w-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{w.description}</div>
                      </div>
                    </div>
                    <div className="md:col-span-2 text-xs font-mono mt-1 md:mt-0 hidden lg:block" style={{ color: "var(--text-muted)" }}>{fmtDate(w.starts_at)}</div>
                    <div className={`md:col-span-1 md:text-right text-sm font-mono font-bold mt-1 md:mt-0 ${daysColor}`}>
                      {d === null ? "—" : `${d}d`}
                    </div>
                    <div className="md:col-span-1 md:text-right text-sm font-mono" style={{ color: "var(--text-secondary)" }}>{w.registrant_count}</div>
                    <div className="md:col-span-2 md:text-right">
                      <span className={`font-mono text-sm font-bold ${w.attendance_rate >= 60 ? "text-emerald-400" : w.attendance_rate >= 30 ? "text-amber-400" : "text-gray-600"}`}>
                        {w.attendee_count}/{w.registrant_count} · {w.attendance_rate}%
                      </span>
                    </div>
                    <div className="md:col-span-1 md:text-right mt-1 md:mt-0 flex items-center justify-end gap-2">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide ${w.status === "completed" ? "bg-gray-200 text-gray-500" : "bg-white/15 text-white"}`}>
                        {w.status}
                      </span>
                      <button
                        onClick={e => { e.preventDefault(); e.stopPropagation(); setDeleteTarget({ id: w.id, title: w.title }); }}
                        data-testid={`delete-${w.id}`}
                        className="w-6 h-6 rounded-lg flex items-center justify-center text-gray-700 hover:text-red-400 hover:bg-red-500/15 transition-all opacity-0 group-hover:opacity-100"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </Link>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </motion.div>

        </> }

        {/* Registrants Tab */}
        {dashTab === "registrants" && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl overflow-hidden" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }}>
            {/* Stats bar */}
            <div className="grid grid-cols-3 gap-px" style={{ background: "var(--border)" }}>
              {[
                ["Total Registered", registrants.length],
                ["Attended", registrants.filter(r => r.attended).length],
                ["Attendance Rate", registrants.length ? Math.round(registrants.filter(r=>r.attended).length/registrants.length*100)+"%" : "—"]
              ].map(([label, val]) => (
                <div key={label} className="px-5 py-4" style={{ background: "var(--bg-surface)" }}>
                  <div className="text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>{label}</div>
                  <div className="text-2xl font-bold" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>{val}</div>
                </div>
              ))}
            </div>
            {/* Table header */}
            <div className="hidden md:grid grid-cols-12 gap-2 px-5 py-3 border-b" style={{ borderColor: "var(--border)" }}>
              {["Name","Email","Webinar","Source","Attended","Community"].map((h,i) => (
                <div key={h} className={`${i===0?"col-span-2":i===1?"col-span-3":i===2?"col-span-3":"col-span-1 text-right"} text-[10px] font-bold uppercase tracking-wider`} style={{ color: "var(--text-muted)" }}>{h}</div>
              ))}
            </div>
            {registrants.length === 0 && (
              <div className="p-12 text-center text-sm" style={{ color: "var(--text-muted)" }}>No registrants yet — share your public registration link.</div>
            )}
            {registrants.map((r, i) => (
              <div key={r.id || i} className="hidden md:grid grid-cols-12 gap-2 px-5 py-3.5 border-b text-sm items-center hover:bg-white/[0.02] transition-colors" style={{ borderColor: "var(--border)" }}>
                <div className="col-span-2 font-medium truncate" style={{ color: "var(--text-primary)" }}>{r.name}</div>
                <div className="col-span-3 font-mono text-xs truncate" style={{ color: "var(--text-muted)" }}>{r.email}</div>
                <div className="col-span-3 text-xs truncate" style={{ color: "var(--text-secondary)" }}>{r.webinar_title}</div>
                <div className="col-span-1 text-right"><span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: "var(--bg-sunken)", color: "var(--text-muted)" }}>{r.source}</span></div>
                <div className="col-span-1 text-right"><span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${r.attended ? "bg-emerald-500/15 text-emerald-500" : "bg-gray-500/10 text-gray-400"}`}>{r.attended ? "✓" : "—"}</span></div>
                <div className="col-span-1 text-right"><span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${r.community_joined ? "bg-white/15 text-white" : "bg-gray-500/10 text-gray-400"}`}>{r.community_joined ? "✓" : "—"}</span></div>
              </div>
            ))}
            {/* Mobile registrant cards */}
            <div className="md:hidden divide-y" style={{ borderColor: "var(--border)" }}>
              {registrants.map((r, i) => (
                <div key={r.id || i} className="px-4 py-3">
                  <div className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>{r.name}</div>
                  <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{r.email}</div>
                  <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>{r.webinar_title}</div>
                  <div className="flex gap-2 mt-2">
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${r.attended ? "bg-emerald-500/15 text-emerald-500" : "bg-gray-500/10 text-gray-400"}`}>{r.attended ? "Attended" : "No show"}</span>
                    {r.community_joined && <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-white/15 text-white">Community ✓</span>}
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}

      <CreateWebinarDialog open={open} onClose={() => setOpen(false)} onCreated={(id) => { setOpen(false); load(); nav(`/app/webinars/${id}`); }} />
      <FetchWebinarDialog open={fetchOpen} onClose={() => setFetchOpen(false)} onCreated={load} />
      <OnboardingTour />

      {/* Delete confirm modal */}
      <AnimatePresence>
        {deleteTarget && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setDeleteTarget(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.93, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.93, y: 10 }}
              transition={{ duration: 0.2 }}
              className="rounded-2xl p-6 w-full max-w-md" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", boxShadow: "var(--shadow-lg)" }}
              onClick={e => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <div className="w-10 h-10 rounded-xl bg-red-500/15 flex items-center justify-center">
                  <Trash2 size={18} className="text-red-400" />
                </div>
                <button onClick={() => setDeleteTarget(null)} className="text-gray-600 hover:text-gray-300 transition-colors">
                  <X size={18} />
                </button>
              </div>
              <h3 className="text-lg font-bold mb-1" style={{ color: "var(--text-primary)", fontFamily: "Outfit" }}>Delete webinar?</h3>
              <p className="text-sm mb-1" style={{ color: "var(--text-secondary)" }}>
                <span className="text-gray-300 font-medium">"{deleteTarget.title}"</span> and all its touches and registrants will be permanently deleted.
              </p>
              <p className="text-xs text-red-400/80 mb-6">This action cannot be undone.</p>
              <div className="flex gap-3">
                <button onClick={() => setDeleteTarget(null)}
                  className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors" style={{ color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
                  Cancel
                </button>
                <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                  onClick={handleDelete} disabled={deleting}
                  className="flex-1 px-4 py-2.5 rounded-xl text-sm font-bold text-white bg-red-600 hover:bg-red-500 disabled:opacity-50 transition-colors flex items-center justify-center gap-2">
                  {deleting ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <Trash2 size={14} />}
                  {deleting ? "Deleting…" : "Yes, delete"}
                </motion.button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
    </div>
  );
}

function KPI({ label, value, icon: Icon, highlight, isDark }) {
  return (
    <motion.div
      variants={fadeUp}
      whileHover={{ y: -3, transition: { duration: 0.2 } }}
      className="relative rounded-2xl p-5 overflow-hidden"
      style={{
        background: highlight ? "rgba(234,88,12,0.08)" : "var(--bg-surface)",
        border: highlight ? "1px solid rgba(234,88,12,0.25)" : "1px solid var(--border)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {highlight && (
        <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
      )}
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>{label}</div>
        <div className="w-8 h-8 rounded-lg flex items-center justify-center"
          style={{ background: highlight ? "rgba(234,88,12,0.15)" : "var(--bg-sunken)" }}>
          <Icon size={14} style={{ color: highlight ? "#FFFFFF" : "var(--text-muted)" }} />
        </div>
      </div>
      <div className="text-3xl font-bold tracking-tight" style={{ fontFamily: "Outfit", color: highlight ? "#FFFFFF" : "var(--text-primary)" }}>
        {value}
      </div>
    </motion.div>
  );
}
