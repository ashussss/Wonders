import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";

/**
 * Blog lead capture (name + email).
 * variant: "card" (end of post / blog page), "inline" (mid-article), "bar" (sticky bottom, dismissible)
 */
export default function SubscribeBox({ variant = "card", slug = "", placement = "" }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [state, setState] = useState("idle"); // idle | sending | done | error
  const [msg, setMsg] = useState("");
  const [hidden, setHidden] = useState(variant === "bar");

  useEffect(() => {
    if (variant !== "bar") return;
    let dismissed = false;
    try {
      dismissed = localStorage.getItem("showup_sub_bar") === "closed" || localStorage.getItem("showup_subscribed") === "1";
    } catch (e) {}
    if (dismissed) return;
    const onScroll = () => {
      const h = document.documentElement;
      if ((h.scrollTop + window.innerHeight) / h.scrollHeight > 0.45) setHidden(false);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [variant]);

  const submit = async (e) => {
    e.preventDefault();
    if (state === "sending") return;
    setState("sending");
    setMsg("");
    try {
      await api.post("/blog/subscribe", { name, email, slug, placement: placement || variant, website });
      setState("done");
      try { localStorage.setItem("showup_subscribed", "1"); } catch (e2) {}
    } catch (err) {
      setState("error");
      setMsg(err?.response?.data?.detail || "Something went wrong. Please try again.");
    }
  };

  const close = () => {
    setHidden(true);
    try { localStorage.setItem("showup_sub_bar", "closed"); } catch (e) {}
  };

  const firstName = name.trim().split(" ")[0];
  const done = (
    <p className="text-sm font-medium" role="status">
      You're in{firstName ? `, ${firstName}` : ""}! New guides will land in your inbox.
    </p>
  );

  const fields = (compact) => (
    <form onSubmit={submit} className={`flex ${compact ? "flex-col sm:flex-row" : "flex-col sm:flex-row"} gap-2 w-full`}>
      <input
        type="text" value={website} onChange={(e) => setWebsite(e.target.value)}
        tabIndex={-1} autoComplete="off" aria-hidden="true"
        style={{ position: "absolute", left: "-9999px", width: 1, height: 1, opacity: 0 }} name="website"
      />
      <label className="sr-only" htmlFor={`sub-name-${placement || variant}`}>First name</label>
      <input
        id={`sub-name-${placement || variant}`} required value={name} onChange={(e) => setName(e.target.value)}
        placeholder="First name" autoComplete="given-name"
        className="flex-1 min-w-0 px-4 py-2.5 rounded-full border bg-white text-black text-sm outline-none focus:ring-2 focus:ring-orange-500"
      />
      <label className="sr-only" htmlFor={`sub-email-${placement || variant}`}>Work email</label>
      <input
        id={`sub-email-${placement || variant}`} required type="email" value={email} onChange={(e) => setEmail(e.target.value)}
        placeholder="Work email" autoComplete="email"
        className="flex-[1.4] min-w-0 px-4 py-2.5 rounded-full border bg-white text-black text-sm outline-none focus:ring-2 focus:ring-orange-500"
      />
      <button
        type="submit" disabled={state === "sending"}
        className="px-5 py-2.5 rounded-full bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold whitespace-nowrap disabled:opacity-60"
      >
        {state === "sending" ? "Subscribing…" : "Subscribe"}
      </button>
    </form>
  );

  const legal = <p className="text-[11px] opacity-70 mt-2">No spam. Unsubscribe anytime.</p>;
  const error = state === "error" && <p className="text-xs text-red-600 mt-2" role="alert">{msg}</p>;

  if (variant === "bar") {
    if (hidden) return null;
    return (
      <div className="fixed bottom-0 inset-x-0 z-40 border-t bg-white/95 backdrop-blur shadow-[0_-4px_20px_rgba(0,0,0,0.06)]"
        style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}>
        <div className="max-w-4xl mx-auto px-4 py-3 flex flex-col md:flex-row md:items-center gap-3 text-black">
          <p className="text-sm font-semibold md:w-64 shrink-0">Get webinar attendance guides by email</p>
          <div className="flex-1">{state === "done" ? done : fields(true)}{error}</div>
          <button onClick={close} aria-label="Close" className="absolute md:static top-2 right-3 text-xl leading-none opacity-60 hover:opacity-100">×</button>
        </div>
      </div>
    );
  }

  if (variant === "inline") {
    return (
      <aside className="my-10 p-5 rounded-xl border-l-4 border-orange-600 bg-orange-50 text-black not-prose">
        <p className="font-semibold">Enjoying this? Get the next guide in your inbox.</p>
        <p className="text-sm opacity-80 mb-3">Data-backed tactics for getting registrants to actually show up.</p>
        {state === "done" ? done : fields(true)}
        {error}
        {state !== "done" && legal}
      </aside>
    );
  }

  return (
    <section className="my-10 p-6 md:p-8 rounded-2xl bg-[#0F0F12] text-white">
      <p className="text-[11px] font-bold uppercase tracking-[0.25em] text-orange-500 mb-2">Newsletter</p>
      <h2 className="text-xl md:text-2xl font-bold mb-2" style={{ fontFamily: "Outfit" }}>
        Get more people to show up to your webinars
      </h2>
      <p className="text-sm text-gray-300 mb-5">
        Practical, number-backed guides on reminders, timing and no-shows. One email when there's something worth reading.
      </p>
      {state === "done" ? <div className="text-white">{done}</div> : fields(false)}
      {error}
      {state !== "done" && legal}
    </section>
  );
}
