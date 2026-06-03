from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv
import os
import pathlib

load_dotenv()

from app.database import create_tables
from app.limiter import limiter
from app.routes import sessoes, itens, contagens, exports, ws, agentes, grupos
from app.websockets.manager import manager  # noqa: F401 — singleton inicializado aqui

logger = logging.getLogger(__name__)

_APP_ENV = os.getenv("APP_ENV", "development")
_IS_PROD = _APP_ENV == "production"

# Em produção, valida que o banco é PostgreSQL
_DATABASE_URL = os.getenv("DATABASE_URL", "")
if _IS_PROD and not _DATABASE_URL.startswith("postgresql"):
    raise RuntimeError(
        "APP_ENV=production requer DATABASE_URL com PostgreSQL. "
        "Configure DATABASE_URL=postgresql://... no arquivo .env ou variáveis de ambiente."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


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
app.include_router(sessoes.router, prefix="/api")
app.include_router(itens.router, prefix="/api")
app.include_router(contagens.router, prefix="/api")
app.include_router(exports.router, prefix="/api")
app.include_router(agentes.router, prefix="/api")
app.include_router(grupos.router, prefix="/api")

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
            "env": _APP_ENV,
            "db": "ok" if db_ok else "error",
            "ws_connections": manager.active_count,
        },
    )


# Serve static frontend
_STATIC = pathlib.Path(__file__).parent.parent / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(_STATIC / "index.html"))

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

    @app.get("/manifest.json")
    def manifest():
        """PWA manifest para instalação como app no celular do operador."""
        return {
            "name": "INVIQ — Inventário QR",
            "short_name": "INVIQ",
            "description": "Inventário físico por QR Code em tempo real",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#071325",
            "theme_color": "#8fd6ff",
            "orientation": "portrait",
            "icons": [
                {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ],
            "shortcuts": [
                {
                    "name": "Scanner",
                    "url": "/mobile/",
                    "description": "Abrir scanner de inventário",
                }
            ],
        }
