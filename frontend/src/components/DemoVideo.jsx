import { useRef, useState } from "react";

// Landing-page product videos. Sources live in project files under video/v2/.
// Each is a 720p H.264 re-encode (+faststart) served from public/video/.
// preload="none": no video bytes are downloaded until the visitor presses play,
// so each player costs only its ~25 KB poster and never touches LCP.
export const VIDEOS = {
  // 74-second step-by-step tutorial, video/v2/showupai-tutorial-16x9.mp4. Used in the hero.
  tutorial: {
    id: "demo",
    src: "/video/showupai-tutorial.mp4",
    poster: "/video/showupai-tutorial-poster.webp",
    captions: "/video/showupai-tutorial.vtt",
    gaTitle: "showupai_tutorial_v2",
    label: "Watch the tutorial · 1:14",
    ariaLabel: "Play the 74-second ShowUpAI tutorial",
    alt: "ShowUpAI step-by-step tutorial video",
  },
};

function track(name, title) {
  try { window.gtag && window.gtag("event", name, { video_title: title }); } catch { /* ignore */ }
}

export function DemoPlayer({ video = VIDEOS.tutorial, className = "", style = {} }) {
  const ref = useRef(null);
  const [started, setStarted] = useState(false);

  const play = () => {
    const v = ref.current;
    if (!v) return;
    setStarted(true);
    v.play().catch(() => {});
  };

  return (
    <div
      id={video.id}
      className={`relative rounded-2xl overflow-hidden scroll-mt-24 ${className}`}
      style={{ aspectRatio: "16 / 9", background: "#0b0b16", border: "1px solid rgba(255,255,255,0.10)", boxShadow: "0 0 0 1px rgba(255,255,255,0.04) inset, 0 30px 80px rgba(0,0,0,0.6), 0 0 80px rgba(234,88,12,0.15)", ...style }}
    >
      <video
        ref={ref}
        className="absolute inset-0 w-full h-full object-cover"
        preload="none"
        playsInline
        controls={started}
        poster={video.poster}
        onPlay={() => track("demo_video_play", video.gaTitle)}
        onEnded={() => track("demo_video_complete", video.gaTitle)}
        aria-label={video.alt}
      >
        <source src={video.src} type="video/mp4" />
        <track kind="captions" src={video.captions} srcLang="en" label="English" />
      </video>

      {!started && (
        <button
          type="button"
          onClick={play}
          aria-label={video.ariaLabel}
          className="group absolute inset-0 flex items-end justify-center pb-2.5 sm:pb-7 bg-black/5 hover:bg-black/15 transition-colors"
        >
          <span className="flex items-center gap-2 sm:gap-3 bg-orange-600 group-hover:bg-orange-500 text-white text-xs sm:text-base font-semibold pl-3.5 pr-4 py-2 sm:pl-5 sm:pr-6 sm:py-3.5 rounded-full shadow-[0_0_40px_rgba(234,88,12,0.5)] transition-all group-hover:scale-105">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.14v13.72a1 1 0 0 0 1.5.86l11-6.86a1 1 0 0 0 0-1.72l-11-6.86A1 1 0 0 0 8 5.14z" /></svg>
            {video.label}
          </span>
        </button>
      )}
    </div>
  );
}
