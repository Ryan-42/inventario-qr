from __future__ import annotations

import hmac
import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.sessao import StatusSessao
from app.repositories import sessao_repo, grupo_repo
from app.websockets.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])

# Close code 4401: não autenticado (RFC 6455 permite 4000–4999 para uso da aplicação)
_WS_CLOSE_UNAUTHORIZED = 4401


def _token_ws_valido(sessao, token: str, db: Session) -> bool:
    """Retorna True se o token é válido para o WebSocket da sessão."""
    if not token:
        return False
    if hmac.compare_digest(sessao.token_acesso or "", token):
        return True
    if sessao.token_supervisor and hmac.compare_digest(sessao.token_supervisor, token):
        return True
    from app.models.admin import Admin
    from app.auth import _SECRET_KEY, _ALGORITHM
    try:
        from jose import jwt as _jwt, JWTError
        payload = _jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
        if payload.get("sub"):
            return True
    except Exception:
        pass
    grupo = grupo_repo.buscar_grupo_por_token(db, sessao.id, token)
    return grupo is not None


@router.websocket("/sessao/{sessao_id}")
async def websocket_sessao(websocket: WebSocket, sessao_id: str,
                           token: str = "",
                           db: Session = Depends(get_db)) -> None:
    """
    Endpoint WebSocket para atualizações em tempo real de uma sessão.
    Rejeita conexões sem token válido (4401) e sessões inexistentes (4404).
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

    if sessao.status == StatusSessao.cancelada:
        await websocket.close(code=4409, reason="Sessão cancelada")
        return

    if not _token_ws_valido(sessao, token, db):
        await websocket.close(code=_WS_CLOSE_UNAUTHORIZED, reason="Token ausente ou inválido")
        logger.warning("WS rejeitado — token inválido sessao=%s", sessao_id)
        return

    connected = await manager.connect(websocket, sessao_id)
    if not connected:
        return
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
