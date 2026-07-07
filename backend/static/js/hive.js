/* ═══════════════════════════════════════════════════════════════════════
   INVIQ — Interactive Honeycomb
   A hexagonal mesh (colmeia) whose vertices are magnetically pulled toward
   the cursor, warping the comb as the mouse moves. Lines glow near the
   pointer. Self-contained canvas 2D; respects prefers-reduced-motion and
   pauses when the tab is hidden.

   Usage: <canvas id="hive-canvas"></canvas> + <script src="/static/js/hive.js"></script>
   Optional data-attributes:
     data-size="42"    hex radius in px (bigger = larger cells)
     data-pull="30"    max vertex displacement toward cursor
     data-reach="180"  cursor influence radius in px
═══════════════════════════════════════════════════════════════════════ */
(function () {
  const canvas = document.getElementById('hive-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const R      = parseFloat(canvas.dataset.size  || '44');   // hex radius (center→vertex)
  const PULL   = parseFloat(canvas.dataset.pull  || '30');   // max attraction (px)
  const REACH  = parseFloat(canvas.dataset.reach || '185');  // cursor influence radius

  // line colors (navy-friendly): base cool blue, near-cursor violet
  const BASE = [96, 140, 230];
  const HOT  = [150, 110, 255];

  let W = 0, H = 0, DPR = 1, raf = null, t = 0;
  let verts = [];   // { hx, hy, x, y }
  let edges = [];   // [i, j]
  const mouse = { x: -9999, y: -9999, active: false };
  const REACH2 = REACH * REACH;

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
    // pointy-top hexagons: a vertex points straight up
    const angs = [];
    for (let k = 0; k < 6; k++) angs.push((Math.PI / 180) * (60 * k - 90));
    const w = Math.sqrt(3) * R;   // horizontal center spacing
    const vspace = 1.5 * R;       // vertical center spacing
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
    const ease = 0.16;
    for (const v of verts) {
      let tx = v.hx, ty = v.hy;
      if (mouse.active) {
        const dx = mouse.x - v.hx, dy = mouse.y - v.hy;
        const d2 = dx * dx + dy * dy;
        if (d2 < REACH2) {
          const d = Math.sqrt(d2) || 1;
          const f = (1 - d / REACH);          // 0..1, strongest near cursor
          const pull = PULL * f * f;           // ease-in falloff
          tx = v.hx + (dx / d) * pull;
          ty = v.hy + (dy / d) * pull;
        }
      }
      v.x += (tx - v.x) * ease;
      v.y += (ty - v.y) * ease;
    }
  }

  function frame() {
    t += 1;
    updateVerts();
    ctx.clearRect(0, 0, W, H);

    // gentle breathing so idle comb still feels alive
    const breathe = 0.5 + 0.5 * Math.sin(t * 0.012);
    const baseAlpha = 0.10 + breathe * 0.05;

    ctx.lineWidth = 1;
    for (const [ia, ib] of edges) {
      const a = verts[ia], b = verts[ib];
      let alpha = baseAlpha, col = BASE;
      if (mouse.active) {
        const mx = (a.x + b.x) * 0.5, my = (a.y + b.y) * 0.5;
        const dx = mouse.x - mx, dy = mouse.y - my;
        const d2 = dx * dx + dy * dy;
        if (d2 < REACH2) {
          const g = 1 - Math.sqrt(d2) / REACH;
          alpha = baseAlpha + g * 0.55;
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

    // glowing nodes near the cursor
    if (mouse.active) {
      for (const v of verts) {
        const dx = mouse.x - v.x, dy = mouse.y - v.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < REACH2) {
          const g = 1 - Math.sqrt(d2) / REACH;
          ctx.globalAlpha = g * 0.9;
          ctx.fillStyle = `rgb(${HOT[0]},${HOT[1]},${HOT[2]})`;
          ctx.shadowColor = `rgb(${HOT[0]},${HOT[1]},${HOT[2]})`;
          ctx.shadowBlur = 8;
          ctx.beginPath();
          ctx.arc(v.x, v.y, 1.4 + g * 1.8, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      ctx.shadowBlur = 0;
      ctx.globalAlpha = 1;
    }

    raf = requestAnimationFrame(frame);
  }

  function pointer(e) {
    const rect = canvas.getBoundingClientRect();
    const src = e.touches ? e.touches[0] : e;
    mouse.x = src.clientX - rect.left;
    mouse.y = src.clientY - rect.top;
    mouse.active = true;
  }
  function clearPointer() { mouse.active = false; mouse.x = mouse.y = -9999; }

  window.addEventListener('mousemove', pointer, { passive: true });
  window.addEventListener('touchmove', pointer, { passive: true });
  window.addEventListener('mouseleave', clearPointer);
  window.addEventListener('touchend', clearPointer);

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
  if (reduce) { frame(); if (raf) cancelAnimationFrame(raf); raf = null; }  // draw one static comb
  else raf = requestAnimationFrame(frame);
})();
