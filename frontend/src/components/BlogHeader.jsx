import React from "react";
import { Link } from "react-router-dom";
import { Zap } from "@/components/Icons";

// Brand header for public blog pages: ShowUpAI logo + wordmark + CTA
export default function BlogHeader() {
  return (
    <div className="mb-8 flex items-center justify-between">
      <Link to="/" className="flex items-center gap-2.5" aria-label="ShowUpAI home">
        <span className="w-8 h-8 rounded-lg bg-orange-600 flex items-center justify-center shadow-[0_0_14px_rgba(234,88,12,0.35)]">
          <Zap size={16} strokeWidth={2.5} className="text-white" />
        </span>
        <span className="font-bold text-lg tracking-tight" style={{ fontFamily: "Outfit" }}>
          ShowUp<span className="text-orange-600">AI</span>
        </span>
      </Link>
      <Link to="/waitlist" className="px-4 py-1.5 rounded-full bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold transition-colors">
        Get more attendees
      </Link>
    </div>
  );
}
