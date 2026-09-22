import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, Mail, RefreshCcw, TrendingUp, User } from "@/components/Icons";
import { motion } from "framer-motion";
import { api, fmtDate } from "@/lib/api";
import { useTheme } from "@/lib/theme";
import { Link } from "react-router-dom";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

const BENCHMARKS = {
  open_rate:    { good: 35, ok: 20, label: "Open Rate",     icon: Mail,         color: "#8B5CF6" },
  click_rate:   { good: 5,  ok: 2,  label: "Click Rate",    icon: ArrowRight, color: "#06B6D4" },
  delivery_rate:{ good: 98, ok: 90, label: "Delivery Rate", icon: CheckCircle2,  color: "#10B981" },
  bounce_rate:  { good: 1,  ok: 3,  label: "Bounce Rate",   icon: AlertTriangle,color: "#F59E0B", invert: true },
  unsub_rate:   { good: 0.2,ok: 0.5,label: "Unsub Rate",    icon: User,    color: "#EF4444", invert: true }};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl px-3 py-2.5 text-xs shadow-xl"
      style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)" }}>
      <div className="font-semibold mb-1.5" style={{ color: "var(--text-secondary)" }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span style={{ color: "var(--text-secondary)" }}>{p.name}:</span>
          <span className="font-bold" style={{ color: "var(--text-primary)" }}>{p.value}</span>
        </div>
      ))}
    </div>
  );
};

