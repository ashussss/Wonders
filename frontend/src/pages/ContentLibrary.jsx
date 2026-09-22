import { useEffect, useState, useMemo } from "react";
import { BookOpen, Check, Copy, Filter, ImageIcon, Send, Zap } from "@/components/Icons";
import { motion, AnimatePresence } from "framer-motion";
import { api, fmtDate, CHANNEL_META, API_BASE } from "@/lib/api";
import { Link } from "react-router-dom";
import { useTheme } from "@/lib/theme";
import { toast } from "sonner";

const TYPE_STYLE = {
  confirmation:       { label: "Confirmation",       color: "bg-blue-500/15 text-blue-400" },
  insight:            { label: "Insight",            color: "bg-purple-500/15 text-purple-400" },
  poll:               { label: "Poll",               color: "bg-pink-500/15 text-pink-400" },
  case_study:         { label: "Case Study",         color: "bg-cyan-500/15 text-cyan-400" },
  thought_provoking:  { label: "Thought-Provoking",  color: "bg-amber-500/15 text-amber-400" },
  reminder:           { label: "Reminder",           color: "bg-gray-500/15 text-gray-400" },
  post_event_insight: { label: "Post-Event",         color: "bg-emerald-500/15 text-emerald-400" },
  fomo:               { label: "FOMO",               color: "bg-red-500/15 text-red-400" }};

const CHANNELS_ALL = ["email","linkedin","linkedin_personal","facebook","instagram","whatsapp","circle"];

