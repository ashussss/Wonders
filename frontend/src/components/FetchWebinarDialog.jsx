import { useState } from "react";
import { AlertTriangle, ArrowRight, Check, Link, Loader, Users, Zap } from "@/components/Icons";
import { motion, AnimatePresence } from "framer-motion";
import { api, API_BASE } from "@/lib/api";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

const PLATFORM_META = {
  circle:      { label: "Circle.so",       emoji: "🔵", color: "#6366F1", canFetch: true  },
  zoom:        { label: "Zoom",            emoji: "🎥", color: "#2D8CFF", canFetch: false },
  google_meet: { label: "Google Meet",     emoji: "📹", color: "#00897B", canFetch: false },
  teams:       { label: "Microsoft Teams", emoji: "💼", color: "#6264A7", canFetch: false },
  linkedin:    { label: "LinkedIn",        emoji: "💼", color: "#0077B5", canFetch: "partial" },
  webex:       { label: "Webex",           emoji: "🌐", color: "#00B2E3", canFetch: false },
  whereby:     { label: "Whereby",         emoji: "🔗", color: "#5C6BC0", canFetch: false },
  calendly:    { label: "Calendly",        emoji: "📅", color: "#006BFF", canFetch: false },
  streamyard:  { label: "StreamYard",      emoji: "🎬", color: "#FF4081", canFetch: false },
  unknown:     { label: "Custom Link",     emoji: "🔗", color: "#EA580C", canFetch: false },
  eventbrite:  { label: "Eventbrite",       emoji: "🎟", color: "#F05537", canFetch: true  },
  luma:        { label: "Luma",             emoji: "🌸", color: "#6B4FBB", canFetch: true  },
  hopin:       { label: "Hopin",            emoji: "🎪", color: "#6B48FF", canFetch: false },
  airmeet:     { label: "Airmeet",          emoji: "✈️", color: "#4F46E5", canFetch: false },
};

function detectPlatformFrontend(url) {
  const u = url.toLowerCase();
  if (u.includes("circle.so") || u.includes("schoolbusinessmanager.uk") || u.includes("app.circle.so")) return "circle";
  if (u.includes("zoom.us")) return "zoom";
  if (u.includes("meet.google.com")) return "google_meet";
  if (u.includes("teams.microsoft.com") || u.includes("teams.live.com")) return "teams";
  if (u.includes("linkedin.com/events")) return "linkedin";
  if (u.includes("webex.com")) return "webex";
  if (u.includes("whereby.com")) return "whereby";
  if (u.includes("calendly.com")) return "calendly";
  if (u.includes("streamyard.com")) return "streamyard";
  if (u.includes("eventbrite.com") || u.includes("eventbrite.co.uk")) return "eventbrite";
  if (u.includes("lu.ma")) return "luma";
  if (u.includes("hopin.com")) return "hopin";
  if (u.includes("airmeet.com")) return "airmeet";
  return "unknown";
}

