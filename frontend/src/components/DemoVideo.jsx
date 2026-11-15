import { useRef, useState } from "react";
import { motion } from "framer-motion";

// 74-second product tutorial (v2, Nov 2026). Source renders live in project files
// video/v2/; this is a 720p H.264 re-encode (~3.5 MB, faststart).
// preload="none": no video bytes are downloaded until the visitor presses play,
// so the section costs only the ~26 KB poster and never touches LCP.
const SRC = "/video/showupai-tutorial.mp4";
const POSTER_WEBP = "/video/showupai-tutorial-poster.webp";
const CAPTIONS = "/video/showupai-tutorial.vtt";

function track(name) {
  try { window.gtag && window.gtag("event", name, { video_title: "showupai_tutorial_v2" }); } catch { /* ignore */ }
}

export default function DemoVideo() {
  const ref = useRef(null);
  const [started, setStarted] = useState(false);

  const play = () => {
    const v = ref.current;
    if (!v) return;
    setStarted(true);
    v.play().catch(() => {});
  };

  return (
    <section id="demo" className="py-20 px-6 scroll-mt-20">
      <div className="max-w-5xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-10">
          <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-orange-500 mb-4">See it in 74 seconds</div>
          <h2 className="text-4xl sm:text-5xl font-bold text-white" style={{ fontFamily: "Outfit" }}>Paste a link. Get a full room.</h2>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.7 }}
          className="relative rounded-2xl overflow-hidden"
          style={{ aspectRatio: "16 / 9", background: "#0b0b16", border: "1px solid rgba(255,255,255,0.08)", boxShadow: "0 0 0 1px rgba(255,255,255,0.04) inset, 0 30px 80px rgba(0,0,0,0.6), 0 0 80px rgba(234,88,12,0.12)" }}
        >
          <video
            ref={ref}
            className="absolute inset-0 w-full h-full object-cover"
            preload="none"
            playsInline
            controls={started}
            poster={POSTER_WEBP}
            onPlay={() => track("demo_video_play")}
            onEnded={() => track("demo_video_complete")}
            aria-label="ShowUpAI product tutorial video"
          >
            <source src={SRC} type="video/mp4" />
            <track kind="captions" src={CAPTIONS} srcLang="en" label="English" />
          </video>

          {!started && (
            <button
              type="button"
              onClick={play}
              aria-label="Play the 74-second ShowUpAI demo"
              className="group absolute inset-0 flex items-center justify-center bg-black/10 hover:bg-black/20 transition-colors"
            >
              <span className="flex items-center gap-2 sm:gap-3 bg-orange-600 group-hover:bg-orange-500 text-white text-sm sm:text-base font-semibold pl-4 pr-5 py-2.5 sm:pl-5 sm:pr-6 sm:py-3.5 rounded-full shadow-[0_0_40px_rgba(234,88,12,0.5)] transition-all group-hover:scale-105">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.14v13.72a1 1 0 0 0 1.5.86l11-6.86a1 1 0 0 0 0-1.72l-11-6.86A1 1 0 0 0 8 5.14z" /></svg>
                Watch the demo · 1:14
              </span>
            </button>
          )}
        </motion.div>
      </div>
    </section>
  );
}
