"""
Endpoints empresariais: trilha de auditoria, comparação entre sessões e estatísticas consolidadas.
"""
from __future__ import annotations
from app.auth import get_admin_logado

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import sessao_repo, item_repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessoes", tags=["Auditoria & Empresa"], dependencies=[Depends(get_admin_logado)])


# ── Trilha de Auditoria ───────────────────────────────────────────────────────

@router.get("/{sessao_id}/auditoria")
def trilha_auditoria(
    sessao_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    codigo: str | None = Query(default=None),
    operador: str | None = Query(default=None),
    apenas_divergencias: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    """
    Trilha de auditoria completa da sessão — todas as ações de contagem com detalhes.
    Exportável para conformidade e auditoria fiscal.
    Filtrável por código de item, operador e apenas divergências.
    """
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    # Filtros aplicados no SQL ANTES da paginação — aplicá-los depois produzia
    # páginas incompletas e total_registros/tem_mais incorretos.
    historico = item_repo.listar_historico(
        db, sessao_id, codigo=codigo, limit=limit + 1, offset=offset,
        operador=operador, apenas_divergencias=apenas_divergencias,
    )

    tem_mais = len(historico) > limit
    historico = historico[:limit]

    registros = []
    for h in historico:
        registros.append({
            "id": h.id,
            "codigo": h.codigo,
            "rodada": h.rodada,
            "quantidade_base": h.quantidade_base,
            "quantidade_encontrada": h.quantidade_encontrada,
            "diferenca": h.quantidade_encontrada - h.quantidade_base if h.quantidade_encontrada is not None else None,
            "divergencia": h.divergencia,
            "para_ajuste": h.para_ajuste,
            "operador": h.operador or "—",
            "observacao": h.observacao,
            "timestamp": h.timestamp.isoformat() if h.timestamp else None,
            "acao": _classificar_acao(h),
        })

    return {
        "sessao_id": sessao_id,
        "sessao_nome": sessao.nome,
        "total_registros": len(registros),
        "tem_mais": tem_mais,
        "offset": offset,
        "limit": limit,
        "registros": registros,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }


def _classificar_acao(h) -> str:
    if h.para_ajuste:
        return "CONFIRMADO_PARA_AJUSTE"
    if h.divergencia:
        return "DIVERGENCIA_REGISTRADA"
    return "CONTAGEM_OK"


# ── Comparação entre Sessões ──────────────────────────────────────────────────

@router.get("/{sessao_id}/comparar/{sessao_ref_id}")
def comparar_sessoes(
    sessao_id: str,
    sessao_ref_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Compara duas sessões de inventário: atual vs referência.
    Identifica itens que melhoraram, pioraram ou se mantiveram entre inventários.
    Útil para trend analysis e auditoria cruzada.
    """
    sessao_atual = sessao_repo.buscar_sessao(db, sessao_id)
    sessao_ref = sessao_repo.buscar_sessao(db, sessao_ref_id)

    if not sessao_atual:
        raise HTTPException(status_code=404, detail="Sessão atual não encontrada")
    if not sessao_ref:
        raise HTTPException(status_code=404, detail="Sessão de referência não encontrada")


    from app.services.sessao_service import montar_inventario_completo
    itens_atual = {i["codigo"]: i for i in montar_inventario_completo(db, sessao_id)}
    itens_ref = {i["codigo"]: i for i in montar_inventario_completo(db, sessao_ref_id)}

    codigos_comuns = set(itens_atual.keys()) & set(itens_ref.keys())
    so_atual = set(itens_atual.keys()) - set(itens_ref.keys())
    so_ref = set(itens_ref.keys()) - set(itens_atual.keys())

    melhoraram, pioraram, mantiveram, novos_problemas = [], [], [], []

    for cod in codigos_comuns:
        a = itens_atual[cod]
        r = itens_ref[cod]
        status_a = str(a.get("status", ""))
        status_r = str(r.get("status", ""))

        if status_r == "Divergente" and status_a not in ("Divergente", "Para Ajuste"):
            melhoraram.append(_resumo_item(a, r))
        elif status_r not in ("Divergente", "Para Ajuste") and status_a == "Divergente":
            pioraram.append(_resumo_item(a, r))
        elif status_a == "Divergente" and status_r == "Divergente":
            novos_problemas.append(_resumo_item(a, r))
        else:
            mantiveram.append(cod)

    stats_atual = sessao_repo.stats_sessao(db, sessao_id)
    stats_ref = sessao_repo.stats_sessao(db, sessao_ref_id)

    taxa_div_atual = round(
        stats_atual["divergencias"] / stats_atual["conferidos"] * 100, 1
    ) if stats_atual["conferidos"] > 0 else 0.0
    taxa_div_ref = round(
        stats_ref["divergencias"] / stats_ref["conferidos"] * 100, 1
    ) if stats_ref["conferidos"] > 0 else 0.0

    return {
        "sessao_atual": {"id": sessao_id, "nome": sessao_atual.nome, "codigo": sessao_atual.codigo},
        "sessao_referencia": {"id": sessao_ref_id, "nome": sessao_ref.nome, "codigo": sessao_ref.codigo},
        "resumo": {
            "itens_em_comum": len(codigos_comuns),
            "apenas_atual": len(so_atual),
            "apenas_referencia": len(so_ref),
            "melhoraram": len(melhoraram),
            "pioraram": len(pioraram),
            "persistem_divergentes": len(novos_problemas),
            "sem_mudanca": len(mantiveram),
            "taxa_divergencia_atual_pct": taxa_div_atual,
            "taxa_divergencia_referencia_pct": taxa_div_ref,
            "variacao_taxa_pct": round(taxa_div_atual - taxa_div_ref, 1),
        },
        "itens_que_melhoraram": melhoraram,
        "itens_que_pioraram": pioraram,
        "itens_persistem_divergentes": novos_problemas,
        "codigos_so_nesta_sessao": sorted(so_atual)[:50],
        "codigos_so_na_referencia": sorted(so_ref)[:50],
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }


def _resumo_item(atual: dict, ref: dict) -> dict:
    return {
        "codigo": atual.get("codigo"),
        "produto": atual.get("produto"),
        "status_atual": atual.get("status"),
        "status_anterior": ref.get("status"),
        "diferenca_atual": atual.get("diferenca"),
        "diferenca_anterior": ref.get("diferenca"),
    }


# ── Estatísticas Consolidadas ─────────────────────────────────────────────────

@router.get("/{sessao_id}/relatorio-operadores")
def relatorio_operadores(
    sessao_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Relatório detalhado por operador: produtividade, precisão e divergências.
    Ideal para avaliação de desempenho e treinamento.
    """
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    historico = item_repo.listar_historico(db, sessao_id, limit=10_000)
    contagens = item_repo.listar_contagens(db, sessao_id)

    # Agrupa por operador
    from collections import defaultdict
    ops: dict = defaultdict(lambda: {
        "total_tentativas": 0,
        "itens_unicos": set(),
        "divergencias": 0,
        "para_ajuste": 0,
        "ok": 0,
        "timestamps": [],
    })

    for h in historico:
        op = h.operador or "Sem operador"
        ops[op]["total_tentativas"] += 1
        ops[op]["itens_unicos"].add(h.codigo)
        if h.divergencia:
            ops[op]["divergencias"] += 1
        if h.para_ajuste:
            ops[op]["para_ajuste"] += 1
        if not h.divergencia:
            ops[op]["ok"] += 1
        if h.timestamp:
            ops[op]["timestamps"].append(h.timestamp)

    resultado = []
    for op, dados in ops.items():
        total = dados["total_tentativas"]
        itens_u = len(dados["itens_unicos"])
        taxa_divergencia = round(dados["divergencias"] / total * 100, 1) if total > 0 else 0.0
        taxa_precisao = round(dados["ok"] / total * 100, 1) if total > 0 else 0.0

        primeiro = min(dados["timestamps"]) if dados["timestamps"] else None
        ultimo = max(dados["timestamps"]) if dados["timestamps"] else None
        duracao_min = None
        itens_por_min = None
        if primeiro and ultimo:
            delta = (ultimo - primeiro).total_seconds() / 60
            duracao_min = round(delta, 1)
            if delta > 0:
                itens_por_min = round(itens_u / delta, 2)

        resultado.append({
            "operador": op,
            "total_tentativas": total,
            "itens_unicos": itens_u,
            "contagens_ok": dados["ok"],
            "divergencias": dados["divergencias"],
            "para_ajuste": dados["para_ajuste"],
            "taxa_divergencia_pct": taxa_divergencia,
            "taxa_precisao_pct": taxa_precisao,
            "primeiro_registro": primeiro.isoformat() if primeiro else None,
            "ultimo_registro": ultimo.isoformat() if ultimo else None,
            "duracao_minutos": duracao_min,
            "itens_por_minuto": itens_por_min,
        })

    resultado.sort(key=lambda x: x["taxa_precisao_pct"], reverse=True)

    return {
        "sessao_id": sessao_id,
        "sessao_nome": sessao.nome,
        "total_operadores": len(resultado),
        "operadores": resultado,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }
