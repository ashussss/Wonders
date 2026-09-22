import { useEffect, useState } from "react";
import { BarChart3, Copy, ImageIcon, Link, RefreshCcw, X, Zap } from "@/components/Icons";
import { motion, AnimatePresence } from "framer-motion";
import { api, API_BASE } from "@/lib/api";
import { toast } from "sonner";

export default function AdHocPostDialog({ open, onClose, webinar }) {
  const [audience, setAudience] = useState("linkedin");
  const [withPoll, setWithPoll] = useState(true);
  const [withImageIcon, setWithImage] = useState(true);
  const [imageType, setImageType] = useState('auto');
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!open || !webinar) return;
    // Auto-load any previously generated ad-hoc post for this webinar
    api.get(`/webinars/${webinar.id}/adhoc-post`).then(r => {
      if (r.data && r.data.text_data) setResult({...r.data.text_data, audience: r.data.audience, image_url: r.data.file_id ? `/api/webinars/${webinar.id}/adhoc-image.png?v=${Date.now()}` : null});
    }).catch(() => {});
  }, [open, webinar]);

  const generate = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/webinars/${webinar.id}/adhoc-post/generate`,
        { audience, with_poll: withPoll, with_image: withImageIcon, brief, image_type: imageType === 'auto' ? '' : imageType });
      setResult({ ...r.data, image_url: r.data.base64 || (r.data.image_url ? `${API_BASE}${r.data.image_url}?v=${Date.now()}` : null), post_text: r.data.post_text || r.data.content || "" });
      toast.success("Generated ✨");
    } catch(e) { toast.error(e?.response?.data?.detail || "Generation failed"); }
    finally { setBusy(false); }
  };

  const copyAll = () => {
    if (!result) return;
    const txt = (result.post_text || result.content || "") + "\n\n" + (result.hashtags || []).join(" ") +
      (result.poll_question ? `\n\nPoll: ${result.poll_question}\n• ${(result.poll_options||[]).join("\n• ")}` : "");
    navigator.clipboard.writeText(txt); toast.success("Copied — paste into LinkedIn");
  };

  if (!open) return null;
  return (
    <AnimatePresence>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6"
        data-testid="adhoc-dialog">
        <motion.div initial={{ scale: 0.95, y: 20, opacity: 0 }} animate={{ scale: 1, y: 0, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          className="bg-white rounded-2xl max-w-4xl w-full max-h-[92vh] overflow-auto shadow-2xl">
          <div className="px-5 sm:px-7 py-5 border-b border-gray-100 flex items-start justify-between gap-3 bg-gradient-to-r from-orange-50/60 to-amber-50/30">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.2em] text-orange-600 flex items-center gap-1.5"><Zap size={12}/> AI quick post · GPT-5.4</div>
              <h2 className="text-xl sm:text-2xl font-bold mt-1 tracking-tight" style={{fontFamily:'Outfit'}}>Generate ad-hoc post</h2>
              <p className="text-sm text-gray-500 mt-1">A single LinkedIn / Circle post with optional poll + AI image. Separate from the 8-touch sequence.</p>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-700 shrink-0" data-testid="adhoc-close"><X/></button>
          </div>

          <div className="px-5 sm:px-7 py-5 grid lg:grid-cols-[1fr_1.2fr] gap-6">
            {/* Controls */}
            <div className="space-y-4">
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-1.5 block">Audience</label>
                <div className="flex gap-2">
                  {["linkedin", "circle"].map(a => (
                    <button key={a} type="button" data-testid={`adhoc-audience-${a}`} onClick={()=>setAudience(a)}
                      className={`flex-1 py-2 rounded-lg text-sm font-semibold border transition-all ${audience===a?"bg-orange-600 border-orange-600 text-white":"bg-white border-gray-200 text-gray-700 hover:border-orange-300"}`}>
                      {a === "linkedin" ? "LinkedIn" : "Circle.so"}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-1.5 block">Custom brief (optional)</label>
                <textarea data-testid="adhoc-brief" rows={3} value={brief} onChange={e=>setBrief(e.target.value)}
                  placeholder="e.g. lean into the urgency — only 3 days left"
                  className="w-full border border-gray-200 rounded-lg p-2.5 text-sm focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 focus:outline-none"/>
              </div>

              <label className="flex items-center gap-2 text-sm font-medium cursor-pointer" data-testid="adhoc-toggle-poll-wrap">
                <input type="checkbox" checked={withPoll} onChange={e=>setWithPoll(e.target.checked)} data-testid="adhoc-toggle-poll" className="rounded text-orange-600 focus:ring-orange-500"/>
                <BarChart3 size={14}/> Include poll question
              </label>
              <label className="flex items-center gap-2 text-sm font-medium cursor-pointer" data-testid="adhoc-toggle-image-wrap">
                <input type="checkbox" checked={withImageIcon} onChange={e=>setWithImage(e.target.checked)} data-testid="adhoc-toggle-image" checked={withImageIcon} className="rounded text-orange-600 focus:ring-orange-500"/>
                <ImageIcon size={14}/> Generate accompanying image
              </label>
              {withImageIcon && (
                <div className="ml-6 mt-1">
                  <div className="text-xs text-gray-500 mb-1.5">ImageIcon style</div>
                  <div className="flex gap-1.5 flex-wrap">
                    {[["auto","✨ Auto"],["carousel","🖼 Carousel"],["infographic","📊 Infographic"],["quote_card","💬 Quote"]].map(([val,label]) => (
                      <button key={val} type="button" onClick={() => setImageType(val)}
                        className={`text-xs px-2.5 py-1 rounded-lg border font-medium transition-all ${imageType===val ? "bg-orange-600 border-orange-600 text-white" : "border-gray-200 text-gray-600 hover:border-orange-300"}`}>
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
                data-testid="adhoc-generate" onClick={generate} disabled={busy}
                className="w-full py-3 bg-orange-600 hover:bg-orange-700 text-white font-semibold rounded-lg flex items-center justify-center gap-2 disabled:opacity-50">
                <AnimatePresence mode="wait">
                  {busy ? (
                    <motion.span key="b" className="flex items-center gap-2" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                      <motion.div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full" animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: "linear" }}/>
                      {withImageIcon ? "Generating text + image…" : "Generating…"}
                    </motion.span>
                  ) : (
                    <motion.span key="s" className="flex items-center gap-2" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                      <Zap size={16}/> {result ? "Regenerate" : "Generate post"}
                    </motion.span>
                  )}
                </AnimatePresence>
              </motion.button>
            </div>

            {/* Result */}
            <div data-testid="adhoc-result">
              <AnimatePresence mode="wait">
                {!result ? (
                  <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                    className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center text-gray-400 text-sm h-full flex flex-col items-center justify-center min-h-[280px]">
                    <Zap size={28} className="text-orange-300 mb-3"/>
                    Configure options on the left, then click <strong className="mx-1">Generate post</strong> to draft a {audience} post in seconds.
                  </motion.div>
                ) : (
                  <motion.div key="content" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4 }} className="space-y-3">
                    {result.image_url && (
                      <motion.img initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }}
                        src={result.image_url} alt="AI-generated"
                        className="w-full aspect-square object-cover rounded-xl border border-orange-100"
                        onError={e => { e.target.style.display="none"; }}
                        data-testid="adhoc-image-preview"/>
                    )}
                    <div className="bg-orange-50/40 border border-orange-100 rounded-xl p-4">
                      <div className="text-xs font-bold uppercase tracking-wider text-orange-600 mb-2">Post body</div>
                      <div className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed" data-testid="adhoc-post-body">{result.post_text || result.content || "No content generated"}</div>
                      {(result.hashtags || []).length > 0 && (
                        <div className="text-sm text-orange-700 mt-2 font-medium" data-testid="adhoc-hashtags">{result.hashtags.join(" ")}</div>
                      )}
                    </div>
                    {result.poll_question && (
                      <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 }}
                        className="bg-white border border-gray-200 rounded-xl p-4" data-testid="adhoc-poll">
                        <div className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-2">Poll</div>
                        <div className="font-semibold text-gray-900 mb-2">{result.poll_question}</div>
                        <ul className="space-y-1">
                          {(result.poll_options || []).map((opt, i) => (
                            <li key={i} className="flex items-center gap-2 text-sm text-gray-700">
                              <div className="w-4 h-4 rounded-full border-2 border-orange-400"/> {opt}
                            </li>
                          ))}
                        </ul>
                      </motion.div>
                    )}
                    <div className="flex flex-wrap gap-2 pt-2">
                      <button onClick={copyAll} data-testid="adhoc-copy-all"
                        className="px-3 py-2 bg-orange-600 hover:bg-orange-700 text-white text-sm font-semibold rounded-lg inline-flex items-center gap-1.5"><Copy size={14}/> Copy everything</button>
                      <a href="https://www.linkedin.com/feed/?shareActive=true" target="_blank" rel="noreferrer" data-testid="adhoc-open-linkedin"
                        className="px-3 py-2 border border-gray-300 hover:bg-gray-50 text-gray-700 text-sm font-semibold rounded-lg inline-flex items-center gap-1.5"><Link size={14}/> Open LinkedIn</a>
                      <button onClick={generate} disabled={busy} data-testid="adhoc-regenerate"
                        className="px-3 py-2 border border-gray-300 hover:bg-gray-50 text-gray-700 text-sm rounded-lg inline-flex items-center gap-1.5 disabled:opacity-50"><RefreshCcw size={14}/> Try another angle</button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