export default function FetchWebinarDialog({ open, onClose, onCreated }) {
  const nav = useNavigate();
  const [step, setStep] = useState("url"); // url → fetching → fill → creating
  const [url, setUrl] = useState("");
  const [platform, setPlatform] = useState(null);
  const [fetched, setFetched] = useState(null);
  const [form, setForm] = useState({
    title: "", description: "", speaker: "", speakers: "",
    target_audience: "", starts_at: "", timezone: "Europe/London",
    join_link: "", key_topics: "", custom_context: "",
  });
  const [attendees, setAttendees] = useState([]);
  const [importing, setImporting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [circleEvents, setCircleEvents] = useState([]);
  const [loadingCircle, setLoadingCircle] = useState(false);
  const [showCirclePicker, setShowCirclePicker] = useState(false);

  const upd = k => e => setForm(f => ({ ...f, [k]: e.target.value }));

  const loadCircleEvents = async () => {
    setLoadingCircle(true);
    try {
      const r = await api.get("/circle/upcoming-events");
      setCircleEvents(r.data.events || []);
      setShowCirclePicker(true);
    } catch(e) {
      toast.error("Could not load Circle events — check API key in Settings");
    } finally { setLoadingCircle(false); }
  };

  const selectCircleEvent = (ev) => {
    setForm(prev => ({
      ...prev,
      title: ev.name || prev.title,
      starts_at: ev.published_at ? ev.published_at.slice(0,16) : prev.starts_at,
      join_link: ev.url || prev.join_link,
      cover_image_url: ev.cover_image_url || prev.cover_image_url,
    }));
    setFetched({ platform: "circle", error: null });
    setShowCirclePicker(false);
    setStep("fill");
  };

  const onUrlChange = (val) => {
    setUrl(val);
    if (val.length > 10) setPlatform(detectPlatformFrontend(val));
    else setPlatform(null);
  };

  const fetchDetails = async () => {
    if (!url.trim()) return;
    setStep("fetching");
    try {
      const r = await api.post("/webinars/fetch-from-url", { url });
      const d = r.data;
      setFetched(d);
      setAttendees(d.attendees || []);
      setForm(prev => ({
        ...prev,
        title:       d.title || prev.title,
        description: d.description || prev.description,
        speaker:     d.speaker || prev.speaker,
        join_link:   d.join_link || url,
        starts_at:   d.starts_at ? d.starts_at.slice(0,16) : prev.starts_at,
        cover_image_url: d.cover_image_url || prev.cover_image_url || "",
      }));
      setStep("fill");
    } catch(e) {
      toast.error(e?.response?.data?.detail || "Fetch failed");
      setStep("url");
    }
  };

  const createWebinar = async () => {
    if (!form.title) { toast.error("Title required"); return; }
    setCreating(true);
    try {
      // Create webinar
      const r = await api.post("/webinars", {
        ...form,
        starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : new Date(Date.now() + 7*24*60*60*1000).toISOString(),
      });
      const wid = r.data.id;

      // Import attendees if any
      if (attendees.length > 0 && wid) {
        setImporting(true);
        try {
          await api.post(`/webinars/${wid}/registrants/import`,
            attendees.map(a => ({ name: a.name || a.email, email: a.email, source: "circle_import" }))
          );
          toast.success(`Webinar created + ${attendees.length} attendees imported!`);
        } catch(e) {
          toast.success("Webinar created! (attendee import failed)");
        } finally { setImporting(false); }
      } else {
        toast.success("Webinar created — AI is generating your 8 touches!");
      }

      onClose();
      if (onCreated) onCreated();
      nav(`/app/webinars/${wid}`);
    } catch(e) {
      toast.error(e?.response?.data?.detail || "Create failed");
    } finally { setCreating(false); }
  };

  const reset = () => {
    setStep("url"); setUrl(""); setPlatform(null);
    setFetched(null); setAttendees([]); setImporting(false);
    setForm({ title:"", description:"", speaker:"", speakers:"",
      target_audience:"", starts_at:"", timezone:"Europe/London",
      join_link:"", key_topics:"", custom_context:"" });
  };

  const pm = platform ? (PLATFORM_META[platform] || PLATFORM_META.unknown) : null;

  const inputStyle = {
    width:"100%", padding:"8px 12px", borderRadius:"8px", fontSize:"14px",
    background:"var(--bg-sunken)", border:"1px solid var(--border)",
    color:"var(--text-primary)", outline:"none",
  };
  const labelStyle = {
    display:"block", fontSize:"11px", fontWeight:700,
    textTransform:"uppercase", letterSpacing:"0.1em",
    color:"var(--text-muted)", marginBottom:"4px",
  };

  if (!open) return null;

  return (
    <AnimatePresence>
      <motion.div initial={{ opacity:0 }} animate={{ opacity:1 }} exit={{ opacity:0 }}
        className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
        onClick={() => { reset(); onClose(); }}>
        <motion.div initial={{ opacity:0, scale:0.95, y:10 }} animate={{ opacity:1, scale:1, y:0 }}
          exit={{ opacity:0, scale:0.95 }}
          className="rounded-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto"
          style={{ background:"var(--bg-elevated)", border:"1px solid var(--border)", boxShadow:"var(--shadow-lg)" }}
          onClick={e => e.stopPropagation()}>

          {/* Header */}
          <div className="px-6 py-4 flex items-center justify-between sticky top-0"
            style={{ background:"var(--bg-elevated)", borderBottom:"1px solid var(--border)" }}>
            <div className="flex items-center gap-2">
              <Link size={16} className="text-orange-500" />
              <h3 className="font-bold text-base" style={{ fontFamily:"Outfit", color:"var(--text-primary)" }}>
                Add Webinar from Link
              </h3>
            </div>
            <button onClick={() => { reset(); onClose(); }} style={{ color:"var(--text-muted)", fontSize:"18px" }}>✕</button>
          </div>

          <div className="px-6 py-5">

            {/* STEP 1 — URL input */}
            {(step === "url" || step === "fetching") && (
              <div className="space-y-4">
                <p className="text-sm" style={{ color:"var(--text-muted)" }}>
                  Paste any webinar link — Circle.so, Zoom, Google Meet, Teams, LinkedIn and more.
                </p>

                {/* Circle.so quick pick */}
                <div className="rounded-xl p-3 flex items-center justify-between" style={{ background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.2)" }}>
                  <div>
                    <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>🔵 Import from Circle.so</div>
                    <div className="text-xs" style={{ color: "var(--text-muted)" }}>Pick from your upcoming events list</div>
                  </div>
                  <button onClick={loadCircleEvents} disabled={loadingCircle}
                    className="text-xs px-3 py-1.5 rounded-lg font-bold transition-colors disabled:opacity-50"
                    style={{ background: "#6366F1", color: "#fff" }}>
                    {loadingCircle ? "Loading..." : "Pick Event"}
                  </button>
                </div>

                {/* Circle events dropdown */}
                {showCirclePicker && circleEvents.length > 0 && (
                  <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)", background: "var(--bg-surface)", maxHeight: "300px", overflowY: "auto" }}>
                    {circleEvents.map(ev => (
                      <button key={ev.id} onClick={() => selectCircleEvent(ev)}
                        className="w-full text-left px-4 py-3 hover:bg-orange-500/5 transition-colors flex items-center gap-3"
                        style={{ borderBottom: "1px solid var(--border)" }}>
                        {ev.cover_image_url && <img src={ev.cover_image_url} alt="" className="w-10 h-10 rounded object-cover shrink-0" />}
                        <div className="min-w-0">
                          <div className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>{ev.name}</div>
                          <div className="text-xs" style={{ color: "var(--text-muted)" }}>{ev.published_at?.slice(0,10)}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                <div className="text-center text-xs" style={{ color: "var(--text-muted)" }}>— or paste any link below —</div>

                <div>
                  <label style={labelStyle}>Webinar / Event Link</label>
                  <div className="relative">
                    <input value={url} onChange={e => onUrlChange(e.target.value)}
                      placeholder="https://app.circle.so/c/... or zoom.us/j/..."
                      style={{ ...inputStyle, paddingLeft: pm ? "40px" : "12px" }}
                      onKeyDown={e => e.key === "Enter" && url && fetchDetails()} />
                    {pm && (
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-lg">{pm.emoji}</span>
                    )}
                  </div>

                  {/* Platform badge */}
                  {pm && (
                    <div className="mt-2 flex items-center gap-2">
                      <span className="text-xs px-2 py-0.5 rounded-full font-bold"
                        style={{ background:`${pm.color}15`, color:pm.color }}>
                        {pm.emoji} {pm.label} detected
                      </span>
                      {pm.canFetch === true && (
                        <span className="text-xs text-emerald-500 font-semibold">✓ Full fetch available</span>
                      )}
                      {pm.canFetch === "partial" && (
                        <span className="text-xs text-amber-500 font-semibold">⚡ Partial fetch</span>
                      )}
                      {pm.canFetch === false && (
                        <span className="text-xs font-semibold" style={{ color:"var(--text-muted)" }}>Join link will be set</span>
                      )}
                    </div>
                  )}
                </div>

                {/* Platform info */}
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { p:"circle", note:"Title + Date + Attendees" },
                    { p:"zoom", note:"Join link only" },
                    { p:"google_meet", note:"Join link only" },
                    { p:"teams", note:"Join link only" },
                    { p:"linkedin", note:"Title + Date" },
                    { p:"eventbrite", note:"Title + Date + Description" },
                    { p:"luma", note:"Title + Date + Join link" },
                    { p:"unknown", note:"Join link only" },
                  ].map(({ p, note }) => {
                    const meta = PLATFORM_META[p];
                    return (
                      <div key={p} className="flex items-center gap-1.5 text-[10px] rounded-lg px-2 py-1.5"
                        style={{ background:"var(--bg-sunken)", color:"var(--text-muted)" }}>
                        <span>{meta.emoji}</span>
                        <div>
                          <div className="font-bold" style={{ color:"var(--text-secondary)" }}>{meta.label}</div>
                          <div>{note}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <motion.button whileHover={{ scale:1.01 }} whileTap={{ scale:0.99 }}
                  onClick={fetchDetails} disabled={!url.trim() || step === "fetching"}
                  className="w-full py-3 bg-orange-600 hover:bg-orange-500 text-white font-bold rounded-xl flex items-center justify-center gap-2 transition-colors disabled:opacity-50">
                  {step === "fetching"
                    ? <><Loader size={16} className="animate-spin" /> Fetching details…</>
                    : <><Zap size={16} /> Fetch Webinar Details</>}
                </motion.button>
              </div>
            )}

            {/* STEP 2 — Fill form */}
            {step === "fill" && (
              <div className="space-y-4">

                {/* Fetch result banner */}
                {fetched && (
                  <div className="rounded-xl p-3 text-xs"
                    style={fetched.error
                      ? { background:"rgba(245,158,11,0.08)", border:"1px solid rgba(245,158,11,0.3)", color:"#F59E0B" }
                      : { background:"rgba(16,185,129,0.08)", border:"1px solid rgba(16,185,129,0.3)", color:"#10B981" }}>
                    {fetched.error
                      ? <><AlertTriangle size={12} className="inline mr-1" />{fetched.error}</>
                      : <><Check size={12} className="inline mr-1" />Details fetched from {PLATFORM_META[fetched.platform]?.label || fetched.platform}</>}
                  </div>
                )}

                {/* Cover image preview */}
                {fetched?.cover_image_url && (
                  <div className="rounded-xl overflow-hidden" style={{ maxHeight: "120px" }}>
                    <img src={fetched.cover_image_url} alt="Webinar cover"
                      className="w-full object-cover" style={{ maxHeight: "120px" }} />
                  </div>
                )}

                {/* Attendees badge */}
                {attendees.length > 0 && (
                  <div className="rounded-xl p-3 flex items-center gap-2 text-sm"
                    style={{ background:"rgba(234,88,12,0.08)", border:"1px solid rgba(234,88,12,0.25)" }}>
                    <Users size={14} className="text-orange-500" />
                    <span style={{ color:"var(--text-primary)" }}>
                      <strong className="text-orange-500">{attendees.length} attendees</strong> will be imported as registrants
                    </span>
                  </div>
                )}

                <div>
                  <label style={labelStyle}>Title *</label>
                  <input value={form.title} onChange={upd("title")} style={inputStyle} placeholder="Webinar title" />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label style={labelStyle}>Date & Time</label>
                    <input type="datetime-local" value={form.starts_at} onChange={upd("starts_at")} style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Timezone</label>
                    <select value={form.timezone} onChange={upd("timezone")} style={inputStyle}>
                      {["Europe/London","Europe/Paris","America/New_York","America/Chicago","America/Los_Angeles","Asia/Kolkata","Asia/Singapore"].map(tz => (
                        <option key={tz} value={tz}>{tz}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label style={labelStyle}>Speaker</label>
                    <input value={form.speaker} onChange={upd("speaker")} style={inputStyle} placeholder="Richard Clarke" />
                  </div>
                  <div>
                    <label style={labelStyle}>Target Audience</label>
                    <input value={form.target_audience} onChange={upd("target_audience")} style={inputStyle} placeholder="UK school business managers" />
                  </div>
                </div>

                <div>
                  <label style={labelStyle}>Description</label>
                  <textarea value={form.description} onChange={upd("description")} rows={3}
                    style={{ ...inputStyle, resize:"vertical" }} placeholder="What will attendees learn?" />
                </div>

                <div>
                  <label style={labelStyle}>Join Link</label>
                  <input value={form.join_link} onChange={upd("join_link")} style={inputStyle} />
                </div>

                <div>
                  <label style={labelStyle}>Key Topics</label>
                  <input value={form.key_topics} onChange={upd("key_topics")} style={inputStyle}
                    placeholder="Martyn's Law, safeguarding, compliance" />
                </div>

                <div>
                  <label style={labelStyle}>AI Instructions (optional)</label>
                  <textarea value={form.custom_context} onChange={upd("custom_context")} rows={2}
                    style={{ ...inputStyle, resize:"vertical" }}
                    placeholder="e.g. Always mention compliance deadline, use urgent professional tone" />
                </div>

                <div className="flex gap-3 pt-2">
                  <button onClick={() => { setStep("url"); setFetched(null); }}
                    className="px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors"
                    style={{ border:"1px solid var(--border)", color:"var(--text-secondary)" }}>
                    ← Back
                  </button>
                  <motion.button whileHover={{ scale:1.01 }} whileTap={{ scale:0.99 }}
                    onClick={createWebinar} disabled={creating || importing}
                    className="flex-1 py-2.5 bg-orange-600 hover:bg-orange-500 text-white font-bold rounded-xl flex items-center justify-center gap-2 transition-colors disabled:opacity-50">
                    {creating || importing
                      ? <><Loader size={15} className="animate-spin" />{importing ? "Importing attendees…" : "Creating…"}</>
                      : <><Zap size={15} /> Create & Generate AI Content <ArrowRight size={14} /></>}
                  </motion.button>
                </div>
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
