/* ═══════════════════════════════════════════════════════════════════════
   INVIQ — Interactive Honeycomb (v4, magnetic + 3D relief)
   A hexagonal mesh (colmeia) whose vertices GRAB toward the cursor — each
   moves a fraction of the way to the pointer, so nearby lines stick to it
   (they never flee). The grabbed region rises in Z into a dome, rendered
   as 3D relief through depth-driven size, brightness and glow (no outward
   perspective push, so nothing runs away from the cursor). Scrolling sends
   a traveling wave through the comb. Self-contained canvas 2D; respects
   prefers-reduced-motion and pauses when hidden.

   Usage: <canvas id="hive-canvas"></canvas> + <script src="/static/js/hive.js"></script>
   data-size="32"   hex radius px (smaller = denser, smoother dome)
   data-grab="0.8"  how hard lines stick to the cursor (0..0.9)
   data-reach="210" cursor influence radius px
   data-bulge="150" 3D dome height
   data-flow="2.6"  idle wave amplitude
═══════════════════════════════════════════════════════════════════════ */
(function () {
  const canvas = document.getElementById('hive-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const R      = parseFloat(canvas.dataset.size  || '32');
  const GRAB   = Math.min(parseFloat(canvas.dataset.grab || '0.8'), 0.9);
  const REACH  = parseFloat(canvas.dataset.reach || '210');
  const BULGE  = parseFloat(canvas.dataset.bulge || '150');
  const FLOW   = parseFloat(canvas.dataset.flow  || '2.6');
  const LIFT   = 0.07;   // subtle upward screen offset per unit Z (relief hint)

  const BASE = [92, 132, 224];   // cool blue
  const HOT  = [162, 118, 255];  // violet

  let W = 0, H = 0, DPR = 1, raf = null, t = 0;
  let verts = [];   // { hx,hy, x,y,z, sx,sy }
  let edges = [];   // [i, j]
  const mouse = { x: -9999, y: -9999, active: false };
  const REACH2 = REACH * REACH;

  let scrollPhase = 0, scrollEnergy = 0;

  function buildGrid() {
    verts = []; edges = [];
    const map = new Map();
    const key = (x, y) => Math.round(x) + ',' + Math.round(y);
    function vid(x, y) {
      const k = key(x, y);
      if (map.has(k)) return map.get(k);
      const id = verts.length;
      verts.push({ hx: x, hy: y, x, y, z: 0, sx: x, sy: y });
      map.set(k, id);
      return id;
    }
    const angs = [];
    for (let k = 0; k < 6; k++) angs.push((Math.PI / 180) * (60 * k - 90));
    const w = Math.sqrt(3) * R;
    const vspace = 1.5 * R;
    const cols = Math.ceil(W / w) + 2;
    const rows = Math.ceil(H / vspace) + 2;
    const edgeSet = new Set();
    for (let r = -1; r < rows; r++) {
      for (let c = -1; c < cols; c++) {
        const hcx = c * w + (r & 1 ? w / 2 : 0);
        const hcy = r * vspace;
        const ids = [];
        for (let k = 0; k < 6; k++) {
          ids.push(vid(hcx + R * Math.cos(angs[k]), hcy + R * Math.sin(angs[k])));
        }
        for (let k = 0; k < 6; k++) {
          let a = ids[k], b = ids[(k + 1) % 6];
          if (a === b) continue;
          if (a > b) { const tmp = a; a = b; b = tmp; }
          const ek = a + '-' + b;
          if (!edgeSet.has(ek)) { edgeSet.add(ek); edges.push([a, b]); }
        }
      }
    }
  }

  function resize() {
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    W = rect.width; H = rect.height;
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    buildGrid();
  }

  function updateVerts() {
    scrollEnergy *= 0.93;
    if (scrollEnergy < 0.02) scrollEnergy = 0;

    const flowAmp = FLOW + scrollEnergy * 0.7;
    const ease = 0.2, zEase = 0.16;

    for (const v of verts) {
      // gentle flowing base position (keeps the comb alive when idle)
      let bx = v.hx + Math.cos(v.hx * 0.011 + t * 0.017 - scrollPhase * 0.5) * flowAmp;
      let by = v.hy + Math.sin(v.hy * 0.010 + t * 0.021 + scrollPhase * 0.7) * flowAmp;
      let tz = Math.sin(v.hx * 0.008 + v.hy * 0.006 + t * 0.02) * 6;

      // scroll shockwave (also lifts Z)
      if (scrollEnergy > 0.05) {
        const band = Math.sin(v.hy * 0.022 - scrollPhase * 1.4);
        by += band * scrollEnergy * 0.9;
        tz += band * scrollEnergy * 1.5;
      }

      let tx = bx, ty = by;

      // MAGNETIC GRAB: move a fraction of the way toward the cursor, so lines
      // stick to it (fraction scales with proximity → no overshoot, no flee)
      if (mouse.active) {
        const dx = mouse.x - bx, dy = mouse.y - by;
        const d2 = dx * dx + dy * dy;
        if (d2 < REACH2) {
          const f = 1 - Math.sqrt(d2) / REACH;   // 0..1
          const grab = GRAB * f * f;             // ease-in stickiness
          tx = bx + dx * grab;
          ty = by + dy * grab;
          tz += BULGE * (0.5 - 0.5 * Math.cos(f * Math.PI));  // smooth dome
        }
      }

      v.x += (tx - v.x) * ease;
      v.y += (ty - v.y) * ease;
      v.z += (tz - v.z) * zEase;
      // screen position: no outward perspective; only a tiny upward relief lift
      v.sx = v.x;
      v.sy = v.y - v.z * LIFT;
    }
  }

  function frame() {
    t += 1;
    updateVerts();
    ctx.clearRect(0, 0, W, H);

    const breathe = 0.5 + 0.5 * Math.sin(t * 0.012);
    const energyGlow = Math.min(scrollEnergy * 0.02, 0.28);
    const baseAlpha = 0.10 + breathe * 0.05 + energyGlow;
    const invB = 1 / BULGE;

    for (const [ia, ib] of edges) {
      const a = verts[ia], b = verts[ib];
      // depth cue from Z (0 at rest → 1 at dome apex): brighter, thicker, violet
      const dk = Math.min(Math.max((a.z + b.z) * 0.5 * invB, 0), 1);
      const alpha = Math.min(baseAlpha + dk * 0.62, 0.98);
      const col = [
        Math.round(BASE[0] + (HOT[0] - BASE[0]) * dk),
        Math.round(BASE[1] + (HOT[1] - BASE[1]) * dk),
        Math.round(BASE[2] + (HOT[2] - BASE[2]) * dk),
      ];
      ctx.lineWidth = 0.85 + dk * 1.7;
      ctx.strokeStyle = `rgba(${col[0]},${col[1]},${col[2]},${alpha})`;
      ctx.beginPath();
      ctx.moveTo(a.sx, a.sy);
      ctx.lineTo(b.sx, b.sy);
      ctx.stroke();
    }

    // glowing apex nodes (the risen dome tips near the cursor)
    ctx.shadowColor = `rgb(${HOT[0]},${HOT[1]},${HOT[2]})`;
    ctx.fillStyle = `rgb(${HOT[0]},${HOT[1]},${HOT[2]})`;
    for (const v of verts) {
      const dk = v.z * invB;
      if (dk <= 0.06) continue;
      ctx.globalAlpha = Math.min(dk, 1) * 0.92;
      ctx.shadowBlur = 10;
      ctx.beginPath();
      ctx.arc(v.sx, v.sy, 1.3 + Math.min(dk, 1) * 2.8, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;

    raf = requestAnimationFrame(frame);
  }

  /* ── interaction ─────────────────────────────────────────────────── */
  function pointer(e) {
    const rect = canvas.getBoundingClientRect();
    const src = e.touches ? e.touches[0] : e;
    if (!src) return;
    mouse.x = src.clientX - rect.left;
    mouse.y = src.clientY - rect.top;
    mouse.active = true;
  }
  function clearPointer() { mouse.active = false; mouse.x = mouse.y = -9999; }

  let lastTouchY = null;
  function addScroll(delta) {
    scrollPhase += delta * 0.006;
    scrollEnergy = Math.min(scrollEnergy + Math.abs(delta) * 0.06, 26);
  }
  window.addEventListener('wheel', (e) => addScroll(e.deltaY), { passive: true });
  window.addEventListener('scroll', () => addScroll(8), { passive: true, capture: true });
  window.addEventListener('touchstart', (e) => { lastTouchY = e.touches[0] ? e.touches[0].clientY : null; }, { passive: true });
  window.addEventListener('touchmove', (e) => {
    pointer(e);
    if (lastTouchY != null && e.touches[0]) {
      const dy = lastTouchY - e.touches[0].clientY;
      addScroll(dy * 1.4);
      lastTouchY = e.touches[0].clientY;
    }
  }, { passive: true });

  window.addEventListener('mousemove', pointer, { passive: true });
  window.addEventListener('mouseleave', clearPointer);
  window.addEventListener('touchend', () => { clearPointer(); lastTouchY = null; });

  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resize, 180);
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { if (raf) cancelAnimationFrame(raf); raf = null; }
    else if (!reduce && !raf) { raf = requestAnimationFrame(frame); }
  });

  resize();
  if (reduce) { updateVerts(); frame(); if (raf) cancelAnimationFrame(raf); raf = null; }
  else raf = requestAnimationFrame(frame);
})();
