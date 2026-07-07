/* ═══════════════════════════════════════════════════════════════════════
   INVIQ — Interactive Honeycomb (v3, pseudo-3D)
   A hexagonal mesh (colmeia) with real depth: every vertex has a Z axis and
   is projected in perspective. Near the cursor the comb is pulled in XY AND
   lifted toward the viewer, forming a 3D dome that follows the pointer.
   Scrolling injects a traveling depth-shockwave. Lines/nodes closer to the
   camera grow brighter and thicker. Self-contained canvas 2D; respects
   prefers-reduced-motion and pauses when the tab is hidden.

   Usage: <canvas id="hive-canvas"></canvas> + <script src="/static/js/hive.js"></script>
   data-size="44"    hex radius px      data-pull="48"   XY attraction px
   data-reach="215"  cursor radius px   data-bulge="170" 3D lift toward viewer
   data-flow="3.4"   idle wave amplitude
═══════════════════════════════════════════════════════════════════════ */
(function () {
  const canvas = document.getElementById('hive-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const R      = parseFloat(canvas.dataset.size  || '44');
  const PULL   = parseFloat(canvas.dataset.pull  || '48');
  const REACH  = parseFloat(canvas.dataset.reach || '215');
  const BULGE  = parseFloat(canvas.dataset.bulge || '170');   // 3D lift toward camera
  const FLOW   = parseFloat(canvas.dataset.flow  || '3.4');
  const FOV    = 460;                                          // perspective focal length

  const BASE = [96, 140, 230];   // cool blue
  const HOT  = [155, 112, 255];  // violet

  let W = 0, H = 0, DPR = 1, raf = null, t = 0;
  let cx = 0, cy = 0;            // camera / projection center
  let verts = [];               // { hx,hy, x,y,z, sx,sy,s }
  let edges = [];               // [i, j]
  const mouse = { x: -9999, y: -9999, active: false };
  const REACH2 = REACH * REACH;

  let scrollPhase = 0, scrollEnergy = 0, swirlDir = 1;

  function buildGrid() {
    verts = []; edges = [];
    const map = new Map();
    const key = (x, y) => Math.round(x) + ',' + Math.round(y);
    function vid(x, y) {
      const k = key(x, y);
      if (map.has(k)) return map.get(k);
      const id = verts.length;
      verts.push({ hx: x, hy: y, x, y, z: 0, sx: x, sy: y, s: 1 });
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
    cx = W * 0.5; cy = H * 0.5;
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    buildGrid();
  }

  function updateVerts() {
    scrollEnergy *= 0.93;
    if (scrollEnergy < 0.02) scrollEnergy = 0;

    const flowAmp = FLOW + scrollEnergy * 0.9;
    const ease = 0.16;
    const zEase = 0.14;

    for (const v of verts) {
      // flowing XY field
      let fx = Math.cos(v.hx * 0.011 + t * 0.017 - scrollPhase * 0.5) * flowAmp;
      let fy = Math.sin(v.hy * 0.010 + t * 0.021 + scrollPhase * 0.7) * flowAmp;
      // idle depth undulation
      let tz = Math.sin(v.hx * 0.008 + v.hy * 0.006 + t * 0.02) * 7;

      // scroll depth-shockwave (travels vertically, lifts in Z too)
      if (scrollEnergy > 0.05) {
        const band = Math.sin(v.hy * 0.022 - scrollPhase * 1.4);
        fy += band * scrollEnergy * 1.0;
        tz += band * scrollEnergy * 1.6;
      }

      // cursor magnetism (XY) + 3D bulge (Z) + swirl
      if (mouse.active) {
        const dx = mouse.x - v.hx, dy = mouse.y - v.hy;
        const d2 = dx * dx + dy * dy;
        if (d2 < REACH2) {
          const d = Math.sqrt(d2) || 1;
          const f = 1 - d / REACH;
          const ff = f * f;
          const pull = PULL * ff;
          fx += (dx / d) * pull;
          fy += (dy / d) * pull;
          fx += (-dy / d) * pull * 0.42 * swirlDir;
          fy += (dx / d) * pull * 0.42 * swirlDir;
          // smooth dome (cosine) lifts the region toward the viewer
          tz += BULGE * (0.5 - 0.5 * Math.cos(f * Math.PI));
        }
      }

      v.x += (v.hx + fx - v.x) * ease;
      v.y += (v.hy + fy - v.y) * ease;
      v.z += (tz - v.z) * zEase;
    }
  }

  function project() {
    for (const v of verts) {
      const zc = Math.min(v.z, FOV * 0.82);           // clamp so denom stays positive
      const s = FOV / (FOV - zc);                      // >1 when toward viewer
      v.s = s;
      v.sx = cx + (v.x - cx) * s;
      v.sy = cy + (v.y - cy) * s;
    }
  }

  function frame() {
    t += 1;
    updateVerts();
    project();
    ctx.clearRect(0, 0, W, H);

    const breathe = 0.5 + 0.5 * Math.sin(t * 0.012);
    const energyGlow = Math.min(scrollEnergy * 0.02, 0.3);
    const baseAlpha = 0.09 + breathe * 0.05 + energyGlow;

    for (const [ia, ib] of edges) {
      const a = verts[ia], b = verts[ib];
      // depth cue: closer (bigger s) → brighter, thicker, more violet
      const depth = Math.max(0, ((a.s + b.s) * 0.5 - 1));   // 0 at rest plane
      const dk = Math.min(depth * 1.5, 1);
      let alpha = baseAlpha + dk * 0.5;
      let col = [
        Math.round(BASE[0] + (HOT[0] - BASE[0]) * dk),
        Math.round(BASE[1] + (HOT[1] - BASE[1]) * dk),
        Math.round(BASE[2] + (HOT[2] - BASE[2]) * dk),
      ];
      if (mouse.active) {
        const mx = (a.sx + b.sx) * 0.5, my = (a.sy + b.sy) * 0.5;
        const dx = mouse.x - mx, dy = mouse.y - my;
        const d2 = dx * dx + dy * dy;
        if (d2 < REACH2) {
          const g = 1 - Math.sqrt(d2) / REACH;
          alpha = Math.min(alpha + g * 0.5, 0.98);
        }
      }
      ctx.lineWidth = 0.9 + dk * 1.4;
      ctx.strokeStyle = `rgba(${col[0]},${col[1]},${col[2]},${alpha})`;
      ctx.beginPath();
      ctx.moveTo(a.sx, a.sy);
      ctx.lineTo(b.sx, b.sy);
      ctx.stroke();
    }

    // sparks: nodes that have risen toward the camera
    ctx.shadowColor = `rgb(${HOT[0]},${HOT[1]},${HOT[2]})`;
    ctx.fillStyle = `rgb(${HOT[0]},${HOT[1]},${HOT[2]})`;
    for (const v of verts) {
      const depth = v.s - 1;
      if (depth <= 0.04) continue;
      const dk = Math.min(depth * 1.4, 1);
      ctx.globalAlpha = dk * 0.9;
      ctx.shadowBlur = 10;
      ctx.beginPath();
      ctx.arc(v.sx, v.sy, 1.3 + dk * 2.6, 0, Math.PI * 2);
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
    scrollEnergy = Math.min(scrollEnergy + Math.abs(delta) * 0.06, 28);
    swirlDir = delta >= 0 ? 1 : -1;
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
  if (reduce) { updateVerts(); project(); frame(); if (raf) cancelAnimationFrame(raf); raf = null; }
  else raf = requestAnimationFrame(frame);
})();
