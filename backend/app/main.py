from contextlib import asynccontextmanager
import logging
import logging.config

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.datastructures import MutableHeaders
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv
import os
import pathlib

load_dotenv()

from app.database import create_tables
from app.limiter import limiter
from app.routes import sessoes, itens, contagens, exports, ws, agentes, grupos, auditoria, integracoes, agendamentos, dashboard, filiais, auth as auth_routes
from app.websockets.manager import manager  # noqa: F401 — singleton inicializado aqui

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

from app.config import APP_ENV, validar_config_producao

_IS_PROD = APP_ENV == "production"

# Valida configurações críticas de produção (SECRET_KEY, etc.)
validar_config_producao()

# Em produção, valida que o banco é PostgreSQL
_DATABASE_URL = os.getenv("DATABASE_URL", "")
if _IS_PROD and not _DATABASE_URL.startswith("postgresql"):
    raise RuntimeError(
        "APP_ENV=production requer DATABASE_URL com PostgreSQL. "
        "Configure DATABASE_URL=postgresql://... no arquivo .env ou variáveis de ambiente."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Em produção, o schema é gerenciado exclusivamente pelo Alembic (entrypoint.sh).
    # create_tables() só roda fora de produção (dev/test) para facilitar o setup local.
    if not _IS_PROD:
        create_tables()
    # Inicia scheduler de agendamentos em background.
    # A referência é guardada em app.state: tasks sem referência podem ser
    # coletadas pelo GC no meio da execução (aviso documentado do asyncio).
    import asyncio
    from app.services.scheduler import loop_agendamentos
    app.state.scheduler_task = asyncio.create_task(loop_agendamentos())
    yield
    app.state.scheduler_task.cancel()


app = FastAPI(
    title="INVIQ — Inventário por QR Code",
    description="Sistema de inventário físico via QR Code com FastAPI + PostgreSQL + IA",
    version="1.1.0",
    lifespan=lifespan,
    # Desativa docs em produção por segurança
    docs_url=None if _IS_PROD else "/docs",
    redoc_url=None if _IS_PROD else "/redoc",
    openapi_url=None if _IS_PROD else "/openapi.json",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class SecurityHeadersMiddleware:
    """
    Middleware ASGI puro que adiciona headers de segurança sem bufferizar responses.
    Ao contrário de BaseHTTPMiddleware, intercepta diretamente o evento 'http.response.start'
    e modifica os headers antes de enviá-los — não consome o body, preserva streaming.
    """
    def __init__(self, app: ASGIApp, is_prod: bool = False) -> None:
        self.app = app
        # CSP: permite CDN do Tailwind/MDI/Google Fonts e WebSocket local
        # DÉBITO TÉCNICO: 'unsafe-inline' em script-src é necessário enquanto o frontend usa scripts
        # inline em HTML. Para remover, mover scripts inline para arquivos .js externos.
        # Rastreado em ROADMAP.md (Sprint futura — Hardening CSP).
        _csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' wss: ws:; "
            "img-src 'self' data: blob:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        self._headers = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"x-xss-protection", b"1; mode=block"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            (b"permissions-policy", b"camera=self, microphone=(), geolocation=(), payment=()"),
            (b"content-security-policy", _csp.encode()),
            (b"cross-origin-opener-policy", b"same-origin"),
            (b"cross-origin-resource-policy", b"same-origin"),
        ]
        if is_prod:
            self._headers.append(
                (b"strict-transport-security", b"max-age=63072000; includeSubDomains; preload")
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Limite de body: rejeita requests > 50 MB antes de processar
        if scope["type"] == "http":
            content_length = dict(scope.get("headers", [])).get(b"content-length")
            if content_length and int(content_length) > 50 * 1024 * 1024:
                import json as _json
                body = _json.dumps({"detail": "Request body muito grande (máximo 50 MB)."}).encode()
                await send({"type": "http.response.start", "status": 413, "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ]})
                await send({"type": "http.response.body", "body": body})
                return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self._headers:
                    headers.append(name.decode(), value.decode())
            await send(message)

        await self.app(scope, receive, send_with_headers)


app.add_middleware(SecurityHeadersMiddleware, is_prod=_IS_PROD)

# CORS — suporta múltiplas origens via ALLOWED_ORIGINS (separadas por vírgula)
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:8000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# Segurança: bloqueia wildcard com credentials (CSRF risk)
if "*" in _allowed_origins and _IS_PROD:
    raise RuntimeError("CORS com wildcard '*' não é permitido em produção. Configure ALLOWED_ORIGINS com origens específicas.")
if "*" in _allowed_origins:
    logger.warning("CORS com wildcard '*' configurado — NÃO use em produção!")

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

# Registra routers HTTP
app.include_router(auth_routes.router)          # /auth/login, /auth/logout, /auth/me
app.include_router(sessoes.router, prefix="/api")
app.include_router(itens.router, prefix="/api")
app.include_router(contagens.router, prefix="/api")
app.include_router(exports.router, prefix="/api")
app.include_router(agentes.router, prefix="/api")
app.include_router(grupos.router, prefix="/api")
app.include_router(auditoria.router, prefix="/api")
app.include_router(integracoes.router, prefix="/api")
app.include_router(agendamentos.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(filiais.router, prefix="/api")

# Registra router WebSocket
app.include_router(ws.router, prefix="/api")


@app.get("/health")
async def health():
    """Health check com validação de banco de dados — usado por load balancers e container orchestration."""
    from app.database import SessionLocal
    db_ok = False
    try:
        from sqlalchemy import text
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.error("Health check DB falhou: %s", exc)

    status = "ok" if db_ok else "degraded"
    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={
            "status": status,
            "sistema": "INVIQ",
            "env": APP_ENV,
            "db": "ok" if db_ok else "error",
            "ws_connections": manager.active_count,
        },
    )


# Serve static frontend
_STATIC = pathlib.Path(__file__).parent.parent / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    @app.get("/login")
    def login_page():
        return FileResponse(str(_STATIC / "login.html"))

    @app.get("/")
    def index():
        return FileResponse(str(_STATIC / "index.html"))

    @app.get("/dashboard")
    def dashboard_page():
        return FileResponse(str(_STATIC / "dashboard.html"))

    @app.get("/agendamentos")
    def agendamentos_page():
        return FileResponse(str(_STATIC / "agendamentos.html"))

    @app.get("/sessao/{sessao_id}")
    def sessao_page(sessao_id: str):
        return FileResponse(str(_STATIC / "sessao.html"))

    @app.get("/mobile/{sessao_id}")
    def mobile_page(sessao_id: str):
        return FileResponse(str(_STATIC / "mobile.html"))

    @app.get("/supervisor/{sessao_id}")
    def supervisor_page(sessao_id: str):
        return FileResponse(str(_STATIC / "supervisor.html"))

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots_txt():
        """Impede crawlers de indexar dados sensíveis."""
        return (
            "User-agent: *\n"
            "Disallow: /api/\n"
            "Disallow: /mobile/\n"
            "Disallow: /supervisor/\n"
            "Disallow: /sessao/\n"
            "Allow: /\n"
        )

    @app.get("/sw.js", response_class=FileResponse)
    def service_worker():
        """Service Worker para cache offline e PWA."""
        return FileResponse(
            str(_STATIC / "sw.js"),
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    @app.get("/manifest.json")
    def manifest():
        """PWA manifest para instalação como app no celular do operador."""
        return {
            "name": "INVIQ — Inventário QR",
            "short_name": "INVIQ",
            "description": "Inventário físico por QR Code em tempo real",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#071325",
            "theme_color": "#8fd6ff",
            "orientation": "portrait",
            "categories": ["productivity", "utilities"],
            "icons": [
                {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
            # Sem shortcut para /mobile/ — a rota exige sessao_id ("/mobile/" daria 404).
            # O operador entra sempre pelo QR Code, que embute sessão e token.
            "shortcuts": [],
        }
