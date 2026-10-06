import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Check, Linkedin, Loader2, Plug, Unplug } from "@/components/Icons";
import { useSearchParams } from "react-router-dom";

/**
 * Growth Engine — Integrations.
 *
 * Isolated page for the new Growth Engine OAuth connections. It does NOT touch
 * the existing social/channel settings UI, which remains untouched.
 *
 * The callback is a server redirect, so it lands back here with ?li_status=...
 * and we re-fetch status on mount.
 */
export default function Integrations() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [params, setParams] = useSearchParams();

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const { data: d } = await api.get("/growth/integrations");
      setData(d);
      setError("");
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not load integrations.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Surface the OAuth callback result, then clean the query string.
  useEffect(() => {
    const status = params.get("li_status");
    if (!status) return;
    if (status === "connected") setNotice("LinkedIn connected.");
    if (status === "error") setError(params.get("li_detail") || params.get("li_error") || "LinkedIn connection failed.");
    params.delete("li_status"); params.delete("li_error"); params.delete("li_detail");
    params.delete("li_name"); params.delete("li_sub");
    setParams(params, { replace: true });
  }, [params, setParams]);

  const li = data?.linkedin;
  const configured = data?.configured;

  const connect = async () => {
    // Fetch the authorization URL with the JWT in the Authorization HEADER, then
    // navigate. The token must never be placed in a query string (it would land
    // in browser history, referrers and access logs).
    setBusy(true);
    try {
      const { data: d } = await api.get("/growth/integrations/linkedin/connect", { params: { redirect: false } });
      window.location.href = d.authorization_url;
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not start the LinkedIn connection.");
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      await api.delete("/growth/integrations/linkedin");
      setNotice("LinkedIn disconnected.");
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not disconnect LinkedIn.");
    } finally {
      setBusy(false);
    }
  };

  const caps = data?.capabilities;

  return (
    <div className="p-6 md:p-8 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
          Growth Integrations
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
          Connect the accounts the Growth Engine will publish and report from. Each ShowUp account keeps its own connections.
        </p>
      </div>

      {notice && (
        <div data-testid="growth-notice" className="mb-4 px-4 py-3 rounded-xl text-sm"
             style={{ background: "rgba(34,197,94,0.12)", color: "#16a34a", border: "1px solid rgba(34,197,94,0.3)" }}>
          {notice}
        </div>
      )}
      {error && (
        <div data-testid="growth-error" className="mb-4 px-4 py-3 rounded-xl text-sm"
             style={{ background: "rgba(239,68,68,0.10)", color: "#dc2626", border: "1px solid rgba(239,68,68,0.3)" }}>
          {error}
        </div>
      )}
      {configured === false && (
        <div data-testid="growth-not-configured" className="mb-4 px-4 py-3 rounded-xl text-sm"
             style={{ background: "rgba(234,179,8,0.10)", color: "#b45309", border: "1px solid rgba(234,179,8,0.3)" }}>
          LinkedIn isn’t configured on this server yet. An administrator needs to set the LinkedIn
          client id, secret and redirect URI.
        </div>
      )}

      <div className="rounded-2xl p-5" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
           data-testid="linkedin-card">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl flex items-center justify-center"
                 style={{ background: "rgba(10,102,194,0.12)" }}>
              <Linkedin size={22} className="text-[#0A66C2]" />
            </div>
            <div>
              <div className="font-semibold" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
                LinkedIn
              </div>
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                Personal member account
              </div>
            </div>
          </div>

          {loading ? (
            <Loader2 size={18} className="animate-spin" style={{ color: "var(--text-muted)" }} />
          ) : li?.connected ? (
            <button data-testid="linkedin-disconnect" onClick={disconnect} disabled={busy}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium disabled:opacity-50"
              style={{ background: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--border)" }}>
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Unplug size={15} />}
              Disconnect
            </button>
          ) : (
            <button data-testid="linkedin-connect" onClick={connect} disabled={configured === false || busy}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white disabled:opacity-50"
              style={{ background: "#0A66C2" }}>
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Plug size={15} />}
              {busy ? "Connecting…" : "Connect LinkedIn"}
            </button>
          )}
        </div>

        {li?.connected && (
          <div data-testid="linkedin-connected" className="mt-5 pt-5 space-y-2"
               style={{ borderTop: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 text-sm font-medium" style={{ color: "#16a34a" }}>
              <Check size={15} /> Connected
            </div>
            <div className="text-sm" style={{ color: "var(--text-primary)" }} data-testid="linkedin-name">
              {li.name || "—"}
            </div>
            <div className="text-sm" style={{ color: "var(--text-muted)" }} data-testid="linkedin-email">
              {li.email || "—"}
            </div>
            {li.expires_at && (
              <div className="text-xs pt-1" style={{ color: "var(--text-muted)" }}>
                Token valid until {new Date(li.expires_at).toLocaleDateString("en-GB")}
              </div>
            )}
          </div>
        )}
      </div>

      {caps && (
        <div className="mt-6 rounded-2xl p-5" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
          <h2 className="font-semibold mb-3" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
            What this connection can do
          </h2>
          {[
            ["Available via API", caps.available_via_api, "#16a34a"],
            ["Requires LinkedIn approval", caps.requires_linkedin_approval, "#b45309"],
            ["Not supported by LinkedIn", caps.not_supported, "#dc2626"],
          ].map(([label, items, colour]) => (
            <div key={label} className="mb-4 last:mb-0">
              <div className="text-xs font-semibold uppercase tracking-wide mb-1.5" style={{ color: colour }}>
                {label}
              </div>
              <ul className="text-sm space-y-1" style={{ color: "var(--text-muted)" }}>
                {(items || []).map((i) => <li key={i}>• {i}</li>)}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}