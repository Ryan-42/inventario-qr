/**
 * INVIQ Service Worker
 * Estratégias de cache:
 *   - /static/*          → cache-first  (assets locais, versionados pelo nome)
 *   - CDN externo        → stale-while-revalidate  (jsQR, Tailwind, Fonts)
 *   - /mobile/* + HTML   → network-first, fallback ao cache  (shell do app)
 *   - /api/* e WebSocket → sem interceptação  (dados sempre frescos)
 */

// v4: api.js mudou (401 em página de operador não redireciona mais p/ /login) —
// bump força os clientes a descartarem o cache antigo (cache-first em /static/*)
const CACHE_NAME = 'inviq-v4'

const PRE_CACHE = [
  '/static/css/app.css',
  '/static/js/ws.js',
  '/static/js/api.js',
]

const CDN_HOSTS = [
  'cdn.jsdelivr.net',
  'cdn.tailwindcss.com',
  'fonts.googleapis.com',
  'fonts.gstatic.com',
]

// ── Instalação: pré-cacheia assets locais ─────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRE_CACHE))
      .then(() => self.skipWaiting())
  )
})

// ── Ativação: limpa caches de versões antigas ─────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys =>
        Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  )
})

// ── Interceptação de fetch ────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const req = event.request
  const url = new URL(req.url)

  // WebSocket: nunca intercepta
  if (url.protocol === 'ws:' || url.protocol === 'wss:') return

  // API: sempre vai para a rede (dados em tempo real)
  if (url.pathname.startsWith('/api/')) return

  // CDN externo: stale-while-revalidate (carrega do cache; atualiza em background)
  if (CDN_HOSTS.includes(url.hostname)) {
    event.respondWith(staleWhileRevalidate(req))
    return
  }

  // Assets locais (/static/*): cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(req))
    return
  }

  // Navegação (HTML pages): network-first, fallback ao shell cacheado
  if (req.mode === 'navigate') {
    event.respondWith(networkFirstNav(req))
    return
  }
})

// ── Estratégias ───────────────────────────────────────────────────────────────

async function cacheFirst(req) {
  const cached = await caches.match(req)
  if (cached) return cached
  try {
    const response = await fetch(req)
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME)
      cache.put(req, response.clone())
    }
    return response
  } catch {
    return new Response('', { status: 503 })
  }
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(CACHE_NAME)
  const cached = await cache.match(req)

  const networkPromise = fetch(req)
    .then(res => {
      if (res.ok) cache.put(req, res.clone())
      return res
    })
    .catch(() => null)

  return cached || await networkPromise || new Response('', { status: 503 })
}

async function networkFirstNav(req) {
  try {
    const response = await fetch(req)
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME)
      cache.put(req, response.clone())
    }
    return response
  } catch {
    // Offline: tenta servir do cache (qualquer rota /mobile/* serve o mesmo HTML)
    const cached = await caches.match(req)
    if (cached) return cached

    // Fallback genérico: tenta o shell principal
    const shell = await caches.match('/mobile/__shell__')
    if (shell) return shell

    return new Response(
      `<!DOCTYPE html><html lang="pt-BR"><head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width,initial-scale=1"/>
        <title>INVIQ — Offline</title>
        <style>
          body{font-family:sans-serif;background:#071325;color:#e2eaf2;display:flex;
               align-items:center;justify-content:center;min-height:100vh;margin:0}
          .box{text-align:center;padding:2rem}
          h1{font-size:1.5rem;margin-bottom:.75rem}
          p{opacity:.7;font-size:.9rem}
          button{margin-top:1.5rem;padding:.6rem 1.4rem;background:#1a4a7a;color:#fff;
                 border:none;border-radius:.5rem;font-size:1rem;cursor:pointer}
        </style>
      </head><body>
        <div class="box">
          <h1>📴 Sem conexão</h1>
          <p>Conecte-se à internet para abrir o INVIQ.</p>
          <button onclick="location.reload()">Tentar novamente</button>
        </div>
      </body></html>`,
      { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
    )
  }
}

// ── Background Sync (quando disponível) ──────────────────────────────────────
self.addEventListener('sync', event => {
  if (event.tag === 'inviq-offline-queue') {
    event.waitUntil(
      self.clients.matchAll().then(clients => {
        clients.forEach(client => client.postMessage({ type: 'FLUSH_QUEUE' }))
      })
    )
  }
})
