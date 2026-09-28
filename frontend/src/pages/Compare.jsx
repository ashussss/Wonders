import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Check, X, Zap, ArrowRight } from "@/components/Icons";

const COMPETITORS = {
  demio: {
    name: "Demio",
    tagline: "Webinar hosting platform",
    logo: "D",
    color: "#6366f1",
    description: "Demio is a webinar hosting platform focused on marketing teams running live and automated webinars.",
    their_focus: "Hosting and recording webinars",
    our_focus: "Getting registered people to actually show up",
    features: [
      { name: "AI-written reminder sequence", showup: true, them: false },
      { name: "8-touch pre-event campaign", showup: true, them: false },
      { name: "Platform-specific copy (LinkedIn vs Email)", showup: true, them: false },
      { name: "Approval queue for copy review", showup: true, them: false },
      { name: "WhatsApp delivery", showup: true, them: false },
      { name: "Circle.so integration", showup: true, them: false },
      { name: "Post-event FOMO sequence", showup: true, them: false },
      { name: "Webinar hosting", showup: false, them: true },
      { name: "Video streaming", showup: false, them: true },
      { name: "Recording", showup: false, them: true },
    ],
    verdict: "Demio helps you host webinars. ShowUp.ai helps people actually attend them. They solve different problems — if your attendance rate is already above 60%, you don't need us. If it isn't, Demio alone won't fix it.",
    stat: "Average Demio customer sees 35% attendance. ShowUp.ai users average 62%+.",
  },
  zoom: {
    name: "Zoom Webinars",
    tagline: "Video conferencing with webinar add-on",
    logo: "Z",
    color: "#2D8CFF",
    description: "Zoom Webinars is an add-on to Zoom's video conferencing platform for hosting large online events.",
    their_focus: "Video infrastructure and conferencing",
    our_focus: "Turning registrants into attendees before they even log on",
    features: [
      { name: "AI-written reminder sequence", showup: true, them: false },
      { name: "Multi-channel delivery (6 channels)", showup: true, them: false },
      { name: "Intent-based content per touch", showup: true, them: false },
      { name: "Approval queue", showup: true, them: false },
      { name: "Post-event no-show FOMO", showup: true, them: false },
      { name: "3-week warmup campaign", showup: true, them: false },
      { name: "Video conferencing", showup: false, them: true },
      { name: "Breakout rooms", showup: false, them: true },
      { name: "Up to 50,000 attendees", showup: false, them: true },
    ],
    verdict: "Zoom sends one reminder email. ShowUp.ai sends 8 intent-based touches across 6 channels. If you're using Zoom for webinars and your attendance is below 50%, add ShowUp.ai — they work together perfectly.",
    stat: "Zoom's default reminder = 1 email. ShowUp.ai = 8 platform-specific touches.",
  },
  webinarjam: {
    name: "WebinarJam",
    tagline: "All-in-one webinar platform",
    logo: "W",
    color: "#f97316",
    description: "WebinarJam is a webinar hosting platform with built-in email reminders, analytics, and marketing features.",
    their_focus: "All-in-one webinar hosting and marketing",
    our_focus: "The specific problem of turning registrants into attendees",
    features: [
      { name: "AI-written copy per channel", showup: true, them: false },
      { name: "LinkedIn + WhatsApp + Circle.so delivery", showup: true, them: false },
      { name: "Approval queue for copy control", showup: true, them: false },
      { name: "Dynamic scheduling (any date)", showup: true, them: false },
      { name: "Post-event no-show sequence", showup: true, them: false },
      { name: "Built-in email reminders", showup: true, them: true },
      { name: "Webinar hosting", showup: false, them: true },
      { name: "Evergreen automation", showup: false, them: true },
      { name: "Panic button", showup: false, them: true },
    ],
    verdict: "WebinarJam has email reminders but they're generic. ShowUp.ai writes platform-specific, intent-based content for each touch — a poll 14 days out, a case study 10 days out, a clean join link 1 hour before. The difference shows in your attendance rate.",
    stat: "Generic reminders average 31% attendance. Intent-based sequences average 62%+.",
  },
  activecampaign: {
    name: "ActiveCampaign",
    tagline: "Marketing automation platform",
    logo: "A",
    color: "#356ae6",
    description: "ActiveCampaign is a marketing automation tool used by many webinar hosts to send email sequences.",
    their_focus: "General marketing automation and CRM",
    our_focus: "Webinar attendance specifically — every feature built for one outcome",
    features: [
      { name: "Webinar-specific sequence logic", showup: true, them: false },
      { name: "AI copy generation", showup: true, them: false },
      { name: "LinkedIn + WhatsApp + Circle.so", showup: true, them: false },
      { name: "Intent-based content (poll, case study, insight)", showup: true, them: false },
      { name: "Setup in 30 seconds", showup: true, them: false },
      { name: "Email automation", showup: true, them: true },
      { name: "CRM features", showup: false, them: true },
      { name: "Sales pipelines", showup: false, them: true },
      { name: "Advanced segmentation", showup: false, them: true },
    ],
    verdict: "ActiveCampaign can send webinar reminders but you have to build the sequence yourself, write all the copy manually, and it only covers email. ShowUp.ai is purpose-built for webinar attendance — it does the whole job in 30 seconds.",
    stat: "ActiveCampaign setup for webinars: 4-6 hours. ShowUp.ai: 30 seconds.",
  },
  buffer: {
    name: "Buffer",
    tagline: "Social media scheduling tool",
    logo: "B",
    color: "#168eea",
    description: "Buffer is a social media scheduling platform that marketers use to plan and publish posts.",
    their_focus: "Scheduling existing social content",
    our_focus: "Writing AND scheduling webinar content across email + social",
    features: [
      { name: "AI writes the copy for you", showup: true, them: false },
      { name: "Email delivery included", showup: true, them: false },
      { name: "WhatsApp delivery", showup: true, them: false },
      { name: "Webinar-specific content types", showup: true, them: false },
      { name: "Intent-based sequence logic", showup: true, them: false },
      { name: "Social post scheduling", showup: true, them: true },
      { name: "Analytics dashboard", showup: false, them: true },
      { name: "Team collaboration", showup: false, them: true },
    ],
    verdict: "Buffer schedules posts you write. ShowUp.ai writes AND schedules posts designed specifically to drive webinar attendance. Two different tools for two different jobs.",
    stat: "Buffer users still write all copy manually. ShowUp.ai generates 8 touches in 30 seconds.",
  },
};

