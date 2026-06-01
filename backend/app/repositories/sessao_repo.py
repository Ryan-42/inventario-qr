from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException

from app.models.sessao import Sessao, StatusSessao
from app.models.item_base import ItemBase
from app.models.contagem import Contagem


def gerar_codigo_sessao(db: Session) -> str:
    """Gera código único baseado no último código existente (evita race condition por count)."""
    ano = datetime.now().year
    ultima = (
        db.query(Sessao)
        .filter(Sessao.codigo.like(f"INV-{ano}-%"))
        .order_by(Sessao.codigo.desc())
        .first()
    )
    if ultima:
        try:
            ultimo_num = int(ultima.codigo.rsplit("-", 1)[-1])
        except ValueError:
            ultimo_num = 0
        proximo = ultimo_num + 1
    else:
        proximo = 1
    return f"INV-{ano}-{proximo:04d}"


def criar_sessao(db: Session, nome: str) -> Sessao:
    codigo = gerar_codigo_sessao(db)
    sessao = Sessao(nome=nome, codigo=codigo)
    db.add(sessao)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflito ao gerar código de sessão. Tente novamente.")
    db.refresh(sessao)
    return sessao


def listar_sessoes(db: Session) -> list[Sessao]:
    return db.query(Sessao).order_by(Sessao.data_inicio.desc()).all()


def listar_sessoes_com_stats(db: Session) -> list[dict]:
    from sqlalchemy import case
    rows = (
        db.query(
            Sessao,
            func.count(func.distinct(ItemBase.id)).label("total_itens"),
            func.count(func.distinct(Contagem.id)).label("itens_contados"),
            func.count(func.distinct(
                case((Contagem.divergencia == True, Contagem.id), else_=None)  # noqa
            )).label("total_divergencias"),
        )
        .outerjoin(ItemBase, ItemBase.sessao_id == Sessao.id)
        .outerjoin(Contagem, Contagem.sessao_id == Sessao.id)
        .group_by(Sessao.id)
        .order_by(Sessao.data_inicio.desc())
        .all()
    )
    result = []
    for sessao, total_itens, itens_contados, total_divergencias in rows:
        d = {
            "id": sessao.id,
            "codigo": sessao.codigo,
            "nome": sessao.nome,
            "status": sessao.status,
            "data_inicio": sessao.data_inicio,
            "data_fim": sessao.data_fim,
            "total_itens": total_itens or 0,
            "itens_contados": itens_contados or 0,
            "total_divergencias": int(total_divergencias or 0),
        }
        result.append(d)
    return result


def buscar_sessao(db: Session, sessao_id: str) -> Optional[Sessao]:
    return db.query(Sessao).filter(Sessao.id == sessao_id).first()


def concluir_sessao(db: Session, sessao_id: str) -> Optional[Sessao]:
    sessao = buscar_sessao(db, sessao_id)
    if sessao:
        sessao.status = StatusSessao.concluida
        sessao.data_fim = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sessao)
    return sessao


def cancelar_sessao(db: Session, sessao_id: str) -> Optional[Sessao]:
    sessao = buscar_sessao(db, sessao_id)
    if sessao:
        sessao.status = StatusSessao.cancelada
        sessao.data_fim = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sessao)
    return sessao


def calcular_valor_estoque(db: Session, sessao_id: str) -> dict:
    """
    Calcula o impacto financeiro do inventário.

    valor_inicial = soma de valor_estoque de todos os itens base
    valor_final   = soma de (qtd_encontrada × preço_unitário) para itens contados
                  + valor_estoque original para itens não contados

    preço_unitário = valor_estoque / quantidade_base
    """
    itens = db.query(ItemBase).filter(ItemBase.sessao_id == sessao_id).all()
    contagens_map = {
        c.codigo: c
        for c in db.query(Contagem).filter(Contagem.sessao_id == sessao_id).all()
    }

    valor_inicial = 0.0
    valor_final = 0.0
    itens_com_valor = 0
    itens_sem_valor = 0
    perdas = []
    ganhos = []

    for item in itens:
        if item.valor_estoque is None:
            itens_sem_valor += 1
            continue

        itens_com_valor += 1
        vi = float(item.valor_estoque)
        valor_inicial += vi

        # preço unitário calculado a partir do valor total
        # se quantidade_base == 0, não há como calcular preço unitário → usa vi como fallback
        if item.quantidade_base > 0:
            unit = vi / item.quantidade_base
        else:
            unit = None

        contagem = contagens_map.get(item.codigo)
        if contagem and unit is not None:
            vf_item = contagem.quantidade_encontrada * unit
        else:
            vf_item = vi  # não contado ou base=0 → mantém valor original

        valor_final += vf_item
        delta = round(vf_item - vi, 2)

        if abs(delta) > 0.01:
            entrada = {
                "codigo": item.codigo,
                "produto": item.produto,
                "local_fisico": item.local_fisico,
                "valor_base": round(vi, 2),
                "valor_final": round(vf_item, 2),
                "diferenca_valor": delta,
                "percentual_item": round(delta / vi * 100, 1) if vi > 0 else 0.0,
            }
            if delta < 0:
                perdas.append(entrada)
            else:
                ganhos.append(entrada)

    diferenca = round(valor_final - valor_inicial, 2)
    percentual = round(diferenca / valor_inicial * 100, 2) if valor_inicial > 0 else 0.0

    return {
        "valor_inicial": round(valor_inicial, 2),
        "valor_final": round(valor_final, 2),
        "diferenca": diferenca,
        "percentual_variacao": percentual,
        "itens_com_valor": itens_com_valor,
        "itens_sem_valor": itens_sem_valor,
        "maiores_perdas": sorted(perdas, key=lambda x: x["diferenca_valor"])[:5],
        "maiores_ganhos": sorted(ganhos, key=lambda x: x["diferenca_valor"], reverse=True)[:5],
        "tem_dados_financeiros": itens_com_valor > 0,
    }


def stats_sessao(db: Session, sessao_id: str) -> dict:
    row = (
        db.query(
            func.count(ItemBase.id).label("total"),
            func.count(Contagem.id).label("conferidos"),
            func.count(case((Contagem.divergencia == True, 1))).label("divergencias"),  # noqa
        )
        .select_from(ItemBase)
        .outerjoin(Contagem, and_(
            Contagem.sessao_id == ItemBase.sessao_id,
            Contagem.codigo == ItemBase.codigo,
        ))
        .filter(ItemBase.sessao_id == sessao_id)
        .one()
    )
    total, conferidos, divs = row
    pendentes = max(0, total - conferidos)
    percentual = round(conferidos / total * 100, 1) if total > 0 else 0.0
    return {
        "total": total,
        "conferidos": conferidos,
        "pendentes": pendentes,
        "divergencias": divs,
        "percentual": percentual,
    }
