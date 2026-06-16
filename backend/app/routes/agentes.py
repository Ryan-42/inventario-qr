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
from app.agents.preditor import PredictionAgent
from app.agents.antifraude import AntiFraudeAgent
from app.agents.sync_erp import SyncERPAgent
from app.agents.sop_coach import SopCoachAgent
from app.agents.plano_acao import PlanoAcaoAgent
from app.auth import get_admin_logado
from app.database import get_db
from app.limiter import limiter
from app.repositories import sessao_repo, item_repo
from app.services.sessao_service import montar_divergencias, montar_inventario_completo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agentes", tags=["Agentes IA"], dependencies=[Depends(get_admin_logado)])

_validation_agent = ValidationAgent()
_analise_agent = AnaliseAgent()
_alerta_agent = AlertaAgent()
_relatorio_agent = RelatorioExecutivoAgent()
_ajuste_agent = RecomendacaoAjusteAgent()
_prediction_agent = PredictionAgent()
_antifraude_agent = AntiFraudeAgent()
_sync_erp_agent = SyncERPAgent()
_sop_coach_agent = SopCoachAgent()
_plano_acao_agent = PlanoAcaoAgent()


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


# ---------------------------------------------------------------------------
# Novos Agentes Integrados (SaaS / Groq)
# ---------------------------------------------------------------------------

class ERPConfigRequest(BaseModel):
    erp_nome: str


class SopChatRequest(BaseModel):
    mensagens: list[dict[str, Any]]
    contexto_extra: str | None = None


@router.post("/predicao/{sessao_id}")
@limiter.limit("20/minute")
def prever_sessao(request: Request, sessao_id: str, db: Session = Depends(get_db)) -> dict:
    """Previsão preventiva de riscos e tempo estimado para a sessão."""
    try:
        return _prediction_agent.prever(sessao_id, db)
    except Exception as exc:
        logger.error("Falha no PredictionAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno no PredictionAgent.") from exc


@router.post("/antifraude/{sessao_id}")
@limiter.limit("20/minute")
def auditar_fraude_sessao(request: Request, sessao_id: str, db: Session = Depends(get_db)) -> dict:
    """Auditoria comportamental de operadores para detecção de fraudes."""
    try:
        return _antifraude_agent.auditar(sessao_id, db)
    except Exception as exc:
        logger.error("Falha no AntiFraudeAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno no AntiFraudeAgent.") from exc


@router.post("/sync-erp/{sessao_id}")
@limiter.limit("20/minute")
def conciliar_erp_sessao(request: Request, sessao_id: str, payload: ERPConfigRequest, db: Session = Depends(get_db)) -> dict:
    """Traduz os ajustes de estoque confirmados em um payload pronto para conciliação no ERP."""
    try:
        return _sync_erp_agent.conciliar(sessao_id, payload.erp_nome, db)
    except Exception as exc:
        logger.error("Falha no SyncERPAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno no SyncERPAgent.") from exc


@router.post("/sop-coach/{sessao_id}")
@limiter.limit("40/minute")
def responder_operador(request: Request, sessao_id: str, payload: SopChatRequest) -> dict:
    """Chatbot de suporte operacional para orientar operadores sobre POPs do depósito."""
    try:
        return _sop_coach_agent.responder(payload.mensagens, payload.contexto_extra)
    except Exception as exc:
        logger.error("Falha no SopCoachAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno no SopCoachAgent.") from exc


@router.post("/plano-acao/{sessao_id}")
@limiter.limit("20/minute")
def gerar_plano_acao_sessao(request: Request, sessao_id: str, db: Session = Depends(get_db)) -> dict:
    """Gera um plano de ação estruturado 5W2H pós-inventário para melhoria contínua."""
    try:
        return _plano_acao_agent.gerar_plano(sessao_id, db)
    except Exception as exc:
        logger.error("Falha no PlanoAcaoAgent: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno no PlanoAcaoAgent.") from exc
