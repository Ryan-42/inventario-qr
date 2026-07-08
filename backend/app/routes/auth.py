"""Rotas de autenticação: login, logout, me."""
from __future__ import annotations

import logging
import time
import threading
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import criar_token, verificar_senha, get_admin_logado, _ip_de as _ip_confiavel
from app.database import get_db
from app.limiter import limiter
from app.models.admin import Admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

# ── Rate limit de login (5 tentativas / 60s por IP) ──────────────────────────

_LOGIN_MAX  = 5
_LOGIN_JANELA = 60
_login_falhas: dict[str, list[float]] = defaultdict(list)
_login_lock = threading.Lock()


def _check_login_rate(ip: str) -> None:
    agora = time.monotonic()
    with _login_lock:
        _login_falhas[ip] = [t for t in _login_falhas[ip] if agora - t < _LOGIN_JANELA]
        if len(_login_falhas[ip]) >= _LOGIN_MAX:
            raise HTTPException(
                status_code=429,
                detail="Muitas tentativas de login. Aguarde 60 segundos.",
                headers={"Retry-After": "60"},
            )


def _login_falha(ip: str) -> None:
    with _login_lock:
        _login_falhas[ip].append(time.monotonic())


def _login_ok(ip: str) -> None:
    with _login_lock:
        _login_falhas.pop(ip, None)


def _ip_de(request: Request) -> str:
    # Reusa a versão TRUST_PROXY-aware de app.auth: sem proxy confiável configurado,
    # X-Forwarded-For pode ser forjado pelo cliente para burlar o rate limit de login.
    return _ip_confiavel(request)


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginPayload(BaseModel):
    email: str
    senha: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: dict


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginPayload, db: Session = Depends(get_db)):
    ip = _ip_de(request)
    _check_login_rate(ip)

    admin = db.query(Admin).filter(Admin.email == payload.email).first()
    if not admin or not verificar_senha(payload.senha, admin.senha_hash):
        _login_falha(ip)
        logger.warning("login_failed email=%s ip=%s", payload.email, ip)
        raise HTTPException(status_code=401, detail="Email ou senha inválidos.")

    _login_ok(ip)
    token = criar_token({"sub": admin.email})
    logger.info("login_ok email=%s ip=%s", admin.email, ip)
    return {
        "access_token": token,
        "token_type": "bearer",
        "admin": {"id": admin.id, "nome": admin.nome, "email": admin.email},
    }


@router.post("/logout")
async def logout(request: Request, admin=Depends(get_admin_logado)):
    from jose import jwt as _jwt
    from app.services.token_blacklist import revoke
    from datetime import datetime, timezone

    from app.auth import _SECRET_KEY, _ALGORITHM  # noqa

    # Extrai token para revogar o jti
    from fastapi.security import OAuth2PasswordBearer
    token = request.cookies.get("token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if token:
        try:
            payload = _jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                revoke(jti, datetime.fromtimestamp(exp, tz=timezone.utc))
        except Exception as exc:
            logger.debug("logout: não foi possível revogar JTI (token inválido ou expirado): %s", exc)

    logger.info("logout email=%s", admin.email)
    return {"ok": True}


@router.get("/me")
async def me(admin=Depends(get_admin_logado)):
    return {"id": admin.id, "nome": admin.nome, "email": admin.email}


# Endpoint compatível com OAuth2 form (Swagger UI)
# Mesmas proteções do /auth/login — sem elas este endpoint seria um bypass
# do rate limit e do rastreio de brute-force.
@router.post("/token")
@limiter.limit("10/minute")
async def token_form(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    ip = _ip_de(request)
    _check_login_rate(ip)
    admin = db.query(Admin).filter(Admin.email == form.username).first()
    if not admin or not verificar_senha(form.password, admin.senha_hash):
        _login_falha(ip)
        logger.warning("login_failed email=%s ip=%s (via /auth/token)", form.username, ip)
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")
    _login_ok(ip)
    token = criar_token({"sub": admin.email})
    return {"access_token": token, "token_type": "bearer"}


class AlterarSenhaPayload(BaseModel):
    senha_atual: str
    senha_nova: str


@router.post("/alterar-senha")
async def alterar_senha(
    payload: AlterarSenhaPayload,
    admin=Depends(get_admin_logado),
    db: Session = Depends(get_db),
):
    """Permite ao admin logado trocar a própria senha (antes só era possível via criar_admin.py no servidor)."""
    from app.auth import hash_senha
    if not verificar_senha(payload.senha_atual, admin.senha_hash):
        raise HTTPException(status_code=403, detail="Senha atual incorreta.")
    if len(payload.senha_nova) < 8:
        raise HTTPException(status_code=422, detail="A nova senha deve ter no mínimo 8 caracteres.")
    admin.senha_hash = hash_senha(payload.senha_nova)
    db.commit()
    logger.info("senha_alterada email=%s", admin.email)
    return {"ok": True, "mensagem": "Senha alterada com sucesso."}
