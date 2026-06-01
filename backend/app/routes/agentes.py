from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.validation import ValidationAgent
from app.agents.analise import AnaliseAgent
from app.agents.chat import InventarioChatAgent
from app.agents.alerta import AlertaAgent
from app.database import get_db
from app.limiter import limiter
from app.repositories import sessao_repo, item_repo
from app.services.sessao_service import montar_divergencias, montar_inventario_completo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agentes", tags=["Agentes IA"])

_validation_agent = ValidationAgent()
_analise_agent = AnaliseAgent()
_chat_agent = InventarioChatAgent()
_alerta_agent = AlertaAgent()


class ValidarItemsRequest(BaseModel):
    items: list[dict[str, Any]]


class ChatRequest(BaseModel):
    mensagem: str
    historico: list[dict[str, Any]] = []


class AlertaRequest(BaseModel):
    codigo: str
    quantidade_encontrada: int
    quantidade_base: int
    operador: str | None = None


@router.post("/validar")
@limiter.limit("30/minute")
def validar_items(request: Request, payload: ValidarItemsRequest) -> dict:
    """Valida lista de itens antes do import (com ou sem IA)."""
    if not isinstance(payload.items, list):
        raise HTTPException(status_code=422, detail="'items' deve ser uma lista")
    try:
        return _validation_agent.validate(payload.items)
    except Exception as exc:
        logger.error("Falha no ValidationAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno na validação.") from exc


@router.post("/analisar-sessao/{sessao_id}")
@limiter.limit("20/minute")
def analisar_sessao(request: Request, sessao_id: str, db: Session = Depends(get_db)) -> dict:
    """Analisa sessão de inventário com IA e retorna insights acionáveis."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    try:
        stats = sessao_repo.stats_sessao(db, sessao_id)
        divergencias = montar_divergencias(db, sessao_id)
        itens_sample = montar_inventario_completo(db, sessao_id)
        valor_estoque = sessao_repo.calcular_valor_estoque(db, sessao_id)
        return _analise_agent.analisar(sessao, stats, divergencias, itens_sample, valor_estoque)
    except Exception as exc:
        logger.error("Falha no AnaliseAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno na análise.") from exc


@router.post("/chat/{sessao_id}")
@limiter.limit("30/minute")
def chat_sessao(request: Request, sessao_id: str, payload: ChatRequest, db: Session = Depends(get_db)) -> dict:
    """Chat em linguagem natural sobre a sessão — responde perguntas sobre o inventário."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    try:
        stats = sessao_repo.stats_sessao(db, sessao_id)
        divergencias = montar_divergencias(db, sessao_id)
        itens = montar_inventario_completo(db, sessao_id)
        contagens_raw = item_repo.listar_contagens(db, sessao_id)
        contagens = [
            {
                "codigo": c.codigo,
                "divergencia": c.divergencia,
                "operador": c.operador,
                "timestamp": c.timestamp.isoformat() if c.timestamp else None,
            }
            for c in contagens_raw
        ]

        # Build rodadas_info for chat context
        rodada_maxima = max((c.rodada for c in contagens_raw), default=0)
        rodadas_info: dict = {
            "rodada_maxima": rodada_maxima,
            "itens_segunda": [],
            "itens_terceira": [],
        }
        itens_map = {i["codigo"]: i for i in itens}
        for c in contagens_raw:
            rodada = getattr(c, "rodada", 1) or 1
            if rodada == 1 and c.divergencia:
                item = itens_map.get(c.codigo)
                rodadas_info["itens_segunda"].append({
                    "codigo": c.codigo,
                    "produto": item.get("produto", c.codigo) if item else c.codigo,
                })
            elif rodada == 2 and c.divergencia:
                item = itens_map.get(c.codigo)
                rodadas_info["itens_terceira"].append({
                    "codigo": c.codigo,
                    "produto": item.get("produto", c.codigo) if item else c.codigo,
                })

        return _chat_agent.responder(
            sessao=sessao,
            stats=stats,
            divergencias=divergencias,
            itens=itens,
            contagens=contagens,
            mensagem=payload.mensagem,
            historico=payload.historico,
            rodadas_info=rodadas_info,
        )
    except Exception as exc:
        logger.error("Falha no ChatAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno no chat.") from exc


@router.post("/alerta/{sessao_id}")
@limiter.limit("60/minute")
def alerta_sessao(request: Request, sessao_id: str, payload: AlertaRequest, db: Session = Depends(get_db)) -> dict:
    """Detecta anomalias em tempo real após cada contagem."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    try:
        contagens_raw = item_repo.listar_contagens(db, sessao_id)
        contagens = [
            {
                "codigo": c.codigo,
                "divergencia": c.divergencia,
                "operador": c.operador,
            }
            for c in contagens_raw
        ]
        return _alerta_agent.analisar(
            codigo=payload.codigo,
            quantidade_encontrada=payload.quantidade_encontrada,
            quantidade_base=payload.quantidade_base,
            operador=payload.operador,
            contagens=contagens,
        )
    except Exception as exc:
        logger.error("Falha no AlertaAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno no alerta.") from exc
