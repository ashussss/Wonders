import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import axios from "axios";
import { API_BASE } from "@/lib/api";
import ConnectHelp, { friendlyConnectError } from "@/components/ConnectHelp";

// The page an agency's client opens to connect their own LinkedIn, Facebook Page
// and email sender. No ShowUp login: the link itself says whose workspace it is.
export default function ClientConnect() {
  const { token } = useParams();
  const [params] = useSearchParams();
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [email, setEmail] = useState({ api_key: "", sender_email: "", sender_name: "" });
  const [emailMsg, setEmailMsg] = useState("");

  const base = `${API_BASE}/connect/${token}`;
  const load = () => axios.get(base).then(r => setInfo(r.data))
    .catch(e => setErr(e?.response?.data?.detail || "This link has expired. Ask for a new one."));
  useEffect(() => { load(); }, [token]);

  const oauth = async (which) => {
    setBusy(which);
    try {
      const r = await axios.post(`${base}/${which}`);
      window.location.href = r.data.authorization_url;
    } catch (e) {
      setErr(e?.response?.data?.detail || "Couldn't start the connection");
      setBusy("");
    }
  };

  const saveEmail = async (e) => {
    e.preventDefault();
    setBusy("email"); setEmailMsg("");
    try {
      await axios.post(`${base}/email`, email);
      setEmail({ api_key: "", sender_email: "", sender_name: "" });
      setEmailMsg("Saved.");
      load();
    } catch (e2) {
      setEmailMsg(e2?.response?.data?.detail || "Couldn't save");
    } finally { setBusy(""); }
  };

  const back = params.get("li_status") || params.get("meta_status");
  const backWhich = params.get("li_status") ? "linkedin" : "facebook";
  const backErr = friendlyConnectError(backWhich, params.get("li_detail") || params.get("li_error") || params.get("meta_error"));
  const failed = back === "error" ? backWhich : "";
  const doneCount = info ? [info.linkedin.connected, info.facebook.connected, info.email.connected].filter(Boolean).length : 0;

  const card = { background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: "16px", padding: "18px" };
  const input = { width: "100%", padding: "9px 12px", borderRadius: "8px", fontSize: "14px", marginTop: "6px",
                  background: "var(--bg-sunken)", border: "1px solid var(--border)", color: "var(--text-primary)" };
  const btn = { padding: "9px 14px", borderRadius: "10px", fontWeight: 700, fontSize: "14px", background: "#EA580C", color: "#fff" };
  const done = { fontSize: "13px", fontWeight: 700, color: "#16a34a" };

  return (
    <div className="min-h-screen px-4 py-10" style={{ background: "var(--bg-base)", color: "var(--text-primary)" }}>
      <div className="max-w-lg mx-auto space-y-4">
        {err && !info ? (
          <div style={card}><p>{err}</p></div>
        ) : !info ? (
          <p style={{ color: "var(--text-muted)" }}>Loading…</p>
        ) : (
          <>
            <div>
              <h1 className="text-2xl font-bold" style={{ fontFamily: "Outfit" }}>Connect {info.client_name}'s accounts</h1>
              <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
                {info.agency_name || "Your agency"} runs your webinar promotion on ShowUp AI. Connect your accounts
                here so posts and emails go out from you. Nothing is posted without being approved first.
              </p>
              <div style={{ ...card, padding: "14px", marginTop: "14px" }}>
                <div className="text-sm font-bold">3 quick steps, about 5 minutes ({doneCount} of 3 done)</div>
                <ol className="text-xs mt-2 space-y-1" style={{ color: "var(--text-secondary)" }}>
                  <li>1. LinkedIn: click Connect, log in, press Allow.</li>
                  <li>2. Facebook Page: click Connect, tick your Page (and Instagram), keep every permission on.</li>
                  <li>3. Email: paste your Brevo API key and the address you send from.</li>
                </ol>
                <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
                  Each box has "How to connect, and fixes if it's stuck" if anything looks different. You can skip a step and come back to this link later.
                </p>
              </div>
            </div>
            {back === "connected" && <div style={{ ...card, ...done }}>Connected.</div>}
            {back === "error" && <div style={{ ...card, color: "#dc2626", fontSize: "13px" }}>{backErr || "That didn't connect. Try again."}</div>}
            {err && <div style={{ ...card, color: "#dc2626", fontSize: "13px" }}>{err}</div>}

            <div style={card}>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="font-bold">LinkedIn</div>
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>Posts go on your own LinkedIn profile.</div>
                </div>
                {info.linkedin.connected
                  ? <span style={done}>✓ {info.linkedin.name || "Connected"}</span>
                  : <button style={btn} disabled={!!busy || !info.linkedin.configured} onClick={() => oauth("linkedin")}>
                      {busy === "linkedin" ? "Opening…" : "Connect"}</button>}
              </div>
              {!info.linkedin.connected && <ConnectHelp which="linkedin" open={failed === "linkedin"} />}
            </div>

            <div style={card}>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="font-bold">Facebook Page</div>
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                    Choose your Page (and its Instagram account) in the Facebook window.
                  </div>
                </div>
                {info.facebook.connected
                  ? <span style={done}>✓ {info.facebook.page_name || "Connected"}</span>
                  : <button style={btn} disabled={!!busy || !info.facebook.configured} onClick={() => oauth("facebook")}>
                      {busy === "facebook" ? "Opening…" : "Connect"}</button>}
              </div>
              {!info.facebook.connected && <ConnectHelp which="facebook" open={failed === "facebook"} />}
            </div>

            <form style={card} onSubmit={saveEmail}>
              <div className="flex items-center justify-between gap-3">
                <div className="font-bold">Email sender (Brevo)</div>
                {info.email.connected && <span style={done}>✓ {info.email.sender_email}</span>}
              </div>
              <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                Emails go out from your own address through your Brevo account (the free plan is fine).
              </p>
              {!info.email.connected && <ConnectHelp which="email" />}
              <label className="block text-xs font-semibold mt-3">Brevo API key
                <input style={input} type="password" autoComplete="off" value={email.api_key} placeholder="xkeysib-…"
                  onChange={e => setEmail({ ...email, api_key: e.target.value })} required /></label>
              <label className="block text-xs font-semibold mt-3">Send from (email)
                <input style={input} type="email" value={email.sender_email} placeholder="events@yourschool.org"
                  onChange={e => setEmail({ ...email, sender_email: e.target.value })} required /></label>
              <label className="block text-xs font-semibold mt-3">Sender name
                <input style={input} value={email.sender_name} placeholder={info.client_name}
                  onChange={e => setEmail({ ...email, sender_name: e.target.value })} /></label>
              <div className="flex items-center gap-3 mt-4">
                <button style={btn} disabled={!!busy}>{busy === "email" ? "Saving…" : info.email.connected ? "Replace" : "Save"}</button>
                {emailMsg && <span className="text-xs">{emailMsg}</span>}
              </div>
            </form>
            <p className="text-[11px] text-center" style={{ color: "var(--text-muted)" }}>Powered by ShowUp AI</p>
          </>
        )}
      </div>
    </div>
  );
}
