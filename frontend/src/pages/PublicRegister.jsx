import { useEffect, useState } from "react";
import { CheckCircle2 } from "@/components/Icons";
import { useParams } from "react-router-dom";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function whenText(info) {
  if (!info?.starts_at) return "";
  try {
    const d = new Date(info.starts_at);
    const opts = { weekday: "long", day: "numeric", month: "long", hour: "numeric", minute: "2-digit",
                   timeZone: info.timezone || "UTC", timeZoneName: "short" };
    return d.toLocaleString("en-GB", opts);
  } catch { return ""; }
}

// The host's sign-up page: their banner, title and date, then name + email.
// If the host set an "after sign-up" page (their own event page), people are sent
// there once they're registered here, so the host keeps both lists.
export default function PublicRegister() {
  const { wid } = useParams();
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState({ name: "", email: "", phone: "" });
  const [done, setDone] = useState(false);
  const [nextUrl, setNextUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    axios.get(`${API}/webinars/${wid}/public`).then(r => setInfo(r.data)).catch(() => setInfo({}));
  }, [wid]);

  useEffect(() => {
    if (!done || !nextUrl) return undefined;
    const t = setTimeout(() => { window.location.href = nextUrl; }, 2500);
    return () => clearTimeout(t);
  }, [done, nextUrl]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const r = await axios.post(`${API}/webinars/${wid}/register`, { ...form, source: "form" });
      setNextUrl(r.data?.next_url || info?.next_url || "");
      setDone(true);
    } catch (e) {
      setErr(e?.response?.data?.detail || "Failed to register");
    } finally { setBusy(false); }
  };

  const btn = info?.button_color || "#ffffff";
  const btnText = info?.button_text_color || (info?.button_color ? "#fff" : "#000");
  const when = whenText(info);
  const input = "w-full border border-white/[0.1] bg-white/[0.05] text-white rounded-md px-3 py-2 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-white/30";

  return (
    <div className="min-h-screen flex items-center justify-center p-4 sm:p-6 bg-black">
      <div className="bg-[#0A0A0A] border border-white/[0.1] rounded-xl shadow-lg max-w-md w-full overflow-hidden">
        {info?.has_banner && (
          <img src={`${API}/webinars/${wid}/banner.img`} alt="" className="w-full h-auto block" data-testid="pr-banner" />
        )}
        <div className="p-6 sm:p-8">
          {info?.brand_name && <div className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">{info.brand_name}</div>}
          {info?.title && <h1 className="text-2xl font-bold text-white mb-1" style={{ fontFamily: "Outfit" }} data-testid="pr-title">{info.title}</h1>}
          {when && <div className="text-sm text-gray-300 mb-1">{when}{info?.speaker ? ` · with ${info.speaker.split(",")[0]}` : ""}</div>}
          <div className="text-xs text-gray-500 mb-6">Free · Live online</div>
          {done ? (
            <div className="text-center py-4" data-testid="reg-success">
              <CheckCircle2 size={44} className="text-white mx-auto mb-3" />
              <h2 className="text-xl font-bold mb-1 text-white" style={{ fontFamily: "Outfit" }}>You&apos;re in.</h2>
              <p className="text-gray-400 text-sm">Check your inbox: your confirmation and calendar invite are on the way.</p>
              {nextUrl && (
                <a href={nextUrl} data-testid="pr-next" className="inline-block mt-5 px-5 py-2.5 rounded-md font-semibold"
                  style={{ background: btn, color: btnText }}>
                  One last step: confirm your seat on {info?.brand_name || "the event page"}
                </a>
              )}
            </div>
          ) : (
            <form onSubmit={submit} data-testid="public-reg-form" className="space-y-3">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Name</label>
                <input data-testid="pr-name" required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className={input} />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Work email</label>
                <input data-testid="pr-email" type="email" required value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} className={input} />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Phone (optional)</label>
                <input data-testid="pr-phone" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className={input} />
              </div>
              {err && <div className="text-sm text-red-500">{err}</div>}
              <button data-testid="pr-submit" disabled={busy} className="w-full font-semibold py-2.5 rounded-md disabled:opacity-50"
                style={{ background: btn, color: btnText }}>
                {busy ? "Saving your seat…" : (info?.cta_label || "Save my free seat")}
              </button>
            </form>
          )}
          <div className="text-[11px] text-gray-600 mt-6 text-center">Powered by ShowUp AI</div>
        </div>
      </div>
    </div>
  );
}
