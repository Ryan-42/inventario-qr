"""Utilitários de autenticação compartilhados entre rotas."""
import hmac
from fastapi import HTTPException
from app.models.sessao import Sessao


def verificar_token_admin(sessao: Sessao, token_admin: str) -> None:
    """Valida token_admin via timing-safe compare. Levanta 403 se inválido."""
    if not hmac.compare_digest(sessao.token_admin or "", token_admin or ""):
        raise HTTPException(status_code=403, detail="Token de administrador inválido.")
