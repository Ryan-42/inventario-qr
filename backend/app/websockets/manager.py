from __future__ import annotations

import json
import logging
from decimal import Decimal
from datetime import datetime, date
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


def _json_serial(obj):
    """Serializa tipos não-nativos do JSON de forma explícita (sem silenciar erros)."""
    if isinstance(obj, Decimal):
        return float(round(obj, 2))
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Tipo não serializável: {type(obj)!r}")


_MAX_CONNECTIONS_PER_SESSION = 50


class ConnectionManager:
    """Gerencia conexões WebSocket agrupadas por sessao_id."""

    def __init__(self) -> None:
        # sessao_id -> conjunto de WebSockets ativos
        self._connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, sessao_id: str) -> bool:
        """Aceita a conexão e registra no grupo da sessão.

        Retorna False e fecha o socket se o limite por sessão foi atingido.
        """
        await websocket.accept()
        if sessao_id not in self._connections:
            self._connections[sessao_id] = set()
        if len(self._connections[sessao_id]) >= _MAX_CONNECTIONS_PER_SESSION:
            await websocket.close(code=1008, reason="Too many connections for this session")
            logger.warning("WS rejeitado — sessao=%s limite=%d atingido", sessao_id, _MAX_CONNECTIONS_PER_SESSION)
            return False
        self._connections[sessao_id].add(websocket)
        # Remove sessões sem conexões acumuladas (limpeza preventiva de memory leak)
        self._cleanup_empty()
        logger.info("WS conectado — sessao=%s total=%d", sessao_id, len(self._connections[sessao_id]))
        return True

    def disconnect(self, websocket: WebSocket, sessao_id: str) -> None:
        """Remove a conexão do grupo da sessão."""
        grupo = self._connections.get(sessao_id)
        if grupo:
            grupo.discard(websocket)
            if not grupo:
                del self._connections[sessao_id]
        logger.info("WS desconectado — sessao=%s", sessao_id)

    def _cleanup_empty(self) -> None:
        """Remove sessões sem conexões ativas para evitar acúmulo de chaves vazias."""
        vazias = [k for k, v in self._connections.items() if not v]
        for k in vazias:
            del self._connections[k]

    async def broadcast(self, sessao_id: str, data: dict) -> None:
        """Envia JSON para todos os clients da sessão. Ignora falhas individuais."""
        grupo = self._connections.get(sessao_id)
        if not grupo:
            return

        try:
            payload = json.dumps(data, ensure_ascii=False, default=_json_serial)
        except TypeError as exc:
            logger.error("WS broadcast: falha ao serializar dados — sessao=%s erro=%s", sessao_id, exc)
            return

        mortos: list[WebSocket] = []

        for ws in list(grupo):
            try:
                await ws.send_text(payload)
            except Exception as exc:
                logger.warning("WS send falhou — sessao=%s erro=%s", sessao_id, exc)
                mortos.append(ws)

        # Limpa conexões que falharam
        for ws in mortos:
            grupo.discard(ws)
        if not grupo:
            self._connections.pop(sessao_id, None)

    @property
    def active_count(self) -> int:
        """Retorna total de conexões ativas em todas as sessões."""
        return sum(len(g) for g in self._connections.values())


# Singleton global — importar com: from app.websockets.manager import manager
manager = ConnectionManager()
