"""Blacklist em memória para JWTs revogados (logout).
Para ambientes multi-instância, substitua por Redis."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

_store: dict[str, datetime] = {}
_lock = threading.Lock()


def revoke(jti: str, expiry: datetime) -> None:
    with _lock:
        _store[jti] = expiry
        _prune()


def is_revoked(jti: str) -> bool:
    with _lock:
        _prune()
        return jti in _store


def _prune() -> None:
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _store.items() if v <= now]
    for k in expired:
        del _store[k]