export default function Compare() {
  const { competitor } = useParams();
  const data = COMPETITORS[competitor?.toLowerCase()];
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setTimeout(() => setVisible(true), 100);
    window.scrollTo(0, 0);
  }, [competitor]);

  if (!data) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center" style={{ background: "#05050F" }}>
        <h1 className="text-3xl font-bold text-white mb-4">Comparison not found</h1>
        <Link to="/" className="text-orange-500">← Back to ShowUp.ai</Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen text-white" style={{ background: "#05050F" }}>
      {/* Nav */}
      <nav className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 font-bold text-lg">
          <span className="w-8 h-8 rounded-lg bg-orange-600 flex items-center justify-center">
            <Zap size={16} color="white" />
          </span>
          ShowUp.ai
        </Link>
        <Link to="/register" className="bg-orange-600 hover:bg-orange-500 text-white text-sm font-bold px-4 py-2 rounded-lg transition-colors">
          Start free →
        </Link>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-16">

        {/* Header */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: visible ? 1 : 0, y: visible ? 0 : 20 }} transition={{ duration: 0.5 }}>
          <p className="text-orange-500 text-sm font-bold uppercase tracking-widest mb-4">
            ShowUp.ai vs {data.name}
          </p>
          <h1 className="text-4xl md:text-5xl font-bold text-white mb-6">
            ShowUp.ai vs {data.name}:<br />
            <span className="text-orange-500">What's the difference?</span>
          </h1>
          <p className="text-xl text-gray-400 mb-12">{data.verdict}</p>
        </motion.div>

        {/* Stat highlight */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: visible ? 1 : 0 }} transition={{ delay: 0.2 }}
          className="rounded-2xl p-6 mb-12 border border-orange-500/30"
          style={{ background: "rgba(234,88,12,0.08)" }}>
          <p className="text-orange-400 font-bold text-lg">📊 {data.stat}</p>
        </motion.div>

        {/* Focus comparison */}
        <div className="grid md:grid-cols-2 gap-6 mb-12">
          <div className="rounded-2xl p-6 border border-white/10" style={{ background: "rgba(255,255,255,0.03)" }}>
            <div className="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-white mb-4 text-lg"
              style={{ background: data.color }}>
              {data.logo}
            </div>
            <h3 className="font-bold text-white mb-2">{data.name} is built for:</h3>
            <p className="text-gray-400">{data.their_focus}</p>
          </div>
          <div className="rounded-2xl p-6 border border-orange-500/30" style={{ background: "rgba(234,88,12,0.06)" }}>
            <div className="w-10 h-10 rounded-xl bg-orange-600 flex items-center justify-center mb-4">
              <Zap size={20} color="white" />
            </div>
            <h3 className="font-bold text-white mb-2">ShowUp.ai is built for:</h3>
            <p className="text-gray-400">{data.our_focus}</p>
          </div>
        </div>

        {/* Feature comparison table */}
        <h2 className="text-2xl font-bold text-white mb-6">Feature Comparison</h2>
        <div className="rounded-2xl overflow-hidden border border-white/10 mb-12">
          {/* Table header */}
          <div className="grid grid-cols-3 px-6 py-4" style={{ background: "rgba(255,255,255,0.05)" }}>
            <span className="text-gray-400 text-sm font-bold uppercase tracking-wider">Feature</span>
            <span className="text-center text-orange-400 text-sm font-bold uppercase tracking-wider">ShowUp.ai</span>
            <span className="text-center text-gray-400 text-sm font-bold uppercase tracking-wider">{data.name}</span>
          </div>
          {/* Rows */}
          {data.features.map((f, i) => (
            <div key={i} className="grid grid-cols-3 px-6 py-4 border-t border-white/5"
              style={{ background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)" }}>
              <span className="text-gray-300 text-sm">{f.name}</span>
              <span className="flex justify-center">
                {f.showup
                  ? <Check size={18} color="#22c55e" />
                  : <X size={18} color="#ef4444" />}
              </span>
              <span className="flex justify-center">
                {f.them
                  ? <Check size={18} color="#22c55e" />
                  : <X size={18} color="#ef4444" />}
              </span>
            </div>
          ))}
        </div>

        {/* Bottom CTA */}
        <div className="rounded-2xl p-8 text-center border border-orange-500/30" style={{ background: "rgba(234,88,12,0.06)" }}>
          <h2 className="text-3xl font-bold text-white mb-4">
            Ready to see 62%+ attendance?
          </h2>
          <p className="text-gray-400 mb-8 text-lg">
            Start free — no card required. Your first webinar campaign in 30 seconds.
          </p>
          <Link to="/register"
            className="inline-flex items-center gap-2 bg-orange-600 hover:bg-orange-500 text-white font-bold px-8 py-4 rounded-xl transition-colors text-lg">
            Start for free <ArrowRight size={20} />
          </Link>
        </div>

        {/* Other comparisons */}
        <div className="mt-16">
          <h3 className="text-gray-400 text-sm font-bold uppercase tracking-wider mb-4">Other comparisons</h3>
          <div className="flex flex-wrap gap-3">
            {Object.entries(COMPETITORS)
              .filter(([key]) => key !== competitor)
              .map(([key, val]) => (
                <Link key={key} to={`/compare/${key}`}
                  className="text-sm px-4 py-2 rounded-lg border border-white/10 text-gray-400 hover:text-white hover:border-white/30 transition-colors">
                  ShowUp.ai vs {val.name}
                </Link>
              ))}
          </div>
        </div>

      </div>

      {/* Footer */}
      <footer className="border-t border-white/10 py-8 text-center text-gray-500 text-sm">
        <Link to="/" className="text-orange-500 hover:text-orange-400">showupai.live</Link> — AI that makes your webinar registrants actually show up.
      </footer>
    </div>
  );
}
