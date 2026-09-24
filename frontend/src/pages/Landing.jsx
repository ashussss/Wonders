import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Zap, ArrowRight, Check, ChevronDown, Menu, X, TrendingUp, Users, Clock, Sparkles, BarChart3, Mail, MessageSquare, Star } from "@/components/Icons";
import StarField from "@/components/StarField";
import CinematicBackground from "@/components/CinematicBackground";

// ── Design tokens ──────────────────────────────────────────
// Palette: near-black #05050F, orange #EA580C, electric accent #FF6B35
// Type: display = system-ui bold condensed feel, body = Inter
// Signature: the "attendance gap" number that counts up on scroll

const ORANGE = "#EA580C";
const PLANS = [
  {
    name: "Starter",
    price: "$29",
    period: "/mo",
    desc: "For independent speakers and solo consultants.",
    features: ["5 webinars/month", "8-touch AI sequences", "Email + LinkedIn", "Public registration page", "Attendance analytics"],
    cta: "Start free trial",
    highlight: false},
  {
    name: "Growth",
    price: "$79",
    period: "/mo",
    desc: "For teams running webinars as a growth channel.",
    features: ["Unlimited webinars", "All 6 channels", "AI image generation", "Poll + case study touches", "Lead magnet builder", "Priority support"],
    cta: "Start free trial",
    highlight: true},
  {
    name: "Agency",
    price: "$199",
    period: "/mo",
    desc: "For agencies managing multiple clients.",
    features: ["Everything in Growth", "Multi-brand workspaces", "White-label reports", "Custom sender domains", "Dedicated onboarding", "SLA support"],
    cta: "Talk to us",
    highlight: false},
];

const FEATURES = [
  { icon: Zap, title: "8 touches. Not 1.", body: "Confirmation, insight, poll, case study, thought-provoking hook, day-before, join link, post-event. The sequence your registrants actually need to show up.", color: "text-orange-400" },
  { icon: Mail, title: "Every channel, one place", body: "Email, LinkedIn, WhatsApp, Circle.so, Facebook, Instagram. One approval, delivered everywhere. No copy-pasting between tools.", color: "text-orange-400" },
  { icon: BarChart3, title: "Know what actually worked", body: "Track opens, attendance, and conversions by channel. See which touch moved the needle. Get better every single webinar.", color: "text-orange-400" },
  { icon: Clock, title: "30 seconds to set up", body: "Paste your webinar link. AI generates your entire 8-touch campaign. You approve. It runs on schedule. That's it.", color: "text-orange-400" },
  { icon: TrendingUp, title: "31% → 62%+ attendance", body: "The industry average is 31%. ShowUp users consistently hit 62%+. The gap isn't your content — it's your follow-through.", color: "text-orange-400" },
  { icon: Users, title: "Works with any platform", body: "Zoom, Teams, Meet, Circle.so, Eventbrite, Luma — paste any link and ShowUp auto-fills your webinar details and imports attendees.", color: "text-orange-400" },
];

const SOCIAL_PROOF = [
  { quote: "First webinar with ShowUp went from our usual 28% to 61%. The day-before case study email was the one that moved people — they showed up wanting answers.", name: "Sarah M.", role: "School Business Manager, UK" },
  { quote: "I used to spend 3 hours per webinar writing reminders. ShowUp generates everything in 30 seconds and the copy is honestly better than what I was writing.", name: "James T.", role: "EdTech Consultant, US" },
  { quote: "The poll touch is genius. We get replies before the webinar even starts.", name: "Priya K.", role: "Corporate Trainer" },
];

// ── Animated counter ────────────────────────────────────────
function Counter({ to, suffix = "", duration = 2 }) {
  const [val, setVal] = useState(0);
  const ref = useRef(null);
  const started = useRef(false);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !started.current) {
        started.current = true;
        const start = performance.now();
        const tick = (now) => {
          const p = Math.min((now - start) / (duration * 1000), 1);
          const ease = 1 - Math.pow(1 - p, 3);
          setVal(Math.round(ease * to));
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      }
    }, { threshold: 0.5 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [to, duration]);
  return <span ref={ref}>{val}{suffix}</span>;
}

