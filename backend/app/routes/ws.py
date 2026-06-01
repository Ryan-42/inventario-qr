from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websockets.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket("/sessao/{sessao_id}")
async def websocket_sessao(websocket: WebSocket, sessao_id: str) -> None:
    """
    Endpoint WebSocket para atualizações em tempo real de uma sessão.

    Clientes conectam em:  ws://host/api/ws/sessao/{sessao_id}

    O servidor envia mensagens JSON nos seguintes eventos:
      - contagem_registrada: nova contagem adicionada à sessão
    """
    await manager.connect(websocket, sessao_id)
    try:
        while True:
            # Mantém a conexão viva aguardando mensagens do cliente.
            # Clientes podem enviar "ping" para verificar conectividade;
            # qualquer outro texto é ignorado silenciosamente.
            data = await websocket.receive_text()
            raw = data.strip()
            # Aceita tanto "ping" texto puro quanto JSON {"tipo":"ping"}
            if raw.lower() == "ping" or '"ping"' in raw:
                await websocket.send_text('{"tipo":"pong"}')
    except WebSocketDisconnect:
        logger.info("WebSocket desconectado normalmente — sessao=%s", sessao_id)
    except Exception as exc:
        logger.warning("WebSocket encerrado com erro — sessao=%s erro=%s", sessao_id, exc)
    finally:
        manager.disconnect(websocket, sessao_id)
