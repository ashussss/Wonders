import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Check, Facebook, Instagram, Linkedin, Loader2, Plug, Unplug } from "@/components/Icons";
import { useSearchParams } from "react-router-dom";

/**
 * Integrations — each user's own social OAuth connections.
 *
 * Webinar touches (routes_delivery) publish with these connections; the manual
 * token fields in Settings stay as a fallback.
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

  useEffect(() => {
    const status = params.get("meta_status");
    if (!status) return;
    if (status === "connected") setNotice("Facebook and Instagram connected.");
    if (status === "error") setError(params.get("meta_error") || "Facebook connection failed.");
    params.delete("meta_status"); params.delete("meta_error");
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

  const mt = data?.meta;
  const metaConfigured = data?.meta_configured;

  const connectMeta = async () => {
    setBusy(true);
    try {
      const { data: d } = await api.get("/growth/integrations/meta/connect");
      window.location.href = d.authorization_url;
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not start the Facebook connection.");
      setBusy(false);
    }
  };

  const disconnectMeta = async () => {
    setBusy(true);
    try {
      await api.delete("/growth/integrations/meta");
      setNotice("Facebook and Instagram disconnected.");
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not disconnect Facebook.");
    } finally {
      setBusy(false);
    }
  };

  const selectPage = async (pageId) => {
    setBusy(true);
    try {
      await api.post("/growth/integrations/meta/page", { page_id: pageId });
      setNotice("Page updated.");
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not change the Page.");
    } finally {
      setBusy(false);
    }
  };

  const caps = data?.capabilities;

  return (
    <div className="p-6 md:p-8 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
          Social accounts
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
          Connect your accounts once. Your webinar touches post to them automatically at their scheduled time.
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
              <div className="text-xs pt-1" data-testid="linkedin-expiry"
                   style={{ color: expiresSoon(li.expires_at) ? "#b45309" : "var(--text-muted)" }}>
                {expiresSoon(li.expires_at)
                  ? `LinkedIn access ends on ${new Date(li.expires_at).toLocaleDateString("en-GB")}. Reconnect to keep posting.`
                  : `Token valid until ${new Date(li.expires_at).toLocaleDateString("en-GB")}`}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="mt-6 rounded-2xl p-5" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
           data-testid="meta-card">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl flex items-center justify-center gap-0.5"
                 style={{ background: "rgba(24,119,242,0.12)" }}>
              <Facebook size={18} className="text-[#1877F2]" />
              <Instagram size={16} className="text-[#E1306C]" />
            </div>
            <div>
              <div className="font-semibold" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
                Facebook + Instagram
              </div>
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                Facebook Page and its linked Instagram Business account
              </div>
            </div>
          </div>

          {loading ? (
            <Loader2 size={18} className="animate-spin" style={{ color: "var(--text-muted)" }} />
          ) : mt?.connected ? (
            <button data-testid="meta-disconnect" onClick={disconnectMeta} disabled={busy}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium disabled:opacity-50"
              style={{ background: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--border)" }}>
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Unplug size={15} />}
              Disconnect
            </button>
          ) : (
            <button data-testid="meta-connect" onClick={connectMeta} disabled={metaConfigured === false || busy}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white disabled:opacity-50"
              style={{ background: "#1877F2" }}>
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Plug size={15} />}
              {busy ? "Connecting…" : "Connect Facebook"}
            </button>
          )}
        </div>

        {metaConfigured === false && (
          <div data-testid="meta-not-configured" className="mt-4 text-sm" style={{ color: "#b45309" }}>
            Facebook isn’t configured on this server yet. An administrator needs to set the Meta app id,
            secret and redirect URI.
          </div>
        )}

        {mt?.connected && (
          <div data-testid="meta-connected" className="mt-5 pt-5 space-y-2" style={{ borderTop: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 text-sm font-medium" style={{ color: "#16a34a" }}>
              <Check size={15} /> Connected{mt.name ? ` as ${mt.name}` : ""}
            </div>
            <div className="text-sm" style={{ color: "var(--text-primary)" }} data-testid="meta-page">
              Facebook Page: {mt.page_name || "—"}
            </div>
            <div className="text-sm" style={{ color: mt.ig_username ? "var(--text-primary)" : "#b45309" }} data-testid="meta-ig">
              Instagram: {mt.ig_username ? `@${mt.ig_username}` : "not linked to this Page (Instagram posts will be skipped)"}
            </div>
            {(mt.pages || []).length > 1 && (
              <label className="block text-sm pt-1" style={{ color: "var(--text-muted)" }}>
                Post to Page{" "}
                <select data-testid="meta-page-select" value={mt.page_id} disabled={busy}
                  onChange={(e) => selectPage(e.target.value)}
                  className="ml-1 rounded-lg px-2 py-1 text-sm"
                  style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}>
                  {mt.pages.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}{p.ig_username ? ` (@${p.ig_username})` : ""}</option>
                  ))}
                </select>
              </label>
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

// LinkedIn gives no refresh token, so warn a week before the connection lapses.
function expiresSoon(iso) {
  return new Date(iso).getTime() - Date.now() < 7 * 24 * 3600 * 1000;
}
