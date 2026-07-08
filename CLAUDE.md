# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dev server (from backend/)
uvicorn app.main:app --reload --port 8000
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000   # expose to phones on same Wi-Fi

# Tests (from backend/) — SQLite in-memory, 429 passed / 1 pre-existing skip
pytest tests/ -q
pytest tests/test_contagens.py -q                            # single file
pytest tests/test_contagens.py::test_contagem_sem_token_retorna_401 -v   # single test

# Admin user (from backend/) — creates/updates the first admin login
python criar_admin.py                                         # interactive
ADMIN_EMAIL=a@b.com ADMIN_SENHA='Senha123!' python criar_admin.py   # non-interactive

# Migrations (from backend/)
alembic upgrade head
alembic heads          # should always show exactly one head

# Docker (from repo root)
docker compose up --build                # dev, hot-reload
docker compose -f docker-compose.prod.yml up --build   # prod-like, Postgres
```

`backend/requirements.txt` (`>=` pins, used by the Dockerfile) is the source of truth for what gets installed. `backend/requirements.lock` is a reference pin-file for reproducible installs — note it was generated from a Windows dev venv, so `gunicorn` (Unix-only, won't install on Windows) is added to it by hand. Don't regenerate it blindly with `pip freeze` on Windows without re-adding `gunicorn`.

## Architecture

**Stack:** FastAPI + SQLAlchemy 2.x, dual database (SQLite for dev/tests, PostgreSQL in production), static HTML/vanilla-JS frontend with no build step (Tailwind via CDN).

### AI agents are loaded dynamically, not imported normally

`backend/app/agents/__init__.py` walks `backend/.agents/{name}/{name}.py` at import time and registers each as `sys.modules['app.agents.{name}']` via `importlib`. Routes then do `from app.agents.validation import ValidationAgent` as if it were a normal package. The 11 real agents are: `ajuste`, `alerta`, `analise`, `antifraude`, `plano_acao`, `preditor`, `provider`, `relatorio`, `sop_coach`, `sync_erp`, `validation`. `provider.py` is the `AIProvider` abstraction that switches between Anthropic/Groq and is gated by `AI_ENABLED` (default `false` — no external API calls without explicit opt-in, for LGPD compliance).

**`.agents/` must live inside `backend/`** (`backend/.agents/`), never at the repo root. The Docker build uses `dockerContext: ./backend`, so anything outside `backend/` never reaches the image — this exact mistake caused a production outage (`ModuleNotFoundError: app.agents.validation`) that was fixed by moving the folder in and updating the loader's `parents[2]` index.

**`AGENTS.md` at the repo root is aspirational, not descriptive.** It documents a Redis/Celery/pgvector "queen-hierarchy" multi-agent design that was never built (`requirements.txt` has no redis/celery/pgvector). The real system is the simple dynamic loader described above — don't take `AGENTS.md` as ground truth for how agents currently work.

### Auth has two independent systems

- **Admin login**: JWT, `app/auth.py` (`get_admin_logado`, `get_admin_logado_opcional` for routes admins can optionally use).
- **Operator/session access**: per-session tokens (`token_acesso`, `token_supervisor`, group tokens), compared with `hmac.compare_digest`. Always reject an empty token explicitly before comparing — `hmac.compare_digest("", "") == True`, so an unset `token_supervisor` (`None` → `""`) will silently accept an empty token unless guarded.

Blind counting is enforced at the API: `GET /itens`, `/contagens`, `/historico`, `/stats`, `/rodadas`, `/metricas`, `/valor-estoque`, `/grupos`, `/segunda-aprovacao` and the QR-code PNG endpoints require admin JWT (they expose `quantidade_base` or embedded tokens). `/buscar/{codigo}` and `/itens-operador` accept an operator token but return `quantidade_base`/`contagem_anterior` only to admins. `GET /sessoes/{id}` and `/progresso` stay public (mobile/supervisor pages consume them without JWT), with `webhook_url` stripped for non-admins. Regression coverage: `tests/test_hardening.py`.

`static/sw.js` pre-caches `/static/js/*.js` cache-first — **bump `CACHE_NAME` whenever api.js/ws.js/auth.js change**, or deployed clients keep the stale bundle indefinitely.

### Counting rounds ("rodadas") and WebSocket

Sessions go through up to 3 recount rounds for divergent items; a repeated identical divergence goes to "Para Ajuste" instead of triggering another round. `app/websockets/manager.py` broadcasts per-session updates; the WebSocket requires a token in the query string (same token set as `/contagens`) and closes with code `4401` before accepting if invalid.

### Scheduler uses a Postgres advisory lock

`app/services/scheduler.py` runs a background asyncio loop from the FastAPI `lifespan`. It calls `pg_try_advisory_lock` so that only one gunicorn worker processes pending agendamentos per cycle — on SQLite this always "succeeds" (dev is assumed single-worker). Requires a **direct** (non-pooled) Postgres connection; PgBouncer/connection poolers break advisory locks.

### Migrations vs. `create_tables()`

`alembic/versions/0001` uses non-idempotent `op.create_table`. Later migrations (0007, 0008+) intentionally use raw `CREATE TABLE IF NOT EXISTS` / dialect-branching SQL, both because some operations (`ALTER TYPE`) are Postgres-only, and to safely handle databases that already have the schema. In dev/test, `create_tables()` (`Base.metadata.create_all`) runs instead of Alembic; it's gated off when `APP_ENV=production`, where only Alembic (via `entrypoint.sh`) manages schema.

`entrypoint.sh` boot sequence: wait for DB → `scripts/detect_schema_state.py` (checks whether `sessoes` exists without `alembic_version`, e.g. a Neon DB seeded before Alembic was adopted) → `alembic stamp head` if so → `alembic upgrade head` → `exec gunicorn`. Every step aborts loudly with a diagnostic message instead of failing silently into a 502.

### Deploy

`render.yaml` provisions only the web service (Docker, `dockerContext: ./backend`). Postgres is external (Neon) — `DATABASE_URL` is `sync: false` and must be set by hand to Neon's **direct** connection string. Render's own free Postgres is deleted after ~90 days of inactivity-free tier lifetime, which caused a prior outage; Neon's free tier doesn't expire the same way, hence the externalization.

`.gitattributes` forces LF line endings on `.sh`/Dockerfile/etc. — the repo is developed on Windows but runs in Linux containers; a CRLF-corrupted `entrypoint.sh` shebang breaks the container boot.

### Tests

`backend/tests/conftest.py` wires a single shared SQLite in-memory connection (`StaticPool`) for the whole test session. Security tests deliberately construct a client without the admin JWT header (see `_cliente_sem_jwt` in `test_contagens.py`) to exercise operator-token-only auth paths independently of admin auth.