// ── Nav ────────────────────────────────────────────────────
function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", fn, { passive: true });
    return () => window.removeEventListener("scroll", fn);
  }, []);
  return (
    <header className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${scrolled ? "bg-[#05050F]/90 backdrop-blur-xl border-b border-white/[0.06]" : ""}`}>
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-orange-600 flex items-center justify-center shadow-[0_0_16px_rgba(234,88,12,0.5)]">
            <Zap size={16} strokeWidth={2.5} className="text-white" />
          </div>
          <span className="font-bold text-lg text-white tracking-tight" style={{ fontFamily: "Outfit" }}>
            ShowUp<span className="text-orange-500">AI</span>
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-8">
          {[["#features","Features"],["#how","How it works"],["#pricing","Pricing"],["#about","About"]].map(([href,label]) => (
            <a key={href} href={href} className="text-sm text-gray-400 hover:text-white transition-colors">{label}</a>
          ))}
          <Link to="/blog" className="text-sm text-gray-400 hover:text-white transition-colors">Blog</Link>
        </nav>

        <div className="hidden md:flex items-center gap-3">
          <Link to="/login" className="text-sm text-gray-400 hover:text-white transition-colors px-4 py-2">Sign in</Link>
          <Link to="/app" className="text-sm text-gray-400 hover:text-white transition-colors px-4 py-2">Dashboard</Link>
          <Link to="/waitlist" className="text-sm font-semibold bg-orange-600 hover:bg-orange-500 text-white px-4 py-2 rounded-lg transition-colors shadow-[0_0_20px_rgba(234,88,12,0.3)]">
            Start free →
          </Link>
        </div>

        <button className="md:hidden text-gray-400" onClick={() => setOpen(o => !o)}>
          {open ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>

      {/* Mobile menu */}
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
            className="md:hidden bg-[#08080F] border-b border-white/[0.06] px-6 py-4 flex flex-col gap-4">
            {[["#features","Features"],["#how","How it works"],["#pricing","Pricing"],["#about","About"]].map(([href,label]) => (
              <a key={href} href={href} onClick={() => setOpen(false)} className="text-gray-300 py-1">{label}</a>
            ))}
            <Link to="/blog" onClick={() => setOpen(false)} className="text-gray-300 py-1">Blog</Link>
            <div className="flex gap-3 pt-2 border-t border-white/[0.06]">
              <Link to="/login" className="flex-1 text-center py-2 text-gray-400 border border-white/[0.1] rounded-lg text-sm">Sign in</Link>
              <Link to="/waitlist" className="flex-1 text-center py-2 bg-orange-600 text-white rounded-lg text-sm font-semibold">Start free</Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}

// ── Main Landing ───────────────────────────────────────────
export default function Landing() {
  return (
    <div className="min-h-screen bg-[#05050F] text-white overflow-x-hidden" style={{ scrollBehavior: "smooth", fontFamily: "Inter, sans-serif" }}>
      <style>{`
        @keyframes shimmer { 0% { background-position: 0% center; } 100% { background-position: 300% center; } }
        @keyframes float-slow { 0%,100% { transform: translateY(0px); } 50% { transform: translateY(-8px); } }
        @keyframes glow-pulse { 0%,100% { opacity: 0.6; } 50% { opacity: 1; } }
        @keyframes scan { 0% { transform: translateY(-100%); } 100% { transform: translateY(100vh); } }
        .neon-text { text-shadow: 0 0 20px rgba(234,88,12,0.8), 0 0 40px rgba(234,88,12,0.4), 0 0 80px rgba(234,88,12,0.2); }
        .glass-card { backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); }
        .holographic { background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 50%, rgba(255,255,255,0.1) 100%); }
        section { position: relative; }
      `}</style>
      <Nav />

      {/* ── HERO ── */}
      <section className="relative min-h-screen flex flex-col items-center justify-center text-center px-6 pt-24 pb-16 overflow-hidden">
        {window.innerWidth > 768 
          ? <CinematicBackground intensity={0.8} />
          : <div style={{position:"fixed",inset:0,background:"radial-gradient(ellipse at 20% 30%, rgba(234,88,12,0.18) 0%, transparent 50%), radial-gradient(ellipse at 80% 70%, rgba(234,88,12,0.1) 0%, transparent 45%), #05050F",pointerEvents:"none",zIndex:0}} />
        }
        <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 1 }}>
        </div>
        <div className="absolute inset-0 pointer-events-none" style={{
          background: "radial-gradient(ellipse 80% 70% at 50% 50%, transparent 20%, rgba(5,5,15,0.85) 100%)",
          zIndex: 2
        }} />

        {/* Glow orbs */}
        <motion.div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] rounded-full pointer-events-none"
          style={{ background: "radial-gradient(circle, rgba(234,88,12,0.12) 0%, transparent 65%)", filter: "blur(40px)" }}
          animate={{ scale: [1, 1.08, 1] }} transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }} />
        <motion.div className="absolute top-1/4 left-1/4 w-[400px] h-[400px] rounded-full pointer-events-none"
          style={{ background: "radial-gradient(circle, rgba(99,102,241,0.08) 0%, transparent 70%)", filter: "blur(60px)" }}
          animate={{ x: [0, 40, 0], y: [0, 30, 0] }} transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }} />

        <div className="relative z-10 max-w-4xl mx-auto text-center">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
            <Link to="/waitlist" className="inline-flex items-center gap-2 bg-orange-500/10 border border-orange-500/25 rounded-full px-4 py-1.5 text-xs font-semibold text-orange-400 uppercase tracking-widest mb-8 hover:bg-orange-500/20 transition-colors">
              <span className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-pulse" />
              Early Access Open — 3 Months Free →
            </Link>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.1 }}
            className="text-5xl sm:text-6xl lg:text-7xl xl:text-8xl font-bold tracking-tight leading-[0.95] mb-6"
            style={{ fontFamily: "Outfit", letterSpacing: "-0.02em", position: "relative", zIndex: 10 }}
          >
            <span className="text-white">Make people</span>
            <br />
            <span className="relative inline-block">
              <span className="text-transparent bg-clip-text" style={{ backgroundImage: "linear-gradient(135deg, #EA580C 0%, #FF6B35 30%, #FFB347 60%, #EA580C 100%)", backgroundSize: "300% auto", animation: "shimmer 4s linear infinite", filter: "drop-shadow(0 0 30px rgba(234,88,12,0.5))" }}>
                actually show up.
              </span>
            </span>
          </motion.h1>

          <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.25 }}
            className="text-xl sm:text-2xl text-gray-400 max-w-2xl mx-auto leading-relaxed mb-10">
            You spent weeks building your webinar. 65% of your registrants won't show up — not because they forgot, but because nobody gave them a reason to care. ShowUpAI fixes that.
          </motion.p>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.35 }}
            className="flex flex-col sm:flex-row gap-3 justify-center mb-16">
            <Link to="/waitlist"
              className="group inline-flex items-center justify-center gap-2 bg-orange-600 hover:bg-orange-500 text-white font-semibold px-8 py-4 rounded-xl text-lg transition-all shadow-[0_0_40px_rgba(234,88,12,0.4)] hover:shadow-[0_0_60px_rgba(234,88,12,0.6)]">
              Start for free
              <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
            </Link>
            <a href="#how" className="inline-flex items-center justify-center gap-2 border border-white/[0.12] text-gray-300 hover:text-white hover:border-white/30 px-8 py-4 rounded-xl text-base transition-all">
              See how it works <ChevronDown size={16} />
            </a>
          </motion.div>

          {/* Stats row */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.5 }}
            className="grid grid-cols-3 gap-4 max-w-2xl mx-auto">
            {[["62%+","avg. attendance rate"],["8","AI-written touches"],["<30s","webinar setup time"]].map(([num,label]) => (
              <div key={label} className="text-center p-4 rounded-2xl border border-white/[0.06] bg-white/[0.02]">
                <div className="text-3xl sm:text-4xl font-bold text-white mb-1" style={{ fontFamily: "Outfit" }}>{num}</div>
                <div className="text-xs text-gray-500 leading-tight">{label}</div>
              </div>
            ))}
          </motion.div>
        </div>

        {/* Scroll indicator */}
        <motion.div animate={{ y: [0, 8, 0] }} transition={{ duration: 2, repeat: Infinity }}
          className="absolute bottom-8 left-1/2 -translate-x-1/2 text-gray-700">
          <ChevronDown size={24} />
        </motion.div>
      </section>

      {/* ── THE GAP ── */}
      <section className="py-24 px-6 text-center relative overflow-hidden">
        <div className="max-w-4xl mx-auto relative z-10">
          <motion.div initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.7 }}>
            <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-orange-500 mb-6">The attendance gap</div>
            <div className="flex items-center justify-center gap-8 sm:gap-16 mb-10">
              <div>
                <div className="text-7xl sm:text-9xl font-bold text-gray-700 leading-none" style={{ fontFamily: "Outfit" }}>
                  <Counter to={31} suffix="%" />
                </div>
                <div className="text-gray-600 mt-2 text-sm">Industry average</div>
              </div>
              <div className="text-4xl text-gray-700 font-thin">→</div>
              <div>
                <div className="text-7xl sm:text-9xl font-bold leading-none" style={{ fontFamily: "Outfit", color: ORANGE }}>
                  <Counter to={62} suffix="%" />
                </div>
                <div className="text-orange-500/70 mt-2 text-sm">ShowUp average</div>
              </div>
            </div>
            <p className="text-xl text-gray-400 max-w-2xl mx-auto leading-relaxed">
              Most webinar tools send one reminder. ShowUpAI sends eight — each one different, each one AI-written for your specific audience, each one designed to move someone from "maybe" to "there." It's not an email tool. It's not a webinar platform. It's the only system built exclusively to fix no-shows.
            </p>
          </motion.div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section id="how" className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-16">
            <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-orange-500 mb-4">How it works</div>
            <h2 className="text-4xl sm:text-5xl font-bold text-white" style={{ fontFamily: "Outfit" }}>From link to full room in 3 steps.</h2>
          </motion.div>
          <div className="grid md:grid-cols-3 gap-6">
            {[
              { n: "01", title: "Create your webinar", body: "Add title, date, speaker, target audience. ShowUp generates your entire 8-touch send plan in under 30 seconds." },
              { n: "02", title: "Approve AI copy", body: "Review each touch — insight, poll, case study, reminder. Pick safe or casual variant. Edit if you want, approve when ready." },
              { n: "03", title: "Watch attendance climb", body: "Touches go out automatically. Track opens, registrations, attendance by channel. See what works." },
            ].map((step, i) => (
              <motion.div key={step.n}
                initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
                transition={{ delay: i * 0.12, duration: 0.6 }}
                className="relative p-8 rounded-2xl transition-colors group" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.08)", backdropFilter: "blur(30px)", WebkitBackdropFilter: "blur(30px)", boxShadow: "0 0 0 1px rgba(255,255,255,0.04) inset, 0 20px 60px rgba(0,0,0,0.5)" }}>
                <div className="text-6xl font-bold text-white/[0.12] mb-6 select-none" style={{ fontFamily: "Outfit" }}>{step.n}</div>
                <div className="w-10 h-10 rounded-xl bg-orange-600/15 flex items-center justify-center mb-4 group-hover:bg-orange-600/25 transition-colors">
                  <Zap size={18} className="text-orange-500" />
                </div>
                <h3 className="text-xl font-bold mb-3 text-white" style={{ fontFamily: "Outfit" }}>{step.title}</h3>
                <p className="text-gray-300 leading-relaxed text-sm">{step.body}</p>
                {i < 2 && <div className="hidden md:block absolute top-1/2 -right-3 w-6 h-px bg-white/[0.1]" />}
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section id="features" className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-16">
            <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-orange-500 mb-4">Features</div>
            <h2 className="text-4xl sm:text-5xl font-bold text-white" style={{ fontFamily: "Outfit" }}>Built for one job: filling your webinar room.</h2>
          </motion.div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {FEATURES.map((f, i) => (
              <motion.div key={f.title}
                initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
                transition={{ delay: i * 0.07, duration: 0.5 }}
                className="p-6 rounded-2xl transition-all group" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)", boxShadow: "0 0 0 1px rgba(255,255,255,0.05) inset, 0 8px 32px rgba(0,0,0,0.4)" }} onMouseEnter={e => { e.currentTarget.style.background = "rgba(234,88,12,0.06)"; e.currentTarget.style.borderColor = "rgba(234,88,12,0.3)"; e.currentTarget.style.boxShadow = "0 0 0 1px rgba(234,88,12,0.1) inset, 0 8px 48px rgba(234,88,12,0.15), 0 0 80px rgba(234,88,12,0.05)"; }} onMouseLeave={e => { e.currentTarget.style.background = "rgba(255,255,255,0.03)"; e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)"; e.currentTarget.style.boxShadow = "0 0 0 1px rgba(255,255,255,0.05) inset, 0 8px 32px rgba(0,0,0,0.4)"; }}>
                <div className="w-10 h-10 rounded-xl bg-white/[0.04] flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                  <f.icon size={18} className={f.color} />
                </div>
                <h3 className="font-bold text-white mb-2" style={{ fontFamily: "Outfit" }}>{f.title}</h3>
                <p className="text-gray-300 text-sm leading-relaxed">{f.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── SOCIAL PROOF ── */}
      <section className="py-24 px-6 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-orange-950/10 to-transparent pointer-events-none" />
        <div className="max-w-6xl mx-auto relative z-10">
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-16">
            <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-orange-500 mb-4">What they say</div>
            <h2 className="text-4xl sm:text-5xl font-bold text-white" style={{ fontFamily: "Outfit" }}>Real results, real words.</h2>
          </motion.div>
          <div className="grid md:grid-cols-3 gap-5">
            {SOCIAL_PROOF.map((s, i) => (
              <motion.div key={i}
                initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.5 }}
                className="p-6 rounded-2xl" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.1)", backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)", boxShadow: "0 0 0 1px rgba(255,255,255,0.05) inset, 0 8px 32px rgba(0,0,0,0.4)" }}>
                <div className="flex gap-0.5 mb-4">
                  {[...Array(5)].map((_, j) => <Star key={j} size={14} fill="#EA580C" className="text-orange-500" />)}
                </div>
                <p className="text-gray-200 text-sm leading-relaxed mb-5 italic">"{s.quote}"</p>
                <div>
                  <div className="font-bold text-white text-sm">{s.name}</div>
                  <div className="text-gray-400 text-xs mt-0.5">{s.role}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PRICING ── */}
      <section id="pricing" className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-16">
            <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-orange-500 mb-4">Pricing</div>
            <h2 className="text-4xl sm:text-5xl font-bold text-white mb-3" style={{ fontFamily: "Outfit" }}>Simple. No surprises.</h2>
            <p className="text-gray-300">14-day free trial on all plans. No card required.</p>
          </motion.div>
          <div className="grid md:grid-cols-3 gap-5 items-start">
            {PLANS.map((plan, i) => (
              <motion.div key={plan.name}
                initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.5 }}
                className="relative rounded-2xl p-8"
                style={plan.highlight
                  ? { background: "linear-gradient(to bottom, rgba(234,88,12,0.12), rgba(234,88,12,0.04))", border: "1px solid rgba(234,88,12,0.5)", boxShadow: "0 0 0 1px rgba(234,88,12,0.2) inset, 0 0 60px rgba(234,88,12,0.2), 0 0 120px rgba(234,88,12,0.08)", backdropFilter: "blur(20px)" }
                  : { background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.1)", backdropFilter: "blur(20px)" }}>
                {plan.highlight && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 bg-orange-600 text-white text-[10px] font-bold uppercase tracking-widest px-4 py-1 rounded-full">
                    Most popular
                  </div>
                )}
                <div className="text-sm font-bold text-gray-300 mb-2 uppercase tracking-wider">{plan.name}</div>
                <div className="flex items-baseline gap-1 mb-2">
                  <span className="text-5xl font-bold text-white" style={{ fontFamily: "Outfit" }}>{plan.price}</span>
                  <span className="text-gray-500 text-sm">{plan.period}</span>
                </div>
                <p className="text-gray-300 text-sm mb-6">{plan.desc}</p>
                <Link to="/waitlist"
                  className={`block text-center py-3 rounded-xl text-sm font-semibold mb-6 transition-all ${plan.highlight
                    ? "bg-orange-600 hover:bg-orange-500 text-white shadow-[0_0_24px_rgba(234,88,12,0.4)]"
                    : "border border-white/[0.12] text-gray-300 hover:bg-white/[0.06]"}`}>
                  {plan.cta} →
                </Link>
                <ul className="space-y-3">
                  {plan.features.map(f => (
                    <li key={f} className="flex items-start gap-2.5 text-sm text-gray-200">
                      <Check size={14} className="text-orange-500 mt-0.5 shrink-0" /> {f}
                    </li>
                  ))}
                </ul>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── ABOUT ── */}
      <section id="about" className="py-24 px-6 border-t border-white/[0.04]">
        <div className="max-w-4xl mx-auto text-center">
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}>
            <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-orange-500 mb-4">About</div>
            <h2 className="text-4xl sm:text-5xl font-bold mb-6 text-white" style={{ fontFamily: "Outfit" }}>Built by marketers, for marketers.</h2>
            <p className="text-gray-200 text-lg leading-relaxed mb-4 max-w-2xl mx-auto">
              ShowUpAI was built after running webinars across education, healthcare and law enforcement communities in the UK, US and Europe — and watching the same thing happen every single time. Good topic. Good speaker. 100 registrations. 5 people show up.
            </p>
            <p className="text-gray-300 leading-relaxed max-w-2xl mx-auto">
              The difference between a 5% week and a 35% week had nothing to do with the topic or the speaker. It was entirely what happened in the 7 days before the event. ShowUpAI automates exactly that — and it takes 30 seconds to set up.
            </p>
          </motion.div>
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="py-32 px-6 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-orange-950/15 to-transparent pointer-events-none" />
        <StarField count={window.innerWidth > 768 ? 80 : 30} speed={0.2} />
        <motion.div initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
          className="relative z-10 max-w-3xl mx-auto text-center">
          <h2 className="text-5xl sm:text-7xl font-bold mb-6 leading-[0.95]" style={{ fontFamily: "Outfit", letterSpacing: "-0.02em" }}>
            <span className="text-white">Your next webinar</span><br />
            <span className="text-transparent bg-clip-text" style={{ backgroundImage: "linear-gradient(90deg, #EA580C, #FF9A3C)" }}>
              deserves a full room.
            </span>
          </h2>
          <p className="text-gray-400 text-xl mb-10">Join 100+ webinar hosts already using ShowUp. 14-day free trial, no card required.</p>
          <Link to="/waitlist"
            className="inline-flex items-center gap-2 bg-orange-600 hover:bg-orange-500 text-white font-semibold px-10 py-5 rounded-xl text-lg transition-all shadow-[0_0_60px_rgba(234,88,12,0.5)] hover:shadow-[0_0_80px_rgba(234,88,12,0.7)]">
            Get started free <ArrowRight size={20} />
          </Link>
        </motion.div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="border-t border-white/[0.06] py-10 px-6">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-orange-600 flex items-center justify-center">
              <Zap size={12} className="text-white" strokeWidth={2.5} />
            </div>
            <span className="font-bold text-white text-sm" style={{ fontFamily: "Outfit" }}>ShowUp<span className="text-orange-500">AI</span></span>
          </div>
          <div className="flex gap-6 text-sm text-gray-400">
            <a href="#features" className="hover:text-gray-400 transition-colors">Features</a>
            <a href="#pricing" className="hover:text-gray-400 transition-colors">Pricing</a>
            <a href="#about" className="hover:text-gray-400 transition-colors">About</a>
            <Link to="/blog" className="hover:text-gray-400 transition-colors">Blog</Link>
            <Link to="/login" className="hover:text-gray-400 transition-colors">Sign in</Link>
          </div>
          <div className="flex items-center gap-4">
            <a href="https://fazier.com/launches/extraordinary-cocada-bbf9a2.netlify.app" target="_blank" rel="noreferrer">
              <img src="https://fazier.com/api/v1//public/badges/launch_badges.svg?badge_type=launched&theme=dark" width={120} alt="Featured on Fazier" />
            </a>
            <a href="https://fazier.com" target="_blank" rel="noreferrer">
              <img src="https://fazier.com/api/v1//public/badges/launch_badges.svg?badge_type=featured&theme=light" width={120} alt="Fazier badge" />
            </a>
          </div>
          <div className="text-xs text-gray-500">© {new Date().getFullYear()} ShowUpAI. All rights reserved.</div>
        </div>
      </footer>

      <style>{`
        @keyframes shimmer { 0% { background-position: 0% center } 100% { background-position: 200% center } }
      `}</style>
    </div>
  );
}
