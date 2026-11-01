import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { api, API_BASE } from "@/lib/api";
import { Globe, Sparkles, Upload, Trash2 } from "@/components/Icons";

// Fonts that look good on cards. Any Google Fonts family name also works.
const FONTS = ["", "Poppins", "Inter", "DM Sans", "Montserrat", "Lato", "Open Sans", "Raleway", "Nunito",
  "Work Sans", "Manrope", "Playfair Display", "Lora", "Merriweather", "Libre Baskerville", "Space Grotesk"];

const PREVIEWS = [["story", "Case study"], ["insights", "Tips"], ["poll", "Poll"], ["problem", "The problem"]];

const BACKEND_ROOT = API_BASE.replace(/\/api$/, "");

export default function BrandKit() {
  const [k, setK] = useState(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState("");
  const [preview, setPreview] = useState("story");
  const [cardSrc, setCardSrc] = useState("");
  const [emailHtml, setEmailHtml] = useState("");
  const [version, setVersion] = useState(0);
  const fileRef = useRef(null);

  useEffect(() => {
    api.get("/brand-kit").then(r => { setK(r.data || {}); setUrl(r.data?.website || ""); });
  }, []);

  // Re-draw the previews whenever the saved kit changes.
  useEffect(() => {
    if (!k) return;
    let revoke = "";
    api.get(`/brand-kit/preview.jpg?kind=${preview}`, { responseType: "blob" })
      .then(r => { revoke = URL.createObjectURL(r.data); setCardSrc(revoke); })
      .catch(() => setCardSrc(""));
    api.get("/brand-kit/preview-email").then(r => setEmailHtml(r.data.html)).catch(() => setEmailHtml(""));
    return () => { if (revoke) URL.revokeObjectURL(revoke); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview, version]);

  if (!k) return <div className="p-8" style={{ color: "var(--text-secondary)" }}>Loading…</div>;

  const set = (key, v) => setK({ ...k, [key]: v });
  const after = (data, msg) => { setK(data); setVersion(v => v + 1); if (msg) toast.success(msg); };
  const err = (e, fallback) => toast.error(e?.response?.data?.detail || fallback);

  const save = async () => {
    setBusy("save");
    try {
      const fields = ["business_name", "website", "primary_color", "background_color", "text_color", "font",
        "tone", "voice_sample", "audience", "cta_label", "hide_powered_by"];
      const body = Object.fromEntries(fields.map(f => [f, k[f] ?? (f === "hide_powered_by" ? false : "")]));
      after((await api.patch("/brand-kit", body)).data, "Brand kit saved. New cards and emails use it.");
    } catch (e) { err(e, "Couldn't save"); } finally { setBusy(""); }
  };

  const extract = async () => {
    if (!url.trim()) return toast.error("Enter your website address");
    setBusy("extract");
    try {
      const r = await api.post("/brand-kit/extract", { url });
      after(r.data, r.data.found?.length ? `Picked up: ${r.data.found.join(", ").replaceAll("_", " ")}. Check it and save.` : "Nothing found, fill it in by hand.");
    } catch (e) { err(e, "Couldn't read that website"); } finally { setBusy(""); }
  };

  const upload = (file) => {
    if (!file) return;
    if (file.size > 3_000_000) return toast.error("Logo must be under 3 MB");
    const reader = new FileReader();
    reader.onload = async () => {
      setBusy("logo");
      try { after((await api.post("/brand-kit/logo", { data_url: reader.result })).data, "Logo updated"); }
      catch (e) { err(e, "Couldn't use that logo"); } finally { setBusy(""); }
    };
    reader.readAsDataURL(file);
  };

  const removeLogo = async () => {
    try { after((await api.delete("/brand-kit/logo")).data, "Logo removed"); } catch (e) { err(e, "Failed"); }
  };

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
      className="p-4 sm:p-8 max-w-6xl mx-auto pb-24 min-h-screen" style={{ background: "var(--bg-base)" }}>
      <div className="text-xs font-bold uppercase tracking-[0.2em] mb-2" style={{ color: "#EA580C" }}>Your brand</div>
      <h1 className="text-3xl sm:text-4xl font-bold mb-2 tracking-tight" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>Brand Kit</h1>
      <p className="text-sm mb-6 max-w-2xl" style={{ color: "var(--text-secondary)" }}>
        Every reminder card, email and post goes out in your brand: your logo, colours, font and the way you talk.
        Your audience sees you, not us.
      </p>

      <Group title="Start from your website">
        <div className="flex flex-col sm:flex-row gap-2">
          <input data-testid="brand-url" value={url} onChange={e => setUrl(e.target.value)} className="input flex-1"
            placeholder="yourbusiness.com" onKeyDown={e => e.key === "Enter" && extract()} />
          <button data-testid="brand-extract" onClick={extract} disabled={busy === "extract"}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: "#EA580C" }}>
            <Globe size={15} /> {busy === "extract" ? "Reading your site…" : "Get my brand"}
          </button>
        </div>
        <Hint>We pick up your name, logo, colours, font and a sample of how you write. You can change anything after.</Hint>
      </Group>

      <div className="grid lg:grid-cols-[1fr_420px] gap-5 items-start">
        <div>
          <Group title="Look">
            <Row label="Business name">
              <input data-testid="brand-name" value={k.business_name || ""} onChange={e => set("business_name", e.target.value)} className="input" placeholder="Acme Physio" />
            </Row>
            <div>
              <Label>Logo</Label>
              <div className="flex items-center gap-3">
                <div className="w-40 h-16 rounded-md flex items-center justify-center overflow-hidden"
                  style={{ background: k.background_color || "#FFFFFF", border: "1px solid var(--border)" }}>
                  {k.logo_url ? <img src={`${BACKEND_ROOT}${k.logo_url}`} alt="Logo" className="max-h-12 max-w-[9rem] object-contain" />
                    : <span className="text-xs" style={{ color: "#999" }}>No logo yet</span>}
                </div>
                <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                  onChange={e => { upload(e.target.files?.[0]); e.target.value = ""; }} />
                <SmallButton onClick={() => fileRef.current?.click()} disabled={busy === "logo"}>
                  <Upload size={14} /> {busy === "logo" ? "Uploading…" : "Upload"}
                </SmallButton>
                {k.logo_url && <SmallButton onClick={removeLogo}><Trash2 size={14} /> Remove</SmallButton>}
              </div>
              <Hint>PNG with a transparent background looks best. SVG isn't supported yet, export it as PNG.</Hint>
            </div>
            <div className="grid sm:grid-cols-3 gap-3">
              <ColorField label="Brand colour" value={k.primary_color} onChange={v => set("primary_color", v)} testId="brand-primary" />
              <ColorField label="Background" value={k.background_color} onChange={v => set("background_color", v)} placeholder="#FFFFFF" testId="brand-bg" />
              <ColorField label="Text" value={k.text_color} onChange={v => set("text_color", v)} placeholder="auto" testId="brand-text" />
            </div>
            <Hint>We check contrast for you. If a colour would be hard to read, cards use a readable one instead.</Hint>
            <Row label="Font">
              <input list="brand-fonts" data-testid="brand-font" value={k.font || ""} onChange={e => set("font", e.target.value)} className="input" placeholder="Any Google Font, e.g. DM Sans" />
              <datalist id="brand-fonts">{FONTS.filter(Boolean).map(f => <option key={f} value={f} />)}</datalist>
            </Row>
          </Group>

          <Group title="Voice">
            <Row label="How you sound">
              <textarea data-testid="brand-tone" rows={2} value={k.tone || ""} onChange={e => set("tone", e.target.value)} className="input"
                placeholder="Warm and direct. Short sentences. We talk like a friend who knows their stuff, never salesy." />
            </Row>
            <Row label="Who you talk to">
              <input value={k.audience || ""} onChange={e => set("audience", e.target.value)} className="input" placeholder="Desk workers with back pain, 30 to 50" />
            </Row>
            <Row label="Paste something you wrote">
              <textarea data-testid="brand-sample" rows={6} value={k.voice_sample || ""} onChange={e => set("voice_sample", e.target.value)} className="input"
                placeholder="Two or three of your own posts or an email you sent. The AI copies your rhythm and words, not your sentences." />
            </Row>
            <Row label="Your button text">
              <input data-testid="brand-cta" value={k.cta_label || ""} onChange={e => set("cta_label", e.target.value)} className="input" placeholder="Save my spot" />
            </Row>
            <Hint>Used on email buttons and in how posts point to your link. Copy still follows our rules: human, plain words, a hook in the first line, no hype.</Hint>
          </Group>

          <Group title="ShowUp AI mark">
            <label className={`flex items-start gap-3 text-sm ${k.can_hide_powered_by ? "" : "opacity-60"}`} style={{ color: "var(--text-secondary)" }}>
              <input type="checkbox" className="mt-1" disabled={!k.can_hide_powered_by} checked={!!k.hide_powered_by}
                onChange={e => set("hide_powered_by", e.target.checked)} data-testid="brand-hide-mark" />
              <span>
                Hide the small "Powered by ShowUp AI" line on cards and emails.
                {!k.can_hide_powered_by && <> Available on the <a href="/app/billing" className="underline">Agency plan</a> (white-label).</>}
              </span>
            </label>
          </Group>

          <button data-testid="brand-save" onClick={save} disabled={busy === "save"}
            className="w-full sm:w-auto px-6 py-2.5 rounded-md text-sm font-semibold text-white disabled:opacity-60" style={{ background: "#EA580C" }}>
            {busy === "save" ? "Saving…" : "Save brand kit"}
          </button>
        </div>

        <div className="lg:sticky lg:top-6">
          <Group title="Preview">
            <div className="flex flex-wrap gap-1.5 mb-1">
              {PREVIEWS.map(([key, label]) => (
                <button key={key} onClick={() => setPreview(key)} className="text-xs px-2.5 py-1 rounded-md"
                  style={{ border: "1px solid var(--border)", background: preview === key ? "#EA580C" : "var(--bg-surface)", color: preview === key ? "#fff" : "var(--text-secondary)" }}>
                  {label}
                </button>
              ))}
            </div>
            {cardSrc ? <img src={cardSrc} alt="Card preview" className="w-full rounded-md" style={{ border: "1px solid var(--border)" }} />
              : <div className="aspect-[4/5] rounded-md flex items-center justify-center text-xs" style={{ background: "var(--bg-sunken)", color: "var(--text-muted)" }}><Sparkles size={14} />&nbsp;Drawing…</div>}
            <Hint>Save to update the preview. Cards already made are redrawn in your brand the next time they send.</Hint>
            <Label>Reminder email</Label>
            {emailHtml && <iframe title="Email preview" srcDoc={emailHtml} sandbox="" className="w-full h-80 rounded-md bg-white" style={{ border: "1px solid var(--border)" }} />}
          </Group>
        </div>
      </div>
    </motion.div>
  );
}

