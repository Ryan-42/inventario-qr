# Tech Stack Completo — Inventário QR

> Versão: 1.0 | Data: 2026-05-24  
> Stack atual + todas as tecnologias recomendadas por fase

---

## Stack Atual (MVP)

```
Frontend:   React 18 + Vite + TailwindCSS + React Router + Axios
Backend:    FastAPI + SQLAlchemy + PostgreSQL + Alembic + Uvicorn
Infra:      Docker Compose
Scanner:    html5-qrcode
```

---

## Stack Alvo (Fase 1 — Fundação)

### Frontend

| Lib | Versão | Por quê |
|-----|--------|---------|
| **Next.js** | 15.x | SSR, App Router, deploy Vercel trivial |
| **TypeScript** | 5.x | Type safety, refactor seguro, DX superior |
| **shadcn/ui** | latest | Design system pronto, acessível, customizável |
| **Radix UI** | latest | Primitivos acessíveis (base do shadcn) |
| **Tailwind CSS** | 4.x | Styling rápido, consistente com atual |
| **Framer Motion** | 11.x | Animações 150-300ms (WCAG AA) |
| **Zustand** | 5.x | Estado global simples sem boilerplate |
| **TanStack Query** | 5.x | Cache/sync de server state, retry, stale |
| **TanStack Virtual** | 3.x | Virtualização listas 10k+ itens |
| **Recharts** | 2.x | Gráficos React, leve, responsivo |
| **@zxing/browser** | latest | Scanner QR + barcode 1D (EAN, Code128) |
| **NextAuth.js** | 5.x | Auth com JWT, sessions, múltiplos providers |
| **React Hook Form** | 7.x | Forms performáticos sem re-renders |
| **Zod** | 3.x | Validação de schema, integra com RHF |
| **Workbox** | 7.x | Service Worker / PWA / offline sync |
| **Lucide React** | latest | Ícones (já em uso, manter) |
| **date-fns** | 3.x | Manipulação de datas leve |
| **sonner** | latest | Toast notifications elegantes |

### Backend

| Lib | Versão | Por quê |
|-----|--------|---------|
| **FastAPI** | 0.115.x | Manter, adicionar WebSocket support |
| **SQLAlchemy** | 2.x | Manter, adicionar async support |
| **PostgreSQL** | 16 | Manter, adicionar pgvector extension |
| **pgvector** | 0.7.x | Embeddings para SearchAgent (RAG) |
| **Alembic** | 1.13.x | Manter, criar migrations para novos schemas |
| **Redis** | 7.x | Cache + pub/sub + filas Celery |
| **Celery** | 5.4.x | Tarefas background (export PDF, analytics) |
| **python-jose** | 3.x | JWT encoding/decoding |
| **passlib[bcrypt]** | 1.7.x | Hash seguro de senhas |
| **anthropic** | 0.34.x | SDK Claude AI para todos os agentes |
| **websockets** | 12.x | WebSocket nativo FastAPI |
| **reportlab** | 4.x | Geração de PDF profissional |
| **pandas** | 2.x | Manter, adicionar mais formatos |
| **openpyxl** | 3.x | Manter |
| **python-magic** | 0.4.x | Detecção de tipo de arquivo no ImportAgent |
| **Pydantic** | 2.x | Manter, validação de schemas |
| **httpx** | 0.27.x | HTTP async para chamadas internas |
| **pytest** | 8.x | Testes unitários e integração |
| **pytest-asyncio** | latest | Testes de código async |
| **Sentry SDK** | latest | Error tracking + performance |
| **prometheus-client** | latest | Métricas dos agentes |
| **structlog** | latest | Logging estruturado (JSON) |

### Infra Local

| Tecnologia | Uso |
|-----------|-----|
| **Docker Compose** | Manter, adicionar Redis e Celery services |
| **Nginx** | Reverse proxy local + SSL (mkcert) |
| **pgAdmin** | UI para PostgreSQL em dev |
| **RedisInsight** | UI para Redis em dev |

---

## Stack Alvo (Fase 2 — Agentes IA)

