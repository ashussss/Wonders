import React, { useEffect } from "react";
import { Link } from "react-router-dom";
import BlogHeader from "@/components/BlogHeader";

const SITE = "https://showupai.live";

export default function About() {
  useEffect(() => {
    document.title = "About ShowUpAI — Webinar Attendance Software";
    let ld = document.getElementById("about-jsonld");
    if (!ld) {
      ld = document.createElement("script");
      ld.type = "application/ld+json";
      ld.id = "about-jsonld";
      document.head.appendChild(ld);
    }
    ld.textContent = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "AboutPage",
      "@id": `${SITE}/about#webpage`,
      url: `${SITE}/about`,
      name: "About ShowUpAI",
      about: { "@id": `${SITE}/#organization` },
      isPartOf: { "@id": `${SITE}/#website` },
    });
    return () => { const el = document.getElementById("about-jsonld"); if (el) el.remove(); };
  }, []);

  return (
    <div className="max-w-2xl mx-auto p-6 text-[17px] leading-[1.75]">
      <BlogHeader />
      <h1 className="text-3xl font-bold tracking-tight mb-4" style={{ fontFamily: "Outfit" }}>About ShowUpAI</h1>
      <p className="text-lg mb-6">
        ShowUpAI is webinar attendance software. It exists for one reason: to make the people who register for your
        webinar actually show up.
      </p>

      <h2 className="text-2xl font-semibold mt-10 mb-3">What we do</h2>
      <p className="mb-4">
        You add a webinar, and ShowUpAI writes, schedules and sends an 11-touch reminder sequence across email, LinkedIn,
        Facebook, Instagram, WhatsApp/SMS, Circle.so and calendar invites. It starts three weeks before the event with
        value-led touches (an insight, a poll, a case study), moves to urgency and the join link, and ends with separate
        follow-ups for attendees and no-shows. You approve every message before it goes out.
      </p>
      <p className="mb-4">
        ShowUpAI works alongside whichever webinar platform you already use, including Zoom, Microsoft Teams, Google Meet,
        Livestorm, Circle.so events, Eventbrite and Luma.
      </p>

      <h2 className="text-2xl font-semibold mt-10 mb-3">Why we built it</h2>
      <p className="mb-4">
        Running webinars for B2B and education communities, we kept seeing the same pattern: a good topic, a good speaker,
        plenty of registrations, and a room that was mostly empty. The difference between a full session and a quiet one
        was almost always what happened between sign-up and start time. ShowUpAI automates that part.
      </p>

      <h2 className="text-2xl font-semibold mt-10 mb-3">Who's behind it</h2>
      <p className="mb-4">
        ShowUpAI is built by <strong>Ashutosh Kumar Singh</strong>, a B2B marketer with 13+ years across SEO, content,
        demand generation and events.
      </p>

      <h2 className="text-2xl font-semibold mt-10 mb-3">Facts</h2>
      <ul className="list-disc pl-6 space-y-1 mb-4">
        <li>Product: webinar attendance software (web app)</li>
        <li>Website: <a className="underline" href={SITE}>showupai.live</a></li>
        <li>Launched: 2026</li>
        <li>Plans: Starter $29/month, Growth $79/month, Agency $199/month; 14-day free trial, no card required</li>
        <li>Contact: <a className="underline" href="mailto:hello@showupai.live">hello@showupai.live</a></li>
      </ul>

      <div className="mt-10 flex flex-col sm:flex-row gap-3">
        <Link to="/waitlist" className="flex-1 text-center px-5 py-3 rounded-full bg-orange-600 hover:bg-orange-500 text-white font-semibold">
          Increase my attendance →
        </Link>
        <Link to="/blog" className="flex-1 text-center px-5 py-3 rounded-full border font-semibold hover:bg-black/5">
          Read the blog →
        </Link>
      </div>
    </div>
  );
}