function ColorField({ label, value, onChange, placeholder = "#0E7C66", testId }) {
  const valid = /^#[0-9a-fA-F]{6}$/.test(value || "");
  return (
    <div>
      <Label>{label}</Label>
      <div className="flex items-center gap-2">
        <input type="color" value={valid ? value : "#ffffff"} onChange={e => onChange(e.target.value.toUpperCase())}
          className="w-10 h-10 rounded cursor-pointer" style={{ border: "1px solid var(--border)", padding: 2 }} />
        <input data-testid={testId} value={value || ""} onChange={e => onChange(e.target.value)} className="input flex-1 font-mono" placeholder={placeholder} />
      </div>
    </div>
  );
}

function Group({ title, children }) {
  return <section className="rounded-md p-5 mb-5" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
    <h2 className="text-lg font-semibold mb-4" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>{title}</h2>
    <div className="space-y-3">{children}</div>
  </section>;
}
function Label({ children }) {
  return <span className="block text-xs font-semibold uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>{children}</span>;
}
function Row({ label, children }) {
  return <label className="block"><Label>{label}</Label>{children}</label>;
}
function Hint({ children }) {
  return <p className="text-xs" style={{ color: "var(--text-muted)" }}>{children}</p>;
}
function SmallButton({ children, ...p }) {
  return <button type="button" {...p} className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 font-semibold rounded-md disabled:opacity-50"
    style={{ border: "1px solid var(--border)", background: "var(--bg-surface)", color: "var(--text-secondary)" }}>{children}</button>;
}