| Tecnologia | Uso |
|-----------|-----|
| **anthropic SDK** | Claude Sonnet 4.6 + Haiku 4.5 para agentes |
| **MCP (Model Context Protocol)** | Orquestração de ferramentas dos agentes |
| **Celery Beat** | Agendamento de tarefas recorrentes (PredictionAgent) |
| **Redis Streams** | Fila de eventos para comunicação entre agentes |
| **sentence-transformers** | Embeddings locais para pgvector (custo zero) |
| **Flower** | Monitoramento de workers Celery |

### Configuração Docker Compose expandida

```yaml
services:
  postgres:     # existente + pgvector extension
  backend:      # existente
  redis:        # NOVO — cache + pub/sub
  celery:       # NOVO — worker de tarefas background
  celery-beat:  # NOVO — scheduler
  flower:       # NOVO — monitoramento Celery
  nginx:        # NOVO — reverse proxy
```

---

## Stack Alvo (Fase 3 — PWA + Analytics)

| Tecnologia | Uso |
|-----------|-----|
| **Workbox** | Service Worker strategies (cache-first, bg-sync) |
| **idb** | IndexedDB wrapper para armazenamento offline |
| **web-push** | Push notifications servidor → browser |
| **@tanstack/react-charts** | Gráficos avançados para analytics |
| **react-map-gl** | Mapa de setores (se geolocalização) |
| **jsPDF** | Export PDF client-side como fallback |

---

## Stack Alvo (Fase 4 — Enterprise)

| Tecnologia | Uso |
|-----------|-----|
| **React Native + Expo** | App mobile nativo |
| **Expo Camera** | Scanner nativo (2x mais rápido) |
| **Expo Notifications** | Push nativas iOS/Android |
| **Stripe** | Billing multi-tenant |
| **PostHog** | Analytics de produto (self-hosted) |
| **OpenTelemetry** | Observabilidade distribuída |
| **Grafana** | Dashboard de métricas |
| **Prometheus** | Coleta de métricas |
| **Resend** | Emails transacionais |
| **Twilio** | SMS/WhatsApp para notificações |

---

## Deploy — Opções por Ambiente

### Desenvolvimento Local
```bash
docker compose up -d  # postgres + redis + backend
cd frontend && npm run dev  # Next.js dev server
```

### Staging / Produção Simples (recomendado para começar)

| Serviço | Plataforma | Custo |
|---------|-----------|-------|
| Frontend | **Vercel** | Grátis (hobby) |
| Backend | **Railway** | $5/mês |
| PostgreSQL | **Neon** (serverless) | Grátis 0.5GB |
| Redis | **Upstash** | Grátis 10k req/dia |
| Celery | **Railway** (2º service) | +$3/mês |

**Total estimado:** ~$8/mês para MVP production

### Produção Robusta (Fase 3+)

| Serviço | Plataforma | Custo |
|---------|-----------|-------|
| Frontend | Vercel Pro | $20/mês |
| Backend | Railway Pro | $20/mês |
| PostgreSQL | Neon Pro / Supabase | $25/mês |
| Redis | Upstash Pro | $10/mês |
| CDN + Segurança | Cloudflare | Grátis |
| Monitoramento | Sentry Free | Grátis |
| Emails | Resend | $20/mês |

**Total estimado:** ~$95/mês

---

## Guia de Migração do MVP

### Passo 1: Setup Next.js com conteúdo atual
```bash
# Na pasta frontend/
npx create-next-app@latest . --typescript --tailwind --app --src-dir
npm install shadcn-ui
npx shadcn-ui@latest init

# Migrar páginas JSX → TSX no App Router:
# pages/Dashboard.jsx       → src/app/page.tsx
# pages/SessaoDetalhe.jsx   → src/app/sessao/[id]/page.tsx
# pages/Mobile.jsx          → src/app/mobile/[sessaoId]/page.tsx
# api/client.js             → src/lib/api.ts  (com tipos TypeScript)
```

### Passo 2: Adicionar Redis ao Docker Compose
```yaml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
  command: redis-server --appendonly yes
```

