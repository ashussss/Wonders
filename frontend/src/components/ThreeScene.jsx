import { useEffect, useRef } from "react";

export default function ThreeScene({ mode = "hero" }) {
  const mountRef = useRef(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    let animId, renderer, cleanup = [];

    const script = document.createElement("script");
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js";
    script.onload = () => {
      const THREE = window.THREE;
      const W = mount.offsetWidth, H = mount.offsetHeight;

      // ── Renderer ──────────────────────────
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setSize(W, H);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setClearColor(0x000000, 0);
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.5;
      mount.appendChild(renderer.domElement);

      const scene = new THREE.Scene();
      scene.fog = new THREE.FogExp2(0x000510, 0.008);

      const camera = new THREE.PerspectiveCamera(70, W / H, 0.1, 2000);
      camera.position.set(0, 0, 90);

      // ── Colors ────────────────────────────
      const C = {
        orange: new THREE.Color(0xFF5500),
        purple: new THREE.Color(0x7C3AED),
        blue:   new THREE.Color(0x2563EB),
        cyan:   new THREE.Color(0x06B6D4),
        white:  new THREE.Color(0xFFFFFF),
        gold:   new THREE.Color(0xFFAA00),
      };
      const palette = [C.orange, C.purple, C.blue, C.cyan, C.white, C.gold];

      // ── MAIN SPHERE — 8000 particles ──────
      const N = 8000;
      const pos = new Float32Array(N * 3);
      const col = new Float32Array(N * 3);
      const sz  = new Float32Array(N);
      const vel = new Float32Array(N * 3); // for turbulence

      for (let i = 0; i < N; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi   = Math.acos(2 * Math.random() - 1);
        // Multiple shell layers
        const shell = Math.floor(Math.random() * 3);
        const r = [38, 48, 58][shell] + (Math.random() - 0.5) * 8;

        pos[i*3]   = r * Math.sin(phi) * Math.cos(theta);
        pos[i*3+1] = r * Math.sin(phi) * Math.sin(theta);
        pos[i*3+2] = r * Math.cos(phi);

        vel[i*3]   = (Math.random() - 0.5) * 0.02;
        vel[i*3+1] = (Math.random() - 0.5) * 0.02;
        vel[i*3+2] = (Math.random() - 0.5) * 0.02;

        const c = palette[Math.floor(Math.random() * palette.length)];
        col[i*3]   = c.r;
        col[i*3+1] = c.g;
        col[i*3+2] = c.b;

        sz[i] = Math.random() * 2 + 0.4;
      }

      const sGeo = new THREE.BufferGeometry();
      sGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      sGeo.setAttribute("color",    new THREE.BufferAttribute(col, 3));

      const sMat = new THREE.PointsMaterial({
        size: 1.4, vertexColors: true,
        transparent: true, opacity: 0.95,
        sizeAttenuation: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const sphere = new THREE.Points(sGeo, sMat);
      scene.add(sphere);

      // Glow pass
      const gGeo = new THREE.BufferGeometry();
      gGeo.setAttribute("position", new THREE.BufferAttribute(pos.slice(), 3));
      gGeo.setAttribute("color",    new THREE.BufferAttribute(col.slice(), 3));
      const gMat = new THREE.PointsMaterial({
        size: 6, vertexColors: true,
        transparent: true, opacity: 0.06,
        sizeAttenuation: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      scene.add(new THREE.Points(gGeo, gMat));

      // ── RINGS — 5 orbital rings ────────────
      const ringData = [
        { r: 52, tube: 0.2, col: 0xFF5500, opacity: 0.6, speed: 0.003,  tilt: [0.3, 0, 0] },
        { r: 62, tube: 0.15, col: 0x7C3AED, opacity: 0.5, speed: -0.002, tilt: [0, 0.5, 0.2] },
        { r: 44, tube: 0.12, col: 0x06B6D4, opacity: 0.4, speed: 0.004,  tilt: [0.8, 0.3, 0] },
        { r: 70, tube: 0.1,  col: 0xFFAA00, opacity: 0.3, speed: -0.001, tilt: [0.2, 0.8, 0.1] },
        { r: 36, tube: 0.08, col: 0x2563EB, opacity: 0.25,speed: 0.005,  tilt: [1.2, 0.1, 0.5] },
      ];

      const rings = ringData.map(d => {
        const geo = new THREE.TorusGeometry(d.r, d.tube, 8, 200);
        const mat = new THREE.MeshBasicMaterial({
          color: d.col, transparent: true, opacity: d.opacity,
          blending: THREE.AdditiveBlending, depthWrite: false,
        });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.rotation.set(...d.tilt);
        mesh.userData = { speed: d.speed };
        scene.add(mesh);
        return mesh;
      });

      // ── NEBULA CLOUDS — volumetric look ────
      const nebulaCount = 2000;
      const nebPos = new Float32Array(nebulaCount * 3);
      const nebCol = new Float32Array(nebulaCount * 3);
      for (let i = 0; i < nebulaCount; i++) {
        const angle = Math.random() * Math.PI * 2;
        const r = Math.random() * 130 + 30;
        const spread = (Math.random() - 0.5) * 60;
        nebPos[i*3]   = Math.cos(angle) * r;
        nebPos[i*3+1] = spread;
        nebPos[i*3+2] = Math.sin(angle) * r - 80;
        const nc = Math.random() > 0.5 ? C.purple : Math.random() > 0.5 ? C.orange : C.blue;
        nebCol[i*3]   = nc.r;
        nebCol[i*3+1] = nc.g;
        nebCol[i*3+2] = nc.b;
      }
      const nebGeo = new THREE.BufferGeometry();
      nebGeo.setAttribute("position", new THREE.BufferAttribute(nebPos, 3));
      nebGeo.setAttribute("color",    new THREE.BufferAttribute(nebCol, 3));
      const nebMat = new THREE.PointsMaterial({
        size: 8, vertexColors: true, transparent: true, opacity: 0.04,
        sizeAttenuation: true, blending: THREE.AdditiveBlending, depthWrite: false,
      });
      scene.add(new THREE.Points(nebGeo, nebMat));

      // ── ENERGY CORE ────────────────────────
      const coreGeo = new THREE.IcosahedronGeometry(6, 2);
      const coreMat = new THREE.MeshBasicMaterial({
        color: 0xFF6600, wireframe: true, transparent: true, opacity: 0.15,
        blending: THREE.AdditiveBlending,
      });
      const core = new THREE.Mesh(coreGeo, coreMat);
      scene.add(core);

      // Inner core glow
      const innerGeo = new THREE.SphereGeometry(4, 16, 16);
      const innerMat = new THREE.MeshBasicMaterial({
        color: 0xFF8800, transparent: true, opacity: 0.08,
        blending: THREE.AdditiveBlending,
      });
      scene.add(new THREE.Mesh(innerGeo, innerMat));

      // ── SHOOTING STARS ─────────────────────
      const shooters = Array.from({ length: 8 }, () => ({
        active: false, progress: 0, speed: 0,
        start: new THREE.Vector3(), end: new THREE.Vector3(),
        mesh: null,
      }));

      const spawnShooter = (s) => {
        s.active = true; s.progress = 0;
        s.speed = Math.random() * 0.015 + 0.008;
        s.start.set((Math.random() - 0.5) * 200, (Math.random() - 0.5) * 100, (Math.random() - 0.5) * 100);
        s.end.set((Math.random() - 0.5) * 200, (Math.random() - 0.5) * 100, (Math.random() - 0.5) * 100);
      };

      shooters.forEach((s, i) => { if (Math.random() > 0.5) spawnShooter(s); });

      const shootGeo = new THREE.BufferGeometry();
      const shootPos = new Float32Array(shooters.length * 2 * 3);
      shootGeo.setAttribute("position", new THREE.BufferAttribute(shootPos, 3));
      const shootMat = new THREE.LineBasicMaterial({
        color: 0xFFFFFF, transparent: true, opacity: 0.6,
        blending: THREE.AdditiveBlending,
      });
      // (Line segments for shooters drawn procedurally)

      // ── MOUSE ─────────────────────────────
      let mx = 0, my = 0, tmx = 0, tmy = 0;
      const onMouse = (e) => {
        tmx = (e.clientX / window.innerWidth  - 0.5) * 2;
        tmy = (e.clientY / window.innerHeight - 0.5) * 2;
      };
      window.addEventListener("mousemove", onMouse);
      cleanup.push(() => window.removeEventListener("mousemove", onMouse));

      // ── RESIZE ────────────────────────────
      const onResize = () => {
        const w = mount.offsetWidth, h = mount.offsetHeight;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      };
      window.addEventListener("resize", onResize);
      cleanup.push(() => window.removeEventListener("resize", onResize));

      // ── ANIMATE ───────────────────────────
      let t = 0;
      const animate = () => {
        animId = requestAnimationFrame(animate);
        t += 0.008;

        // Smooth mouse
        mx += (tmx - mx) * 0.04;
        my += (tmy - my) * 0.04;

        // Sphere rotation — dramatic + mouse tilt
        sphere.rotation.y = t * 0.18 + mx * 0.5;
        sphere.rotation.x = t * 0.06 + my * 0.3;
        sphere.rotation.z = Math.sin(t * 0.1) * 0.1;

        // Core pulse + spin
        core.rotation.x = t * 0.4;
        core.rotation.y = t * 0.3;
        const pulse = 1 + Math.sin(t * 3) * 0.15;
        core.scale.setScalar(pulse);

        // Rings orbit
        rings.forEach((r, i) => {
          r.rotation.z += r.userData.speed;
          r.rotation.x += r.userData.speed * 0.3;
          // Subtle breathe
          const s = 1 + Math.sin(t * 0.5 + i) * 0.02;
          r.scale.setScalar(s);
        });

        // Particle turbulence
        const posArr = sGeo.attributes.position.array;
        for (let i = 0; i < N; i += 20) { // update subset per frame for perf
          posArr[i*3]   += Math.sin(t + i) * 0.003;
          posArr[i*3+1] += Math.cos(t + i * 0.7) * 0.003;
        }
        sGeo.attributes.position.needsUpdate = true;

        // Glow copy follows sphere
        gGeo.attributes.position.array.set(posArr);
        gGeo.attributes.position.needsUpdate = true;

        // Shooting stars
        shooters.forEach((s, i) => {
          if (!s.active) {
            if (Math.random() < 0.003) spawnShooter(s);
            return;
          }
          s.progress += s.speed;
          if (s.progress >= 1) { s.active = false; }
        });

        // Camera orbit + mouse follow
        camera.position.x += (mx * 20 - camera.position.x) * 0.015;
        camera.position.y += (-my * 12 - camera.position.y) * 0.015;
        camera.position.z = 90 + Math.sin(t * 0.2) * 5;
        camera.lookAt(0, 0, 0);

        renderer.render(scene, camera);
      };
      animate();

      cleanup.push(() => {
        cancelAnimationFrame(animId);
        renderer.dispose();
        if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement);
      });
    };

    document.head.appendChild(script);
    return () => {
      cleanup.forEach(fn => fn());
      if (script.parentNode) script.parentNode.removeChild(script);
    };
  }, []);

  return (
    <div ref={mountRef} className="absolute inset-0 w-full h-full pointer-events-none" style={{ zIndex: 1 }} />
  );
}
