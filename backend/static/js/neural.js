/* ═══════════════════════════════════════════════════════════════════════
   INVIQ — Neural Constellation
   Animated particle brain: colored nodes forming a brain silhouette,
   linked by faint edges, with synaptic pulses traveling between them.
   Self-contained, canvas 2D, respects prefers-reduced-motion.

   Usage: <canvas id="neural-canvas"></canvas>  +  <script src="/static/js/neural.js"></script>
   Optional data-attributes on the canvas:
     data-count="180"   number of brain nodes
     data-ambient="40"  scattered background particles
     data-link="0.85"   connection reach multiplier
═══════════════════════════════════════════════════════════════════════ */
(function () {
  const canvas = document.getElementById('neural-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const PALETTE = ['#8052ff', '#a68aff', '#ffb829', '#5fc9b4', '#4a7bff', '#c96bff'];
  const NODE_COUNT    = parseInt(canvas.dataset.count   || '170', 10);
  const AMBIENT_COUNT = parseInt(canvas.dataset.ambient || '46', 10);
  const LINK_MULT     = parseFloat(canvas.dataset.link  || '1');

  let W = 0, H = 0, DPR = 1;
  let nodes = [];
  let ambient = [];
  let pulses = [];
  let linkDist = 0;
  let raf = null;
  let t = 0;

  /* Brain silhouette: a lumpy polar boundary (the gyri) over an ellipse
     wider than tall, with a central longitudinal fissure carving the two
     hemispheres apart in the upper region. Coordinates are normalized to a
     unit box centered at (0,0), roughly [-1,1] on each axis. */
  function inBrain(nx, ny) {
    const ex = nx / 1.0, ey = ny / 0.82;
    const r = Math.hypot(ex, ey);
    const th = Math.atan2(ey, ex);
    const rb = 0.86
      + 0.06 * Math.sin(7 * th + 0.6)
      + 0.05 * Math.sin(11 * th + 2.1)
      + 0.03 * Math.sin(5 * th);
    if (r > rb) return false;
    // central fissure between hemispheres (upper half only)
    if (Math.abs(nx) < 0.05 && ny < 0.30) return false;
    return true;
  }

  function pick(arr) { return arr[(Math.random() * arr.length) | 0]; }

  function computeGeometry() {
    // brain occupies a centered box scaled to the smaller canvas dimension
    const scale = Math.min(W, H) * (W < 640 ? 0.46 : 0.40);
    const cx = W * 0.5, cy = H * 0.48;
    return { scale, cx, cy };
  }

  function buildNodes() {
    nodes = [];
    const { scale, cx, cy } = computeGeometry();
    let attempts = 0;
    while (nodes.length < NODE_COUNT && attempts < NODE_COUNT * 60) {
      attempts++;
      const nx = (Math.random() * 2 - 1) * 1.05;
      const ny = (Math.random() * 2 - 1) * 1.05;
      if (!inBrain(nx, ny)) continue;
      const px = cx + nx * scale;
      const py = cy + ny * scale;
      nodes.push({
        hx: px, hy: py,                       // home position
        x: px, y: py,
        nx, ny,
        phase: Math.random() * Math.PI * 2,
        amp: 1.2 + Math.random() * 2.6,       // drift amplitude (px)
        speed: 0.4 + Math.random() * 0.8,
        size: 1.0 + Math.random() * 1.8,
        color: pick(PALETTE),
        tri: Math.random() > 0.45,            // some are triangles, some dots
        rot: Math.random() * Math.PI,
        twinkle: Math.random() * Math.PI * 2,
      });
    }
    linkDist = Math.min(W, H) * 0.085 * LINK_MULT;
  }

  function buildAmbient() {
    ambient = [];
    for (let i = 0; i < AMBIENT_COUNT; i++) {
      ambient.push({
        x: Math.random() * W,
        y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.12,
        vy: (Math.random() - 0.5) * 0.12,
        size: 0.8 + Math.random() * 1.6,
        color: pick(PALETTE),
        alpha: 0.12 + Math.random() * 0.28,
        tri: Math.random() > 0.4,
        rot: Math.random() * Math.PI,
      });
    }
  }

  function resize() {
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    W = rect.width; H = rect.height;
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    buildNodes();
    buildAmbient();
  }

  function drawTriangle(x, y, s, rot) {
    ctx.beginPath();
    for (let i = 0; i < 3; i++) {
      const a = rot + (i * 2 * Math.PI) / 3 - Math.PI / 2;
      const vx = x + Math.cos(a) * s, vy = y + Math.sin(a) * s;
      i === 0 ? ctx.moveTo(vx, vy) : ctx.lineTo(vx, vy);
    }
    ctx.closePath();
  }

  function spawnPulse() {
    if (nodes.length < 2) return;
    const a = nodes[(Math.random() * nodes.length) | 0];
    // find a nearby node to travel to
    let best = null, bestD = Infinity;
    for (let k = 0; k < 12; k++) {
      const b = nodes[(Math.random() * nodes.length) | 0];
      if (b === a) continue;
      const d = (b.hx - a.hx) ** 2 + (b.hy - a.hy) ** 2;
      if (d < bestD && d > 100) { bestD = d; best = b; }
    }
    if (!best) return;
    pulses.push({ a, b: best, p: 0, speed: 0.012 + Math.random() * 0.02, color: Math.random() > 0.5 ? '#ffb829' : '#a68aff' });
  }

  function frame() {
    t += 1;
    ctx.clearRect(0, 0, W, H);

    // update node positions (gentle organic drift around home)
    for (const n of nodes) {
      n.x = n.hx + Math.cos(t * 0.008 * n.speed + n.phase) * n.amp;
      n.y = n.hy + Math.sin(t * 0.008 * n.speed + n.phase * 1.3) * n.amp;
    }

    // draw connections (only near pairs) — faint violet-white webbing
    ctx.lineWidth = 1;
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < linkDist) {
          const alpha = (1 - d / linkDist) * 0.22;
          ctx.strokeStyle = `rgba(130, 120, 220, ${alpha})`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    // synaptic pulses traveling along edges
    for (let i = pulses.length - 1; i >= 0; i--) {
      const pu = pulses[i];
      pu.p += pu.speed;
      if (pu.p >= 1) { pulses.splice(i, 1); continue; }
      const x = pu.a.x + (pu.b.x - pu.a.x) * pu.p;
      const y = pu.a.y + (pu.b.y - pu.a.y) * pu.p;
      const g = ctx.createRadialGradient(x, y, 0, x, y, 6);
      g.addColorStop(0, pu.color);
      g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(x, y, 6, 0, Math.PI * 2);
      ctx.fill();
    }

    // draw brain nodes (twinkling triangles + dots with glow)
    for (const n of nodes) {
      const tw = 0.55 + Math.sin(t * 0.03 + n.twinkle) * 0.45;
      ctx.globalAlpha = 0.35 + tw * 0.55;
      ctx.fillStyle = n.color;
      ctx.shadowColor = n.color;
      ctx.shadowBlur = 6;
      if (n.tri) {
        drawTriangle(n.x, n.y, n.size + 1.1, n.rot + t * 0.002);
        ctx.fill();
      } else {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.size, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;

    // ambient drifting particles (outside the brain)
    for (const p of ambient) {
      p.x += p.vx; p.y += p.vy;
      if (p.x < -10) p.x = W + 10; if (p.x > W + 10) p.x = -10;
      if (p.y < -10) p.y = H + 10; if (p.y > H + 10) p.y = -10;
      ctx.globalAlpha = p.alpha;
      ctx.fillStyle = p.color;
      if (p.tri) { drawTriangle(p.x, p.y, p.size + 0.6, p.rot); ctx.fill(); }
      else { ctx.beginPath(); ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2); ctx.fill(); }
    }
    ctx.globalAlpha = 1;

    if (t % 26 === 0) spawnPulse();
    raf = requestAnimationFrame(frame);
  }

  function renderStatic() {
    // reduced-motion: draw one frame, no animation
    for (const n of nodes) { n.x = n.hx; n.y = n.hy; }
    frameOnce();
  }
  function frameOnce() {
    ctx.clearRect(0, 0, W, H);
    ctx.lineWidth = 1;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < linkDist) {
          ctx.strokeStyle = `rgba(130,120,220,${(1 - d / linkDist) * 0.2})`;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
    }
    for (const n of nodes) {
      ctx.fillStyle = n.color; ctx.globalAlpha = 0.8;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.size, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { resize(); if (reduce) renderStatic(); }, 180);
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { if (raf) cancelAnimationFrame(raf); raf = null; }
    else if (!reduce && !raf) { raf = requestAnimationFrame(frame); }
  });

  resize();
  if (reduce) renderStatic();
  else raf = requestAnimationFrame(frame);
})();
