/* ═══════════════════════════════════════════════════════════════════════
   INVIQ — Interactive Honeycomb (v2, reactive)
   A hexagonal mesh (colmeia) that:
     • undulates continuously with a flowing multi-wave field
     • is magnetically pulled + swirled toward the cursor
     • ripples with a traveling shockwave when the page is scrolled
   Lines glow (blue→violet) and thicken with energy; nodes spark near the
   pointer. Self-contained canvas 2D; respects prefers-reduced-motion and
   pauses when the tab is hidden.

   Usage: <canvas id="hive-canvas"></canvas> + <script src="/static/js/hive.js"></script>
   Optional data-attributes:
     data-size="44"    hex radius in px (bigger = larger cells)
     data-pull="30"    max vertex displacement toward cursor
     data-reach="185"  cursor influence radius in px
     data-flow="3"     idle wave amplitude in px (bigger = livelier)
═══════════════════════════════════════════════════════════════════════ */
(function () {
  const canvas = document.getElementById('hive-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const R      = parseFloat(canvas.dataset.size  || '44');
  const PULL   = parseFloat(canvas.dataset.pull  || '32');
  const REACH  = parseFloat(canvas.dataset.reach || '190');
  const FLOW   = parseFloat(canvas.dataset.flow  || '3.2');   // idle wave amplitude

  // line colors (navy-friendly): base cool blue, near-cursor violet
  const BASE = [96, 140, 230];
  const HOT  = [150, 110, 255];

  let W = 0, H = 0, DPR = 1, raf = null, t = 0;
  let verts = [];   // { hx, hy, x, y }
  let edges = [];   // [i, j]
  const mouse = { x: -9999, y: -9999, active: false };
  const REACH2 = REACH * REACH;

  // scroll-driven state
  let scrollPhase = 0;     // accumulated scroll → drives traveling wave
  let scrollEnergy = 0;    // decays each frame; amplifies the ripple
  let swirlDir = 1;

  function buildGrid() {
    verts = []; edges = [];
    const map = new Map();
    const key = (x, y) => Math.round(x) + ',' + Math.round(y);
    function vid(x, y) {
      const k = key(x, y);
      if (map.has(k)) return map.get(k);
      const id = verts.length;
      verts.push({ hx: x, hy: y, x, y });
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
        const cx = c * w + (r & 1 ? w / 2 : 0);
        const cy = r * vspace;
        const ids = [];
        for (let k = 0; k < 6; k++) {
          ids.push(vid(cx + R * Math.cos(angs[k]), cy + R * Math.sin(angs[k])));
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
    // decay scroll shock; keep the traveling phase slowly easing back
    scrollEnergy *= 0.93;
    if (scrollEnergy < 0.02) scrollEnergy = 0;

    const flowAmp = FLOW + scrollEnergy * 0.9;
    const ease = 0.18;

    for (const v of verts) {
      // continuous flowing field — two crossing waves keep the comb alive
      let fx = Math.cos(v.hx * 0.011 + t * 0.017 - scrollPhase * 0.5) * flowAmp;
      let fy = Math.sin(v.hy * 0.010 + t * 0.021 + scrollPhase * 0.7) * flowAmp;

      // scroll shockwave: a horizontal band that travels vertically
      if (scrollEnergy > 0.05) {
        const band = Math.sin(v.hy * 0.022 - scrollPhase * 1.4);
        fy += band * scrollEnergy * 1.15;
        fx += Math.cos(v.hy * 0.018 - scrollPhase * 1.4) * scrollEnergy * 0.5;
      }

      // cursor magnetism + swirl
      if (mouse.active) {
        const dx = mouse.x - v.hx, dy = mouse.y - v.hy;
        const d2 = dx * dx + dy * dy;
        if (d2 < REACH2) {
          const d = Math.sqrt(d2) || 1;
          const f = (1 - d / REACH);
          const pull = PULL * f * f;
          fx += (dx / d) * pull;
          fy += (dy / d) * pull;
          // perpendicular swirl for a living, vortex-like drag
          fx += (-dy / d) * pull * 0.45 * swirlDir;
          fy += (dx / d) * pull * 0.45 * swirlDir;
        }
      }

      v.x += (v.hx + fx - v.x) * ease;
      v.y += (v.hy + fy - v.y) * ease;
    }
  }

  function frame() {
    t += 1;
    updateVerts();
    ctx.clearRect(0, 0, W, H);

    const breathe = 0.5 + 0.5 * Math.sin(t * 0.012);
    const energyGlow = Math.min(scrollEnergy * 0.02, 0.35);
    const baseAlpha = 0.10 + breathe * 0.05 + energyGlow;
    ctx.lineWidth = 1 + Math.min(scrollEnergy * 0.03, 0.8);

    for (const [ia, ib] of edges) {
      const a = verts[ia], b = verts[ib];
      let alpha = baseAlpha, col = BASE;
      if (mouse.active) {
        const mx = (a.x + b.x) * 0.5, my = (a.y + b.y) * 0.5;
        const dx = mouse.x - mx, dy = mouse.y - my;
        const d2 = dx * dx + dy * dy;
        if (d2 < REACH2) {
          const g = 1 - Math.sqrt(d2) / REACH;
          alpha = Math.min(alpha + g * 0.6, 0.95);
          col = [
            Math.round(BASE[0] + (HOT[0] - BASE[0]) * g),
            Math.round(BASE[1] + (HOT[1] - BASE[1]) * g),
            Math.round(BASE[2] + (HOT[2] - BASE[2]) * g),
          ];
        }
      }
      ctx.strokeStyle = `rgba(${col[0]},${col[1]},${col[2]},${alpha})`;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }

    // sparks near the cursor
    if (mouse.active) {
      ctx.shadowColor = `rgb(${HOT[0]},${HOT[1]},${HOT[2]})`;
      ctx.fillStyle = `rgb(${HOT[0]},${HOT[1]},${HOT[2]})`;
      for (const v of verts) {
        const dx = mouse.x - v.x, dy = mouse.y - v.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < REACH2) {
          const g = 1 - Math.sqrt(d2) / REACH;
          ctx.globalAlpha = g * 0.9;
          ctx.shadowBlur = 8;
          ctx.beginPath();
          ctx.arc(v.x, v.y, 1.4 + g * 1.9, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      ctx.shadowBlur = 0;
      ctx.globalAlpha = 1;
    }

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

  // scroll energy — works for wheel, trackpad, touch, and inner scroll containers
  let lastTouchY = null;
  function addScroll(delta) {
    scrollPhase += delta * 0.006;
    scrollEnergy = Math.min(scrollEnergy + Math.abs(delta) * 0.06, 26);
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
  if (reduce) { updateVerts(); frame(); if (raf) cancelAnimationFrame(raf); raf = null; }
  else raf = requestAnimationFrame(frame);
})();
