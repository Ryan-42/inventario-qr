from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.validation import ValidationAgent
from app.agents.analise import AnaliseAgent
from app.agents.alerta import AlertaAgent
from app.agents.relatorio import RelatorioExecutivoAgent
from app.agents.ajuste import RecomendacaoAjusteAgent
from app.database import get_db
from app.limiter import limiter
from app.repositories import sessao_repo, item_repo
from app.services.sessao_service import montar_divergencias, montar_inventario_completo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agentes", tags=["Agentes IA"])

_validation_agent = ValidationAgent()
_analise_agent = AnaliseAgent()
_alerta_agent = AlertaAgent()
_relatorio_agent = RelatorioExecutivoAgent()
_ajuste_agent = RecomendacaoAjusteAgent()


class ValidarItemsRequest(BaseModel):
    items: list[dict[str, Any]]


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
        itens_sample = montar_inventario_completo(db, sessao_id)[:100]
        valor_estoque = sessao_repo.calcular_valor_estoque(db, sessao_id)
        metricas = sessao_repo.calcular_metricas_sessao(db, sessao_id)
        return _analise_agent.analisar(sessao, stats, divergencias[:50], itens_sample, valor_estoque, metricas)
    except Exception as exc:
        logger.error("Falha no AnaliseAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno na análise.") from exc


@router.post("/alerta/{sessao_id}")
@limiter.limit("60/minute")
def alerta_sessao(request: Request, sessao_id: str, payload: AlertaRequest, db: Session = Depends(get_db)) -> dict:
    """Detecta anomalias em tempo real após cada contagem."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    try:
        # Alerta agent precisa de todas as contagens para detectar padrões;
        # limitamos a 1000 para proteger contra sessões enormes
        contagens_raw = item_repo.listar_contagens(db, sessao_id, limit=1000)
        # Inclui local_fisico via join com ItemBase para habilitar alerta de local_critico
        itens_map = {
            i.codigo: i
            for i in item_repo.buscar_itens_por_codigos(
                db, sessao_id, list({c.codigo for c in contagens_raw})
            )
        }
        contagens = [
            {
                "codigo": c.codigo,
                "divergencia": c.divergencia,
                "operador": c.operador,
                "local_fisico": itens_map.get(c.codigo, None) and itens_map[c.codigo].local_fisico,
            }
            for c in contagens_raw
        ]
        item_atual = itens_map.get(payload.codigo)
        return _alerta_agent.analisar(
            codigo=payload.codigo,
            quantidade_encontrada=payload.quantidade_encontrada,
            quantidade_base=payload.quantidade_base,
            operador=payload.operador,
            valor_estoque_item=float(item_atual.valor_estoque) if item_atual and item_atual.valor_estoque else None,
            local_fisico_item=item_atual.local_fisico if item_atual else None,
            contagens=contagens,
        )
    except Exception as exc:
        logger.error("Falha no AlertaAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno no alerta.") from exc


# ---------------------------------------------------------------------------
# Relatório Executivo
# ---------------------------------------------------------------------------

@router.get("/relatorio-executivo/{sessao_id}")
@limiter.limit("10/minute")
async def relatorio_executivo(request: Request, sessao_id: str, db: Session = Depends(get_db)) -> dict:
    """
    Gera relatório executivo completo consolidando métricas, financeiro,
    ranking de operadores e divergências críticas — pronto para apresentação gerencial.
    """
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    try:
        stats = sessao_repo.stats_sessao(db, sessao_id)
        metricas = sessao_repo.calcular_metricas_sessao(db, sessao_id)
        valor_estoque = sessao_repo.calcular_valor_estoque(db, sessao_id)
        divergencias = montar_divergencias(db, sessao_id)
        return _relatorio_agent.gerar(sessao, stats, metricas, valor_estoque, divergencias)
    except Exception as exc:
        logger.error("Falha no RelatorioExecutivoAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao gerar relatório.") from exc


# ---------------------------------------------------------------------------
# Recomendação de Ajuste
# ---------------------------------------------------------------------------

class ItemHistoricoRequest(BaseModel):
    codigos: list[str]


@router.post("/recomendar-ajuste/{sessao_id}")
@limiter.limit("30/minute")
async def recomendar_ajuste(
    request: Request,
    sessao_id: str,
    payload: ItemHistoricoRequest,
    db: Session = Depends(get_db),
) -> dict:
    """
    Analisa o histórico de contagem dos itens informados e recomenda:
    'ajustar' | 'recontar' | 'investigar' — com justificativa e quantidade sugerida.

    Ideal para o supervisor decidir quais itens divergentes podem ser fechados como Para Ajuste.
    """
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if not payload.codigos:
        raise HTTPException(status_code=422, detail="Informe ao menos um código.")
    if len(payload.codigos) > 100:
        raise HTTPException(status_code=422, detail="Máximo de 100 itens por requisição.")
    try:
        codigos = list(set(payload.codigos))
        itens_base = {
            i.codigo: i
            for i in item_repo.buscar_itens_por_codigos(db, sessao_id, codigos)
        }
        contagens_map = {
            c.codigo: c
            for c in item_repo.listar_contagens(db, sessao_id, limit=10_000)
            if c.codigo in codigos
        }

        itens_historico = []
        for codigo in codigos:
            item = itens_base.get(codigo)
            contagem = contagens_map.get(codigo)
            hist_raw = item_repo.listar_historico(db, sessao_id, codigo)
            historico = [
                {
                    "quantidade": h.quantidade_encontrada,
                    "operador": h.operador,
                    "rodada": h.rodada,
                    "timestamp": h.timestamp.isoformat() if h.timestamp else None,
                }
                for h in hist_raw
            ]
            itens_historico.append({
                "codigo": codigo,
                "produto": item.produto if item else codigo,
                "quantidade_base": item.quantidade_base if item else 0,
                "valor_estoque": float(item.valor_estoque) if item and item.valor_estoque else None,
                "historico": historico,
                "rodada_atual": contagem.rodada if contagem else 1,
            })

        recomendacoes = _ajuste_agent.recomendar(itens_historico)
        return {
            "sessao_id": sessao_id,
            "total_itens": len(recomendacoes),
            "resumo": {
                "ajustar": sum(1 for r in recomendacoes if r["recomendacao"] == "ajustar"),
                "recontar": sum(1 for r in recomendacoes if r["recomendacao"] == "recontar"),
                "investigar": sum(1 for r in recomendacoes if r["recomendacao"] == "investigar"),
            },
            "recomendacoes": recomendacoes,
        }
    except Exception as exc:
        logger.error("Falha no RecomendacaoAjusteAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno na recomendação.") from exc
