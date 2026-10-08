import { useState } from "react";
import { API_BASE } from "@/lib/api";

// Loaded once per page view, so a card re-rendered after a regenerate shows up on reload.
const VISUAL_VERSION = Date.now();

export default function TouchVisual({ touch }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  const src = `${API_BASE}/touches/${touch.id}/visual.jpg?v=${VISUAL_VERSION}`;
  return (
    <div className="px-5 pt-4 flex gap-4 items-start" data-testid={`touch-visual-${touch.touch_num}`}>
      <a href={src} target="_blank" rel="noreferrer" className="shrink-0">
        <img src={src} alt="Card sent with this touch" loading="lazy" onError={() => setFailed(true)}
          className="w-28 rounded-lg" style={{ border: "1px solid var(--border)" }} />
      </a>
      <div className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
        This card goes out with the post and the email, so the reminder carries something worth saving.
        It's built from the Lead Magnets tab; edit that and regenerate to change it.
        <div className="mt-2">
          <a href={src} download target="_blank" rel="noreferrer" className="underline">Download card</a>
        </div>
      </div>
    </div>
  );
}
