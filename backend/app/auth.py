"""Utilitários de autenticação com proteção contra brute-force."""
from __future__ import annotations

import hmac
import logging
import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request

from app.models.sessao import Sessao

logger = logging.getLogger(__name__)

# ── Brute-force protection ────────────────────────────────────────────────────
# Rastreia tentativas falhas por IP em memória (TTL de 15 minutos).
# Thread-safe via lock; sem dependência de Redis para facilitar o deploy.

_TENTATIVAS_MAX   = 10   # falhas até bloqueio por IP
_JANELA_SEGUNDOS  = 900  # 15 minutos
_BLOQUEIO_SEGUNDOS = 300  # 5 minutos de bloqueio após exceder limite

_falhas: dict[str, list[float]] = defaultdict(list)
_bloqueados: dict[str, float] = {}
_lock = threading.Lock()


def _ip_de(request: Request | None) -> str:
    if request is None:
        return "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _verificar_bloqueio(ip: str) -> None:
    """Levanta 429 se o IP estiver temporariamente bloqueado."""
    agora = time.monotonic()
    with _lock:
        bloqueado_ate = _bloqueados.get(ip)
        if bloqueado_ate and agora < bloqueado_ate:
            restante = int(bloqueado_ate - agora)
            logger.warning("auth_blocked ip=%s restante=%ds", ip, restante)
            raise HTTPException(
                status_code=429,
                detail=f"Muitas tentativas incorretas. Aguarde {restante} segundos.",
                headers={"Retry-After": str(restante)},
            )
        # Remove bloqueio expirado
        if bloqueado_ate and agora >= bloqueado_ate:
            del _bloqueados[ip]


def _registrar_falha(ip: str, sessao_id: str) -> None:
    """Registra falha de autenticação. Bloqueia o IP ao atingir o limite."""
    agora = time.monotonic()
    with _lock:
        # Remove tentativas fora da janela
        _falhas[ip] = [t for t in _falhas[ip] if agora - t < _JANELA_SEGUNDOS]
        _falhas[ip].append(agora)
        total = len(_falhas[ip])

        if total >= _TENTATIVAS_MAX:
            _bloqueados[ip] = agora + _BLOQUEIO_SEGUNDOS
            _falhas[ip].clear()
            logger.warning(
                "auth_brute_force_blocked ip=%s sessao=%s tentativas=%d",
                ip, sessao_id, total,
            )
        else:
            logger.warning(
                "auth_failed ip=%s sessao=%s tentativa=%d/%d",
                ip, sessao_id, total, _TENTATIVAS_MAX,
            )


def _registrar_sucesso(ip: str) -> None:
    """Limpa histórico de falhas após autenticação bem-sucedida."""
    with _lock:
        _falhas.pop(ip, None)


# ── API pública ───────────────────────────────────────────────────────────────

def verificar_token_admin(
    sessao: Sessao,
    token_admin: str,
    request: Request | None = None,
) -> None:
    """
    Valida token_admin via timing-safe compare com proteção contra brute-force.
    Levanta 403 se inválido, 429 se o IP foi bloqueado por excesso de tentativas.
    """
    ip = _ip_de(request)
    _verificar_bloqueio(ip)

    valido = hmac.compare_digest(sessao.token_admin or "", token_admin or "")
    if not valido:
        sessao_id = getattr(sessao, "id", "?")
        _registrar_falha(ip, sessao_id)
        raise HTTPException(status_code=403, detail="Token de administrador inválido.")

    _registrar_sucesso(ip)


def verificar_token_admin_str(
    token_esperado: str,
    token_recebido: str,
    ip: str = "unknown",
    contexto: str = "?",
) -> None:
    """Variante para quando não há objeto Sessao disponível (ex: agendamentos)."""
    _verificar_bloqueio(ip)
    if not hmac.compare_digest(token_esperado or "", token_recebido or ""):
        _registrar_falha(ip, contexto)
        raise HTTPException(status_code=403, detail="Token inválido.")
    _registrar_sucesso(ip)


def status_brute_force(ip: str) -> dict:
    """Retorna situação de brute-force para um IP (uso interno/diagnóstico)."""
    agora = time.monotonic()
    with _lock:
        falhas = len([t for t in _falhas.get(ip, []) if agora - t < _JANELA_SEGUNDOS])
        bloqueado_ate = _bloqueados.get(ip)
        return {
            "ip": ip,
            "falhas_na_janela": falhas,
            "bloqueado": bool(bloqueado_ate and agora < bloqueado_ate),
            "bloqueado_por_mais": max(0, int((bloqueado_ate or 0) - agora)),
        }
