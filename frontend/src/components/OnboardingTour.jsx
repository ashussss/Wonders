import { useState, useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, X, Zap } from "@/components/Icons";
import { motion, AnimatePresence } from "framer-motion";

const TOUR_KEY = "showup_tour_done";

const STEPS = [
  {
    id: "welcome",
    title: "Welcome to ShowUp.ai! ⚡",
    body: "Let's get you set up in 2 minutes. This quick tour will show you everything you need to double your webinar attendance.",
    target: null,
    position: "center",
  },
  {
    id: "dashboard",
    title: "Your Control Room",
    body: "This is your dashboard — see all your webinars, registrants, and attendance rates at a glance.",
    target: "[data-testid='nav-dashboard']",
    position: "right",
  },
  {
    id: "create",
    title: "Create Your First Webinar",
    body: "Click '+ New Webinar' or '🔗 Add from Link' to paste any webinar URL. ShowUp will auto-fill the details and generate your 8-touch AI sequence.",
    target: "[data-testid='create-webinar-btn']",
    position: "bottom",
  },
  {
    id: "approvals",
    title: "Approve AI Copy",
    body: "AI writes 8 different touches — confirmation, insight, poll, case study and more. You review and approve before anything goes out.",
    target: "[data-testid='nav-approvals']",
    position: "right",
  },
  {
    id: "settings",
    title: "Connect Your Channels",
    body: "Go to Settings to connect Brevo (email), Circle.so, WhatsApp and more. Takes 2 minutes — then everything sends automatically.",
    target: "[data-testid='nav-settings']",
    position: "right",
  },
  {
    id: "done",
    title: "You're ready! 🎉",
    body: "Create your first webinar and watch your attendance climb from 31% to 62%+. Need help? The tour is always available from the menu.",
    target: null,
    position: "center",
  },
];

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
              ShowUp.ai Tour
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
          {STEPS.map((_, i) => (
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

  useEffect(() => {
    const done = localStorage.getItem(TOUR_KEY);
    if (!done || forceShow) {
      // Small delay so dashboard renders first
      setTimeout(() => setActive(true), 800);
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
    localStorage.setItem(TOUR_KEY, "1");
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

// Hook to restart tour
export function useRestartTour() {
  return () => {
    localStorage.removeItem(TOUR_KEY);
    window.location.reload();
  };
}
