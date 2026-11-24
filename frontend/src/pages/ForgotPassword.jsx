import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { ArrowRight, Mail, Zap } from "@/components/Icons";
import StarField from "@/components/StarField";

export function AuthShell({ children }) {
  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden p-6" style={{ background: "#050816" }}>
      <StarField count={140} speed={0.3} className="z-0" />
      <div className="absolute top-[-15%] left-[-8%] w-[520px] h-[520px] rounded-full pointer-events-none z-0"
        style={{ background: "radial-gradient(circle, rgba(234,88,12,0.16) 0%, transparent 70%)", filter: "blur(60px)" }} />
      <div className="relative z-10 w-full max-w-md">
        <Link to="/" className="flex items-center justify-center gap-2.5 mb-8">
          <div className="w-10 h-10 rounded-xl bg-orange-600 flex items-center justify-center shadow-[0_0_24px_rgba(234,88,12,0.4)]">
            <Zap size={20} className="text-white" strokeWidth={2.5} />
          </div>
          <span className="text-2xl font-bold tracking-tight text-white" style={{ fontFamily: "Outfit" }}>ShowUpAI</span>
        </Link>
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="bg-white/[0.04] backdrop-blur-xl border border-white/[0.08] rounded-2xl p-8 shadow-2xl">
          {children}
        </motion.div>
      </div>
    </div>
  );
}

export const authInput = "w-full bg-white/[0.03] border border-white/10 focus:border-white/60 rounded-xl px-4 py-3 text-white placeholder-white/30 focus:outline-none transition-colors";
export const authButton = "mt-6 w-full bg-orange-600 hover:bg-orange-500 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try { await api.post("/auth/forgot-password", { email }); setSent(true); }
    catch (err) { toast.error(err?.response?.data?.detail || "Could not send the reset link. Try again in a minute."); }
    finally { setBusy(false); }
  };

  return (
    <AuthShell>
      {sent ? (
        <div data-testid="forgot-sent" className="text-center">
          <div className="w-12 h-12 rounded-2xl bg-orange-600/15 text-orange-500 flex items-center justify-center mx-auto mb-4">
            <Mail size={22} />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2" style={{ fontFamily: "Outfit" }}>Check your inbox</h2>
          <p className="text-sm text-white/60 leading-relaxed">
            If <span className="text-white">{email}</span> has a ShowUp AI account, a reset link is on its way.
            It expires in 60 minutes. Check spam if you don't see it.
          </p>
          <button onClick={() => setSent(false)} className="text-sm text-white/50 hover:text-white mt-6">Use a different email</button>
        </div>
      ) : (
        <form onSubmit={submit} data-testid="forgot-form">
          <h2 className="text-3xl font-bold tracking-tight text-white mb-1" style={{ fontFamily: "Outfit" }}>Forgot password?</h2>
          <p className="text-sm text-white/50 mb-7">Enter your account email and we'll send you a link to set a new one.</p>
          <label className="text-xs font-medium text-white/60 mb-1.5 block">Email</label>
          <input data-testid="forgot-email" type="email" required autoFocus value={email}
            onChange={e => setEmail(e.target.value)} placeholder="you@company.com" className={authInput} />
          <button data-testid="forgot-submit" disabled={busy} className={authButton}
            style={{ boxShadow: "0 0 20px rgba(234,88,12,0.4)" }}>
            {busy ? "Sending…" : <>Send reset link <ArrowRight size={16} /></>}
          </button>
        </form>
      )}
      <p className="text-sm text-white/50 mt-6 text-center">
        Remembered it? <Link to="/login" className="text-white font-semibold hover:text-gray-200">Back to sign in →</Link>
      </p>
    </AuthShell>
  );
}