export default function EmailAnalytics() {
  const { isDark } = useTheme();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [chartMetric, setChartMetric] = useState("opens");

  const load = async (refresh = false) => {
    if (refresh) setRefreshing(true);
    try {
      const r = await api.get("/email-analytics");
      setData(r.data);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, []);

  const getStatus = (key, value) => {
    const b = BENCHMARKS[key];
    if (!b) return "neutral";
    if (b.invert) return value <= b.good ? "good" : value <= b.ok ? "ok" : "bad";
    return value >= b.good ? "good" : value >= b.ok ? "ok" : "bad";
  };

  const statusColors = {
    good: { bg: "rgba(16,185,129,0.1)", text: "#10B981", label: "Great" },
    ok:   { bg: "rgba(245,158,11,0.1)", text: "#F59E0B", label: "OK" },
    bad:  { bg: "rgba(239,68,68,0.1)",  text: "#EF4444", label: "Low" },
    neutral: { bg: "var(--bg-sunken)", text: "var(--text-muted)", label: "—" }};

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
      className="min-h-screen p-4 sm:p-8" style={{ background: "var(--bg-base)" }}>
      <div className="max-w-7xl mx-auto">

        {/* Header */}
        <div className="flex items-center gap-2 mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
          <span className="text-[10px] font-bold uppercase tracking-[0.25em] text-white">Email</span>
        </div>
        <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
          <div>
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
              Email Analytics
            </h1>
            <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
              Open rate · Click rate · Bounce · Unsubscribes — last 30 days via Brevo.
            </p>
          </div>
          <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
            onClick={() => load(true)} disabled={refreshing}
            className="flex items-center gap-2 text-sm font-semibold px-4 py-2 rounded-xl transition-all disabled:opacity-50"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
            <RefreshCcw size={14} className={refreshing ? "animate-spin" : ""} />
            {refreshing ? "Refreshing…" : "Refresh"}
          </motion.button>
        </div>

        {/* No Brevo configured */}
        {!loading && data?.error === "Brevo not configured" && (
          <div className="rounded-2xl p-8 text-center" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
            <Mail size={32} className="text-white mx-auto mb-3" />
            <div className="font-semibold text-lg mb-1" style={{ color: "var(--text-primary)" }}>Brevo not connected</div>
            <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>Add your Brevo API key in Settings to see email analytics.</p>
            <Link to="/app/settings" className="inline-flex items-center gap-2 bg-white hover:bg-gray-100 text-black text-sm font-semibold px-4 py-2 rounded-xl transition-colors">
              Go to Settings <Link size={13} />
            </Link>
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center py-24">
            <div className="w-7 h-7 border-2 border-white border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {!loading && data && !data.error && (
          <>
            {/* KPI Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 sm:gap-4 mb-6">
              {Object.entries(BENCHMARKS).map(([key, b], i) => {
                const value = data.rates?.[key] ?? 0;
                const status = getStatus(key, value);
                const sc = statusColors[status];
                return (
                  <motion.div key={key}
                    initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.08 }}
                    whileHover={{ y: -2 }}
                    className="rounded-2xl p-5 relative overflow-hidden"
                    style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }}>
                    <div className="flex items-center justify-between mb-3">
                      <div className="text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>{b.label}</div>
                      <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: `${b.color}18` }}>
                        <b.icon size={13} style={{ color: b.color }} />
                      </div>
                    </div>
                    <div className="text-3xl font-bold mb-2" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
                      {value}%
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full" style={{ background: sc.bg, color: sc.text }}>
                        {sc.label}
                      </span>
                      <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                        {b.invert ? `≤${b.good}% ideal` : `≥${b.good}% ideal`}
                      </span>
                    </div>
                  </motion.div>
                );
              })}
            </div>

            {/* Raw counts */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
              {[
                ["Sent",        data.stats?.sent,          "#FFFFFF"],
                ["Delivered",   data.stats?.delivered,     "#10B981"],
                ["Hard Bounces",data.stats?.hard_bounces,  "#EF4444"],
                ["Spam Reports",data.stats?.spam,          "#F59E0B"],
              ].map(([label, val, color]) => (
                <div key={label} className="rounded-xl p-4"
                  style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
                  <div className="text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>{label}</div>
                  <div className="text-2xl font-bold" style={{ fontFamily: "Outfit", color }}>{val ?? 0}</div>
                </div>
              ))}
            </div>

            {/* Chart */}
            {data.daily?.length > 0 && (
              <div className="rounded-2xl p-5 mb-6" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }}>
                <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
                  <div className="font-semibold" style={{ color: "var(--text-primary)" }}>30-day trend</div>
                  <div className="flex gap-1.5">
                    {[["opens","Opens","#8B5CF6"],["clicks","Clicks","#06B6D4"],["bounces","Bounces","#F59E0B"]].map(([k, l, col]) => (
                      <button key={k} onClick={() => setChartMetric(k)}
                        className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-lg transition-all"
                        style={{
                          background: chartMetric === k ? `${col}20` : "var(--bg-sunken)",
                          color: chartMetric === k ? col : "var(--text-muted)",
                          border: `1px solid ${chartMetric === k ? `${col}40` : "transparent"}`}}>
                        {l}
                      </button>
                    ))}
                  </div>
                </div>
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={data.daily} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.05)"} />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--text-muted)" }} tickLine={false} axisLine={false}
                      tickFormatter={d => d?.slice(5)} />
                    <YAxis tick={{ fontSize: 10, fill: "var(--text-muted)" }} tickLine={false} axisLine={false} />
                    <Tooltip content={<CustomTooltip />} />
                    <Line type="monotone" dataKey={chartMetric}
                      stroke={chartMetric === "opens" ? "#8B5CF6" : chartMetric === "clicks" ? "#06B6D4" : "#F59E0B"}
                      strokeWidth={2.5} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Benchmarks table */}
            <div className="rounded-2xl p-5 mb-6" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
              <div className="font-semibold mb-4" style={{ color: "var(--text-primary)" }}>How you compare</div>
              <div className="space-y-3">
                {[
                  ["Open Rate",     data.rates?.open_rate,    "Industry avg 21%", "38-41% achievable"],
                  ["Click Rate",    data.rates?.click_rate,   "Industry avg 2.3%","5%+ is excellent"],
                  ["Bounce Rate",   data.rates?.bounce_rate,  "Keep below 2%",    "Hard bounces hurt sender rep"],
                  ["Unsub Rate",    data.rates?.unsub_rate,   "Keep below 0.5%",  "High = bad list hygiene"],
                  ["Delivery Rate", data.rates?.delivery_rate,"Target 98%+",      "Below 90% = inbox issues"],
                ].map(([label, value, bench, tip]) => {
                  const key = label.toLowerCase().replace(" ", "_");
                  const status = getStatus(key + "_rate" in data.rates ? key + "_rate" : key, value);
                  const sc = statusColors[status];
                  const pct = Math.min((value || 0) / (label.includes("Bounce") || label.includes("Unsub") ? 5 : 100) * 100, 100);
                  return (
                    <div key={label}>
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{label}</span>
                          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold" style={{ background: sc.bg, color: sc.text }}>{sc.label}</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{bench}</span>
                          <span className="font-bold text-sm" style={{ color: "var(--text-primary)", fontFamily: "Outfit" }}>{value ?? 0}%</span>
                        </div>
                      </div>
                      <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--bg-sunken)" }}>
                        <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.8, ease: "easeOut" }}
                          className="h-full rounded-full" style={{ background: sc.text }} />
                      </div>
                      <div className="text-[10px] mt-1" style={{ color: "var(--text-muted)" }}>{tip}</div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Per-touch breakdown */}
            {data.touches?.length > 0 && (
              <div className="rounded-2xl overflow-hidden" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
                <div className="px-5 py-4 border-b font-semibold" style={{ borderColor: "var(--border)", color: "var(--text-primary)" }}>
                  Sent touches
                </div>
                {data.touches.map((t, i) => (
                  <div key={t.touch_id} className="px-5 py-4 border-b flex flex-wrap items-center gap-3 hover:bg-white/[0.02] transition-colors"
                    style={{ borderColor: "var(--border)" }}>
                    <div className="w-7 h-7 rounded-lg bg-orange-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">
                      {t.touch_num}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>{t.touch_name}</div>
                      <Link to={`/app/webinars/${t.webinar_id}`}
                        className="text-[10px] hover:text-orange-500 transition-colors truncate block" style={{ color: "var(--text-muted)" }}>
                        {t.webinar_title}
                      </Link>
                    </div>
                    <div className="flex gap-2 flex-wrap">
                      {t.delivery_log?.filter(l => l.channel === "email").map((log, li) => (
                        <span key={li} className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${log.ok ? "bg-emerald-500/10 text-emerald-500" : "bg-red-500/10 text-red-400"}`}>
                          {log.ok ? `✓ ${log.recipient?.split("@")[0] || "sent"}` : `✗ ${log.detail?.slice(0, 30)}`}
                        </span>
                      ))}
                    </div>
                    <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                      {t.sent_at?.slice(0, 10)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </motion.div>
  );
}
