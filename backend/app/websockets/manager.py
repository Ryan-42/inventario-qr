from __future__ import annotations

import json
import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Gerencia conexões WebSocket agrupadas por sessao_id."""

    def __init__(self) -> None:
        # sessao_id -> conjunto de WebSockets ativos
        self._connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, sessao_id: str) -> None:
        """Aceita a conexão e registra no grupo da sessão."""
        await websocket.accept()
        if sessao_id not in self._connections:
            self._connections[sessao_id] = set()
        self._connections[sessao_id].add(websocket)
        logger.info("WS conectado — sessao=%s total=%d", sessao_id, len(self._connections[sessao_id]))

    def disconnect(self, websocket: WebSocket, sessao_id: str) -> None:
        """Remove a conexão do grupo da sessão."""
        grupo = self._connections.get(sessao_id)
        if grupo:
            grupo.discard(websocket)
            if not grupo:
                del self._connections[sessao_id]
        logger.info("WS desconectado — sessao=%s", sessao_id)

    async def broadcast(self, sessao_id: str, data: dict) -> None:
        """Envia JSON para todos os clients da sessão. Ignora falhas individuais."""
        grupo = self._connections.get(sessao_id)
        if not grupo:
            return

        payload = json.dumps(data, ensure_ascii=False, default=str)
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
