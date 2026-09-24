import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { BarChart3, BookOpen, CalendarDays, Inbox, LayoutDashboard, LogOut, Mail, Menu, Moon, Settings, Star, Sun, X, Zap } from "@/components/Icons";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { useRestartTour } from "@/components/OnboardingTour";
import StarField from "@/components/StarField";

const NAV = [
  { to: "/app",            label: "Dashboard",     icon: LayoutDashboard, testId: "nav-dashboard" },
  { to: "/app/approvals",  label: "Approvals",     icon: Inbox,           testId: "nav-approvals" },
  { to: "/app/library",    label: "Content",       icon: BookOpen,        testId: "nav-library" },
  { to: "/app/schedule",   label: "Schedule",      icon: CalendarDays,    testId: "nav-schedule" },
  { to: "/app/analytics",  label: "Analytics",     icon: BarChart3,       testId: "nav-analytics" },
  { to: "/app/email",       label: "Email Stats",   icon: Mail,            testId: "nav-email" },
  { to: "/app/settings",   label: "Settings",      icon: Settings,             testId: "nav-settings" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const { isDark, toggle } = useTheme();
  const loc = useLocation();
  const nav = useNavigate();
  const [openMobile, setOpenMobile] = useState(false);

  const isAdmin = user?.role === "admin" || user?.role === "superadmin";

  const SidebarContent = () => (
    <>
      {/* Logo */}
      <div className="px-5 py-5 flex items-center gap-3" style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="w-9 h-9 rounded-xl bg-orange-600 flex items-center justify-center"
          style={{ boxShadow: "0 0 20px rgba(234,88,12,0.45)" }}>
          <Zap size={17} strokeWidth={2.5} className="text-white" />
        </div>
        <div>
          <div className="font-bold text-lg leading-none" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
            ShowUp<span className="text-orange-500">AI</span>
          </div>
          <div className="text-[9px] uppercase tracking-[0.2em] mt-0.5" style={{ color: "var(--text-muted)" }}>
            Webinar Booster
          </div>
        </div>
      </div>

      {/* Back to site */}
      <div className="px-3 pt-3">
        <a href="/"
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-colors"
          style={{ color: "var(--text-muted)" }}
          onMouseEnter={e => e.currentTarget.style.color = "var(--text-secondary)"}
          onMouseLeave={e => e.currentTarget.style.color = "var(--text-muted)"}>
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          Back to site
        </a>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-3 space-y-0.5">
        {NAV.map(({ to, label, icon: Icon, testId }, idx) => {
          const active = loc.pathname === to || (to !== "/app" && loc.pathname.startsWith(to));
          return (
            <motion.div key={to} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.04 + 0.05 }}>
              <Link to={to} data-testid={testId} onClick={() => setOpenMobile(false)}
                className="relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all"
                style={{
                  background: active ? "#EA580C" : "transparent",
                  color: active ? "#ffffff" : "var(--text-secondary)",
                }}>
                {active && (
                  <motion.div layoutId="sidebar-indicator" transition={{ type: "spring", stiffness: 400, damping: 32 }}
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-full bg-white/50" />
                )}
                <Icon size={16} style={{ opacity: active ? 1 : 0.7 }} />
                {label}
              </Link>
            </motion.div>
          );
        })}

        {/* Admin link */}
        {isAdmin && (
          <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.35 }}>
            <Link to="/app/admin" onClick={() => setOpenMobile(false)}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all mt-2"
              style={{
                background: loc.pathname === "/app/admin" ? "rgba(234,88,12,0.1)" : "transparent",
                color: loc.pathname === "/app/admin" ? "#EA580C" : "var(--text-muted)",
                borderTop: "1px solid var(--border)",
                marginTop: "8px",
                paddingTop: "12px",
              }}>
              <Star size={15} className="text-orange-500/70" />
              Admin
            </Link>
          </motion.div>
        )}
      </nav>

      {/* User section */}
      <div className="p-3 mx-2 mb-3 rounded-2xl" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)" }}>
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-8 h-8 rounded-xl flex items-center justify-center text-orange-500 text-xs font-bold"
            style={{ background: "rgba(234,88,12,0.12)" }}>
            {user?.name?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase() || "U"}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold truncate" style={{ color: "var(--text-primary)" }}>
              {user?.name || "User"}
            </div>
            <div className="text-[10px] truncate" style={{ color: "var(--text-muted)" }}>{user?.email}</div>
          </div>
        </div>
        <div className="flex items-center justify-between">
          <button data-testid="logout-btn" onClick={() => { logout(); nav("/login"); }}
            className="flex items-center gap-1.5 text-xs transition-colors"
            style={{ color: "var(--text-muted)" }}
            onMouseEnter={e => e.currentTarget.style.color = "var(--text-secondary)"}
            onMouseLeave={e => e.currentTarget.style.color = "var(--text-muted)"}>
            <LogOut size={12} /> Sign out
          </button>
          <button onClick={toggle}
            className="w-7 h-7 rounded-lg flex items-center justify-center transition-all"
            style={{ background: "var(--bg-sunken)", color: "var(--text-muted)" }}
            title="Toggle theme">
            {isDark ? <Sun size={13} /> : <Moon size={13} />}
          </button>
        </div>
      </div>
    </>
  );

  return (
    <div className="min-h-screen flex" style={{ background: "var(--bg-base)" }}>
      {/* Mobile top bar */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-30 px-4 py-3.5 flex items-center justify-between"
        style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border)", backdropFilter: "blur(12px)" }}>
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-orange-600 flex items-center justify-center">
            <Zap size={13} className="text-white" strokeWidth={2.5} />
          </div>
          <span className="font-bold text-sm" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
            ShowUp<span className="text-orange-500">AI</span>
          </span>
        </div>
        <button onClick={() => setOpenMobile(o => !o)} data-testid="mobile-menu-toggle"
          style={{ color: "var(--text-muted)" }}>
          {openMobile ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile overlay */}
      <AnimatePresence>
        {openMobile && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="lg:hidden fixed inset-0 bg-black/50 z-30" onClick={() => setOpenMobile(false)} />
            <motion.aside initial={{ x: -260 }} animate={{ x: 0 }} exit={{ x: -260 }}
              transition={{ type: "spring", stiffness: 300, damping: 32 }}
              className="lg:hidden fixed inset-y-0 left-0 top-0 w-64 z-40 flex flex-col"
              style={{ background: "var(--bg-surface)", borderRight: "1px solid var(--border)" }}>
              <SidebarContent />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-60 flex-col shrink-0 sticky top-0 h-screen" data-testid="sidebar"
        style={{ background: "var(--bg-surface)", borderRight: "1px solid var(--border)" }}>
        <SidebarContent />
      </aside>

      <main className="flex-1 overflow-auto pt-14 lg:pt-0 relative" style={{ background: "var(--bg-base)" }}>
        {isDark && <StarField count={60} speed={0.15} className="z-0 opacity-40" />}
        <Outlet />
      </main>
    </div>
  );
}