export default function ContentLibrary() {
  const { isDark } = useTheme();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterChannel, setFilterChannel] = useState("all");
  const [filterType, setFilterType] = useState("all");
  const [filterWebinar, setFilterWebinar] = useState("all");
  const [copied, setCopied] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [generatingImg, setGeneratingImg] = useState(null); // touch_id being generated
  const [imgType, setImgType] = useState({}); // {touch_id: "carousel"|"infographic"|"quote_card"}

  useEffect(() => { load(); }, []);

  const webinars = useMemo(() => {
    const seen = {};
    items.forEach(i => { seen[i.webinar_id] = i.webinar_title; });
    return Object.entries(seen);
  }, [items]);

  const filtered = useMemo(() => items.filter(i => {
    if (filterChannel !== "all" && !i.channels.includes(filterChannel)) return false;
    if (filterType !== "all" && i.touch_type !== filterType) return false;
    if (filterWebinar !== "all" && i.webinar_id !== filterWebinar) return false;
    return true;
  }), [items, filterChannel, filterType, filterWebinar]);

  const generateImageIcon = async (item) => {
    const type = imgType[item.touch_id] || "carousel";
    setGeneratingImg(item.touch_id);
    try {
      const r = await api.post(`/webinars/${item.webinar_id}/social-image/generate`, { image_type: type });
      toast.success(`${type.charAt(0).toUpperCase()+type.slice(1)} image generated!`);
      load();
    } catch (e) {
      const detail = e?.response?.data?.detail || "ImageIcon generation failed";
      toast.error(detail);
      console.error("ImageIcon gen error:", e?.response?.data);
    } finally { setGeneratingImg(null); }
  };

  const load = () => {
    api.get("/content-library").then(r => { setItems(r.data); setLoading(false); });
  };

  const copyText = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    toast.success("Copied!");
    setTimeout(() => setCopied(null), 2000);
  };

  const card = "";
  const cardStyle = { background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" };
  const text = "";
  const textStyle = { color: "var(--text-primary)" };
  const muted = "";
  const mutedStyle = { color: "var(--text-muted)" };
  const divider = "";

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
      className="min-h-screen p-4 sm:p-8" style={{ background: "var(--bg-base)" }}>
      <div className="max-w-7xl mx-auto">

        {/* Header */}
        <div className="flex items-center gap-2 mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
          <span className="text-[10px] font-bold uppercase tracking-[0.25em] text-white">Content</span>
        </div>
        <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
          <div>
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight" style={{ fontFamily: "Outfit", color: "var(--text-primary)" }}>
              Content Library
            </h1>
            <p className="mt-1 text-sm " style={{ color: "var(--text-muted)" }}>All approved posts — ready to copy, schedule or publish.</p>
          </div>
          <div className={`text-sm font-semibold px-3 py-1.5 rounded-xl border ${isDark ? "border-white/[0.06] text-gray-400" : "border-gray-200 text-gray-500"}`}>
            {filtered.length} posts
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3 mb-6 p-4 rounded-2xl border " style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }}>
          <div className="flex items-center gap-1.5">
            <Filter size={14} className="text-white" />
            <span className="text-xs font-bold uppercase tracking-wider " style={{ color: "var(--text-muted)" }}>Filter:</span>
          </div>

          {/* Channel filter */}
          <select value={filterChannel} onChange={e => setFilterChannel(e.target.value)}
            className="text-xs px-3 py-1.5 rounded-lg border transition-colors" style={{ background: "var(--bg-sunken)", border: "1px solid var(--border)", color: "var(--text-primary)" }}>
            <option value="all">All channels</option>
            {CHANNELS_ALL.map(ch => <option key={ch} value={ch}>{CHANNEL_META[ch]?.label || ch}</option>)}
          </select>

          {/* Type filter */}
          <select value={filterType} onChange={e => setFilterType(e.target.value)}
            className="text-xs px-3 py-1.5 rounded-lg border transition-colors" style={{ background: "var(--bg-sunken)", border: "1px solid var(--border)", color: "var(--text-primary)" }}>
            <option value="all">All types</option>
            {Object.entries(TYPE_STYLE).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>

          {/* Webinar filter */}
          <select value={filterWebinar} onChange={e => setFilterWebinar(e.target.value)}
            className="text-xs px-3 py-1.5 rounded-lg border transition-colors" style={{ background: "var(--bg-sunken)", border: "1px solid var(--border)", color: "var(--text-primary)" }}>
            <option value="all">All webinars</option>
            {webinars.map(([id, title]) => <option key={id} value={id}>{title.slice(0, 40)}</option>)}
          </select>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-24">
            <div className="w-7 h-7 border-2 border-white border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {/* Empty */}
        {!loading && filtered.length === 0 && (
          <div className="rounded-2xl border p-16 text-center " style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }}>
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4" style={{ background: "var(--bg-sunken)" }}>
              <BookOpen size={24} className={muted} />
            </div>
            <div className="font-medium mb-1 " style={{ color: "var(--text-primary)" }}>No approved posts yet</div>
            <div className="text-sm " style={{ color: "var(--text-muted)" }}>Approve touches in a webinar to see them here.</div>
          </div>
        )}

        {/* LayoutDashboard */}
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
          <AnimatePresence>
            {filtered.map((item, i) => {
              const typeStyle = TYPE_STYLE[item.touch_type] || TYPE_STYLE.reminder;
              const variantKey = item.selected_variant === 1 ? "casual" : "safe";
              const isExpanded = expanded === item.touch_id;

              return (
                <motion.div key={item.touch_id}
                  initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.97 }}
                  transition={{ delay: i * 0.04, duration: 0.35 }}
                  className="rounded-2xl border overflow-hidden " style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }}>

                  {/* ImageIcon type picker + generate */}
                  <div className="px-4 pt-3 pb-1 flex items-center gap-2 flex-wrap" style={{ borderBottom: "1px solid var(--border)" }}>
                    {["carousel","infographic","quote_card"].map(t => (
                      <button key={t} type="button"
                        onClick={() => setImgType(prev => ({ ...prev, [item.touch_id]: t }))}
                        className="text-[9px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide transition-all"
                        style={(imgType[item.touch_id] || "carousel") === t
                          ? { background: "#EA580C", color: "#fff" }
                          : { background: "var(--bg-sunken)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                        {t === "quote_card" ? "Quote" : t.charAt(0).toUpperCase() + t.slice(1)}
                      </button>
                    ))}
                    <motion.button whileTap={{ scale: 0.95 }}
                      onClick={() => generateImage(item)}
                      disabled={generatingImg === item.touch_id}
                      className="ml-auto text-[9px] px-2.5 py-1 rounded-full font-bold flex items-center gap-1 disabled:opacity-50 transition-colors"
                      style={{ background: "rgba(234,88,12,0.12)", color: "#EA580C" }}>
                      {generatingImg === item.touch_id
                        ? <span className="w-2.5 h-2.5 border border-orange-500 border-t-transparent rounded-full animate-spin" />
                        : <Zap size={9} />}
                      {generatingImg === item.touch_id ? "..." : "Generate"}
                    </motion.button>
                  </div>

                  {/* ImageIcon */}
                  {item.has_image && item.image_url && (
                    <div className="relative">
                      <img src={`${API_BASE}${item.image_url}?v=1`} alt="Post visual"
                        className="w-full aspect-video object-cover"
                        onError={e => { e.target.parentElement.style.display = "none"; }} />
                      <div className="absolute top-2 right-2">
                        <a href={`${API_BASE}${item.image_url}`} download target="_blank" rel="noreferrer"
                          className="w-7 h-7 rounded-lg bg-black/50 backdrop-blur-sm flex items-center justify-center text-white hover:bg-black/70 transition-colors">
                          <ImageIcon size={13} />
                        </a>
                      </div>
                    </div>
                  )}

                  {/* Card header */}
                  <div className={`px-4 py-3 border-b ${divider} flex items-center justify-between gap-2`}>
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="w-6 h-6 rounded-lg bg-orange-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">
                        {item.touch_num}
                      </div>
                      <div className="min-w-0">
                        <Link to={`/app/webinars/${item.webinar_id}`}
                          className={`text-[10px] font-semibold truncate block hover:text-orange-500 transition-colors ${isDark ? "text-gray-500" : "text-gray-400"}`}>
                          {item.webinar_title}
                        </Link>
                        <div className="text-xs font-medium truncate " style={{ color: "var(--text-primary)" }}>{item.touch_name}</div>
                      </div>
                    </div>
                    <span className={`text-[9px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full shrink-0 ${typeStyle.color}`}>
                      {typeStyle.label}
                    </span>
                  </div>

                  {/* Channel tabs */}
                  <div className={`flex gap-1 px-4 py-2 border-b overflow-x-auto ${divider}`}>
                    {item.channels.map(ch => (
                      <span key={ch} className="text-[9px] px-2 py-0.5 rounded-full shrink-0 font-medium" style={{ background: "var(--bg-sunken)", color: "var(--text-muted)" }}>
                        {CHANNEL_META[ch]?.label || ch}
                      </span>
                    ))}
                    <span className={`text-[9px] px-2 py-0.5 rounded-full shrink-0 ml-auto ${isDark ? "bg-orange-500/10 text-orange-400" : "bg-orange-50 text-orange-600"}`}>
                      {variantKey}
                    </span>
                  </div>

                  {/* Copy content — first channel */}
                  {(() => {
                    const ch = item.channels[0];
                    const copy = item.ai_copy?.channels?.[ch]?.[variantKey];
                    if (!copy) return null;
                    const text_content = (copy.subject ? `${copy.subject}\n\n` : "") + (copy.body || "");
                    return (
                      <div className="px-4 py-3">
                        {copy.subject && (
                          <div className={`text-xs font-semibold mb-1.5 border-l-2 border-orange-500 pl-2 ${isDark ? "text-gray-300" : "text-gray-700"}`}>
                            {copy.subject}
                          </div>
                        )}
                        <div className={`text-sm leading-relaxed ${isExpanded ? "" : "line-clamp-3"} ${isDark ? "text-gray-400" : "text-gray-600"}`}>
                          {copy.body}
                        </div>
                        {copy.body && copy.body.length > 200 && (
                          <button onClick={() => setExpanded(isExpanded ? null : item.touch_id)}
                            className="text-xs text-orange-500 hover:text-orange-400 mt-1 transition-colors">
                            {isExpanded ? "Show less" : "Show more"}
                          </button>
                        )}
                        {/* All channels copy */}
                        {item.channels.length > 1 && isExpanded && (
                          <div className={`mt-3 pt-3 border-t space-y-3 ${divider}`}>
                            {item.channels.slice(1).map(channel => {
                              const c = item.ai_copy?.channels?.[channel]?.[variantKey];
                              if (!c) return null;
                              return (
                                <div key={channel}>
                                  <div className="text-[10px] font-bold uppercase tracking-wider mb-1 " style={{ color: "var(--text-muted)" }}>
                                    {CHANNEL_META[channel]?.label}
                                  </div>
                                  <div className={`text-xs leading-relaxed ${isDark ? "text-gray-500" : "text-gray-500"}`}>
                                    {c.body}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {/* Actions */}
                  <div className={`px-4 py-3 border-t flex items-center gap-2 ${divider}`}>
                    <motion.button whileTap={{ scale: 0.95 }}
                      onClick={() => {
                        const ch = item.channels[0];
                        const copy = item.ai_copy?.channels?.[ch]?.[variantKey];
                        if (!copy) return;
                        copyText((copy.subject ? copy.subject + "\n\n" : "") + copy.body, item.touch_id);
                      }}
                      className={`flex-1 text-xs py-2 rounded-lg font-semibold flex items-center justify-center gap-1.5 transition-colors ${
                        copied === item.touch_id
                          ? "bg-emerald-600 text-white"
                          : "bg-orange-600 hover:bg-orange-500 text-white"
                      }`}>
                      {copied === item.touch_id ? <Check size={12} /> : <Copy size={12} />}
                      {copied === item.touch_id ? "Copied!" : "Copy"}
                    </motion.button>

                    {item.sent_status === "sent" ? (
                      <span className={`text-[10px] px-2.5 py-1.5 rounded-lg font-bold uppercase tracking-wide ${isDark ? "bg-emerald-500/15 text-emerald-400" : "bg-emerald-50 text-emerald-600"}`}>
                        ✓ Sent
                      </span>
                    ) : (
                      <Link to={`/app/webinars/${item.webinar_id}`}
                        className={`text-xs px-3 py-2 rounded-lg border flex items-center gap-1 transition-colors ${isDark ? "border-white/[0.1] text-gray-400 hover:text-white" : "border-gray-200 text-gray-500 hover:text-gray-800"}`}>
                        <Link size={11} /> View
                      </Link>
                    )}

                    {item.scheduled_at && (
                      <div className="text-[10px] hidden sm:block" style={{ color: "var(--text-muted)" }}>
                        {fmtDate(item.scheduled_at)}
                      </div>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}
