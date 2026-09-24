import { useState, useEffect } from "react";
import { ArrowRight, Check, Clock, TrendingUp, Users, Zap } from "@/components/Icons";
import { motion, AnimatePresence } from "framer-motion";
import { Link } from "react-router-dom";
import StarField from "@/components/StarField";
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "https://showup-backend-2bfj.onrender.com";

const ROLES = [
  "Coach / Consultant",
  "B2B SaaS Company",
  "Course Creator",
  "Agency / Freelancer",
  "EdTech Platform",
  "Community Manager",
  "HR / L&D Team",
  "Other",
];

const SOCIAL_PROOF = [
  { stat: "62%+", label: "Average attendance rate" },
  { stat: "8", label: "AI-written touches per webinar" },
  { stat: "6", label: "Channels automated" },
];

// CSS fix for autofill background
const autofillStyle = `
  input:-webkit-autofill,
  input:-webkit-autofill:hover,
  input:-webkit-autofill:focus {
    -webkit-box-shadow: 0 0 0px 1000px rgba(30,27,60,0.95) inset !important;
    -webkit-text-fill-color: white !important;
    caret-color: white !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
  }
`;

export default function Waitlist() {
  const [step, setStep] = useState("form"); // form | success
  const [name, setName]   = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole]   = useState("");
  const [busy, setBusy]   = useState(false);
  const [error, setError] = useState("");
  const [position, setPosition] = useState(null);
  const [count, setCount] = useState(null);

  useEffect(() => {
    fetch(`${BACKEND_URL}/api/auth/waitlist/count`)
      .then(r => r.json())
      .then(d => setCount(d.count))
      .catch(() => {});
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!email || !role) { setError("Email and role are required."); return; }
    setBusy(true); setError("");
    
    const trySubmit = async (retries = 2) => {
      const r = await fetch(`${BACKEND_URL}/api/auth/waitlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, name, role, source: "waitlist-page" })
      });
      if (!r.ok && retries > 0) {
        // Server waking up — wait 3s and retry
        await new Promise(res => setTimeout(res, 3000));
        return trySubmit(retries - 1);
      }
      return r;
    };

    try {
      const r = await trySubmit();
      const d = await r.json();
      if (d.ok) { setPosition(d.position); setStep("success"); }
      else setError(d.detail || "Something went wrong.");
    } catch (err) { 
      setError("Could not connect — server may be starting up. Please try again in 10 seconds.");
    }
    finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen relative overflow-hidden" style={{ background: "#050816" }}>
      <style>{autofillStyle}</style>
      <StarField count={120} speed={0.25} />

      {/* Glow */}
      <div className="absolute top-[-10%] left-[50%] -translate-x-1/2 w-[600px] h-[400px] rounded-full pointer-events-none"
        style={{ background: "radial-gradient(circle, rgba(234,88,12,0.18) 0%, transparent 70%)", filter: "blur(80px)" }} />

      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between px-6 py-5 max-w-6xl mx-auto">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-white flex items-center justify-center"
            style={{ boxShadow: "0 0 20px rgba(234,88,12,0.5)" }}>
            <Zap size={17} strokeWidth={2.5} className="text-white" />
          </div>
          <span className="text-xl font-bold text-white" style={{ fontFamily: "Outfit" }}>
            ShowUpAI
          </span>
        </Link>
        <Link to="/login" className="text-sm text-white/40 hover:text-white/70 transition-colors">
          Already have an account →
        </Link>
      </nav>

      <div className="relative z-10 max-w-5xl mx-auto px-6 pt-12 pb-24">

        {/* Badge */}
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
          className="flex justify-center mb-8">
          <div className="flex items-center gap-2 px-4 py-2 rounded-full text-xs font-bold uppercase tracking-widest text-white"
            style={{ background: "rgba(234,88,12,0.12)", border: "1px solid rgba(234,88,12,0.25)" }}>
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
            Early Access — Limited Spots
          </div>
        </motion.div>

        {/* Headline */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="text-center mb-12">
          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-black tracking-tight text-white leading-[0.95] mb-6"
            style={{ fontFamily: "Outfit" }}>
            Stop losing<br />
            <span className="text-white">your registrants.</span>
          </h1>
          <p className="text-white/60 text-xl max-w-2xl mx-auto leading-relaxed">
            AI writes 8 personalised reminder touches per webinar — across email, LinkedIn, WhatsApp, Instagram and more.
            You approve. They show up.
          </p>
        </motion.div>

        {/* Stats */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          className="flex flex-wrap justify-center gap-8 mb-14">
          {SOCIAL_PROOF.map((s, i) => (
            <div key={i} className="text-center">
                <div className="text-3xl font-black text-white" style={{ fontFamily: "Outfit" }}>{s.stat}</div>
              <div className="text-xs text-white/40 uppercase tracking-wider mt-1">{s.label}</div>
            </div>
          ))}
          {count !== null && (
            <div className="text-center">
              <div className="text-3xl font-black text-white" style={{ fontFamily: "Outfit" }}>{count}+</div>
              <div className="text-xs text-white/40 uppercase tracking-wider mt-1">On the waitlist</div>
            </div>
          )}
        </motion.div>

        {/* Form / Success */}
        <div className="max-w-md mx-auto">
          <AnimatePresence mode="wait">
            {step === "form" ? (
              <motion.form key="form" onSubmit={submit}
                initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }}
                className="rounded-2xl p-7"
                style={{ background: "rgba(255,255,255,0.04)", backdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.08)" }}>

                <h2 className="text-xl font-bold text-white mb-1" style={{ fontFamily: "Outfit" }}>
                  Join the waitlist
                </h2>
                <p className="text-sm text-white/40 mb-6">
                  Early access members get 3 months free.
                </p>

                {/* Name */}
                <div className="mb-4">
                  <label className="block text-[10px] font-bold uppercase tracking-widest text-white/40 mb-1.5">Name</label>
                  <input type="text" value={name} onChange={e => setName(e.target.value)}
                    placeholder="Jane Smith"
                    className="w-full px-3.5 py-2.5 rounded-xl text-sm text-white placeholder-white/20 focus:outline-none transition-colors autofill-dark"
                    style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", colorScheme: "dark" }} />
                </div>

                {/* Email */}
                <div className="mb-4">
                  <label className="block text-[10px] font-bold uppercase tracking-widest text-white/40 mb-1.5">Work email *</label>
                  <input type="email" required value={email} onChange={e => setEmail(e.target.value)}
                    placeholder="jane@company.com"
                    className="w-full px-3.5 py-2.5 rounded-xl text-sm text-white placeholder-white/20 focus:outline-none transition-colors autofill-dark"
                    style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", colorScheme: "dark" }} />
                </div>

                {/* Role */}
                <div className="mb-6">
                  <label className="block text-[10px] font-bold uppercase tracking-widest text-white/40 mb-1.5">I run webinars as a *</label>
                  <div className="grid grid-cols-2 gap-2">
                    {ROLES.map(r => (
                      <button key={r} type="button" onClick={() => setRole(r)}
                        className="text-xs px-3 py-2 rounded-xl text-left transition-all"
                        style={role === r
                          ? { background: "rgba(255,255,255,0.2)", border: "1px solid rgba(255,255,255,0.5)", color: "#FFFFFF", fontWeight: 700 }
                          : { background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.5)" }}>
                        {r}
                      </button>
                    ))}
                  </div>
                </div>

                {error && <p className="text-red-400 text-xs mb-4">{error}</p>}

                <motion.button whileHover={{ scale: 1.01, boxShadow: "0 0 32px rgba(234,88,12,0.4)" }}
                  whileTap={{ scale: 0.99 }} type="submit" disabled={busy}
                  className="w-full py-3 bg-white hover:bg-gray-100 text-black font-bold rounded-xl flex items-center justify-center gap-2 transition-colors disabled:opacity-50">
                  {busy
                    ? <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /><span>Saving your spot...</span></>
                    : <><span>Claim my spot</span> <ArrowRight size={16} /></>}
                </motion.button>

                <p className="text-[10px] text-white/25 text-center mt-3">
                  No spam. No credit card. Unsubscribe anytime.
                </p>
              </motion.form>

            ) : (
              <motion.div key="success"
                initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
                className="rounded-2xl p-8 text-center"
                style={{ background: "rgba(255,255,255,0.04)", backdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.08)" }}>

                <div className="w-14 h-14 rounded-2xl bg-emerald-500/20 flex items-center justify-center mx-auto mb-4">
                  <Check size={24} className="text-emerald-400" />
                </div>
                <h2 className="text-2xl font-black text-white mb-2" style={{ fontFamily: "Outfit" }}>
                  You're on the list!
                </h2>
                <p className="text-white/50 text-sm mb-6">
                  You're <span className="text-white font-bold">#{position}</span> on the waitlist.
                  Early access members get <span className="text-white font-semibold">3 months free</span>.
                  We'll email you the moment your spot opens.
                </p>

                {/* Share2 nudge */}
                <div className="rounded-xl p-4 mb-6" style={{ background: "rgba(234,88,12,0.08)", border: "1px solid rgba(234,88,12,0.2)" }}>
                  <p className="text-xs text-orange-400/80 font-semibold mb-2 uppercase tracking-wider">Move up the list</p>
                  <p className="text-xs text-white/50 mb-3">Share2 ShowUpAI with others who run webinars — every referral moves you up.</p>
                  <div className="flex gap-2">
                    <button onClick={() => {
                      navigator.clipboard.writeText("https://showupai.app/waitlist");
                      alert("Link copied!");
                    }} className="flex-1 text-xs py-2 rounded-lg font-semibold text-white transition-colors"
                      style={{ background: "#EA580C" }}>
                      Copy referral link
                    </button>
                    <a href={`https://twitter.com/intent/tweet?text=${encodeURIComponent("Just joined the waitlist for ShowUpAI — AI that makes people actually show up to your webinar. 62%+ attendance rate. Check it out: https://showupai.app/waitlist")}`}
                      target="_blank" rel="noreferrer"
                      className="flex-1 text-xs py-2 rounded-lg font-semibold text-white text-center transition-colors"
                      style={{ background: "rgba(255,255,255,0.1)", border: "1px solid rgba(255,255,255,0.1)" }}>
                      Share2 on X
                    </a>
                  </div>
                </div>

                <Link to="/" className="text-xs text-white/30 hover:text-white/60 transition-colors">
                  ← Back to home
                </Link>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Bottom trust signals */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }}
          className="flex flex-wrap justify-center gap-6 mt-16 text-xs text-white/25">
          {["Works with Zoom, Meet, Teams", "Email + LinkedIn + WhatsApp", "AI-written copy, you approve", "No credit card for early access"].map((t, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <Check size={11} className="text-orange-500/60" />
              {t}
            </div>
          ))}
        </motion.div>
      </div>
    </div>
  );
}
