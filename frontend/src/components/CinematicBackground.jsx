import { useEffect, useRef } from "react";

export default function CinematicBackground({ intensity = 1 }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let animId;
    let W, H, mouse = { x: 0, y: 0 };

    const resize = () => {
      W = canvas.width  = canvas.offsetWidth;
      H = canvas.height = canvas.offsetHeight;
    };

    const rand = (a, b) => a + Math.random() * (b - a);

    // ── Particle system ─────────────────────────
    const PARTICLE_COUNT = Math.floor(120 * intensity);
    const particles = Array.from({ length: PARTICLE_COUNT }, () => ({
      x: rand(0, 1), y: rand(0, 1),
      vx: rand(-0.0002, 0.0002), vy: rand(-0.0003, -0.0001),
      size: rand(0.5, 2.5),
      alpha: rand(0.1, 0.7),
      color: Math.random() > 0.6 ? "234,88,12" : "255,255,255",
      pulse: rand(0, Math.PI * 2),
      pulseSpeed: rand(0.005, 0.02),
    }));

    // ── LayoutDashboard lines (holographic) ─────────────────
    const GRID_COLS = 12;
    const GRID_ROWS = 8;

    // ── Orbs ─────────────────────────────────────
    const orbs = [
      { x: 0.2, y: 0.3, r: 0.25, color: "234,88,12", speed: 0.0003 },
      { x: 0.8, y: 0.6, r: 0.2,  color: "234,88,12", speed: 0.0002 },
      { x: 0.5, y: 0.8, r: 0.18, color: "180,60,5", speed: 0.00025 },
    ];

    let t = 0;

    const onMouseMove = (e) => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = (e.clientX - rect.left) / W;
      mouse.y = (e.clientY - rect.top) / H;
    };
    canvas.addEventListener("mousemove", onMouseMove);

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const draw = () => {
      t += 0.01;
      ctx.clearRect(0, 0, W, H);

      // ── Radial gradient background ────────────
      const bg = ctx.createRadialGradient(W * 0.5, H * 0.3, 0, W * 0.5, H * 0.3, W * 0.8);
      bg.addColorStop(0, "rgba(15,5,30,1)");
      bg.addColorStop(0.5, "rgba(5,5,15,1)");
      bg.addColorStop(1, "rgba(2,2,8,1)");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);

      // ── Glow orbs ────────────────────────────
      orbs.forEach((orb, i) => {
        const ox = orb.x + Math.sin(t * orb.speed * 100 + i) * 0.1;
        const oy = orb.y + Math.cos(t * orb.speed * 80 + i) * 0.08;
        const grd = ctx.createRadialGradient(ox*W, oy*H, 0, ox*W, oy*H, orb.r * W);
        grd.addColorStop(0, `rgba(${orb.color},0.12)`);
        grd.addColorStop(0.5, `rgba(${orb.color},0.04)`);
        grd.addColorStop(1, `rgba(${orb.color},0)`);
        ctx.fillStyle = grd;
        ctx.fillRect(0, 0, W, H);
      });

      // Mouse interactive glow
      const mgrd = ctx.createRadialGradient(mouse.x*W, mouse.y*H, 0, mouse.x*W, mouse.y*H, W*0.2);
      mgrd.addColorStop(0, "rgba(234,88,12,0.06)");
      mgrd.addColorStop(1, "rgba(234,88,12,0)");
      ctx.fillStyle = mgrd;
      ctx.fillRect(0, 0, W, H);

      // ── Holographic grid ──────────────────────
      const gridAlpha = 0.025 + Math.sin(t * 0.5) * 0.008;
      ctx.strokeStyle = `rgba(234,88,12,${gridAlpha * 0.4})`;
      ctx.lineWidth = 0.5;
      // Vertical lines
      for (let i = 0; i <= GRID_COLS; i++) {
        const x = (i / GRID_COLS) * W;
        const offset = Math.sin(t * 0.3 + i * 0.5) * 3;
        ctx.beginPath();
        ctx.moveTo(x + offset, 0);
        ctx.lineTo(x - offset, H);
        ctx.stroke();
      }
      // Horizontal lines (perspective-like)
      for (let j = 0; j <= GRID_ROWS; j++) {
        const y = (j / GRID_ROWS) * H;
        const alpha = gridAlpha * (1 - j / GRID_ROWS * 0.5);
        ctx.strokeStyle = `rgba(234,88,12,${alpha * 0.3})`;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(W, y);
        ctx.stroke();
      }

      // ── Particles ────────────────────────────
      particles.forEach(p => {
        p.x += p.vx + (mouse.x - p.x) * 0.00005;
        p.y += p.vy;
        p.pulse += p.pulseSpeed;

        if (p.y < -0.02) { p.y = 1.02; p.x = Math.random(); }
        if (p.x < -0.02) p.x = 1.02;
        if (p.x >  1.02) p.x = -0.02;

        const pulseAlpha = p.alpha * (0.7 + 0.3 * Math.sin(p.pulse));
        const px = p.x * W, py = p.y * H;

        // Glow
        const pgrd = ctx.createRadialGradient(px, py, 0, px, py, p.size * 4);
        pgrd.addColorStop(0, `rgba(${p.color},${pulseAlpha * 0.8})`);
        pgrd.addColorStop(1, `rgba(${p.color},0)`);
        ctx.beginPath();
        ctx.arc(px, py, p.size * 4, 0, Math.PI * 2);
        ctx.fillStyle = pgrd;
        ctx.fill();

        // Core
        ctx.beginPath();
        ctx.arc(px, py, p.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${p.color},${pulseAlpha})`;
        ctx.fill();
      });

      // ── Scanning line ────────────────────────
      const scanY = ((t * 0.3) % 1) * H;
      const scanGrd = ctx.createLinearGradient(0, scanY - 40, 0, scanY + 40);
      scanGrd.addColorStop(0, "rgba(234,88,12,0)");
      scanGrd.addColorStop(0.5, "rgba(234,88,12,0.03)");
      scanGrd.addColorStop(1, "rgba(234,88,12,0)");
      ctx.fillStyle = scanGrd;
      ctx.fillRect(0, scanY - 40, W, 80);

      // ── Connection lines between nearby particles ─
      for (let i = 0; i < particles.length; i += 3) {
        for (let j = i + 1; j < Math.min(i + 8, particles.length); j++) {
          const dx = (particles[i].x - particles[j].x) * W;
          const dy = (particles[i].y - particles[j].y) * H;
          const dist = Math.sqrt(dx*dx + dy*dy);
          if (dist < 80) {
            const lineAlpha = (1 - dist/80) * 0.08;
            ctx.strokeStyle = `rgba(139,92,246,${lineAlpha})`;
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(particles[i].x*W, particles[i].y*H);
            ctx.lineTo(particles[j].x*W, particles[j].y*H);
            ctx.stroke();
          }
        }
      }

      animId = requestAnimationFrame(draw);
    };

    draw();
    return () => {
      cancelAnimationFrame(animId);
      canvas.removeEventListener("mousemove", onMouseMove);
      ro.disconnect();
    };
  }, [intensity]);

  return (
    <canvas ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none"
      style={{ mixBlendMode: "screen" }} />
  );
}