### Passo 3: WebSockets no FastAPI
```python
# backend/app/websockets.py
from fastapi import WebSocket
from typing import Dict, Set

class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, sessao_id: str):
        await websocket.accept()
        self.active.setdefault(sessao_id, set()).add(websocket)

    async def broadcast(self, sessao_id: str, message: dict):
        for ws in self.active.get(sessao_id, set()):
            await ws.send_json(message)
```

### Passo 4: JWT Auth
```python
# backend/app/auth.py
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta

SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"])

def create_access_token(data: dict, expires: timedelta = timedelta(hours=8)):
    payload = {**data, "exp": datetime.utcnow() + expires}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
```

### Passo 5: Primeiro agente — ValidationAgent
```python
# backend/agents/validation.py
import anthropic, json

class ValidationAgent:
    def __init__(self):
        self.client = anthropic.Anthropic()

    async def validate(self, items: list[dict]) -> dict:
        prompt = f"Valide estes {len(items)} itens de inventário: {json.dumps(items[:20])}"
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(response.content[0].text)
```

---

## Checklist de Qualidade (UI/UX Pro Max)

### Acessibilidade (WCAG AA)
- [ ] Contraste mínimo 4.5:1 para texto normal
- [ ] Contraste mínimo 3:1 para texto grande
- [ ] Todos os elementos interativos acessíveis via teclado
- [ ] Atributos `aria-*` em componentes customizados
- [ ] Focus ring visível em todos os elementos
- [ ] Sem informação apenas por cor

### Performance
- [ ] LCP < 2.5s (Largest Contentful Paint)
- [ ] CLS < 0.1 (Cumulative Layout Shift)
- [ ] FID < 100ms (First Input Delay)
- [ ] Imagens com lazy loading e WebP
- [ ] Code splitting por rota
- [ ] Bundle < 200KB (gzip) para rota inicial

### Responsividade
- [ ] 375px (iPhone SE) — scanner funciona
- [ ] 768px (iPad) — admin mobile
- [ ] 1024px (laptop) — dashboard completo
- [ ] 1440px (desktop wide) — vista expandida
- [ ] Sem horizontal scroll em nenhum breakpoint

### UX
- [ ] Loading states em todas as ações assíncronas
- [ ] Error states com mensagem clara e ação
- [ ] Empty states com call-to-action
- [ ] Confirmação antes de ações destrutivas
- [ ] Feedback de sucesso após ações positivas
- [ ] Transições suaves 150-300ms
- [ ] Botões com cursor-pointer
- [ ] Touch targets mínimo 44x44px (mobile)
- [ ] Sem emojis como único indicador de estado

---

## Variáveis de Ambiente Completas

```env
# .env.example — atualizado

# App
APP_ENV=development
APP_NAME="Inventário QR"
SECRET_KEY=your-secret-key-min-32-chars

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/inventario_qr

# Redis
REDIS_URL=redis://localhost:6379/0

# CORS
FRONTEND_URL=http://localhost:3000

# Claude AI
ANTHROPIC_API_KEY=sk-ant-...

# Auth
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=8

# Email (opcional Fase 2)
RESEND_API_KEY=re_...
FROM_EMAIL=noreply@inventarioqr.com.br

# Sentry (opcional)
SENTRY_DSN=https://...

# Agentes
AGENTS_ENABLED=true
AGENTS_MAX_TOKENS_PER_SESSION=50000
```

---

## Estimativa de Esforço por Fase

| Fase | Semanas | Dev Solo | Dev + 1 |
|------|---------|----------|---------|
| Fase 1 — Fundação | 4 | 4 semanas | 2 semanas |
| Fase 2 — Agentes | 4 | 4 semanas | 2 semanas |
| Fase 3 — Avançado | 4 | 5 semanas | 2.5 semanas |
| Fase 4 — Enterprise | 4 | 6 semanas | 3 semanas |
| **Total** | **16** | **19 semanas** | **9.5 semanas** |

> Começando pela Fase 1, em 4 semanas solo o projeto já será profissional e production-ready.
