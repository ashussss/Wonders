import { useEffect, useState } from "react";
import { AlertTriangle, BarChart3, Check, Plus, Shield, Star, Trash2, Users, X, Zap } from "@/components/Icons";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { useTheme } from "@/lib/theme";
import { useAuth } from "@/lib/auth";
import { Navigate } from "react-router-dom";
import { toast } from "sonner";

const ROLE_STYLE = {
  superadmin: { label: "Superadmin", color: "bg-white/20 text-white" },
  admin:      { label: "Admin",      color: "bg-purple-500/20 text-purple-400" },
  moderator:  { label: "Moderator",  color: "bg-blue-500/20 text-blue-400" },
  user:       { label: "User",       color: "bg-gray-500/20 text-gray-400" },
};

export default function AdminDashboard() {
  const { user } = useAuth();
  const { isDark } = useTheme();
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [tab, setTab] = useState("overview");
  const [waitlist, setWaitlist] = useState([]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteData, setInviteData] = useState({ name: "", email: "", role: "moderator", password: "" });
  const [inviting, setInviting] = useState(false);
  const [newCreds, setNewCreds] = useState(null);

  if (!user || !["admin","superadmin"].includes(user.role)) {
    return <Navigate to="/app" replace />;
  }

  const load = async () => {
    const [sr, ur, wr] = await Promise.all([
      api.get("/auth/admin/stats"),
      api.get("/auth/admin/users"),
      api.get("/auth/admin/waitlist").catch(() => ({ data: [] })),
    ]);
    setStats(sr.data);
    setUsers(ur.data);
    setWaitlist(wr.data || []);
    setLoading(false);
    setLoaded(true);
  };
  useEffect(() => { load(); }, []);

  const setRole = async (uid, role) => {
    await api.patch(`/auth/admin/users/${uid}/role`, { role });
    toast.success(`Role updated to ${role}`);
    load();
  };

  const deleteUser = async (uid, email) => {
    if (!confirm(`Delete ${email}? This will delete all their webinars and data.`)) return;
    await api.delete(`/auth/admin/users/${uid}`);
    toast.success("User deleted");
    load();
  };

  const invite = async () => {
    if (!inviteData.email) return toast.error("Email required");
    setInviting(true);
    try {
      const r = await api.post("/auth/admin/invite", inviteData);
      setNewCreds(r.data);
      toast.success(`${r.data.role} account created`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Invite failed");
    } finally {
      setInviting(false);
    }
  };

  // CSS-variable helpers — used as inline style objects or className strings
  const bg   = "min-h-screen p-4 sm:p-8";
  const bgStyle = { background: "var(--bg-base)" };
  const card = "rounded-2xl border overflow-hidden";
  const cardStyle = { background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" };
  const divBorder = { borderColor: "var(--border)" };

  const KPI = ({ label, value, icon: Icon, highlight }) => (
    <div className="rounded-2xl p-5"
      style={highlight
        ? { background: "rgba(234,88,12,0.08)", border: "1px solid rgba(234,88,12,0.3)" }
        : { background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>{label}</div>
        <div className="w-8 h-8 rounded-lg flex items-center justify-center"
          style={{ background: highlight ? "rgba(234,88,12,0.2)" : "var(--bg-sunken)" }}>
          <Icon size={14} style={{ color: highlight ? "#FFFFFF" : "var(--text-muted)" }} />
        </div>
      </div>
      <div className="text-3xl font-bold" style={{ fontFamily: "Outfit", color: highlight ? "#FFFFFF" : "var(--text-primary)" }}>{value ?? "—"}</div>
    </div>
  );

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className="min-h-screen p-4 sm:p-8" style={{ background: "var(--bg-base)" }}>
      <div className="max-w-7xl mx-auto">

        {/* Header */}
        <div className="flex items-center gap-2 mb-2">
          <Star size={14} className="text-white" />
          <span className="text-[10px] font-bold uppercase tracking-[0.25em] text-white">Admin</span>
        </div>
        <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
          <div>
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight" style={{ color: "var(--text-primary)" }} style={{ fontFamily: "Outfit" }}>
              Admin Dashboard
            </h1>
            <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>Platform overview, user management, team roles.</p>
          </div>
          <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
            onClick={() => setInviteOpen(true)}
            className="bg-white hover:bg-gray-100 text-black font-semibold px-4 py-2.5 rounded-xl flex items-center gap-2 text-sm transition-colors">
            <Plus size={16} /> Invite Team Member
          </motion.button>
        </div>

        {/* Tabs */}
        <div className={`border-b mb-7 flex gap-6`} style={divBorder}>
          {[["overview","Overview"], ["users","Users"], ["webinars","Recent Webinars"], ["waitlist","Waitlist"]].map(([k, l]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`pb-3 -mb-px text-sm font-semibold border-b-2 transition-all ${tab === k ? "border-white text-white" : isDark ? "border-transparent text-gray-600 hover:text-gray-300" : "border-transparent text-gray-400 hover:text-gray-700"}`}>
              {l}
            </button>
          ))}
        </div>

        {loading && !loaded && (
          <div className="flex items-center justify-center py-24">
            <div className="w-7 h-7 border-2 border-white border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {!loading && tab === "overview" && stats && (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
              <KPI label="Total Users" value={stats.stats.total_users} icon={Users} />
              <KPI label="Total Webinars" value={stats.stats.total_webinars} icon={Zap} />
              <KPI label="Total Registrants" value={stats.stats.total_registrants} icon={Users} />
              <KPI label="Total Touches" value={stats.stats.total_touches} icon={BarChart3} />
              <KPI label="Sent Touches" value={stats.stats.sent_touches} icon={Check} />
              <KPI label="Approval Rate" value={`${stats.stats.approval_rate}%`} icon={Shield} highlight />
            </div>
            <div className="rounded-2xl border p-5" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }}>
              <div className="text-sm font-semibold mb-4" style={{ color: "var(--text-primary)" }}>Top Users by Webinars</div>
              {stats.webinars_per_user.map((u, i) => (
                <div key={u._id} className={`flex items-center justify-between py-2.5 border-b text-sm`} style={divBorder}>
                  <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>{u._id?.slice(0, 12)}…</span>
                  <span className="font-bold" style={{ color: "var(--text-primary)" }}>{u.count} webinars</span>
                </div>
              ))}
            </div>
          </>
        )}

        {!loading && tab === "users" && (
          <div className="rounded-2xl border overflow-hidden" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }}>
            <div className="hidden md:grid grid-cols-12 px-5 py-3 border-b text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }} style={divBorder}>
              <div className="col-span-3">Name</div>
              <div className="col-span-2">Email</div>
              <div className="col-span-1 text-right">Joined</div>
              <div className="col-span-2">Role</div>
              <div className="col-span-1 text-right">Webinars</div>
              <div className="col-span-1 text-right">Registrants</div>
              <div className="col-span-2 text-right">Actions</div>
            </div>
            {users.map(u => {
              const rs = ROLE_STYLE[u.role || "user"];
              const isSelf = u.id === user.id;
              return (
                <div key={u.id} className={`grid grid-cols-12 px-5 py-3.5 border-b text-sm items-center transition-colors ${"hover:bg-white/[0.02] transition-colors"}`} style={divBorder}>
                  <div className="col-span-3 font-medium truncate" style={{ color: "var(--text-primary)" }}>{u.name || "—"}</div>
                  <div className="col-span-2 font-mono text-xs truncate" style={{ color: "var(--text-muted)" }}>{u.email}</div>
                  <div className="col-span-1 text-right text-xs" style={{ color: "var(--text-muted)" }}>{u.created_at?.slice(0,10) || "—"}</div>
                  <div className="col-span-2">
                    <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${rs.color}`}>
                      {rs.label}
                    </span>
                  </div>
                  <div className="col-span-1 text-right font-mono" style={{ color: "var(--text-muted)" }}>{u.webinar_count}</div>
                  <div className="col-span-1 text-right font-mono" style={{ color: "var(--text-muted)" }}>{u.registrant_count}</div>
                  <div className="col-span-2 flex items-center justify-end gap-1.5">
                    {!isSelf && u.role !== "superadmin" && (
                      <>
                        <select value={u.role || "user"}
                          onChange={e => setRole(u.id, e.target.value)}
                          className="text-[10px] px-1.5 py-1 rounded-lg border rounded-lg transition-colors" style={{ background: "var(--bg-sunken)", border: "1px solid var(--border)", color: "var(--text-primary)" }}>
                          <option value="user">User</option>
                          <option value="moderator">Moderator</option>
                          <option value="admin">Admin</option>
                        </select>
                        <button onClick={() => deleteUser(u.id, u.email)}
                          className="w-6 h-6 rounded-lg text-gray-600 hover:text-red-400 hover:bg-red-500/10 flex items-center justify-center transition-colors">
                          <Trash2 size={11} />
                        </button>
                      </>
                    )}
                    {isSelf && <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>You</span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {!loading && tab === "waitlist" && (
          <div className="rounded-2xl overflow-hidden" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
            <div className="px-5 py-3 flex items-center justify-between" style={{ borderBottom: "1px solid var(--border)" }}>
              <div className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>Waitlist</div>
              <div className="text-xs font-bold px-2 py-0.5 rounded-full bg-white/15 text-white">{waitlist.length} signups</div>
            </div>
            <div className="hidden md:grid grid-cols-12 px-5 py-3 text-[10px] font-bold uppercase tracking-widest" style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>
              <div className="col-span-1">#</div>
              <div className="col-span-2">Name</div>
              <div className="col-span-4">Email</div>
              <div className="col-span-3">Role</div>
              <div className="col-span-2 text-right">Joined</div>
            </div>
            {waitlist.length === 0 && (
              <div className="p-10 text-center text-sm" style={{ color: "var(--text-muted)" }}>No waitlist signups yet.</div>
            )}
            {waitlist.map((w, i) => (
              <div key={w.email} className="grid grid-cols-12 px-5 py-3 text-sm items-center" style={{ borderBottom: "1px solid var(--border)" }}>
                <div className="col-span-1 font-bold text-white">#{w.position || i+1}</div>
                <div className="col-span-2 font-medium truncate" style={{ color: "var(--text-primary)" }}>{w.name || "—"}</div>
                <div className="col-span-4 font-mono text-xs truncate" style={{ color: "var(--text-muted)" }}>{w.email}</div>
                <div className="col-span-3 text-xs truncate" style={{ color: "var(--text-secondary)" }}>{w.role || "—"}</div>
                <div className="col-span-2 text-right text-xs" style={{ color: "var(--text-muted)" }}>{w.joined_at?.slice(0,10) || "—"}</div>
              </div>
            ))}
          </div>
        )}

        {!loading && tab === "webinars" && stats && (
          <div className="rounded-2xl border overflow-hidden" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }}>
            <div className="hidden md:grid grid-cols-12 px-5 py-3 border-b text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }} style={divBorder}>
              <div className="col-span-5">Title</div>
              <div className="col-span-3">Owner</div>
              <div className="col-span-2">Date</div>
              <div className="col-span-2 text-right">Status</div>
            </div>
            {stats.recent_webinars.map(w => (
              <div key={w.id} className={`grid grid-cols-12 px-5 py-3.5 border-b text-sm items-center ${isDark ? "hover:bg-white/[0.02]" : "hover:bg-gray-50"}`} style={divBorder}>
                <div className="col-span-5 font-medium truncate" style={{ color: "var(--text-primary)" }}>{w.title}</div>
                <div className="col-span-3 text-xs truncate" style={{ color: "var(--text-muted)" }}>{w.owner_name || w.owner_email || w.owner_id?.slice(0,10)}</div>
                <div className="col-span-2 text-xs font-mono" style={{ color: "var(--text-muted)" }}>{w.starts_at?.slice(0, 10)}</div>
                <div className="col-span-2 text-right">
                  <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${w.status === "completed" ? "bg-gray-500/15 text-gray-500" : "bg-white/15 text-white"}`}>
                    {w.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Invite Modal */}
      <AnimatePresence>
        {inviteOpen && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => { setInviteOpen(false); setNewCreds(null); }}>
            <motion.div initial={{ opacity: 0, scale: 0.93 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.93 }}
              className="rounded-2xl w-full max-w-md p-6" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", boxShadow: "var(--shadow-lg)" }}
              onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-5">
                <h3 className="text-lg font-bold" style={{ color: "var(--text-primary)" }} style={{ fontFamily: "Outfit" }}>Invite Team Member</h3>
                <button onClick={() => { setInviteOpen(false); setNewCreds(null); }} className="hover:${text} transition-colors" style={{ color: "var(--text-muted)" }}>
                  <X size={18} />
                </button>
              </div>

              {newCreds ? (
                <div>
                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/15 flex items-center justify-center">
                      <Check size={16} className="text-emerald-400" />
                    </div>
                    <div className="font-semibold" style={{ color: "var(--text-primary)" }}>Account created!</div>
                  </div>
                  <div className="rounded-xl p-4 border text-sm space-y-2" style={{ background: "var(--bg-sunken)", border: "1px solid var(--border)" }}>
                    <div><span className={muted}>Email:</span> <span className="font-mono font-medium" style={{ color: "var(--text-primary)" }}>{newCreds.email}</span></div>
                    <div><span className={muted}>Role:</span> <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{newCreds.role}</span></div>
                    <div><span className={muted}>Temp password:</span> <span className="font-mono font-bold text-orange-500">{newCreds.temp_password}</span></div>
                  </div>
                  <div className="flex items-start gap-2 mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
                    <AlertTriangle size={12} className="text-amber-400 mt-0.5 shrink-0" />
                    Share2 these credentials securely. They can change their password in Settings.
                  </div>
                  <button onClick={() => { setInviteOpen(false); setNewCreds(null); setInviteData({ name: "", email: "", role: "moderator", password: "" }); }}
                    className="mt-4 w-full py-2.5 bg-orange-600 hover:bg-orange-500 text-white font-semibold rounded-xl text-sm transition-colors">
                    Done
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {[["Name", "name", "text", "Jane Smith"], ["Email", "email", "email", "jane@company.com"], ["Temp Password", "password", "text", "Leave blank to auto-generate"]].map(([label, key, type, ph]) => (
                    <div key={key}>
                      <label className="text-xs font-bold uppercase tracking-wider block mb-1" style={{ color: "var(--text-muted)" }}>{label}</label>
                      <input type={type} placeholder={ph} value={inviteData[key]}
                        onChange={e => setInviteData(d => ({ ...d, [key]: e.target.value }))}
                        className={`w-full rounded-xl px-3 py-2.5 text-sm border focus:outline-none focus:border-orange-500/50 ${isDark ? "bg-black/30 border-white/[0.1] text-gray-200 placeholder-gray-700" : "bg-gray-50 border-gray-200 text-gray-800"}`} />
                    </div>
                  ))}
                  <div>
                    <label className="text-xs font-bold uppercase tracking-wider block mb-1" style={{ color: "var(--text-muted)" }}>Role</label>
                    <select value={inviteData.role} onChange={e => setInviteData(d => ({ ...d, role: e.target.value }))}
                      className="w-full rounded-xl px-3 py-2.5 text-sm border focus:outline-none" style={{ background: "var(--bg-sunken)", border: "1px solid var(--border)", color: "var(--text-primary)" }}>
                      <option value="moderator">Moderator — can view and manage webinars</option>
                      <option value="admin">Admin — full access including user management</option>
                    </select>
                  </div>
                  <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                    onClick={invite} disabled={inviting}
                    className="w-full py-2.5 bg-orange-600 hover:bg-orange-500 text-white font-semibold rounded-xl text-sm flex items-center justify-center gap-2 disabled:opacity-50 transition-colors mt-2">
                    {inviting ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <Plus size={15} />}
                    {inviting ? "Creating…" : "Create account"}
                  </motion.button>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
