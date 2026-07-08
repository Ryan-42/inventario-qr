"""Configurações centralizadas da aplicação — leia de env vars com defaults seguros."""
from __future__ import annotations

import os

# ── Ambiente ──────────────────────────────────────────────────────────────────
APP_ENV: str = os.getenv("APP_ENV", "development")

# ── JWT ───────────────────────────────────────────────────────────────────────
SECRET_KEY: str = os.getenv("SECRET_KEY", "inviq-local-dev-inseguro")
TOKEN_EXPIRE_HORAS: int = int(os.getenv("TOKEN_EXPIRE_HORAS", "8"))

# ── Brute-force / Login ───────────────────────────────────────────────────────
BRUTE_FORCE_MAX_TENTATIVAS: int = int(os.getenv("BRUTE_FORCE_MAX_TENTATIVAS", "10"))
BRUTE_FORCE_JANELA_SEG: int = int(os.getenv("BRUTE_FORCE_JANELA_SEG", "900"))

LOGIN_MAX_FALHAS: int = int(os.getenv("LOGIN_MAX_FALHAS", "5"))
LOGIN_JANELA_SEG: int = int(os.getenv("LOGIN_JANELA_SEG", "60"))

# ── WebSocket ─────────────────────────────────────────────────────────────────
MAX_CONNECTIONS_PER_SESSION: int = int(os.getenv("MAX_CONNECTIONS_PER_SESSION", "50"))

# ── Inventário ────────────────────────────────────────────────────────────────
MAX_RODADAS_DIVERGENCIA: int = int(os.getenv("MAX_RODADAS_DIVERGENCIA", "5"))
UPLOAD_MAX_ROWS: int = int(os.getenv("UPLOAD_MAX_ROWS", "50000"))

# ── Agendamentos ──────────────────────────────────────────────────────────────
# Fuso em que o campo `hora` dos agendamentos é interpretado. Sem isso, "08:00"
# seria UTC e a sessão nasceria às 05:00 no horário de Brasília.
SCHEDULER_TZ: str = os.getenv("SCHEDULER_TZ", "America/Sao_Paulo")

# ── Limites de campo ─────────────────────────────────────────────────────────
MAX_LEN_OPERADOR: int = 100
MAX_LEN_OBSERVACAO: int = 500
MAX_LEN_NOME_SESSAO: int = 255
MAX_LEN_CODIGO_ITEM: int = 100


# ── IA / LGPD ─────────────────────────────────────────────────────────────────
# AI_ENABLED=false (padrão) — agentes operam em modo local mesmo com chave configurada.
# Defina true apenas após revisar a seção "Governança de dados e LGPD" no README.
AI_ENABLED: bool = os.getenv("AI_ENABLED", "false").lower() in ("1", "true", "yes")


def validar_config_producao() -> None:
    """Levanta RuntimeError se o ambiente for produção e houver config insegura."""
    if APP_ENV != "production":
        return

    erros: list[str] = []

    if SECRET_KEY == "inviq-local-dev-inseguro":
        erros.append(
            "SECRET_KEY não definida ou usa o valor padrão inseguro. "
            "Gere uma chave com: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    if len(SECRET_KEY) < 32:
        erros.append(
            f"SECRET_KEY muito curta ({len(SECRET_KEY)} chars). Use mínimo 32 chars (64 recomendado)."
        )

    if erros:
        raise RuntimeError(
            "Configuração de produção inválida:\n" + "\n".join(f"  • {e}" for e in erros)
        )
