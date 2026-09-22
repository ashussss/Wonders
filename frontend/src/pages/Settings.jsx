import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useTheme } from "@/lib/theme";

const TOUCHES = [
  { num: 1, name: "Registration confirmation" },
  { num: 2, name: "7-day announcement" },
  { num: 3, name: "3-day fresh angle" },
  { num: 4, name: "1-day urgency" },
  { num: 5, name: "3 hours before" },
  { num: 6, name: "15 minutes before" },
  { num: 7, name: "Post-event thank-you (attendees)" },
  { num: 8, name: "Post-event re-engagement (no-shows)" },
];

const ALL_CHANNELS = [
  ["email","Email"],["linkedin","LinkedIn Page"],["linkedin_personal","LinkedIn (manual)"],
  ["facebook","Facebook Page"],["instagram","Instagram"],["whatsapp","WhatsApp/SMS"],["circle","Circle.so"]
];

export default function Settings() {
  const { isDark } = useTheme();
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/settings").then(r => setS(r.data || {})); }, []);

  if (!s) return <div className="p-8" style={{ color: "var(--text-secondary)" }}>Loading…</div>;

  const save = async () => {
    await api.patch("/settings", s);
    toast.success("Settings saved");
  };
  const set = (k, v) => setS({ ...s, [k]: v });
  const toggleDefaultTouch = (n) => {
    const dt = { ...(s.default_touches || {}) };
    dt[n] = !dt[n];
    set("default_touches", dt);
  };
  const toggleChannel = (n, ch) => {
    const dc = { ...(s.default_channels || {}) };
    const list = dc[n] || [];
    dc[n] = list.includes(ch) ? list.filter(c=>c!==ch) : [...list, ch];
    set("default_channels", dc);
  };
  const toggleAuto = (n) => {
    const a = { ...(s.per_touch_auto_send || {}) };
    a[n] = !a[n];
    set("per_touch_auto_send", a);
  };

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="p-4 sm:p-8 max-w-5xl mx-auto pb-24 min-h-screen" style={{ background: "var(--bg-base)" }}>
      <div className="text-xs font-bold uppercase tracking-[0.2em] text-white mb-2">Configuration</div>
      <h1 className="text-3xl sm:text-4xl font-bold mb-6 tracking-tight" style={{fontFamily:'Outfit', color: "var(--text-primary)"}}>Settings</h1>

      <Group title="Email provider">
        <Row label="Active provider"><select data-testid="set-email-provider" value={s.email_provider||""} onChange={e=>set("email_provider", e.target.value)} className="input">
          <option value="">— select —</option><option>Brevo</option><option>Mailchimp</option><option>SendHome</option><option>BuzzAI</option>
        </select></Row>
        <Field label="Brevo API Key" k="brevo_api_key" s={s} set={set}/>
        <Row label="Brevo Sender Email"><input data-testid="set-brevo_sender_email" type="email" value={s.brevo_sender_email||""} onChange={e=>set("brevo_sender_email", e.target.value)} placeholder="hello@yourbrand.com" className="input"/></Row>
        <Row label="Brevo Sender Name"><input data-testid="set-brevo_sender_name" value={s.brevo_sender_name||""} onChange={e=>set("brevo_sender_name", e.target.value)} placeholder="ShowUp.ai" className="input"/></Row>
        <Field label="Mailchimp API Key" k="mailchimp_api_key" s={s} set={set} hint="Mandrill transactional API key (e.g. md-xxx)."/>
        <Row label="Mailchimp Sender Email"><input data-testid="set-mailchimp_sender_email" type="email" value={s.mailchimp_sender_email||""} onChange={e=>set("mailchimp_sender_email", e.target.value)} className="input" placeholder="hello@yourbrand.com"/></Row>
        <Field label="SendLayoutDashboard API Key" k="sendgrid_api_key" s={s} set={set} hint="Starts with 'SG.'"/>
        <Row label="SendLayoutDashboard Sender Email"><input data-testid="set-sendgrid_sender_email" type="email" value={s.sendgrid_sender_email||""} onChange={e=>set("sendgrid_sender_email", e.target.value)} className="input" placeholder="hello@yourbrand.com"/></Row>
        <TestSend label="Send test email to my account" channel="email" testId="test-send-email"/>
      </Group>

      <Group title="Buzz.ai (custom outreach endpoint)">
        <Banner>Buzz.ai does not publish a public REST API. Ask Buzz support for the endpoint URL + auth header convention, then paste below. Same key is used for email and LinkedIn channels.</Banner>
        <Field label="Buzz.ai API Key" k="buzzai_api_key" s={s} set={set}/>
        <Row label="Email Endpoint URL"><input data-testid="set-buzzai_email_endpoint" value={s.buzzai_email_endpoint||""} onChange={e=>set("buzzai_email_endpoint", e.target.value)} placeholder="https://api.buzz.ai/v1/email/send" className="input"/></Row>
        <Row label="LinkedIn Endpoint URL"><input data-testid="set-buzzai_linkedin_endpoint" value={s.buzzai_linkedin_endpoint||""} onChange={e=>set("buzzai_linkedin_endpoint", e.target.value)} placeholder="https://api.buzz.ai/v1/linkedin/post" className="input"/></Row>
        <Row label="Auth Header Name (default: Authorization)"><input data-testid="set-buzzai_auth_header_name" value={s.buzzai_auth_header_name||""} onChange={e=>set("buzzai_auth_header_name", e.target.value)} placeholder="Authorization" className="input"/></Row>
        <Row label="Auth Header Prefix (default: 'Bearer ')"><input data-testid="set-buzzai_auth_header_prefix" value={s.buzzai_auth_header_prefix||""} onChange={e=>set("buzzai_auth_header_prefix", e.target.value)} placeholder="Bearer " className="input"/></Row>
        <TestSend label="Test Buzz.ai email endpoint" channel="email" testId="test-buzzai-email"/>
      </Group>

      <Group title="LinkedIn">
        <Row label="LinkedIn provider for posting"><select data-testid="set-linkedin_provider" value={s.linkedin_provider||"marketing_api"} onChange={e=>set("linkedin_provider", e.target.value)} className="input">
          <option value="marketing_api">LinkedIn Marketing API (default)</option>
          <option value="buzzai">Buzz.ai (uses your Buzz.ai endpoint above)</option>
        </select></Row>
        <Field label="LinkedIn Marketing API Token" k="linkedin_marketing_token" s={s} set={set}/>
        <Row label="LinkedIn Organization URN"><input data-testid="set-linkedin_org_urn" value={s.linkedin_org_urn||""} onChange={e=>set("linkedin_org_urn", e.target.value)} placeholder="urn:li:organization:1234567" className="input"/></Row>
        <Field label="LinkedIn Events API Token (best-effort)" k="linkedin_events_token" s={s} set={set} hint="LinkedIn restricts Events API to approved partners. Manual paste-import is the realistic default."/>
        <Banner>No auto-posting to personal LinkedIn profiles. The app drafts the post and provides a Copy &amp; Paste button.</Banner>
      </Group>

      <Group title="Meta (Facebook + Instagram)">
        <Field label="Meta Graph API Token" k="meta_graph_token" s={s} set={set}/>
        <Field label="Facebook Page ID" k="meta_page_id" s={s} set={set}/>
        <Field label="Instagram Business Account ID" k="instagram_business_id" s={s} set={set} hint="Instagram must be a Business/Creator account linked to the Facebook Page."/>
      </Group>

      <Group title="WhatsApp / SMS (Twilio, optional)">
        <Field label="Twilio Account SID" k="twilio_sid" s={s} set={set}/>
        <Field label="Twilio Auth Token" k="twilio_token" s={s} set={set}/>
        <Field label="Twilio From Number" k="twilio_from" s={s} set={set}/>
        <TestSend label="Send test WhatsApp" channel="whatsapp" testId="test-send-whatsapp" needPhone/>
      </Group>

      <Group title="Circle.so">
        <Field label="Circle.so API Key" k="circle_api_key" s={s} set={set} hint="Admin token from Circle → Developers → Tokens."/>
        <Row label="Space ID (numeric)"><div className="flex gap-2 items-center">
          <input data-testid="set-circle_space_id" value={s.circle_space_id||""} onChange={e=>set("circle_space_id", e.target.value)} placeholder="123456" className="input flex-1"/>
          <CircleSpacesPicker onPick={(id)=>set("circle_space_id", String(id))}/>
        </div></Row>
        <div className="flex flex-wrap gap-2">
          <CircleSync/>
          <CircleDiagnose/>
          <TestSend label="Test post to Circle space" channel="circle" testId="test-send-circle"/>
        </div>
        <div className="text-xs rounded-md p-3" style={{ color: "var(--text-secondary)", background: "var(--bg-sunken)", border: "1px solid var(--border)" }}>
          <div className="font-semibold mb-1" style={{ color: "var(--text-primary)" }}>Webhook URL for Circle.so (member_created event):</div>
          <code className="text-xs">{process.env.REACT_APP_BACKEND_URL}/api/webinars/&lt;webinar_id&gt;/webhooks/circle</code>
          <div className="mt-1" style={{ color: "var(--text-muted)" }}>Accepts the official Circle <code>community_member_created</code> payload <code>{`{community_member:{email,name,...}}`}</code> or a flat <code>{`{email,name}`}</code> object.</div>
        </div>
      </Group>

      <Group title="Brand Voice &amp; AI Instructions">
        <Banner>These instructions are injected into every AI generation. Set your tone once — applies to all webinars and all touches.</Banner>
        <Row label="Brand Tone">
          <select value={s.brand_tone||"professional"} onChange={e=>set("brand_tone",e.target.value)} className="input">
            <option value="professional">Professional — formal, authoritative, trust-building</option>
            <option value="friendly">Friendly — warm, approachable, conversational</option>
            <option value="casual">Casual — direct, punchy, no corporate speak</option>
            <option value="urgent">Urgent — FOMO-driven, action-oriented</option>
          </select>
        </Row>
        <Row label="Language & Region">
          <select value={s.brand_language||"UK English"} onChange={e=>set("brand_language",e.target.value)} className="input">
            <option value="UK English">UK English (favour, organisation, programme)</option>
            <option value="US English">US English (favor, organization, program)</option>
            <option value="Global English">Global English (neutral)</option>
          </select>
        </Row>
        <Row label="Target Audience (global)">
          <input value={s.brand_audience||""} onChange={e=>set("brand_audience",e.target.value)} className="input" placeholder="e.g. UK school business managers, compliance-focused" />
        </Row>
        <Row label="Always Include">
          <input value={s.brand_always_include||""} onChange={e=>set("brand_always_include",e.target.value)} className="input" placeholder="e.g. always mention Martyn's Law, always reference speaker's 20 years experience" />
        </Row>
        <Row label="Banned Phrases (comma separated)">
          <input value={s.brand_banned_phrases||""} onChange={e=>set("brand_banned_phrases",e.target.value)} className="input" placeholder="e.g. exciting opportunity, don't miss out, we are thrilled" />
        </Row>
      </Group>

      <Group title="Video Conferencing">
        <Banner>ShowUp.ai auto-detects Zoom, Google Meet, Microsoft Teams, Webex, Calendly and Whereby links — no API integration needed. Just paste the join link when creating a webinar and the correct platform icon and label will appear automatically.</Banner>
        <div className="rounded-md p-3 text-xs" style={{ background: "var(--bg-sunken)", border: "1px solid var(--border)" }}>
          <div className="font-semibold mb-2" style={{ color: "var(--text-primary)" }}>Supported platforms (auto-detected from URL):</div>
          <div className="flex flex-wrap gap-2">
            {[
              ["🎥","Zoom","zoom.us"],["📹","Google Meet","meet.google.com"],
              ["💼","Microsoft Teams","teams.microsoft.com"],["🌐","Webex","webex.com"],
              ["📅","Calendly","calendly.com"],["🔗","Whereby","whereby.com"],
              ["🎬","StreamYard","streamyard.com"]
            ].map(([emoji,label,domain]) => (
              <span key={label} className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium"
                style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                {emoji} {label} <span style={{ color: "var(--text-muted)", fontSize: "9px" }}>({domain})</span>
              </span>
            ))}
          </div>
        </div>
      </Group>

      <Group title="Default touch sequence & channels">
        <div className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>Toggle which of the 8 touches are on by default for new webinars, and which channels fire on each.</div>
        <div className="space-y-2">
          {TOUCHES.map(t => {
            const enabled = s.default_touches?.[String(t.num)] !== false;
            const chs = s.default_channels?.[String(t.num)] || [];
            return (
              <div key={t.num} className="rounded-md p-3" style={{ border: "1px solid var(--border)" }} data-testid={`touch-row-${t.num}`}>
                <div className="flex items-center justify-between mb-2">
                  <label className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                    <input type="checkbox" data-testid={`touch-enabled-${t.num}`} checked={enabled} onChange={()=>toggleDefaultTouch(String(t.num))}/>
                    <span className="w-7 h-7 rounded-md font-bold flex items-center justify-center text-xs" style={{ background: "rgba(255,255,255,0.15)", color: "#FFFFFF" }}>{t.num}</span>
                    {t.name}
                  </label>
                  <label className="text-xs flex items-center gap-2" style={{ color: "var(--text-secondary)" }}>
                    <input type="checkbox" data-testid={`touch-auto-${t.num}`} checked={!!s.per_touch_auto_send?.[String(t.num)]} onChange={()=>toggleAuto(String(t.num))}/>
                    Auto-send when scheduled
                  </label>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {ALL_CHANNELS.map(([k,label]) => (
                    <button key={k} type="button" data-testid={`touch-${t.num}-defch-${k}`} onClick={()=>toggleChannel(String(t.num), k)}
                      className="text-xs px-2 py-1 rounded-full border" style={chs.includes(k) ? { background: "#FFFFFF", borderColor: "#FFFFFF", color: "#000000" } : { background: "var(--bg-sunken)", borderColor: "var(--border)", color: "var(--text-secondary)" }}>{label}</button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </Group>

      <div className="sticky bottom-4 mt-6 flex justify-end">
        <button onClick={save} data-testid="save-settings" className="px-6 py-2.5 bg-white hover:bg-gray-100 text-black font-semibold rounded-md shadow-lg">Save settings</button>
      </div>

      <style>{`.input{ width:100%; border:1px solid var(--border); border-radius:6px; padding:8px 12px; font-size:14px; outline:none; background:var(--bg-surface); color:var(--text-primary); }
        .input:focus{ border-color:#ffffff; box-shadow:0 0 0 2px rgba(255,255,255,0.25); }
        .input::placeholder{ color:var(--text-muted); }`}</style>
    </motion.div>
  );
}
function Group({title, children}) {
  return <section className="rounded-md p-5 mb-5" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
    <h2 className="text-lg font-semibold mb-4" style={{fontFamily:'Outfit', color: "var(--text-primary)"}}>{title}</h2>
    <div className="space-y-3">{children}</div>
  </section>;
}
function Row({label, children}) {
  return <label className="block">
    <span className="block text-xs font-semibold uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>{label}</span>
    {children}
  </label>;
}
function Field({label, k, s, set, hint}) {
  return <label className="block">
    <span className="block text-xs font-semibold uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>{label}</span>
    <input data-testid={`set-${k}`} type="password" value={s[k]||""} onChange={e=>set(k, e.target.value)} placeholder="••••••••" className="input"/>
    {hint && <span className="text-xs mt-1 block" style={{ color: "var(--text-muted)" }}>{hint}</span>}
  </label>;
}
function Banner({children}) {
  return <div className="text-xs px-3 py-2 rounded-md border" style={{ background: "rgba(245,158,11,0.08)", borderColor: "rgba(245,158,11,0.3)", color: "var(--text-secondary)" }}>{children}</div>;
}

function TestSend({label, channel, testId, needPhone}) {
  const { isDark } = useTheme();
  const [busy, setBusy] = useState(false);
  const [to, setTo] = useState("");
  const fire = async () => {
    setBusy(true);
    try {
      const body = needPhone ? { to_phone: to, body: "ShowUp.ai test message ✓" } : { subject: "ShowUp.ai test", body: "If you see this, your integration works ✓" };
      const r = await api.post(`/test-send/${channel}`, body);
      if (r.data.ok) toast.success(`${channel} test sent ✓`);
      else toast.error(`${channel} test failed: ${r.data.detail}`);
    } catch(e) { toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };
  return (
    <div className="flex items-center gap-2 pt-2">
      {needPhone && <input className="input flex-1" placeholder="+44 7..." value={to} onChange={e=>setTo(e.target.value)} data-testid={`${testId}-to`}/>}
      <button type="button" disabled={busy} data-testid={testId} onClick={fire}
        className="text-xs px-3 py-1.5 rounded-md disabled:opacity-50 transition-colors"
        style={{ border: "1px solid var(--border)", color: "var(--text-secondary)", background: "var(--bg-surface)" }}>
        {busy ? "Sending…" : label}
      </button>
    </div>
  );
}

function CircleSync() {
  const { isDark } = useTheme();
  const [busy, setBusy] = useState(false);
  const sync = async () => {
    setBusy(true);
    try {
      const r = await api.post("/circle/sync");
      if (r.data.error) toast.error(r.data.error);
      else toast.success(`Synced ${r.data.members_synced} community members`);
    } catch(e) { toast.error(e?.response?.data?.detail || "Sync failed"); }
    finally { setBusy(false); }
  };
  return (
    <button type="button" data-testid="circle-sync-btn" disabled={busy} onClick={sync}
      className="text-xs px-3 py-1.5 border border-orange-300 bg-orange-50 text-orange-700 font-semibold rounded-md hover:bg-orange-100 disabled:opacity-50">
      {busy ? "Syncing members…" : "Sync Circle.so members now"}
    </button>
  );
}

function CircleDiagnose() {
  const { isDark } = useTheme();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const run = async () => {
    setBusy(true); setResult(null);
    try {
      const r = await api.get("/circle/diagnose");
      setResult(r.data);
      if (r.data.ok) toast.success(r.data.hint);
      else toast.error(r.data.error || "Diagnosis failed");
    } catch(e) { toast.error(e?.response?.data?.detail || "Diagnosis failed"); }
    finally { setBusy(false); }
  };
  return (
    <div className="w-full">
      <button type="button" data-testid="circle-diagnose-btn" disabled={busy} onClick={run}
        className="text-xs px-3 py-1.5 font-semibold rounded-md disabled:opacity-50 transition-colors"
        style={{ border: "1px solid var(--border)", background: "var(--bg-surface)", color: "var(--text-secondary)" }}>
        {busy ? "Diagnosing token…" : "Diagnose Circle token"}
      </button>
      {result && (
        <div data-testid="circle-diagnose-result" className="mt-2 rounded-md p-3 text-xs" style={result.ok ? { background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.3)", color: isDark ? "#4ade80" : "#166534" } : { background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: isDark ? "#f87171" : "#991b1b" }}>
          <div className="font-bold mb-1">{result.ok ? "✓ Connected" : "✗ Token rejected"}</div>
          {result.scheme_that_worked && <div>Auth scheme: <code>{result.scheme_that_worked}</code></div>}
          {result.first_space && <div>First space: <code>#{result.first_space.id} {result.first_space.name}</code></div>}
          {result.status && <div>HTTP status: <code>{result.status}</code></div>}
          {result.response && <div className="mt-1 text-[10px] font-mono break-words bg-white/50 p-1.5 rounded">Response: {result.response}</div>}
          {result.hint && <div className="mt-2 italic">{result.hint}</div>}
        </div>
      )}
    </div>
  );
}

function CircleSpacesPicker({ onPick }) {
  const { isDark } = useTheme();
  const [open, setOpen] = useState(false);
  const [spaces, setSpaces] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const fetchSpaces = async () => {
    setLoading(true); setErr("");
    try {
      const r = await api.get("/circle/spaces");
      if (r.data.error) setErr(r.data.error);
      setSpaces(r.data.spaces || []);
      setOpen(true);
    } catch(e) { setErr(e?.response?.data?.detail || "Failed"); }
    finally { setLoading(false); }
  };
  return (
    <div className="relative">
      <button type="button" data-testid="circle-spaces-picker" onClick={fetchSpaces} disabled={loading}
        className="text-xs px-3 py-1.5 rounded-md whitespace-nowrap disabled:opacity-50 transition-colors"
        style={{ border: "1px solid var(--border)", background: "var(--bg-surface)", color: "var(--text-secondary)" }}>
        {loading ? "Loading…" : "Pick from list"}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-80 max-h-80 overflow-auto rounded-md shadow-xl z-10" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)" }} data-testid="circle-spaces-list">
          {err && <div className="p-3 text-xs text-red-400">{err}</div>}
          {!err && spaces.length === 0 && <div className="p-3 text-xs" style={{ color: "var(--text-muted)" }}>No spaces found — check your API key.</div>}
          {spaces.map(sp => (
            <button key={sp.id} type="button" onClick={()=>{ onPick(sp.id); setOpen(false); toast.success(`Selected: ${sp.name}`); }}
              className="w-full text-left px-3 py-2 text-sm transition-colors hover:bg-orange-500/10" style={{ borderBottom: "1px solid var(--border)" }}>
              <div className="font-semibold" style={{ color: "var(--text-primary)" }}>{sp.name}</div>
              <div className="text-xs mono" style={{ color: "var(--text-muted)" }}>ID {sp.id} {sp.slug ? `· ${sp.slug}` : ""}</div>
            </button>
          ))}
          <button type="button" onClick={()=>setOpen(false)} className="w-full text-center px-3 py-2 text-xs transition-colors" style={{ color: "var(--text-muted)", borderTop: "1px solid var(--border)" }}>Close</button>
        </div>
      )}
    </div>
  );
}

// Zoom/Meet/Teams section is handled via manual join link paste in webinar creation.
// Below is a helper component already integrated via JoinLinkInput in CreateWebinarDialog.
