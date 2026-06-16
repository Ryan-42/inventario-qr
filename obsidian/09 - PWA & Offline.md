---
tags: [pwa]
aliases: [Service Worker, Offline, PWA, Cache, Background Sync]
---

# PWA & Offline — INVIQ

> [!info] Progressive Web App
> **Service Worker:** `backend/static/sw.js` — 4 estratégias de cache
> **Manifest:** `GET /manifest.json` — servido pelo FastAPI
> **Ícones:** `icon-192.png` + `icon-512.png` — gerados em Python puro
> **Escopo:** `/` — controla todas as páginas

---

## Estratégias de Cache

```mermaid
flowchart TD
    FETCH["Request do Browser"] --> CHK{{"Tipo de recurso?"}}

    CHK -->|"/api/* ou WS"| NET["Network Only\n(dados sempre frescos)"]
    CHK -->|"/static/css,js"| CF["Cache First\n→ instantâneo\n→ atualiza em background"]
    CHK -->|"CDN externo\n(jsQR, Tailwind, Fonts)"| SWR["Stale-While-Revalidate\n→ cache imediato\n→ rede em paralelo"]
    CHK -->|"Navegação HTML\n(/mobile/{id})"| NF["Network First\n→ se offline: cache\n→ se sem cache: fallback"]

    NF -->|"offline sem cache"| FB["Página Offline\ncom botão Tentar novamente"]

    classDef net fill:#E74C3C,stroke:#B71C1C,color:#fff
    classDef cache fill:#2ECC71,stroke:#1B5E20,color:#fff
    classDef swr fill:#4B9FFF,stroke:#1565C0,color:#fff
    classDef nf fill:#E67E22,stroke:#BF360C,color:#fff
    classDef fb fill:#78909C,stroke:#263238,color:#fff
    class NET net
    class CF cache
    class SWR swr
    class NF nf
    class FB fb
```

---

## Ciclo de Vida do Service Worker

```mermaid
stateDiagram-v2
    [*] --> Installing : navigator.serviceWorker.register()
    Installing --> Installed : pre-cache /static/css,js ok
    Installed --> Activating : skipWaiting() chamado
    Activating --> Active : caches antigos removidos\nclients.claim()
    Active --> Redundant : nova versão instalada

    Active --> Fetch : request interceptado
    Fetch --> Active : resposta servida

    note right of Active : controla /\natende todos os requests
```

---

## Pré-Cache na Instalação

```javascript
const PRE_CACHE = [
  '/static/css/app.css',
  '/static/js/ws.js',
  '/static/js/api.js',
]
// CDN (jsQR, Tailwind, Fonts) são cacheados ao primeiro uso
// HTML é cacheado ao primeira navegação (network-first)
```

---

## Offline Queue + Background Sync

```mermaid
sequenceDiagram
    participant OP as Operador
    participant LS as localStorage
    participant SW as Service Worker
    participant API as /api/contagens

    OP->>OP: escaneia item sem rede
    OP->>LS: salvarOffline({sessaoId, payload, ts})
    OP->>SW: sync.register('inviq-offline-queue')

    Note over SW: Conexão retorna
    SW-->>OP: postMessage({type:'FLUSH_QUEUE'})
    OP->>OP: flushOfflineQueue()
    OP->>API: POST contagens (reenvio)
    API-->>OP: 201 Created
    OP->>LS: remove item da fila
```

---

## Instalação como App

| Plataforma | Como instalar | Requisito |
|------------|--------------|-----------|
| Android Chrome | Banner "Adicionar à tela inicial" | HTTPS + manifest + SW |
| iOS Safari | Menu → "Adicionar à tela de início" | `apple-mobile-web-app-capable` + ícone |
| Desktop Chrome | Ícone de instalação na barra | Mesmo que Android |

---

## Notificação de Atualização

```javascript
// Quando nova versão do SW está pronta
reg.addEventListener('updatefound', () => {
  sw.addEventListener('statechange', () => {
    if (sw.state === 'installed' && navigator.serviceWorker.controller) {
      showHintNotif('Nova versão disponível — recarregue para atualizar', 6000)
    }
  })
})
```

---

## Manifest.json

```json
{
  "name": "INVIQ — Inventário QR",
  "short_name": "INVIQ",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#071325",
  "theme_color": "#8fd6ff",
  "orientation": "portrait",
  "icons": [
    {"src": "/static/icon-192.png", "sizes": "192x192", "purpose": "any maskable"},
    {"src": "/static/icon-512.png", "sizes": "512x512", "purpose": "any maskable"}
  ]
}
```

---

## Conexões

- [[04 - Frontend Mobile]] — SW registrado em mobile.html; `salvarOffline()`, `flushOfflineQueue()`
- [[06 - Tempo Real]] — evento `_connected` dispara `flushOfflineQueue()`
- [[10 - Deploy & Infra]] — SW servido com header `Service-Worker-Allowed: /`
- [[00 - INVIQ]] — visão geral
