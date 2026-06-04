import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# Desabilitado quando RATELIMIT_ENABLED=false (ex: ambiente de testes)
_enabled = os.getenv("RATELIMIT_ENABLED", "true").lower() != "false"
limiter = Limiter(key_func=get_remote_address, enabled=_enabled)
