import { useState, useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, X, Zap } from "@/components/Icons";
import { motion, AnimatePresence } from "framer-motion";

const TOUR_KEY = "showup_tour_done";

// Each step points at a real menu item, in the order a new user sets up.
// Steps whose target isn't on screen (e.g. the client switcher outside agency
// mode) are skipped, so the tour never points at nothing.
const ALL_STEPS = [
  {
    id: "welcome",
    title: "Welcome to ShowUp AI",
    body: "You add a webinar, AI writes every reminder and promo post, you approve, and ShowUp sends them on time. This tour shows where each step lives. It takes about a minute.",
    target: null,
    position: "center",
  },
  {
    id: "clients",
    title: "1. Pick whose work this is",
    body: "Running webinars for clients? Switch to the client here first. Everything you add or connect then belongs to that client. Use \"Connect link\" to let the client connect their own LinkedIn, Facebook and email.",
    target: "[data-testid='client-switcher']",
    position: "right",
  },
  {
    id: "brand",
    title: "2. Add your logo and colours",
    body: "Brand Kit: upload your logo and pick colours once. Every email and post image then goes out in your brand.",
    target: "[data-testid='nav-brand']",
    position: "right",
  },
  {
    id: "settings",
    title: "3. Connect your email sender",
    body: "Settings → Email: paste your Brevo (or SendGrid / Mailchimp) API key and the address you send from. Without this, reminder emails can't go out.",
    target: "[data-testid='nav-settings']",
    position: "right",
  },
  {
    id: "integrations",
    title: "4. Connect LinkedIn and Facebook",
    body: "Integrations: click Connect and log in. Each card has a \"Stuck?\" section with fixes for the usual errors (password, missing Page, Instagram not linked).",
    target: "[data-testid='nav-integrations']",
    position: "right",
  },
  {
    id: "create",
    title: "5. Add your webinar",
    body: "Click \"Add from Link\" and paste your Zoom, Luma or event page link. ShowUp fills in the details and writes the full reminder sequence.",
    target: "[data-testid='create-webinar-btn']",
    position: "bottom",
  },
  {
    id: "approvals",
    title: "6. Approve before anything goes out",
    body: "Approvals: read each email and post, edit if you like, then approve. Nothing is sent without your OK.",
    target: "[data-testid='nav-approvals']",
    position: "right",
  },
  {
    id: "schedule",
    title: "7. See what goes out when",
    body: "Schedule shows every approved touch on a calendar. Analytics and Email Stats show opens, clicks and who showed up.",
    target: "[data-testid='nav-schedule']",
    position: "right",
  },
  {
    id: "done",
    title: "You're ready",
    body: "Start with the \"Get set up\" checklist on your dashboard. You can replay this tour any time from \"Take the tour\" at the bottom of the menu.",
    target: null,
    position: "center",
  },
];

function visibleSteps() {
  return ALL_STEPS.filter(s => {
    if (!s.target) return true;
    const el = document.querySelector(s.target);
    return !!el && el.getClientRects().length > 0;
  });
}

function getTargetRect(selector) {
  if (!selector) return null;
  const el = document.querySelector(selector);
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  return {
    top: rect.top + window.scrollY,
    left: rect.left + window.scrollX,
    width: rect.width,
    height: rect.height,
  };
}

