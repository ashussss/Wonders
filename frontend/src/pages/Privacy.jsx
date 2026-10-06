import React, { useEffect } from "react";
import BlogHeader from "@/components/BlogHeader";
import { MarkdownBody } from "@/pages/BlogPost";
import { PRIVACY_MD, PRIVACY_UPDATED } from "@/lib/privacyPolicy";

export default function Privacy() {
  useEffect(() => {
    document.title = "Privacy Policy | ShowUpAI";
  }, []);

  return (
    <div className="max-w-2xl mx-auto p-6 text-[17px] leading-[1.75]">
      <BlogHeader />
      <h1 className="text-3xl font-bold tracking-tight mb-2" style={{ fontFamily: "Outfit" }}>Privacy Policy</h1>
      <p className="text-sm text-gray-500 mb-6">
        Last updated <time dateTime={PRIVACY_UPDATED}>{PRIVACY_UPDATED}</time>
      </p>
      <MarkdownBody content={PRIVACY_MD} />
    </div>
  );
}
