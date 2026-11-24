import { Link } from "react-router-dom";
import { AuthShell } from "@/pages/ForgotPassword";

export default function NotFound() {
  return (
    <AuthShell>
      <div className="text-center" data-testid="not-found">
        <div className="text-5xl font-bold text-white mb-2" style={{ fontFamily: "Outfit" }}>404</div>
        <p className="text-sm text-white/60 mb-6">This page doesn't exist or was moved.</p>
        <div className="flex gap-2 justify-center">
          <Link to="/app" className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold">Go to app</Link>
          <Link to="/" className="px-4 py-2 rounded-xl border border-white/15 text-white/80 hover:text-white text-sm font-semibold">Home</Link>
        </div>
      </div>
    </AuthShell>
  );
}
