import { useEffect, useRef } from "react";

export default function StarField({ count = 160, speed = 0.4, className = "" }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let animId;
    let W, H;

    // ── Static stars ──────────────────────────────
    const stars = [];

    // ── Shooting stars ────────────────────────────
    const shooters = [];
    const MAX_SHOOTERS = 3;

    // ── Satellites ────────────────────────────────
    const satellites = [];
    const MAX_SATS = 2;

    const resize = () => {
      W = canvas.width  = canvas.offsetWidth;
      H = canvas.height = canvas.offsetHeight;
    };

    const randBetween = (a, b) => a + Math.random() * (b - a);

    // Spawn a shooting star from a random top/left edge
    const spawnShooter = () => {
      const fromTop = Math.random() > 0.4;
      const angle   = fromTop
        ? randBetween(20, 60) * Math.PI / 180        // diagonal down-right
        : randBetween(10, 40) * Math.PI / 180;       // shallow angle from left
      const spd     = randBetween(6, 14);
      const len     = randBetween(80, 220);
      return {
        x:     fromTop ? randBetween(0, W) : -20,
        y:     fromTop ? randBetween(-20, H * 0.3) : randBetween(0, H * 0.5),
        vx:    Math.cos(angle) * spd,
        vy:    Math.sin(angle) * spd,
        len,
        alpha: 0,
        phase: "in",       // in → hold → out
        holdFrames: Math.floor(randBetween(4, 14)),
        heldFor: 0,
        color: Math.random() > 0.5 ? "255,255,255" : "255,220,160",
      };
    };

    // Spawn a satellite — slow, straight, blinking
    const spawnSatellite = () => {
      const fromLeft = Math.random() > 0.5;
      const angle    = randBetween(-8, 8) * Math.PI / 180;
      const spd      = randBetween(0.6, 1.4);
      return {
        x:     fromLeft ? -30 : W + 30,
        y:     randBetween(H * 0.05, H * 0.45),
        vx:    fromLeft ? Math.cos(angle) * spd : -Math.cos(angle) * spd,
        vy:    Math.sin(angle) * spd,
        size:  randBetween(2.5, 3.8),
        alpha: 0,
        blinkTimer: 0,
        blinkInterval: Math.floor(randBetween(40, 90)),
        blinkOn: true,
        // tiny solar panel wings
        wingLen: randBetween(6, 10),
      };
    };

    const init = () => {
      resize();
      stars.length = 0;
      for (let i = 0; i < count; i++) {
        stars.push({
          x:          Math.random() * W,
          y:          Math.random() * H,
          r:          randBetween(0.2, 1.5),
          vx:         (Math.random() - 0.5) * speed,
          vy:         (Math.random() - 0.5) * speed,
          alpha:      randBetween(0.15, 0.75),
          twinkleSpd: randBetween(0.004, 0.018),
          twinkleDir: Math.random() > 0.5 ? 1 : -1,
        });
      }
      // Initial satellite
      if (satellites.length === 0) satellites.push(spawnSatellite());
    };

    // ── Draw satellite body ────────────────────────
    const drawSatellite = (s) => {
      if (!s.blinkOn) return;
      ctx.save();
      ctx.globalAlpha = s.alpha * 0.85;
      ctx.translate(s.x, s.y);

      // Body — small bright square
      ctx.fillStyle = "rgba(200,220,255,1)";
      const b = s.size;
      ctx.fillRect(-b/2, -b/2, b, b);

      // Solar panels — two thin rects left/right
      ctx.fillStyle = "rgba(100,160,255,0.7)";
      ctx.fillRect(-b/2 - s.wingLen, -b/4, s.wingLen - 1, b/2);
      ctx.fillRect( b/2 + 1,         -b/4, s.wingLen - 1, b/2);

      // Tiny signal dot
      ctx.beginPath();
      ctx.arc(0, 0, 0.7, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255,255,255,0.9)";
      ctx.fill();

      ctx.restore();
    };

    const draw = () => {
      ctx.clearRect(0, 0, W, H);

      // ── Static stars ──────────────────────────
      for (const s of stars) {
        s.alpha += s.twinkleSpd * s.twinkleDir;
        if (s.alpha >= 0.8 || s.alpha <= 0.05) s.twinkleDir *= -1;
        s.x += s.vx; s.y += s.vy;
        if (s.x < -2) s.x = W + 2;
        if (s.x > W + 2) s.x = -2;
        if (s.y < -2) s.y = H + 2;
        if (s.y > H + 2) s.y = -2;

        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${s.alpha})`;
        ctx.fill();
      }

      // ── Glow stars ────────────────────────────
      for (let i = 0; i < stars.length; i += 18) {
        const s = stars[i];
        const grd = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.r * 5);
        grd.addColorStop(0, `rgba(255,210,150,${s.alpha * 0.5})`);
        grd.addColorStop(1, "rgba(255,210,150,0)");
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r * 5, 0, Math.PI * 2);
        ctx.fillStyle = grd;
        ctx.fill();
      }

      // ── Shooting stars ────────────────────────
      // Randomly spawn
      if (shooters.length < MAX_SHOOTERS && Math.random() < 0.003) {
        shooters.push(spawnShooter());
      }

      for (let i = shooters.length - 1; i >= 0; i--) {
        const s = shooters[i];

        // Phase transitions
        if (s.phase === "in") {
          s.alpha = Math.min(s.alpha + 0.08, 1);
          if (s.alpha >= 1) s.phase = "hold";
        } else if (s.phase === "hold") {
          s.heldFor++;
          if (s.heldFor >= s.holdFrames) s.phase = "out";
        } else {
          s.alpha = Math.max(s.alpha - 0.06, 0);
        }

        s.x += s.vx; s.y += s.vy;

        // Tail — gradient line
        const tailX = s.x - s.vx * (s.len / Math.hypot(s.vx, s.vy));
        const tailY = s.y - s.vy * (s.len / Math.hypot(s.vx, s.vy));

        const grad = ctx.createLinearGradient(tailX, tailY, s.x, s.y);
        grad.addColorStop(0, `rgba(${s.color},0)`);
        grad.addColorStop(0.6, `rgba(${s.color},${s.alpha * 0.3})`);
        grad.addColorStop(1, `rgba(${s.color},${s.alpha})`);

        ctx.beginPath();
        ctx.moveTo(tailX, tailY);
        ctx.lineTo(s.x, s.y);
        ctx.strokeStyle = grad;
        ctx.lineWidth   = 1.5;
        ctx.stroke();

        // Head glow
        const hgrd = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, 4);
        hgrd.addColorStop(0, `rgba(${s.color},${s.alpha})`);
        hgrd.addColorStop(1, `rgba(${s.color},0)`);
        ctx.beginPath();
        ctx.arc(s.x, s.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = hgrd;
        ctx.fill();

        // Remove if off-screen or faded
        if (s.alpha <= 0 || s.x > W + 50 || s.y > H + 50 || s.x < -50 || s.y < -50) {
          shooters.splice(i, 1);
        }
      }

      // ── Satellites ────────────────────────────
      // Randomly spawn new satellite
      if (satellites.length < MAX_SATS && Math.random() < 0.0005) {
        satellites.push(spawnSatellite());
      }

      for (let i = satellites.length - 1; i >= 0; i--) {
        const s = satellites[i];

        // Fade in / fade out near edges
        const edgeDist = Math.min(s.x, W - s.x, 80);
        s.alpha = Math.min(s.alpha + 0.008, Math.min(1, edgeDist / 80));

        // Blink logic
        s.blinkTimer++;
        if (s.blinkTimer >= s.blinkInterval) {
          s.blinkTimer = 0;
          s.blinkOn = !s.blinkOn;
          s.blinkInterval = Math.floor(randBetween(30, 80));
        }

        s.x += s.vx; s.y += s.vy;

        drawSatellite(s);

        // Remove if off-screen
        if (s.x < -60 || s.x > W + 60 || s.y < -60 || s.y > H + 60) {
          satellites.splice(i, 1);
        }
      }

      animId = requestAnimationFrame(draw);
    };

    init();
    draw();

    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    return () => { cancelAnimationFrame(animId); ro.disconnect(); };
  }, [count, speed]);

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 w-full h-full pointer-events-none ${className}`}
    />
  );
}
