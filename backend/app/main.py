from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv
import os
import pathlib

load_dotenv()

from app.database import create_tables
from app.limiter import limiter
from app.routes import sessoes, itens, contagens, exports, ws, agentes
from app.websockets.manager import manager  # noqa: F401 — singleton inicializado aqui


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title="Inventário QR Code API",
    description="Sistema de inventário via QR Code com FastAPI + PostgreSQL",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — suporta múltiplas origens via ALLOWED_ORIGINS (separadas por vírgula)
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:8000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

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

# Registra router WebSocket
app.include_router(ws.router, prefix="/api")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "sistema": "Inventário QR Code",
        "ws_connections": manager.active_count,
    }


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
