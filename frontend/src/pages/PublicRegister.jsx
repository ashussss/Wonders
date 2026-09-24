import { useState } from "react";
import { CheckCircle2, Zap } from "@/components/Icons";
import { useParams } from "react-router-dom";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function PublicRegister() {
  const { wid } = useParams();
  const [form, setForm] = useState({ name: "", email: "", phone: "" });
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await axios.post(`${API}/webinars/${wid}/register`, { ...form, source: "form" });
      setDone(true);
    } catch (e) {
      setErr(e?.response?.data?.detail || "Failed to register");
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-black">
      <div className="bg-[#0A0A0A] border border-white/[0.1] rounded-md shadow-lg max-w-md w-full p-8">
        <div className="flex items-center gap-2 mb-6">
          <div className="w-8 h-8 rounded-md bg-white flex items-center justify-center"><Zap size={18} className="text-black"/></div>
          <span className="font-bold text-lg text-white" style={{fontFamily:'Outfit'}}>ShowUpAI</span>
        </div>
        {done ? (
          <div className="text-center py-6" data-testid="reg-success">
            <CheckCircle2 size={48} className="text-white mx-auto mb-3"/>
            <h2 className="text-2xl font-bold mb-1 text-white" style={{fontFamily:'Outfit'}}>You&apos;re in.</h2>
            <p className="text-gray-400">Check your inbox — a confirmation with calendar invite is on its way.</p>
          </div>
        ) : (
          <form onSubmit={submit} data-testid="public-reg-form">
            <h2 className="text-2xl font-bold mb-1 text-white" style={{fontFamily:'Outfit'}}>Reserve your seat</h2>
            <p className="text-gray-400 text-sm mb-6">Fill in your details to register for this webinar.</p>
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Name</label>
            <input data-testid="pr-name" required value={form.name} onChange={e=>setForm({...form, name:e.target.value})} className="w-full border border-white/[0.1] bg-white/[0.05] text-white rounded-md px-3 py-2 mb-3 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-white/30"/>
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Email</label>
            <input data-testid="pr-email" type="email" required value={form.email} onChange={e=>setForm({...form, email:e.target.value})} className="w-full border border-white/[0.1] bg-white/[0.05] text-white rounded-md px-3 py-2 mb-3 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-white/30"/>
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Phone (optional)</label>
            <input data-testid="pr-phone" value={form.phone} onChange={e=>setForm({...form, phone:e.target.value})} className="w-full border border-white/[0.1] bg-white/[0.05] text-white rounded-md px-3 py-2 mb-5 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-white/30"/>
            {err && <div className="text-sm text-red-500 mb-3">{err}</div>}
            <button data-testid="pr-submit" disabled={busy} className="w-full bg-white hover:bg-gray-100 text-black font-semibold py-2.5 rounded-md disabled:opacity-50">
              {busy ? "Registering…" : "Register"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
