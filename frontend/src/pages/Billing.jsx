import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, fmtDate } from "@/lib/api";
import { Check, Loader2 } from "@/components/Icons";

/**
 * Billing — PayPal subscriptions.
 *
 * Subscribe sends the user to PayPal. PayPal returns here with
 * ?paypal=success&subscription_id=..., and we confirm it with the backend,
 * which reads the subscription from PayPal before activating the plan.
 */
const FEATURES = {
  starter: ["5 webinars a month", "Email + LinkedIn", "Public registration page", "Attendance analytics"],
  growth: ["Unlimited webinars", "All channels incl. WhatsApp", "AI image cards", "Priority support"],
  agency: ["Everything in Growth", "Multi-brand workspaces", "White-label reports", "Dedicated onboarding"],
};

export default function Billing() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [params, setParams] = useSearchParams();
  const confirmed = useRef(false);

  const load = useCallback(async () => {
    try {
      const { data: d } = await api.get("/billing/status");
      setData(d);
      setError("");
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not load billing.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Back from PayPal.
  useEffect(() => {
    const result = params.get("paypal");
    if (!result || confirmed.current) return;
    confirmed.current = true;
    const subId = params.get("subscription_id");
    ["paypal", "subscription_id", "ba_token", "token"].forEach((k) => params.delete(k));
    setParams(params, { replace: true });
    if (result === "cancel") { setNotice("Checkout cancelled. No payment was taken."); return; }
    (async () => {
      setBusy("confirm");
      try {
        // PayPal can take a few seconds to mark a new subscription ACTIVE.
        for (let i = 0; i < 5; i++) {
          const { data: d } = await api.post("/billing/confirm", { subscription_id: subId });
          if (d.status === "ACTIVE") { setNotice("Payment received. Your plan is active."); break; }
          if (i === 4) setNotice("PayPal is still processing your payment. This page will update in a minute.");
          await new Promise((r) => setTimeout(r, 3000));
        }
      } catch (e) {
        setError(e?.response?.data?.detail || "Could not confirm the payment. If you were charged, contact support.");
      } finally {
        setBusy("");
        load();
      }
    })();
  }, [params, setParams, load]);

  const subscribe = async (plan) => {
    setBusy(plan); setError("");
    try {
      const { data: d } = await api.post("/billing/subscribe", { plan });
      window.location.href = d.approve_url;
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not start checkout.");
      setBusy("");
    }
  };

  const cancel = async () => {
    if (!window.confirm("Cancel your subscription? You keep access until the end of the period you paid for.")) return;
    setBusy("cancel"); setError("");
    try {
      await api.post("/billing/cancel");
      setNotice("Subscription cancelled. You won't be charged again.");
      load();
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not cancel.");
    } finally {
      setBusy("");
    }
  };

  if (loading) {
    return <div className="p-8 flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
      <Loader2 size={16} className="animate-spin" /> Loading billing…
    </div>;
  }

  const current = data?.plan;
  const subscribed = data?.reason === "subscribed";
  const trialDays = data?.trial_ends_at
    ? Math.max(0, Math.ceil((new Date(data.trial_ends_at) - new Date()) / 86400000)) : 0;

  let summary = "";
  if (data?.reason === "admin") summary = "Admin account. Billing does not apply.";
  else if (subscribed) summary = `You're on ${data.plans[current].name}. Next payment ${fmtDate(data.paid_through)}.`;
  else if (data?.reason === "paid_period") summary = `Your ${data.plans[current].name} plan is cancelled. Access ends ${fmtDate(data.paid_through)}.`;
  else if (data?.reason === "trial") summary = `Free trial: ${trialDays} day${trialDays === 1 ? "" : "s"} left. No card needed until you pick a plan.`;
  else summary = "Your free trial has ended. Pick a plan to keep creating webinars.";

  return (
    <div className="p-6 lg:p-10 max-w-5xl" data-testid="billing-page">
      <h1 className="text-3xl font-bold mb-2" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>Billing</h1>
      <p className="mb-6" style={{ color: "var(--text-secondary)" }} data-testid="billing-summary">{summary}</p>

      {data?.webinar_limit != null && (
        <p className="mb-6 text-sm" style={{ color: "var(--text-muted)" }}>
          {data.webinars_this_month} of {data.webinar_limit} webinars used this month.
        </p>
      )}
      {!data?.configured && (
        <div className="mb-6 p-4 rounded-xl text-sm" style={{ background: "rgba(180,83,9,0.1)", color: "#b45309" }}>
          Payments aren't switched on yet. Contact us and we'll set up your plan by hand.
        </div>
      )}
      {data?.env === "sandbox" && data?.configured && (
        <div className="mb-6 p-3 rounded-xl text-xs" style={{ background: "rgba(37,99,235,0.08)", color: "#2563eb" }}>
          PayPal sandbox mode: no real money is charged.
        </div>
      )}
      {error && <div className="mb-4 p-3 rounded-xl text-sm" style={{ background: "rgba(220,38,38,0.08)", color: "#dc2626" }}>{error}</div>}
      {notice && <div className="mb-4 p-3 rounded-xl text-sm" style={{ background: "rgba(22,163,74,0.08)", color: "#16a34a" }}>{notice}</div>}
      {busy === "confirm" && (
        <div className="mb-4 flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
          <Loader2 size={14} className="animate-spin" /> Confirming your payment with PayPal…
        </div>
      )}

      <div className="grid md:grid-cols-3 gap-4">
        {Object.entries(data?.plans || {}).map(([key, p]) => {
          const isCurrent = subscribed && current === key;
          return (
            <div key={key} data-testid={`plan-${key}`} className="rounded-2xl p-6 flex flex-col"
              style={{ background: "var(--bg-elevated)", border: `1px solid ${key === "growth" ? "#EA580C" : "var(--border)"}` }}>
              <div className="text-sm font-semibold mb-1" style={{ color: "var(--text-secondary)" }}>{p.name}</div>
              <div className="text-3xl font-bold mb-4" style={{ color: "var(--text-primary)" }}>
                ${Number(p.price).toFixed(0)}<span className="text-sm font-normal" style={{ color: "var(--text-muted)" }}>/mo</span>
              </div>
              <ul className="space-y-2 mb-6 flex-1">
                {(FEATURES[key] || []).map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                    <Check size={14} className="text-orange-500" /> {f}
                  </li>
                ))}
              </ul>
              {isCurrent ? (
                <button disabled className="py-2.5 rounded-xl text-sm font-semibold"
                  style={{ background: "var(--bg)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                  Current plan
                </button>
              ) : (
                <button data-testid={`subscribe-${key}`} onClick={() => subscribe(key)}
                  disabled={!!busy || !data?.configured || data?.reason === "admin"}
                  className="py-2.5 rounded-xl text-sm font-semibold text-white bg-orange-600 hover:bg-orange-500 disabled:opacity-50">
                  {busy === key ? "Opening PayPal…" : subscribed ? `Switch to ${p.name}` : `Subscribe with PayPal`}
                </button>
              )}
            </div>
          );
        })}
      </div>

      {subscribed && (
        <button data-testid="billing-cancel" onClick={cancel} disabled={!!busy}
          className="mt-8 text-sm underline" style={{ color: "var(--text-muted)" }}>
          {busy === "cancel" ? "Cancelling…" : "Cancel subscription"}
        </button>
      )}
    </div>
  );
}
