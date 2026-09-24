import { useState } from "react";
import { ArrowRight, Check, Zap } from "@/components/Icons";
import { Link, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import StarField from "@/components/StarField";

const PERKS = [
  "8 AI-written touches per webinar",
  "6 channels — email, LinkedIn, WhatsApp & more",
  "62%+ average attendance rate",
  "Free 14-day trial, no card required",
];

export default function Register() {
  const { register } = useAuth();
  const [name, setName]   = useState("");
  const [email, setEmail] = useState("");
  const [pw, setPw]       = useState("");
  const [busy, setBusy]   = useState(false);
  const [focus, setFocus] = useState(null);
  const nav = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try { await register(name, email, pw); nav("/app"); }
    catch (err) { toast.error(err?.response?.data?.detail || "Sign-up failed"); }
    finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr] relative overflow-hidden" style={{ background: "#050816" }}>
      <StarField count={160} speed={0.3} className="z-0" />

      {/* Glow */}
      <motion.div className="absolute top-[-10%] right-[30%] w-[500px] h-[500px] rounded-full pointer-events-none z-0"
        style={{ background: "radial-gradient(circle, rgba(234,88,12,0.14) 0%, transparent 70%)", filter: "blur(60px)" }}
        animate={{ scale: [1, 1.1, 1] }} transition={{ duration: 10, repeat: Infinity }} />

      {/* Left panel */}
      <div className="relative px-6 sm:px-12 lg:px-20 py-10 lg:py-16 flex flex-col justify-between z-10">
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
          className="flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-white flex items-center justify-center"
              style={{ boxShadow: "0 0 20px rgba(255,255,255,0.3)" }}>
              <Zap size={17} strokeWidth={2.5} className="text-black" />
            </div>
            <span className="text-xl font-bold tracking-tight text-white" style={{ fontFamily: "Outfit" }}>
              ShowUpAI
            </span>
          </Link>
          <Link to="/" className="flex items-center gap-1.5 text-xs text-white/40 hover:text-white/70 transition-colors">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
            Back to home
          </Link>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.15 }}>
          <div className="text-[10px] font-bold uppercase tracking-[0.25em] text-gray-400 mb-4">Join ShowUpAI</div>
          <h1 className="text-4xl sm:text-5xl font-bold leading-tight tracking-tight text-white mb-4" style={{ fontFamily: "Outfit" }}>
            Your next webinar<br />
            <span className="text-white">deserves a full room.</span>
          </h1>
          <p className="text-white/60 text-lg mb-10">Free for 14 days. No credit card. Cancel anytime.</p>

          <div className="space-y-3">
            {PERKS.map((perk, i) => (
              <motion.div key={i} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4 + i * 0.08 }}
                className="flex items-center gap-3">
                <div className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center shrink-0">
                  <Check size={11} className="text-white" />
                </div>
                <span className="text-sm text-white/70">{perk}</span>
              </motion.div>
            ))}
          </div>
        </motion.div>

        <div className="text-xs text-white/20">© {new Date().getFullYear()} ShowUpAI</div>
      </div>

      {/* Right panel — form */}
      <div className="relative flex items-center justify-center p-6 sm:p-10 z-10">
        <motion.form onSubmit={submit}
          initial={{ opacity: 0, scale: 0.96, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-md rounded-2xl p-8"
          style={{ background: "rgba(255,255,255,0.04)", backdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.08)" }}
          data-testid="register-form">

          <h2 className="text-3xl font-bold tracking-tight text-white mb-1" style={{ fontFamily: "Outfit" }}>Create account</h2>
          <p className="text-sm text-white/50 mb-7">14-day free trial. No card required.</p>

          <FloatLabel label="Full name" focused={focus === "name" || !!name}>
            <input data-testid="reg-name" type="text" required value={name}
              onFocus={() => setFocus("name")} onBlur={() => setFocus(null)}
              onChange={e => setName(e.target.value)}
              className="w-full bg-transparent text-white focus:outline-none pt-5 pb-1.5 px-0 border-0 placeholder-transparent" />
          </FloatLabel>

          <FloatLabel label="Work email" focused={focus === "email" || !!email}>
            <input data-testid="reg-email" type="email" required value={email}
              onFocus={() => setFocus("email")} onBlur={() => setFocus(null)}
              onChange={e => setEmail(e.target.value)}
              className="w-full bg-transparent text-white focus:outline-none pt-5 pb-1.5 px-0 border-0 placeholder-transparent" />
          </FloatLabel>

          <FloatLabel label="Password" focused={focus === "pw" || !!pw}>
            <input data-testid="reg-password" type="password" required value={pw}
              onFocus={() => setFocus("pw")} onBlur={() => setFocus(null)}
              onChange={e => setPw(e.target.value)}
              className="w-full bg-transparent text-white focus:outline-none pt-5 pb-1.5 px-0 border-0 placeholder-transparent" />
          </FloatLabel>

          <motion.button whileHover={{ scale: 1.01, boxShadow: "0 0 32px rgba(255,255,255,0.3)" }}
            whileTap={{ scale: 0.99 }}
            data-testid="reg-submit" disabled={busy}
            className="mt-6 w-full bg-white hover:bg-gray-100 text-black font-semibold py-3 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
            <AnimatePresence mode="wait">
              {busy
                ? <motion.span key="b" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>Creating account…</motion.span>
                : <motion.span key="s" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2">
                    Start free trial <ArrowRight size={16} />
                  </motion.span>
              }
            </AnimatePresence>
          </motion.button>

          <p className="text-xs text-white/30 mt-3 text-center">
            By signing up you agree to our Terms & Privacy Policy.
          </p>
          <p className="text-sm text-white/50 mt-4 text-center">
            Already have an account?{" "}
            <Link data-testid="goto-login" to="/login" className="text-white font-semibold hover:text-gray-200">
              Sign in →
            </Link>
          </p>
        </motion.form>
      </div>
    </div>
  );
}

function FloatLabel({ label, focused, children }) {
  return (
    <div className="relative border-b border-white/10 focus-within:border-white transition-colors mt-3">
      <motion.label
        animate={{ y: focused ? -2 : 16, fontSize: focused ? 11 : 14, color: focused ? "rgb(255,255,255)" : "rgba(255,255,255,0.4)" }}
        transition={{ duration: 0.2 }}
        className="absolute left-0 pointer-events-none font-medium tracking-wide">
        {label}
      </motion.label>
      {children}
    </div>
  );
}
