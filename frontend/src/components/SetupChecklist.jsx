import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Check, X } from "@/components/Icons";

const HIDE_KEY = "showup_setup_hidden";

function hasEmail(s) {
  const p = (s.email_provider || "brevo").trim().toLowerCase();
  if (p === "sendgrid") return !!(s.sendgrid_api_key && s.sendgrid_sender_email);
  if (p === "mailchimp") return !!(s.mailchimp_api_key && s.mailchimp_sender_email);
  if (p === "buzzai") return !!s.buzzai_api_key;
  return !!(s.brevo_api_key && s.brevo_sender_email);
}

/** "Get set up" card on the dashboard: what still needs connecting before reminders can go out. */
export default function SetupChecklist({ webinarCount, onNewWebinar }) {
  const [state, setState] = useState(null);
  const [hidden, setHidden] = useState(() => { try { return localStorage.getItem(HIDE_KEY) === "1"; } catch { return false; } });

  useEffect(() => {
    if (hidden) return;
    Promise.allSettled([api.get("/settings"), api.get("/growth/integrations"), api.get("/brand-kit")]).then(([s, i, b]) => {
      const st = s.value?.data || {}, it = i.value?.data || {}, bk = b.value?.data || {};
      setState({
        email: hasEmail(st),
        social: !!(it.linkedin?.connected || it.meta?.connected || st.linkedin_marketing_token || st.meta_graph_token),
        brand: !!(bk.logo_url || bk.name || bk.business_name),
      });
    });
  }, [hidden]);

  if (hidden || !state) return null;
  const steps = [
    { done: state.email, label: "Connect your email sender", hint: "Brevo, SendGrid or Mailchimp, so reminders reach registrants.", to: "/app/settings", cta: "Open Settings" },
    { done: state.brand, label: "Add your logo and colours", hint: "Emails and post images go out in your brand.", to: "/app/brand", cta: "Open Brand Kit" },
    { done: state.social, label: "Connect LinkedIn or Facebook", hint: "Promo posts publish on schedule without copy-paste.", to: "/app/integrations", cta: "Connect" },
    { done: webinarCount > 0, label: "Create your first webinar", hint: "Paste the event link and AI writes every touch.", onClick: onNewWebinar, cta: "New webinar" },
  ];
  const doneCount = steps.filter(s => s.done).length;
  if (doneCount === steps.length) return null;
  const hide = () => { try { localStorage.setItem(HIDE_KEY, "1"); } catch {} setHidden(true); };

  return (
    <section data-testid="setup-checklist" className="rounded-2xl p-5 mb-6"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-lg font-bold" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>Get set up</h2>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>{doneCount} of {steps.length} done. Finish these and your reminders run on their own.</p>
        </div>
        <button onClick={hide} title="Hide" className="p-1 rounded-md" style={{ color: "var(--text-muted)" }}><X size={16} /></button>
      </div>
      <div className="h-1.5 rounded-full mb-4 overflow-hidden" style={{ background: "var(--bg-sunken)" }}>
        <div className="h-full bg-orange-600 rounded-full transition-all" style={{ width: `${(doneCount / steps.length) * 100}%` }} />
      </div>
      <ul className="space-y-2">
        {steps.map(s => (
          <li key={s.label} className="flex items-center gap-3 rounded-xl px-3 py-2.5"
            style={{ background: "var(--bg-sunken)", opacity: s.done ? 0.6 : 1 }}>
            <span className="w-6 h-6 shrink-0 rounded-full flex items-center justify-center"
              style={{ background: s.done ? "#EA580C" : "transparent", border: s.done ? "none" : "1.5px solid var(--border)" }}>
              {s.done && <Check size={13} className="text-white" />}
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold" style={{ color: "var(--text-primary)", textDecoration: s.done ? "line-through" : "none" }}>{s.label}</div>
              {!s.done && <div className="text-xs" style={{ color: "var(--text-muted)" }}>{s.hint}</div>}
            </div>
            {!s.done && (s.to
              ? <Link to={s.to} className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-white shrink-0">{s.cta}</Link>
              : <button onClick={s.onClick} className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-white shrink-0">{s.cta}</button>)}
          </li>
        ))}
      </ul>
    </section>
  );
}
