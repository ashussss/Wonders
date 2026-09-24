import { useState } from "react";
import { X } from "@/components/Icons";
import { api } from "@/lib/api";
import { toast } from "sonner";


function detectPlatform(url) {
  if (!url) return null;
  if (url.includes("zoom.us")) return { label: "Zoom", color: "#2D8CFF", emoji: "🎥" };
  if (url.includes("meet.google")) return { label: "Google Meet", color: "#00897B", emoji: "📹" };
  if (url.includes("teams.microsoft") || url.includes("teams.live")) return { label: "Microsoft Teams", color: "#6264A7", emoji: "💼" };
  if (url.includes("webex")) return { label: "Webex", color: "#00B2E3", emoji: "🌐" };
  if (url.includes("calendly")) return { label: "Calendly", color: "#006BFF", emoji: "📅" };
  if (url.includes("whereby")) return { label: "Whereby", color: "#5C6BC0", emoji: "🔗" };
  if (url.includes("streamyard")) return { label: "StreamYard", color: "#FF4081", emoji: "🎬" };
  return { label: "Custom", color: "#EA580C", emoji: "🔗" };
}

function JoinLinkInput({ value, onChange }) {
  const platform = detectPlatform(value);
  return (
    <div style={{ position: "relative" }}>
      <input
        data-testid="w-join"
        value={value}
        onChange={onChange}
        className="input"
        placeholder="Paste Zoom, Google Meet, Teams or any link…"
        style={{ paddingLeft: platform ? "36px" : "12px" }}
      />
      {platform && (
        <span style={{
          position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)",
          fontSize: "16px", lineHeight: 1
        }} title={platform.label}>
          {platform.emoji}
        </span>
      )}
      {platform && (
        <span style={{
          position: "absolute", right: "10px", top: "50%", transform: "translateY(-50%)",
          fontSize: "10px", fontWeight: 700, color: platform.color,
          background: platform.color + "18", padding: "2px 6px", borderRadius: "4px"
        }}>
          {platform.label}
        </span>
      )}
    </div>
  );
}

export default function CreateWebinarDialog({ open, onClose, onCreated }) {
  const [form, setForm] = useState({
    title: "", description: "", speaker: "", target_audience: "",
    starts_at: "", timezone: "Europe/London", join_link: "", registration_link: ""
  });
  const [busy, setBusy] = useState(false);
  if (!open) return null;

  const upd = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const dt = new Date(form.starts_at);
      const r = await api.post("/webinars", { ...form, starts_at: dt.toISOString() });
      toast.success("Webinar created. AI is drafting touches and lead magnets…");
      onCreated(r.data.id);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" data-testid="create-webinar-dialog">
      <form onSubmit={submit} className="rounded-xl max-w-2xl w-full p-6" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", boxShadow: "var(--shadow-lg)" }}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold" style={{fontFamily:"Outfit", color:"var(--text-primary)"}}>New Webinar</h2>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>AI will draft an 8-touch send plan and lead magnets automatically.</p>
          </div>
          <button type="button" onClick={onClose} data-testid="close-create-dialog" className="text-gray-400 hover:text-gray-700"><X/></button>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Title" colSpan={2}><input data-testid="w-title" required value={form.title} onChange={upd("title")} className="input"/></Field>
          <Field label="Description" colSpan={2}><textarea data-testid="w-description" required rows={3} value={form.description} onChange={upd("description")} className="input"/></Field>
          <Field label="Speaker(s)"><input data-testid="w-speaker" value={form.speaker} onChange={upd("speaker")} className="input"/></Field>
          <Field label="Target Audience"><input data-testid="w-audience" value={form.target_audience} onChange={upd("target_audience")} className="input" placeholder="e.g. EdTech suppliers"/></Field>
          <Field label="Starts At"><input data-testid="w-starts" required type="datetime-local" value={form.starts_at} onChange={upd("starts_at")} className="input"/></Field>
          <Field label="Timezone"><input data-testid="w-tz" value={form.timezone} onChange={upd("timezone")} className="input"/></Field>
          <Field label="Join Link"><JoinLinkInput value={form.join_link} onChange={upd("join_link")} /></Field>
          <Field label="Registration Link (optional)"><input data-testid="w-reg" value={form.registration_link} onChange={upd("registration_link")} className="input" placeholder="leave blank to use ShowUpAI form"/></Field>
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-md transition-colors" style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}>Cancel</button>
          <button data-testid="submit-create-webinar" disabled={busy} className="px-5 py-2 bg-orange-600 hover:bg-orange-700 text-white font-semibold rounded-md disabled:opacity-50">
            {busy ? "Creating…" : "Create & Generate AI Drafts"}
          </button>
        </div>
      </form>
      <style>{`.input{ width:100%; border:1px solid var(--border); border-radius:6px; padding:8px 12px; font-size:14px; outline:none; background:var(--bg-surface); color:var(--text-primary); }
        .input:focus{ border-color:#ea580c; box-shadow:0 0 0 2px rgba(234,88,12,0.25); }
        .input::placeholder{ color:var(--text-muted); }`}</style>
    </div>
  );
}
function Field({label, children, colSpan=1}) {
  return <label className={`block col-span-${colSpan}`}>
    <span className="block text-xs font-semibold uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>{label}</span>
    {children}
  </label>;
}
