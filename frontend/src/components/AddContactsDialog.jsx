import { useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { EMAIL_RE, parseContacts } from "@/lib/contacts";
import { Check, Download, Upload, X } from "@/components/Icons";

const TEMPLATE = "Name,Email,Phone\nJane Doe,jane@example.com,+44 7700 900123\nRavi Kumar,ravi@example.com,\n";

/**
 * One place to add people to a webinar: one person at a time or many from a CSV,
 * either as invitees (not registered yet) or as registrants (signed up elsewhere).
 */
export default function AddContactsDialog({ webinar, initialKind = "invite", onClose, onDone }) {
  const [kind, setKind] = useState(initialKind);        // "invite" | "registered"
  const [how, setHow] = useState("one");                // "one" | "many"
  const [one, setOne] = useState({ name: "", email: "", phone: "" });
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState("");

  const items = how === "one"
    ? (EMAIL_RE.test(one.email.trim())
        ? [{ name: one.name.trim() || one.email.trim(), email: one.email.trim().toLowerCase(), phone: one.phone.trim() || null }]
        : [])
    : parseContacts(text, kind === "invite" ? "invite" : "import");

  const readFile = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = () => { setText(String(r.result || "")); setFileName(f.name); };
    r.readAsText(f);
    e.target.value = "";
  };

  const downloadTemplate = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv" }));
    a.download = "showup-contacts-template.csv";
    a.click();
  };

  const add = async (keepOpen) => {
    if (!items.length) return toast.error(how === "one" ? "Enter a valid email address" : "No email addresses found");
    setBusy(true);
    try {
      let msg;
      if (kind === "invite") {
        const { data: d } = await api.post(`/webinars/${webinar.id}/invitees/import`, items.map(i => ({ ...i, source: "invite" })));
        msg = `Added ${d.inserted} to the invite list` +
          (d.already_registered ? `, ${d.already_registered} already registered` : "") +
          (d.unsubscribed_before ? `, ${d.unsubscribed_before} had unsubscribed (skipped)` : "");
      } else {
        const { data: d } = await api.post(`/webinars/${webinar.id}/registrants/import`, items.map(i => ({ ...i, source: "manual" })));
        msg = `Added ${d.inserted} registrant${d.inserted === 1 ? "" : "s"}` + (d.deduped ? `, ${d.deduped} were already there` : "");
      }
      toast.success(msg);
      onDone && onDone(kind);
      if (keepOpen) {
        setResult(msg);
        setOne({ name: "", email: "", phone: "" });
      } else {
        onClose();
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't add contacts");
    } finally { setBusy(false); }
  };

  const input = "w-full rounded-xl px-3 py-2 text-sm focus:outline-none";
  const inputStyle = { background: "var(--bg-sunken)", border: "1px solid var(--border)", color: "var(--text-primary)" };
  const muted = { color: "var(--text-muted)" };
  const kinds = [
    ["invite", "Invite them", "They haven't signed up yet. They get your invite emails with the registration link (and an unsubscribe link) until they register."],
    ["registered", "Already registered", "They signed up somewhere else (your own form, Zoom, Luma). They get the join link and every reminder."],
  ];

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" data-testid="add-contacts-dialog">
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
        className="rounded-2xl p-6 w-full max-w-lg max-h-[92vh] overflow-y-auto"
        style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", boxShadow: "var(--shadow-lg)" }}>
        <div className="flex items-start justify-between gap-3 mb-1">
          <h3 className="font-bold text-lg" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>Add contacts</h3>
          <button onClick={onClose} style={muted}><X size={18} /></button>
        </div>
        <p className="text-xs mb-4" style={muted}>to "{webinar.title}"</p>

        <div className="text-xs font-bold uppercase tracking-wide mb-2" style={{ color: "var(--text-secondary)" }}>1. Who are they?</div>
        <div className="grid sm:grid-cols-2 gap-2 mb-5">
          {kinds.map(([k, label, hint]) => (
            <button key={k} type="button" onClick={() => setKind(k)} data-testid={`kind-${k}`}
              className="text-left rounded-xl p-3 transition-colors"
              style={{ border: `1.5px solid ${kind === k ? "#EA580C" : "var(--border)"}`, background: kind === k ? "rgba(234,88,12,0.08)" : "transparent" }}>
              <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                <span className="w-4 h-4 rounded-full flex items-center justify-center shrink-0"
                  style={{ background: kind === k ? "#EA580C" : "transparent", border: kind === k ? "none" : "1.5px solid var(--border)" }}>
                  {kind === k && <Check size={10} className="text-white" />}
                </span>
                {label}
              </div>
              <div className="text-xs mt-1" style={muted}>{hint}</div>
            </button>
          ))}
        </div>

        <div className="text-xs font-bold uppercase tracking-wide mb-2" style={{ color: "var(--text-secondary)" }}>2. Add them</div>
        <div className="inline-flex rounded-xl p-1 mb-3" style={{ background: "var(--bg-sunken)" }}>
          {[["one", "One person"], ["many", "Many (CSV or paste)"]].map(([k, l]) => (
            <button key={k} type="button" onClick={() => setHow(k)} data-testid={`how-${k}`}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg"
              style={{ background: how === k ? "#EA580C" : "transparent", color: how === k ? "#fff" : "var(--text-secondary)" }}>
              {l}
            </button>
          ))}
        </div>

        {how === "one" ? (
          <div className="space-y-2">
            <input className={input} style={inputStyle} placeholder="Name" value={one.name} data-testid="contact-name"
              onChange={e => setOne({ ...one, name: e.target.value })} />
            <input className={input} style={inputStyle} placeholder="Email (required)" type="email" value={one.email} data-testid="contact-email"
              onChange={e => setOne({ ...one, email: e.target.value })}
              onKeyDown={e => e.key === "Enter" && add(true)} />
            <input className={input} style={inputStyle} placeholder="Phone (optional, with country code)" value={one.phone}
              onChange={e => setOne({ ...one, phone: e.target.value })} />
          </div>
        ) : (
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <label className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer"
                style={{ border: "1px solid var(--border)", color: "var(--text-primary)" }}>
                <Upload size={13} /> {fileName || "Upload CSV"}
                <input type="file" accept=".csv,.txt,text/csv" className="hidden" onChange={readFile} data-testid="contacts-file" />
              </label>
              <button type="button" onClick={downloadTemplate} className="inline-flex items-center gap-1.5 text-xs underline" style={muted}>
                <Download size={12} /> Download a sample CSV
              </button>
            </div>
            <textarea rows={6} value={text} onChange={e => setText(e.target.value)} data-testid="contacts-paste"
              className={`${input} font-mono`} style={inputStyle}
              placeholder={"Or paste one person per line:\nJane Doe, jane@example.com\nRavi Kumar, ravi@example.com, +91 98xxxxxx"} />
            <div className="text-xs mt-1" style={muted}>
              Any column order works; we find the email, phone and name ourselves. A header row is skipped.
              Excel or Google Sheets: File → Download → CSV.
              {text && <b style={{ color: "var(--text-primary)" }}> {items.length} people found.</b>}
            </div>
          </div>
        )}

        <p className="text-[11px] mt-3" style={muted}>
          Only add people who know you or opted in to hear from you. Anyone who unsubscribed before is skipped automatically.
        </p>
        {result && <div className="text-xs mt-2 font-semibold" style={{ color: "#16a34a" }}>✓ {result}. Add the next one or click Done.</div>}

        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-xl" style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
            {result ? "Done" : "Cancel"}
          </button>
          {how === "one" && (
            <button disabled={busy || !items.length} onClick={() => add(true)}
              className="px-4 py-2 text-sm rounded-xl font-semibold disabled:opacity-50"
              style={{ border: "1px solid #EA580C", color: "#EA580C" }}>
              Add & next
            </button>
          )}
          <button data-testid="contacts-add" disabled={busy || !items.length} onClick={() => add(false)}
            className="px-4 py-2 text-sm rounded-xl font-semibold text-white bg-orange-600 hover:bg-orange-500 disabled:opacity-50">
            {busy ? "Adding…" : how === "one" ? "Add" : `Add ${items.length || ""} people`.replace("  ", " ")}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
