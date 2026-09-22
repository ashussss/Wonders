import { useState } from "react";
import { ArrowRight, TrendingUp, Users, Zap } from "@/components/Icons";
import { Link, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import StarField from "@/components/StarField";

const STATS = [
  { icon: TrendingUp, value: "62%", label: "avg attendance rate" },
  { icon: Zap, value: "8", label: "AI-orchestrated touches" },
  { icon: Users, value: "6", label: "channels per touch" },
];

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [focus, setFocus] = useState(null);
  const nav = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try { await login(email, pw); nav("/app"); }
    catch (err) { toast.error(err?.response?.data?.detail || "Login failed"); }
    finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr] relative overflow-hidden" style={{ background: "#050816" }}>

      {/* ── Star field (full bleed behind everything) ── */}
      <StarField count={180} speed={0.35} className="z-0" />

      {/* Slow ambient blobs */}
      <motion.div
        className="absolute top-[-15%] left-[-8%] w-[550px] h-[550px] rounded-full pointer-events-none z-0"
        style={{ background: "radial-gradient(circle, rgba(234,88,12,0.18) 0%, transparent 70%)", filter: "blur(60px)" }}
        animate={{ x: [0, 50, 0], y: [0, 35, 0] }}
        transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute bottom-[-20%] right-[-5%] w-[480px] h-[480px] rounded-full pointer-events-none z-0"
        style={{ background: "radial-gradient(circle, rgba(234,88,12,0.08) 0%, transparent 70%)", filter: "blur(60px)" }}
        animate={{ x: [0, -40, 0], y: [0, -30, 0] }}
        transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* ── Left panel ── */}
      <div className="relative px-6 sm:px-12 lg:px-20 py-10 lg:py-16 flex flex-col justify-between z-10">
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
          className="flex items-center justify-between">
          <Link to="/" className="flex items-center gap-1.5 text-xs text-white/40 hover:text-white/70 transition-colors">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            Back to home
          </Link>
          <div className="flex items-center gap-2.5">
          <div className="w-10 h-10 rounded-xl bg-orange-600 flex items-center justify-center shadow-[0_0_24px_rgba(234,88,12,0.4)]">
            <Zap size={20} className="text-white" strokeWidth={2.5} />
          </div>
          <span className="text-2xl font-bold tracking-tight text-white" style={{ fontFamily: 'Outfit' }}>
            ShowUp.ai
          </span>
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.2 }}>
          <div className="text-[10px] font-bold uppercase tracking-[0.25em] text-gray-400 mb-3">Webinar attendance booster</div>
          <h1 className="text-5xl sm:text-6xl font-bold leading-[1.05] tracking-tight text-white" style={{ fontFamily: 'Outfit' }}>
            Make people <br />
            <span className="text-white italic">actually</span> show up.
          </h1>
          <p className="text-lg text-white/60 mt-6 max-w-md leading-relaxed">
            AI-orchestrated 8-touch reminder sequences across email, social, and your community. Lift attendance from 30% to 60%+.
          </p>
          <div className="mt-10 grid grid-cols-3 gap-4 max-w-md">
            {STATS.map((s, i) => (
              <motion.div key={i}
                initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.5 + i * 0.1 }}
                className="border border-white/10 bg-white/[0.04] backdrop-blur-sm rounded-xl p-4">
                <s.icon size={16} className="text-white mb-2" />
                <div className="text-2xl font-bold text-white" style={{ fontFamily: 'Outfit' }}>{s.value}</div>
                <div className="text-[11px] text-white/50 leading-tight">{s.label}</div>
              </motion.div>
            ))}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1 }}
          className="text-xs text-white/30">
          © {new Date().getFullYear()} ShowUp.ai
        </motion.div>
      </div>

      {/* ── Right panel — form ── */}
      <div className="relative flex items-center justify-center p-6 sm:p-10 z-10">
        <motion.form onSubmit={submit}
          initial={{ opacity: 0, scale: 0.96, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-md bg-white/[0.04] backdrop-blur-xl border border-white/[0.08] rounded-2xl p-8 shadow-2xl"
          data-testid="login-form">
          <h2 className="text-3xl font-bold tracking-tight text-white mb-1" style={{ fontFamily: 'Outfit' }}>Welcome back</h2>
          <p className="text-sm text-white/50 mb-7">Your next webinar deserves a full room.</p>

          <FloatLabel label="Email" focused={focus === "email" || !!email} testId="login-email-wrap">
            <input data-testid="login-email" type="email" required value={email}
              onFocus={() => setFocus("email")} onBlur={() => setFocus(null)}
              onChange={e => setEmail(e.target.value)}
              className="w-full bg-transparent text-white focus:outline-none pt-5 pb-1.5 px-0 border-0 placeholder-transparent" />
          </FloatLabel>

          <FloatLabel label="Password" focused={focus === "pw" || !!pw} testId="login-password-wrap">
            <input data-testid="login-password" type="password" required value={pw}
              onFocus={() => setFocus("pw")} onBlur={() => setFocus(null)}
              onChange={e => setPw(e.target.value)}
              className="w-full bg-transparent text-white focus:outline-none pt-5 pb-1.5 px-0 border-0 placeholder-transparent" />
          </FloatLabel>

          <motion.button
            whileHover={{ scale: 1.01, boxShadow: "0 0 32px rgba(255,255,255,0.3)" }}
            whileTap={{ scale: 0.99 }}
            data-testid="login-submit" disabled={busy}
            className="mt-6 w-full bg-orange-600 hover:bg-orange-500 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2" style={{ boxShadow: "0 0 20px rgba(234,88,12,0.4)" }}>
            <AnimatePresence mode="wait">
              {busy
                ? <motion.span key="b" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>Signing in…</motion.span>
                : <motion.span key="s" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2">
                  Sign in <ArrowRight size={16} />
                </motion.span>
              }
            </AnimatePresence>
          </motion.button>

          <p className="text-sm text-white/50 mt-6 text-center">
            New here? <Link data-testid="goto-register" to="/register" className="text-white font-semibold hover:text-gray-200">Create an account →</Link>
          </p>
          <p className="text-sm text-white/30 mt-3 text-center">
            <Link to="/" className="hover:text-white/50 transition-colors">← Back to home</Link>
          </p>
        </motion.form>
      </div>
    </div>
  );
}

function FloatLabel({ label, focused, children, testId }) {
  return (
    <div data-testid={testId} className="relative border-b border-white/10 focus-within:border-white transition-colors mt-3">
      <motion.label
        animate={{ y: focused ? -2 : 16, fontSize: focused ? 11 : 14, color: focused ? "rgb(255,255,255)" : "rgba(255,255,255,0.4)" }}
        transition={{ duration: 0.2, ease: "easeOut" }}
        className="absolute left-0 pointer-events-none font-medium tracking-wide">
        {label}
      </motion.label>
      {children}
    </div>
  );
}
