import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

// Agency mode: pick which client workspace you're working in. Each client has its
// own email sender, LinkedIn, Facebook, brand kit and webinars.
export default function ClientSwitcher() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/clients").then(r => setData(r.data)).catch(() => setData(null));
  useEffect(() => { load(); }, [user?.id]);

  if (!data || (!data.can_manage && !data.clients.length)) return null;

  const current = data.current === data.agency.id ? null : data.clients.find(c => c.id === data.current);

  const go = async (path, body) => {
    setBusy(true);
    try {
      const r = await api.post(path, body);
      localStorage.setItem("showup_token", r.data.token);
      window.location.href = "/app";   // reload so every page reads the new workspace
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't switch");
      setBusy(false);
    }
  };

  const add = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const r = await api.post("/clients", { name: name.trim() });
      setName(""); setAdding(false);
      await go(`/clients/${r.data.id}/switch`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't add client");
      setBusy(false);
    }
  };

  const copyLink = async (cid) => {
    try {
      const r = await api.post(`/clients/${cid}/connect-link`);
      await navigator.clipboard.writeText(r.data.url).catch(() => {});
      toast.success("Connect link copied", {
        description: `Send it to the client on WhatsApp or email. They open it, click Connect on LinkedIn and Facebook, and paste their Brevo key. No ShowUp login needed. Works for ${r.data.expires_in_days} days.`,
        duration: 9000,
      });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't make a link");
    }
  };

  const row = { width: "100%", textAlign: "left", padding: "7px 10px", borderRadius: "8px", fontSize: "12px",
                color: "var(--text-secondary)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "6px" };

  return (
    <div className="px-3 pt-3" data-testid="client-switcher">
      <button onClick={() => setOpen(o => !o)} disabled={busy}
        className="w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-semibold"
        style={{ background: current ? "rgba(234,88,12,0.12)" : "var(--bg-elevated)",
                 border: `1px solid ${current ? "rgba(234,88,12,0.45)" : "var(--border)"}`, color: "var(--text-primary)" }}>
        <span className="truncate">
          <span className="block text-[9px] uppercase tracking-[0.15em] font-bold" style={{ color: "var(--text-muted)" }}>
            {current ? "Client" : "Workspace"}
          </span>
          {current ? current.name : (data.agency.name || "My account")}
        </span>
        <span style={{ color: "var(--text-muted)" }}>{open ? "▴" : "▾"}</span>
      </button>

      {open && (
        <div className="mt-1.5 p-1.5 rounded-xl" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)" }}>
          <button style={row} disabled={busy || !current} onClick={() => go("/clients/switch-back")}>
            <span className="truncate">{data.agency.name || "My account"} <span style={{ color: "var(--text-muted)" }}>(agency)</span></span>
            {!current && <span className="text-orange-500">✓</span>}
          </button>
          {data.clients.map(c => (
            <div key={c.id} style={row}>
              <button className="truncate flex-1 text-left" disabled={busy || c.id === data.current}
                onClick={() => go(`/clients/${c.id}/switch`)}>
                {c.name} <span style={{ color: "var(--text-muted)" }}>· {c.webinars}</span>
              </button>
              {c.id === data.current && <span className="text-orange-500">✓</span>}
              <button title="Copy a link the client can use to connect their own LinkedIn, Facebook and email"
                onClick={() => copyLink(c.id)} className="text-[10px] px-1.5 py-0.5 rounded-md"
                style={{ border: "1px solid var(--border)", color: "var(--text-muted)" }}>
                Connect link
              </button>
            </div>
          ))}
          {data.can_manage && (adding ? (
            <div className="flex gap-1 mt-1">
              <input autoFocus value={name} onChange={e => setName(e.target.value)} placeholder="Client name"
                onKeyDown={e => e.key === "Enter" && add()}
                className="flex-1 min-w-0 px-2 py-1.5 rounded-md text-xs"
                style={{ background: "var(--bg-sunken)", border: "1px solid var(--border)", color: "var(--text-primary)" }} />
              <button onClick={add} disabled={busy} className="px-2 rounded-md text-xs font-bold bg-orange-600 text-white">Add</button>
            </div>
          ) : (
            <button style={{ ...row, color: "#EA580C", fontWeight: 600 }} onClick={() => setAdding(true)}>+ New client</button>
          ))}
        </div>
      )}
    </div>
  );
}
