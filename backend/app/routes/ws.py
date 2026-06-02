from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import sessao_repo
from app.websockets.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket("/sessao/{sessao_id}")
async def websocket_sessao(websocket: WebSocket, sessao_id: str,
                           db: Session = Depends(get_db)) -> None:
    """
    Endpoint WebSocket para atualizações em tempo real de uma sessão.
    Rejeita conexões para sessões inexistentes antes de aceitar.
    """
    # Valida sessão antes de aceitar — previne memory leak com IDs forjados
    try:
        sessao = sessao_repo.buscar_sessao(db, sessao_id)
    except Exception as exc:
        logger.error("WS: falha ao validar sessao=%s erro=%s", sessao_id, exc)
        await websocket.close(code=1011, reason="Erro interno ao validar sessão")
        return

    if not sessao:
        await websocket.close(code=4404, reason="Sessão não encontrada")
        logger.warning("WS rejeitado — sessao_id inexistente: %s", sessao_id)
        return

    await manager.connect(websocket, sessao_id)
    try:
        while True:
            # Mantém a conexão viva aguardando mensagens do cliente.
            # Clientes podem enviar "ping" para verificar conectividade;
            # qualquer outro texto é ignorado silenciosamente.
            data = await websocket.receive_text()
            raw = data.strip()
            # Detecta ping corretamente: JSON {"tipo":"ping"} ou texto "ping"
            is_ping = False
            if raw.lower() == "ping":
                is_ping = True
            else:
                try:
                    is_ping = json.loads(raw).get("tipo") == "ping"
                except (json.JSONDecodeError, AttributeError):
                    pass
            if is_ping:
                await websocket.send_text('{"tipo":"pong"}')
    except WebSocketDisconnect:
        logger.info("WebSocket desconectado normalmente — sessao=%s", sessao_id)
    except Exception as exc:
        logger.warning("WebSocket encerrado com erro — sessao=%s erro=%s", sessao_id, exc)
    finally:
        manager.disconnect(websocket, sessao_id)
