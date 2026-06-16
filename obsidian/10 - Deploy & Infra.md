---
tags: [deploy]
aliases: [Deploy, Infra, Railway, Docker, CI/CD]
---

# Deploy & Infra — INVIQ

> [!info] Produção
> **Backend + DB:** Railway (PostgreSQL + FastAPI no mesmo projeto)
> **Build:** Docker multi-stage · `render.yaml` + `docker-compose.yml`
> **CI/CD:** Push no `main` → Railway faz rebuild automático

---

## Diagrama de Infraestrutura

```mermaid
graph TD
    subgraph Dev["💻 Desenvolvimento Local"]
        DC["docker-compose.yml\nPostgreSQL + Backend"]
        DEV["uvicorn --reload\n:8000"]
    end

    subgraph Railway["🚀 Railway (Produção)"]
        PG["PostgreSQL 16\nRailway Managed"]
        BE["FastAPI (Uvicorn)\nContainer Docker"]
        ALB["Alembic migrations\n(entrypoint.sh)"]
    end

    subgraph Static["📦 Assets Estáticos"]
        CSS["app.css"]
        JS["ws.js · api.js"]
        SW["sw.js (Service Worker)"]
        ICO["icon-192.png · icon-512.png"]
        HTML["*.html"]
    end

    GIT["GitHub (main)"] -->|push| Railway
    ALB --> PG
    BE --> PG
    BE --> Static
    Static -->|servidos pelo FastAPI\n/static/*| USERS["Operadores\n+ Admin"]
    BE -->|/api/* + /ws/*| USERS
```

---

## docker-compose.yml (desenvolvimento)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: inventario_qr
      POSTGRES_USER: inviq
      POSTGRES_PASSWORD: inviq_dev
    ports: ["5432:5432"]
    volumes: [postgres_data:/var/lib/postgresql/data]

  backend:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [postgres]
    environment:
      DATABASE_URL: postgresql://inviq:inviq_dev@postgres:5432/inventario_qr
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    volumes: [./backend:/app]
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## entrypoint.sh (Railway)

```bash
#!/bin/sh
set -e
alembic upgrade head        # migrations automáticas na startup
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port ${PORT:-8000} \
  --workers ${WORKERS:-2}
```

---

## Variáveis de Ambiente

| Variável | Obrigatória | Uso |
|----------|------------|-----|
| `DATABASE_URL` | ✅ | Conexão PostgreSQL |
| `ANTHROPIC_API_KEY` | ⚠️ | Agentes IA (sem ela → fallback determinístico) |
| `SECRET_KEY` | ✅ | HMAC para tokens admin |
| `APP_ENV` | ✅ | `production` habilita HTTPS redirect + desativa Swagger |
| `FRONTEND_URL` | ✅ | CORS origin permitida |
| `WORKERS` | — | Uvicorn workers (default: 2) |
| `PORT` | — | Porta (Railway injeta automaticamente) |

---

## Rota do Service Worker

```python
# main.py — SW precisa de header especial para escopo raiz
@app.get("/sw.js", response_class=FileResponse)
def service_worker():
    return FileResponse(
        str(_STATIC / "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},  # permite controlar todo o site
    )
```

---

## Custo Estimado

| Ambiente | Serviços | Custo |
|----------|---------|-------|
| **Desenvolvimento** | Docker local | $0 |
| **Produção simples** | Railway (backend + PostgreSQL) | ~$10/mês |
| **Produção robusta** | Railway Pro + Neon Pro + Cloudflare | ~$50/mês |

---

## Conexões

- [[01 - Arquitetura]] — decisões de stack que impactam infra
- [[07 - Segurança]] — variáveis sensíveis, HTTPS, HSTS
- [[09 - PWA & Offline]] — rota /sw.js com Service-Worker-Allowed
- [[12 - Testes]] — CI pode rodar pytest antes do deploy
- [[00 - INVIQ]] — visão geral
