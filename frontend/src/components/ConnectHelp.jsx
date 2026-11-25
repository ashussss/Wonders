import { useState } from "react";
import { ChevronDown } from "@/components/Icons";

const SUPPORT = "hello@showupai.live";

/**
 * Step-by-step help for connecting each account, plus fixes for the errors
 * people actually hit. Shared by Integrations (the user's own accounts) and
 * ClientConnect (the page an agency's client opens), so the wording stays the same.
 */
export const HELP = {
  linkedin: {
    steps: [
      "Use the browser where the right LinkedIn account is logged in. LinkedIn connects whoever is logged in there, so log out of any other LinkedIn account first (or use a private window).",
      "Click Connect, log in if LinkedIn asks, then click Allow.",
      "You land back here and the card shows Connected with the account name. Check it's the right person.",
    ],
    fixes: [
      ["LinkedIn asks for a password, but I signed up with Google",
        "LinkedIn's connect screen doesn't always offer \"Sign in with Google\". Set a password once: on linkedin.com click \"Forgot password\" (or Settings → Sign in & security → Change password), then click Connect again and log in with email + that password."],
      ["The wrong LinkedIn account got connected",
        "Click Disconnect, log out of LinkedIn in this browser, log in to the right account on linkedin.com, then click Connect again."],
      ["I want to post on our company page, not my profile",
        "This connection posts to the personal profile. Company page posting needs a separate approval from LinkedIn, so share company posts by hand for now."],
      ["It says the access ends on a date",
        "LinkedIn connections last about 60 days. When the warning shows, click Disconnect and Connect again. It takes 20 seconds."],
      ["It says cancelled or nothing happened",
        "The LinkedIn window was closed or Cancel was clicked. Click Connect again and press Allow at the end. Allow pop-ups for this site if no window opens."],
    ],
  },
  facebook: {
    before: [
      "You are an admin of the Facebook Page (Page → Settings → Page access).",
      "For Instagram: the Instagram account is a Professional account (Business or Creator) and is linked to that Facebook Page (Page → Settings → Linked accounts → Instagram).",
    ],
    steps: [
      "Click Connect and log in to Facebook with the account that manages the Page.",
      "When Facebook asks what to share, click \"Edit access\" (or \"Opt in to all\") and tick your Page and its Instagram account.",
      "Keep every permission switched on, then click Save / Continue.",
      "Back here, check the card shows your Page name and @instagram handle.",
    ],
    fixes: [
      ["\"No Facebook Pages were shared\"",
        "The Page wasn't ticked in the Facebook window. Click Connect again, choose \"Edit access\" and tick your Page."],
      ["Instagram shows \"not linked to this Page\"",
        "Switch Instagram to a Professional account and link it to the Page (see \"Before you start\"). Then Disconnect here and Connect again so Facebook shares it."],
      ["\"Missing Facebook permissions\" or \"did not grant…\"",
        "A permission was switched off in the Facebook window. Disconnect, Connect again, and leave every toggle on."],
      ["Facebook says the app isn't available, isn't active, or \"Feature unavailable\"",
        `Our Facebook app is still in Meta's review, so only invited accounts can connect. Email ${SUPPORT} with the Facebook account name. Once we invite you, accept it at developers.facebook.com/requests and click Connect again.`],
      ["I manage more than one Page",
        "Tick all of them in the Facebook window. After connecting, pick the one to post to from \"Post to Page\" on the card."],
    ],
  },
  email: {
    steps: [
      "Make a free account at brevo.com if you don't have one.",
      "In Brevo, open Senders, Domains & Dedicated IPs. Add the address you'll send from and verify it (best: verify your whole domain so emails don't land in spam).",
      "Open SMTP & API → API Keys → Generate a new API key. Copy it (it starts with xkeysib-).",
      "Paste the key and the same verified address here, then Save.",
    ],
    fixes: [
      ["\"Sender not valid\" or emails never arrive",
        "The send-from address must be exactly the one verified in Brevo. Check spelling, or verify the address in Brevo first."],
      ["The key doesn't work",
        "Use an API key (xkeysib-…), not the SMTP key (xsmtpsib-…). Generate a new one under SMTP & API → API Keys."],
    ],
  },
};

/** Turn a raw OAuth error into a sentence that says what to do. Falls back to the raw text. */
export function friendlyConnectError(which, raw) {
  const t = String(raw || "").toLowerCase();
  if (!t) return "";
  if (t.includes("cancel") || t.includes("access_denied") || t.includes("user_denied"))
    return `The ${which === "linkedin" ? "LinkedIn" : "Facebook"} window was closed or Cancel was clicked. Click Connect again and finish with Allow.`;
  if (t.includes("no facebook pages"))
    return "No Page was shared. Click Connect again, choose \"Edit access\" in the Facebook window and tick your Page (and its Instagram).";
  if (t.includes("did not grant") || t.includes("permission"))
    return raw;
  if (t.includes("not active") || t.includes("not available") || t.includes("unavailable") || t.includes("app not set up") || t.includes("development mode"))
    return `Our Facebook app is still in Meta's review, so only invited accounts can connect. Email ${SUPPORT} and we'll invite you.`;
  if (t.includes("expired") || t.includes("state"))
    return "The connect link timed out. Click Connect again and finish within a few minutes.";
  return raw;
}

/** Collapsible "Stuck? Here's how" block under a connect card. */
export default function ConnectHelp({ which, open: openDefault = false }) {
  const [open, setOpen] = useState(openDefault);
  const h = HELP[which];
  if (!h) return null;
  return (
    <div className="mt-4 pt-3" style={{ borderTop: "1px solid var(--border)" }} data-testid={`help-${which}`}>
      <button type="button" onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between text-sm font-semibold"
        style={{ color: "var(--text-secondary)" }}>
        <span>How to connect, and fixes if it's stuck</span>
        <ChevronDown size={16} style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform .15s" }} />
      </button>
      {open && (
        <div className="mt-3 space-y-4 text-sm" style={{ color: "var(--text-muted)" }}>
          {h.before && (
            <div>
              <div className="text-xs font-bold uppercase tracking-wide mb-1.5" style={{ color: "var(--text-secondary)" }}>Before you start</div>
              <ul className="space-y-1.5">
                {h.before.map(b => <li key={b} className="flex gap-2"><span className="text-orange-500">✓</span><span>{b}</span></li>)}
              </ul>
            </div>
          )}
          <div>
            <div className="text-xs font-bold uppercase tracking-wide mb-1.5" style={{ color: "var(--text-secondary)" }}>Steps</div>
            <ol className="space-y-1.5">
              {h.steps.map((s, i) => (
                <li key={s} className="flex gap-2">
                  <span className="w-5 h-5 shrink-0 rounded-full text-[11px] font-bold flex items-center justify-center text-white bg-orange-600">{i + 1}</span>
                  <span>{s}</span>
                </li>
              ))}
            </ol>
          </div>
          <div>
            <div className="text-xs font-bold uppercase tracking-wide mb-1.5" style={{ color: "var(--text-secondary)" }}>If something goes wrong</div>
            <div className="space-y-2">
              {h.fixes.map(([q, a]) => (
                <div key={q} className="rounded-lg px-3 py-2" style={{ background: "var(--bg-sunken)" }}>
                  <div className="font-semibold" style={{ color: "var(--text-primary)" }}>{q}</div>
                  <div className="mt-0.5">{a}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="text-xs">Still stuck? Email <a className="text-orange-500 underline" href={`mailto:${SUPPORT}`}>{SUPPORT}</a> with a screenshot.</div>
        </div>
      )}
    </div>
  );
}