function TooltipBox({ step, index, total, onNext, onPrev, onSkip, targetRect }) {
  const isCenter = step.position === "center" || !targetRect;

  let style = {};
  if (isCenter) {
    style = {
      position: "fixed",
      top: "50%",
      left: "50%",
      transform: "translate(-50%, -50%)",
      zIndex: 10001,
      width: "360px",
    };
  } else if (step.position === "right" && targetRect) {
    style = {
      position: "absolute",
      top: targetRect.top + targetRect.height / 2 - 80,
      left: targetRect.left + targetRect.width + 16,
      zIndex: 10001,
      width: "300px",
    };
  } else if (step.position === "bottom" && targetRect) {
    style = {
      position: "absolute",
      top: targetRect.top + targetRect.height + 12,
      left: Math.max(16, targetRect.left - 80),
      zIndex: 10001,
      width: "320px",
    };
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ duration: 0.2 }}
      style={style}
      className="rounded-2xl shadow-2xl overflow-hidden"
    >
      {/* Header */}
      <div className="px-5 pt-5 pb-3" style={{ background: "#EA580C" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap size={16} color="white" />
            <span className="text-white text-xs font-bold uppercase tracking-wider">
              ShowUpAI Tour
            </span>
          </div>
          <button onClick={onSkip} className="text-white/70 hover:text-white transition-colors">
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="px-5 py-4" style={{ background: "#1a1a1a" }}>
        <h3 className="text-white font-bold text-base mb-2">{step.title}</h3>
        <p className="text-gray-400 text-sm leading-relaxed">{step.body}</p>

        {/* Progress dots */}
        <div className="flex gap-1.5 mt-4 mb-3">
          {Array.from({ length: total }).map((_, i) => (
            <div
              key={i}
              className="h-1 rounded-full transition-all"
              style={{
                width: i === index ? "20px" : "6px",
                background: i === index ? "#EA580C" : "#444",
              }}
            />
          ))}
        </div>

        {/* Buttons */}
        <div className="flex items-center justify-between">
          <button
            onClick={onSkip}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            Skip tour
          </button>
          <div className="flex gap-2">
            {index > 0 && (
              <button
                onClick={onPrev}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg text-gray-400 hover:text-white transition-colors"
                style={{ border: "1px solid #333" }}
              >
                <ChevronLeft size={12} /> Back
              </button>
            )}
            <button
              onClick={onNext}
              className="flex items-center gap-1 text-xs px-4 py-1.5 rounded-lg font-bold text-white transition-colors"
              style={{ background: "#EA580C" }}
            >
              {index === total - 1 ? "Done! 🚀" : "Next"} 
              {index < total - 1 && <ChevronRight size={12} />}
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export default function OnboardingTour({ forceShow = false }) {
  const [active, setActive] = useState(false);
  const [index, setIndex] = useState(0);
  const [targetRect, setTargetRect] = useState(null);
  const [STEPS, setSteps] = useState(ALL_STEPS);

  useEffect(() => {
    let done = null;
    try { done = localStorage.getItem(TOUR_KEY); } catch {}
    if (!done || forceShow) {
      // Small delay so dashboard renders first
      const t = setTimeout(() => { setSteps(visibleSteps()); setIndex(0); setActive(true); }, 800);
      return () => clearTimeout(t);
    }
  }, [forceShow]);

  useEffect(() => {
    if (!active) return;
    const step = STEPS[index];
    const rect = getTargetRect(step.target);
    setTargetRect(rect);

    // Scroll element into view
    if (step.target) {
      const el = document.querySelector(step.target);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [index, active]);

  const finish = () => {
    try { localStorage.setItem(TOUR_KEY, "1"); } catch {}
    setActive(false);
  };

  const next = () => {
    if (index < STEPS.length - 1) setIndex(i => i + 1);
    else finish();
  };

  const prev = () => {
    if (index > 0) setIndex(i => i - 1);
  };

  if (!active) return null;

  const step = STEPS[index];
  const isCenter = step.position === "center" || !targetRect;

  return (
    <AnimatePresence>
      {/* Overlay */}
      <motion.div
        key="overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0"
        style={{
          background: "rgba(0,0,0,0.65)",
          zIndex: 10000,
          backdropFilter: "blur(2px)",
        }}
        onClick={finish}
      />

      {/* Highlight box around target */}
      {targetRect && !isCenter && (
        <motion.div
          key="highlight"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          style={{
            position: "absolute",
            top: targetRect.top - 6,
            left: targetRect.left - 6,
            width: targetRect.width + 12,
            height: targetRect.height + 12,
            border: "2px solid #EA580C",
            borderRadius: "12px",
            zIndex: 10001,
            boxShadow: "0 0 0 4000px rgba(0,0,0,0.65)",
            pointerEvents: "none",
          }}
        />
      )}

      {/* Tooltip */}
      <TooltipBox
        key={`step-${index}`}
        step={step}
        index={index}
        total={STEPS.length}
        onNext={next}
        onPrev={prev}
        onSkip={finish}
        targetRect={targetRect}
      />
    </AnimatePresence>
  );
}

// Restart the tour. It lives on the dashboard, so go there.
export function useRestartTour() {
  return () => {
    try { localStorage.removeItem(TOUR_KEY); } catch {}
    window.location.href = "/app";
  };
}
