import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Check, Loader2, Zap } from "@/components/Icons";

/**
 * One-step checkout from the pricing page.
 *
 * Signed out: email + password, one button. The backend creates the account
 * (or checks the password of an existing one), starts the PayPal subscription
 * and hands back a session, so we go straight to PayPal.
 * Signed in: one button.
 */
const PLANS = {
  starter: { name: "Starter", price: 29, features: ["5 webinars a month", "11-touch AI sequences", "Email + LinkedIn", "Attendance analytics"] },
  growth: { name: "Growth", price: 79, features: ["Unlimited webinars", "All channels incl. WhatsApp", "AI image cards", "Priority support"] },
  agency: { name: "Agency", price: 199, features: ["Everything in Growth", "Multi-brand workspaces", "White-label reports", "Dedicated onboarding"] },
};

export default function Checkout() {
  const { plan: planParam } = useParams();
  const [plan, setPlan] = useState(PLANS[planParam] ? planParam : "growth");
  const { user, setSession } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const p = PLANS[plan];

  const go = async (e) => {
    e?.preventDefault();
    setBusy(true); setError("");
    try {
      let data;
      if (user) {
        ({ data } = await api.post("/billing/subscribe", { plan }));
      } else {
        ({ data } = await api.post("/billing/checkout", { plan, email, password }));
        setSession(data.token, data.user);
      }
      window.location.href = data.approve_url;
    } catch (err) {
      setError(err?.response?.data?.detail || "Something went wrong. Please try again.");
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-10" style={{ background: "#050816" }}>
      <div className="w-full max-w-md">
        <Link to="/" className="flex items-center gap-2.5 justify-center mb-8">
          <div className="w-9 h-9 rounded-xl bg-orange-600 flex items-center justify-center">
            <Zap size={17} strokeWidth={2.5} className="text-white" />
          </div>
          <span className="text-xl font-bold text-white" style={{ fontFamily: "Outfit" }}>ShowUp<span className="text-orange-500">AI</span></span>
        </Link>

        <div className="rounded-2xl p-6 sm:p-8" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.1)" }}>
          {/* Plan switcher */}
          <div className="grid grid-cols-3 gap-1 p-1 rounded-xl mb-6" style={{ background: "rgba(255,255,255,0.05)" }} role="tablist">
            {Object.entries(PLANS).map(([key, v]) => (
              <button key={key} type="button" role="tab" aria-selected={plan === key} data-testid={`checkout-plan-${key}`}
                onClick={() => setPlan(key)}
                className={`py-2 rounded-lg text-sm font-semibold transition-colors ${plan === key ? "bg-orange-600 text-white" : "text-gray-300 hover:text-white"}`}>
                {v.name}
              </button>
            ))}
          </div>

          <div className="flex items-baseline gap-1 mb-1">
            <span className="text-4xl font-bold text-white" style={{ fontFamily: "Outfit" }}>${p.price}</span>
            <span className="text-gray-400 text-sm">/month</span>
          </div>
          <p className="text-gray-400 text-sm mb-5">ShowUp AI {p.name}. Billed monthly. Cancel anytime.</p>
          <ul className="space-y-2 mb-6">
            {p.features.map((f) => (
              <li key={f} className="flex items-center gap-2 text-sm text-gray-200">
                <Check size={14} className="text-orange-500 shrink-0" /> {f}
              </li>
            ))}
          </ul>

          <form onSubmit={go} className="space-y-3">
            {user ? (
              <p className="text-sm text-gray-300" data-testid="checkout-signed-in">Signed in as <span className="text-white">{user.email}</span></p>
            ) : (
              <>
                <input type="email" required autoComplete="email" placeholder="Work email" value={email}
                  onChange={(e) => setEmail(e.target.value)} data-testid="checkout-email"
                  className="w-full px-4 py-3 rounded-xl text-white placeholder-gray-500 outline-none focus:ring-2 focus:ring-orange-600"
                  style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)" }} />
                <input type="password" required minLength={8} autoComplete="new-password" placeholder="Password (8+ characters)" value={password}
                  onChange={(e) => setPassword(e.target.value)} data-testid="checkout-password"
                  className="w-full px-4 py-3 rounded-xl text-white placeholder-gray-500 outline-none focus:ring-2 focus:ring-orange-600"
                  style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)" }} />
                <p className="text-xs text-gray-500">This creates your ShowUp AI login. Already have one? Use the same email and password.</p>
              </>
            )}
            {error && <div className="text-sm text-red-400" data-testid="checkout-error">{error}</div>}
            <button type="submit" disabled={busy} data-testid="checkout-submit"
              className="w-full py-3.5 rounded-xl font-semibold text-white bg-orange-600 hover:bg-orange-500 disabled:opacity-60 flex items-center justify-center gap-2">
              {busy ? <><Loader2 size={16} className="animate-spin" /> Opening PayPal…</> : `Continue to payment · $${p.price}/mo`}
            </button>
          </form>
          <p className="text-xs text-gray-500 text-center mt-4">Secure checkout by PayPal. Pay with your PayPal balance or a debit/credit card.</p>
        </div>

        <p className="text-center text-sm text-gray-400 mt-6">
          Not ready to pay? <Link to="/register" className="text-orange-400 hover:text-orange-300">Try it free for 14 days</Link>
        </p>
      </div>
    </div>
  );
}
