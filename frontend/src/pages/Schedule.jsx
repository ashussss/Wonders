import { useEffect, useState, useMemo } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Clock, Send } from "@/components/Icons";
import { motion, AnimatePresence } from "framer-motion";
import { api, fmtDate, CHANNEL_META } from "@/lib/api";
import { Link } from "react-router-dom";
import { toast } from "sonner";

const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const DAYS = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

const STATUS_STYLE = {
  approved:  { dot: "bg-emerald-400", text: "text-emerald-400", bg: "bg-emerald-500/20" },
  pending:   { dot: "bg-amber-400",   text: "text-amber-400",   bg: "bg-amber-500/20"   },
  rejected:  { dot: "bg-red-400",     text: "text-red-400",     bg: "bg-red-500/20"     },
  queued:    { dot: "bg-blue-400",    text: "text-blue-400",    bg: "bg-blue-500/20"    },
};

const card = { border: "1px solid var(--border)", background: "var(--bg-surface)" };
const border = { borderBottom: "1px solid var(--border)" };

export default function Schedule() {
  const [touches, setTouches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [today] = useState(new Date());
  const [cursor, setCursor] = useState({ year: today.getFullYear(), month: today.getMonth() });
  const [selected, setSelected] = useState(null);
  const [sending, setSending] = useState(null);

  const load = () => api.get("/schedule").then(r => { setTouches(r.data); setLoading(false); });
  useEffect(() => { load(); }, []);

  const byDate = useMemo(() => {
    const map = {};
    touches.forEach(t => {
      if (!t.scheduled_at) return;
      const d = t.scheduled_at.slice(0, 10);
      if (!map[d]) map[d] = [];
      map[d].push(t);
    });
    return map;
  }, [touches]);

  const unscheduled = useMemo(() => touches.filter(t => !t.scheduled_at), [touches]);

  const { year, month } = cursor;
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  const todayStr = today.toISOString().slice(0, 10);
  const selectedTouches = selected ? (byDate[selected] || []) : [];

  const sendNow = async (tid) => {
    setSending(tid);
    try {
      const r = await api.post(`/touches/${tid}/send-now`);
      toast[r.data.ok ? "success" : "error"](r.data.ok ? "Delivered!" : "Delivery failed — check Settings");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    } finally { setSending(null); }
  };

  const prev = () => setCursor(c => { const d = new Date(c.year, c.month - 1); return { year: d.getFullYear(), month: d.getMonth() }; });
  const next = () => setCursor(c => { const d = new Date(c.year, c.month + 1); return { year: d.getFullYear(), month: d.getMonth() }; });

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
      className="min-h-screen p-4 sm:p-8" style={{ background: "var(--bg-base)" }}>
      <div className="max-w-7xl mx-auto">

        <div className="flex items-center gap-2 mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
          <span className="text-[10px] font-bold uppercase tracking-[0.25em] text-white">Schedule</span>
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-1" style={{ fontFamily: 'Outfit', color: "var(--text-primary)" }}>Send Calendar</h1>
        <p className="mb-8 text-sm" style={{ color: "var(--text-muted)" }}>All scheduled touches across your webinars — approve and send from here.</p>

        <div className="grid lg:grid-cols-[1fr_380px] gap-6">

          {/* CalendarDays */}
          <div className="rounded-2xl overflow-hidden" style={card}>
            {/* Month nav */}
            <div className="flex items-center justify-between px-6 py-4" style={border}>
              <button onClick={prev} className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors"
                style={{ background: "var(--bg-sunken)", color: "var(--text-secondary)" }}>
                <ChevronLeft size={16} />
              </button>
              <div className="font-semibold" style={{ fontFamily: 'Outfit', color: "var(--text-primary)" }}>
                {MONTHS[month]} {year}
              </div>
              <button onClick={next} className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors"
                style={{ background: "var(--bg-sunken)", color: "var(--text-secondary)" }}>
                <ChevronRight size={16} />
              </button>
            </div>

            {/* Day headers */}
            <div className="grid grid-cols-7" style={border}>
              {DAYS.map(d => (
                <div key={d} className="text-center text-[10px] font-bold uppercase tracking-[0.15em] py-2.5" style={{ color: "var(--text-muted)" }}>{d}</div>
              ))}
            </div>

            {/* Cells */}
            <div className="grid grid-cols-7">
              {cells.map((day, i) => {
                if (!day) return <div key={`e-${i}`} className="aspect-square" style={{ borderBottom: "1px solid var(--border)", borderRight: "1px solid var(--border)" }} />;
                const dateStr = `${year}-${String(month+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
                const dayTouches = byDate[dateStr] || [];
                const isToday = dateStr === todayStr;
                const isSelected = dateStr === selected;
                const isPast = dateStr < todayStr;
                return (
                  <motion.button key={dateStr} whileHover={{ scale: 0.97 }}
                    onClick={() => setSelected(isSelected ? null : dateStr)}
                    className="aspect-square p-1.5 flex flex-col items-center relative"
                    style={{
                      borderBottom: "1px solid var(--border)", borderRight: "1px solid var(--border)",
                      background: isSelected ? "rgba(234,88,12,0.1)" : "transparent",
                      opacity: isPast ? 0.4 : 1,
                    }}>
                    <span className="text-xs font-bold w-6 h-6 flex items-center justify-center rounded-full mb-1"
                      style={{
                        background: isToday ? "#FFFFFF" : "transparent",
                        color: isToday ? "#000000" : isSelected ? "#FFFFFF" : "var(--text-secondary)",
                      }}>
                      {day}
                    </span>
                    {dayTouches.length > 0 && (
                      <div className="flex flex-wrap gap-0.5 justify-center">
                        {dayTouches.slice(0, 3).map((t, ti) => {
                          const st = STATUS_STYLE[t.approval_status] || STATUS_STYLE.pending;
                          return <span key={ti} className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />;
                        })}
                        {dayTouches.length > 3 && <span className="text-[8px]" style={{ color: "var(--text-muted)" }}>+{dayTouches.length - 3}</span>}
                      </div>
                    )}
                  </motion.button>
                );
              })}
            </div>

            {/* Legend */}
            <div className="flex items-center gap-4 px-6 py-3" style={{ borderTop: "1px solid var(--border)" }}>
              {Object.entries(STATUS_STYLE).map(([k, v]) => (
                <div key={k} className="flex items-center gap-1.5 text-[10px]" style={{ color: "var(--text-muted)" }}>
                  <span className={`w-2 h-2 rounded-full ${v.dot}`} /> {k}
                </div>
              ))}
            </div>
          </div>

          {/* Right panel */}
          <div className="space-y-4">

            {selected && (
              <div className="rounded-2xl overflow-hidden" style={card}>
                <div className="px-5 py-4 flex items-center justify-between" style={border}>
                  <div>
                    <div className="text-xs font-bold uppercase tracking-[0.15em]" style={{ color: "var(--text-muted)" }}>Selected</div>
                    <div className="font-semibold" style={{ fontFamily: 'Outfit', color: "var(--text-primary)" }}>
                      {new Date(selected + 'T12:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}
                    </div>
                  </div>
                  <CalendarDays size={18} style={{ color: "var(--text-muted)" }} />
                </div>
                {selectedTouches.length === 0
                  ? <div className="p-6 text-center text-sm" style={{ color: "var(--text-muted)" }}>No touches scheduled for this day.</div>
                  : <AnimatePresence>{selectedTouches.map(t => <TouchRow key={t.touch_id} t={t} onSend={sendNow} sending={sending} />)}</AnimatePresence>
                }
              </div>
            )}

            <div className="rounded-2xl overflow-hidden" style={card}>
              <div className="px-5 py-4" style={border}>
                <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Upcoming Touches</div>
                <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {touches.filter(t => t.scheduled_at && t.scheduled_at >= todayStr).length} pending
                </div>
              </div>
              {loading && <div className="p-8 flex justify-center"><div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" /></div>}
              {!loading && touches.filter(t => t.scheduled_at).length === 0 && (
                <div className="p-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>No scheduled touches yet.</div>
              )}
              <div className="max-h-[420px] overflow-y-auto">
                {touches.filter(t => t.scheduled_at && t.scheduled_at >= todayStr).slice(0, 20)
                  .map(t => <TouchRow key={t.touch_id} t={t} onSend={sendNow} sending={sending} />)}
              </div>
            </div>

            {unscheduled.length > 0 && (
              <div className="rounded-2xl overflow-hidden" style={card}>
                <div className="px-5 py-4" style={border}>
                  <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>On Registration</div>
                  <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>Triggered automatically when someone registers</div>
                </div>
                {unscheduled.map(t => <TouchRow key={t.touch_id} t={t} onSend={sendNow} sending={sending} />)}
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function TouchRow({ t, onSend, sending }) {
  const st = STATUS_STYLE[t.approval_status] || STATUS_STYLE.pending;
  return (
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
      className="px-5 py-3.5 transition-colors hover:bg-white/[0.02]"
      style={{ borderBottom: "1px solid var(--border)" }}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2.5 min-w-0">
          <div className="w-7 h-7 rounded-lg bg-white text-black font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">
            {t.touch_num}
          </div>
          <div className="min-w-0">
            <Link to={`/app/webinars/${t.webinar_id}`} className="text-xs font-semibold text-orange-500 hover:text-orange-400 truncate block transition-colors">
              {t.webinar_title}
            </Link>
            <div className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>{t.touch_name}</div>
            <div className="flex items-center gap-1.5 mt-1">
              <Clock size={10} style={{ color: "var(--text-muted)" }} />
              <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                {t.scheduled_at ? fmtDate(t.scheduled_at) : "On registration"}
              </span>
            </div>
            <div className="flex flex-wrap gap-1 mt-1.5">
              {(t.channels || []).slice(0, 4).map(ch => (
                <span key={ch} className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: "var(--bg-sunken)", color: "var(--text-muted)" }}>
                  {CHANNEL_META[ch]?.label || ch}
                </span>
              ))}
            </div>
          </div>
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          <span className={`text-[9px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${st.bg} ${st.text}`}>
            {t.approval_status}
          </span>
          {t.approval_status === "approved" && (
            <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
              onClick={() => onSend(t.touch_id)} disabled={sending === t.touch_id}
              className="text-[10px] px-2.5 py-1 bg-orange-600 hover:bg-orange-500 text-white font-bold rounded-lg flex items-center gap-1 disabled:opacity-50 transition-colors">
              {sending === t.touch_id ? <span className="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin" /> : <Send size={9} />}
              {sending === t.touch_id ? "..." : "Send"}
            </motion.button>
          )}
          {t.approval_status === "pending" && (
            <Link to={`/app/webinars/${t.webinar_id}`} className="text-[10px] px-2.5 py-1 rounded-lg text-amber-400 hover:bg-amber-500/10 transition-colors" style={{ border: "1px solid rgba(245,158,11,0.3)" }}>
              Review
            </Link>
          )}
        </div>
      </div>
    </motion.div>
  );
}
