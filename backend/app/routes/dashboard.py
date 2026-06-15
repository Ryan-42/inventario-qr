"""
Dashboard gerencial — visão consolidada de todas as sessões.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.database import get_db
from app.models.sessao import Sessao, StatusSessao
from app.models.contagem import Contagem, HistoricoContagem
from app.models.item_base import ItemBase

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/resumo")
def resumo_geral(db: Session = Depends(get_db)) -> dict:
    """
    KPIs gerais: totais de sessões, itens, divergências e taxa de acerto.
    """
    total_sessoes = db.query(func.count(Sessao.id)).scalar() or 0
    ativas = db.query(func.count(Sessao.id)).filter(Sessao.status == StatusSessao.ativa).scalar() or 0
    concluidas = db.query(func.count(Sessao.id)).filter(Sessao.status == StatusSessao.concluida).scalar() or 0
    canceladas = db.query(func.count(Sessao.id)).filter(Sessao.status == StatusSessao.cancelada).scalar() or 0

    total_itens = db.query(func.count(ItemBase.id)).scalar() or 0
    total_contagens = db.query(func.count(Contagem.id)).scalar() or 0
    total_divergencias = db.query(func.count(Contagem.id)).filter(Contagem.divergencia == True).scalar() or 0  # noqa: E712
    para_ajuste = db.query(func.count(Contagem.id)).filter(Contagem.para_ajuste == True).scalar() or 0  # noqa: E712

    taxa_acerto = round(
        ((total_contagens - total_divergencias) / total_contagens * 100) if total_contagens else 0,
        1,
    )

    # Sessão mais recente
    ultima = db.query(Sessao).order_by(Sessao.data_inicio.desc()).first()

    return {
        "sessoes": {
            "total": total_sessoes,
            "ativas": ativas,
            "concluidas": concluidas,
            "canceladas": canceladas,
        },
        "itens": {
            "total_base": total_itens,
            "total_contados": total_contagens,
            "divergentes": total_divergencias,
            "para_ajuste": para_ajuste,
        },
        "taxa_acerto_pct": taxa_acerto,
        "ultima_sessao": {
            "id": ultima.id,
            "nome": ultima.nome,
            "status": ultima.status,
            "data_inicio": ultima.data_inicio.isoformat() if ultima.data_inicio else None,
        } if ultima else None,
    }


@router.get("/tendencias")
def tendencias(
    ultimas_n: int = Query(default=10, ge=2, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """
    Taxa de acerto e total de divergências das últimas N sessões concluídas.
    Usado para o gráfico de linha do dashboard.
    """
    sessoes = (
        db.query(Sessao)
        .filter(Sessao.status == StatusSessao.concluida)
        .order_by(Sessao.data_fim.desc())
        .limit(ultimas_n)
        .all()
    )
    sessoes = list(reversed(sessoes))  # cronológico

    pontos = []
    for s in sessoes:
        total = db.query(func.count(Contagem.id)).filter(Contagem.sessao_id == s.id).scalar() or 0
        divs = db.query(func.count(Contagem.id)).filter(
            Contagem.sessao_id == s.id, Contagem.divergencia == True  # noqa: E712
        ).scalar() or 0
        taxa = round(((total - divs) / total * 100) if total else 0, 1)
        pontos.append({
            "sessao_id": s.id,
            "sessao_nome": s.nome,
            "data": s.data_fim.isoformat() if s.data_fim else s.data_inicio.isoformat(),
            "total_itens": total,
            "divergencias": divs,
            "taxa_acerto_pct": taxa,
        })

    return {"pontos": pontos, "total_sessoes": len(pontos)}


@router.get("/top-itens-problematicos")
def top_itens_problematicos(
    limite: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """
    Itens que mais geram divergências ao longo de todas as sessões.
    """
    rows = (
        db.query(
            HistoricoContagem.codigo,
            func.count(HistoricoContagem.id).label("total_contagens"),
            func.sum(case((HistoricoContagem.divergencia == True, 1), else_=0)).label("total_divergencias"),
        )
        .group_by(HistoricoContagem.codigo)
        .having(func.sum(case((HistoricoContagem.divergencia == True, 1), else_=0)) > 0)
        .order_by(func.sum(case((HistoricoContagem.divergencia == True, 1), else_=0)).desc())
        .limit(limite)
        .all()
    )

    # Busca nome mais recente de cada código
    codigos = [r.codigo for r in rows]
    nomes_map: dict[str, str] = {}
    if codigos:
        itens = db.query(ItemBase.codigo, ItemBase.produto).filter(ItemBase.codigo.in_(codigos)).all()
        for it in itens:
            nomes_map.setdefault(it.codigo, it.produto)

    items_list = []
    for r in rows:
        total = r.total_contagens or 0
        divs = int(r.total_divergencias or 0)
        items_list.append({
            "codigo": r.codigo,
            "produto": nomes_map.get(r.codigo, "—"),
            "total_contagens": total,
            "total_divergencias": divs,
            "taxa_divergencia_pct": round(divs / total * 100, 1) if total else 0,
        })

    return {"itens": items_list}


@router.get("/operadores")
def ranking_operadores(
    db: Session = Depends(get_db),
) -> dict:
    """
    Ranking de operadores por taxa de acerto consolidada em todas as sessões.
    """
    rows = (
        db.query(
            HistoricoContagem.operador,
            func.count(HistoricoContagem.id).label("total"),
            func.sum(case((HistoricoContagem.divergencia == True, 1), else_=0)).label("divergencias"),
        )
        .filter(HistoricoContagem.operador != None)  # noqa: E711
        .group_by(HistoricoContagem.operador)
        .order_by(func.count(HistoricoContagem.id).desc())
        .all()
    )

    operadores = []
    for r in rows:
        total = r.total or 0
        divs = int(r.divergencias or 0)
        operadores.append({
            "operador": r.operador,
            "total_contagens": total,
            "divergencias": divs,
            "taxa_acerto_pct": round((total - divs) / total * 100, 1) if total else 0,
        })

    return {"operadores": operadores}


@router.get("/sessoes-recentes")
def sessoes_recentes(
    limite: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> dict:
    """
    Últimas N sessões com seus KPIs básicos para o painel lateral.
    """
    sessoes = (
        db.query(Sessao)
        .order_by(Sessao.data_inicio.desc())
        .limit(limite)
        .all()
    )

    resultado = []
    for s in sessoes:
        total_base = db.query(func.count(ItemBase.id)).filter(ItemBase.sessao_id == s.id).scalar() or 0
        total_cont = db.query(func.count(Contagem.id)).filter(Contagem.sessao_id == s.id).scalar() or 0
        divs = db.query(func.count(Contagem.id)).filter(
            Contagem.sessao_id == s.id, Contagem.divergencia == True  # noqa: E712
        ).scalar() or 0
        progresso = round(total_cont / total_base * 100, 0) if total_base else 0
        resultado.append({
            "id": s.id,
            "nome": s.nome,
            "codigo": s.codigo,
            "status": str(s.status.value if hasattr(s.status, "value") else s.status),
            "data_inicio": s.data_inicio.isoformat() if s.data_inicio else None,
            "data_fim": s.data_fim.isoformat() if s.data_fim else None,
            "total_itens": total_base,
            "itens_contados": total_cont,
            "divergencias": divs,
            "progresso_pct": progresso,
        })

    return {"sessoes": resultado}
