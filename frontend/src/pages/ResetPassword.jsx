import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ArrowRight } from "@/components/Icons";
import { AuthShell, authButton, authInput } from "@/pages/ForgotPassword";

const MIN_LEN = 8;

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const { setSession } = useAuth();
  const nav = useNavigate();
  const [valid, setValid] = useState(null);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) { setValid(false); return; }
    api.get("/auth/reset-password/check", { params: { token } })
      .then(r => setValid(!!r.data.valid)).catch(() => setValid(false));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    if (pw.length < MIN_LEN) return toast.error(`Password must be at least ${MIN_LEN} characters`);
    if (pw !== pw2) return toast.error("Passwords don't match");
    setBusy(true);
    try {
      const r = await api.post("/auth/reset-password", { token, password: pw });
      setSession(r.data.token, r.data.user);
      toast.success("Password updated. You're signed in.");
      nav("/app");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not reset password");
    } finally { setBusy(false); }
  };

  return (
    <AuthShell>
      {valid === null && <p className="text-sm text-white/60 text-center">Checking your link…</p>}
      {valid === false && (
        <div data-testid="reset-invalid" className="text-center">
          <h2 className="text-2xl font-bold text-white mb-2" style={{ fontFamily: "Outfit" }}>Link expired</h2>
          <p className="text-sm text-white/60">This reset link is invalid, already used, or older than 60 minutes.</p>
          <Link to="/forgot-password" className={authButton}>Send a new link <ArrowRight size={16} /></Link>
        </div>
      )}
      {valid && (
        <form onSubmit={submit} data-testid="reset-form">
          <h2 className="text-3xl font-bold tracking-tight text-white mb-1" style={{ fontFamily: "Outfit" }}>Set a new password</h2>
          <p className="text-sm text-white/50 mb-7">At least {MIN_LEN} characters. You'll be signed out everywhere else.</p>
          <label className="text-xs font-medium text-white/60 mb-1.5 block">New password</label>
          <input data-testid="reset-password" type="password" required autoFocus minLength={MIN_LEN} value={pw}
            onChange={e => setPw(e.target.value)} className={authInput} autoComplete="new-password" />
          <label className="text-xs font-medium text-white/60 mb-1.5 mt-4 block">Confirm new password</label>
          <input data-testid="reset-password-confirm" type="password" required minLength={MIN_LEN} value={pw2}
            onChange={e => setPw2(e.target.value)} className={authInput} autoComplete="new-password" />
          <button data-testid="reset-submit" disabled={busy} className={authButton}
            style={{ boxShadow: "0 0 20px rgba(234,88,12,0.4)" }}>
            {busy ? "Saving…" : <>Save and sign in <ArrowRight size={16} /></>}
          </button>
        </form>
      )}
      <p className="text-sm text-white/50 mt-6 text-center">
        <Link to="/login" className="hover:text-white transition-colors">← Back to sign in</Link>
      </p>
    </AuthShell>
  );
}
