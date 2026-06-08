import os
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _key_por_token_ou_ip(request: Request) -> str:
    """Usa token de acesso como chave de rate limit quando presente.
    Isso evita bloquear múltiplos operadores legítimos atrás do mesmo NAT/IP."""
    token = (
        request.query_params.get("token")
        or request.query_params.get("token_admin")
    )
    if token:
        return f"token:{token}"
    return get_remote_address(request)


# Desabilitado quando RATELIMIT_ENABLED=false (ex: ambiente de testes)
_enabled = os.getenv("RATELIMIT_ENABLED", "true").lower() != "false"
limiter = Limiter(key_func=_key_por_token_ou_ip, enabled=_enabled)
