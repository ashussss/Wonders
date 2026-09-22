import { useEffect, useState } from "react";
import { BarChart3, CalendarDays, Target, TrendingUp, User, Users } from "@/components/Icons";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { BarChart as ReBarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, LineChart, Line, CartesianGrid } from "recharts";
import { useTheme } from "@/lib/theme";

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-xl px-3 py-2 text-xs" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", boxShadow: "var(--shadow-md)" }}>
        <div className="mb-1" style={{ color: "var(--text-secondary)" }}>{label}</div>
        <div className="font-bold" style={{ color: "var(--text-primary)" }}>{payload[0].value}{payload[0].unit || "%"}</div>
      </div>
    );
  }
  return null;
};

export default function Analytics() {
  const { isDark } = useTheme();
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/analytics/overview").then(r => setData(r.data)); }, []);

  if (!data) return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg-base)" }}>
      <div className="w-7 h-7 border-2 border-white border-t-transparent rounded-full animate-spin" />
    </div>
  );

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
      className="min-h-screen p-4 sm:p-8" style={{ background: "var(--bg-base)" }}>
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center gap-2 mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
          <span className="text-[10px] font-bold uppercase tracking-[0.25em] text-white">Analytics</span>
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-1" style={{ fontFamily: 'Outfit', color: "var(--text-primary)" }}>Performance</h1>
        <p className="mb-8 text-sm" style={{ color: "var(--text-muted)" }}>Attendance rate by channel — the metric that actually matters.</p>

        {/* KPI Row */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4 mb-8">
          <KPI label="Overall Attendance" value={`${data.overall_rate}%`} highlight icon={TrendingUp} />
          <KPI label="Total Webinars" value={data.total_webinars} icon={CalendarDays} />
          <KPI label="Registrants" value={data.total_registrants} icon={Users} />
          <KPI label="Attendees" value={data.total_attendees} icon={Target} />
          <KPI label="Community Joined" value={data.community_joined_total ?? 0} icon={User} highlight={data.community_joined_total > 0} />
        </div>

        {/* Charts */}
        <div className="grid lg:grid-cols-2 gap-5 mb-6">
          <ChartCard title="Attendance by Channel" subtitle="Which source actually shows up?" testId="chart-by-channel">
            {data.by_channel.length === 0 ? <Empty /> : (
              <ResponsiveContainer width="100%" height={240}>
                <ReBarChart data={data.by_channel} margin={{ top: 10, right: 10, left: -10, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                  <XAxis dataKey="channel" stroke="#4B5563" fontSize={11} tick={{ fill: '#6B7280' }} />
                  <YAxis stroke="#4B5563" fontSize={11} unit="%" tick={{ fill: '#6B7280' }} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="attendance_rate" fill="#FFFFFF" radius={[6, 6, 0, 0]} />
                </ReBarChart>
              </ResponsiveContainer>
            )}
          </ChartCard>
          <ChartCard title="Attendance Trend" subtitle="Across past webinars" testId="chart-trend">
            {data.per_webinar.filter(w => w.registrants > 0).length === 0 ? <Empty /> : (
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={[...data.per_webinar].reverse()} margin={{ top: 10, right: 10, left: -10, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                  <XAxis dataKey="title" stroke="#4B5563" fontSize={10} angle={-12} textAnchor="end" height={45} tick={{ fill: '#6B7280' }} />
                  <YAxis stroke="#4B5563" fontSize={11} unit="%" tick={{ fill: '#6B7280' }} />
                  <Tooltip content={<CustomTooltip />} />
                  <Line type="monotone" dataKey="rate" stroke="#FFFFFF" strokeWidth={2.5} dot={{ fill: '#FFFFFF', r: 4, strokeWidth: 0 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </ChartCard>
        </div>

        {/* Channel breakdown table */}
        <div className="rounded-2xl overflow-hidden mb-5" style={{ border: "1px solid var(--border)", background: "var(--bg-surface)" }} data-testid="channels-table">
          <div className="px-5 py-4 border-b border-white/[0.06]">
            <div className="text-sm font-semibold text-white">Channel Performance</div>
          </div>
          <div className="hidden md:grid grid-cols-12 px-5 py-3 text-[10px] font-bold uppercase tracking-[0.18em]" style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>
            <div className="col-span-5">Channel</div>
            <div className="col-span-2 text-right">Registrants</div>
            <div className="col-span-2 text-right">Attendees</div>
            <div className="col-span-3 text-right">Attendance Rate</div>
          </div>
          {data.by_channel.length === 0 && <div className="p-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>No attendance data yet.</div>}
          {data.by_channel.map(c => (
            <div key={c.channel} className="grid grid-cols-12 px-5 py-3.5 text-sm transition-colors" style={{ borderBottom: "1px solid var(--border)" }} onMouseEnter={e=>e.currentTarget.style.background="var(--bg-sunken)"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
              <div className="col-span-5 font-medium" style={{ color: "var(--text-primary)" }}>{c.channel}</div>
              <div className="col-span-2 text-right font-mono text-gray-500">{c.registrants}</div>
              <div className="col-span-2 text-right font-mono text-gray-500">{c.attendees}</div>
              <div className="col-span-3 text-right">
                <span className={`font-mono font-bold ${c.attendance_rate >= 60 ? "text-emerald-400" : c.attendance_rate >= 30 ? "text-amber-400" : "text-gray-600"}`}>
                  {c.attendance_rate}%
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Per-webinar table */}
        <div className="rounded-2xl overflow-hidden mb-5" style={{ border: "1px solid var(--border)", background: "var(--bg-surface)" }} data-testid="community-table">
          <div className="px-5 py-4 border-b border-white/[0.06]">
            <div className="text-sm font-semibold text-white">Community Joins per Webinar</div>
          </div>
          {(!data.community_per_webinar || data.community_per_webinar.length === 0) && (
            <div className="p-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>No data yet.</div>
          )}
          {(data.community_per_webinar || []).map(c => (
            <div key={c.id} className="grid grid-cols-12 px-5 py-3.5 text-sm transition-colors" style={{ borderBottom: "1px solid var(--border)" }} onMouseEnter={e=>e.currentTarget.style.background="var(--bg-sunken)"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
              <div className="col-span-9 font-medium" style={{ color: "var(--text-primary)" }}>{c.title}</div>
              <div className="col-span-3 text-right">
                <span className="font-mono font-bold text-white">{c.community_joined}</span>
                <span className="text-xs text-gray-600 ml-1">joins</span>
              </div>
            </div>
          ))}
        </div>

        {/* Webinar-by-webinar */}
        <div className="rounded-2xl overflow-hidden" style={{ border: "1px solid var(--border)", background: "var(--bg-surface)" }}>
          <div className="px-5 py-4 border-b border-white/[0.06]">
            <div className="text-sm font-semibold text-white">Webinar by Webinar</div>
          </div>
          {data.per_webinar.length === 0 && <div className="p-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>No webinars yet.</div>}
          {data.per_webinar.map(w => (
            <div key={w.id} className="grid grid-cols-12 px-5 py-3.5 text-sm transition-colors" style={{ borderBottom: "1px solid var(--border)" }} onMouseEnter={e=>e.currentTarget.style.background="var(--bg-sunken)"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
              <div className="col-span-6 font-medium" style={{ color: "var(--text-primary)" }}>{w.title}</div>
              <div className="col-span-2 text-right font-mono text-gray-600">{w.registrants} reg.</div>
              <div className="col-span-2 text-right font-mono text-gray-600">{w.attendees} att.</div>
              <div className="col-span-2 text-right">
                <span className={`font-mono font-bold ${w.rate >= 60 ? "text-emerald-400" : w.rate >= 30 ? "text-amber-400" : "text-gray-600"}`}>{w.rate}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

function KPI({ label, value, icon: Icon, highlight }) {
  return (
    <motion.div whileHover={{ y: -2 }} transition={{ duration: 0.2 }}
      className="rounded-2xl p-5" style={highlight ? { background: "rgba(234,88,12,0.08)", border: "1px solid rgba(234,88,12,0.3)" } : { background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>{label}</div>
        <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: highlight ? "rgba(234,88,12,0.2)" : "var(--bg-sunken)" }}>
          <Icon size={14} style={{ color: highlight ? "#FFFFFF" : "var(--text-muted)" }} />
        </div>
      </div>
      <div className="text-3xl font-bold tracking-tight" style={{ fontFamily: 'Outfit', color: highlight ? "#FFFFFF" : "var(--text-primary)" }}>{value}</div>
    </motion.div>
  );
}

function ChartCard({ title, subtitle, children, testId }) {
  return (
    <div className="rounded-2xl p-5" style={{ border: "1px solid var(--border)", background: "var(--bg-surface)" }} data-testid={testId}>
      <div className="text-sm font-semibold mb-0.5" style={{ color: "var(--text-primary)" }}>{title}</div>
      <div className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>{subtitle}</div>
      {children}
    </div>
  );
}

function Empty() {
  return <div className="h-[240px] flex items-center justify-center text-sm" style={{ color: "var(--text-muted)" }}>No data yet</div>;
}
