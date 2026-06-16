from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, case, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.contagem import Contagem, HistoricoContagem
from app.models.item_base import ItemBase
from app.models.sessao import Sessao, StatusSessao


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


def criar_sessao(
    db: Session,
    nome: str,
    webhook_url: str | None = None,
    filial_id: str | None = None,
) -> Sessao:
    # Retry loop: em caso de race condition (dois requests simultâneos gerando o mesmo código),
    # o segundo recebe IntegrityError e tenta novamente com o próximo número disponível.
    for _ in range(5):
        try:
            codigo = gerar_codigo_sessao(db)
            sessao = Sessao(nome=nome, codigo=codigo, webhook_url=webhook_url, filial_id=filial_id)
            db.add(sessao)
            db.commit()
            db.refresh(sessao)
            return sessao
        except IntegrityError:
            db.rollback()
    raise HTTPException(status_code=409, detail="Conflito ao gerar código de sessão. Tente novamente.")


def listar_sessoes(db: Session) -> list[Sessao]:
    return db.query(Sessao).order_by(Sessao.data_inicio.desc()).all()


def listar_sessoes_com_stats(db: Session) -> list[dict]:
    from sqlalchemy import case
    # O JOIN duplo (ItemBase + Contagem via sessao_id) cria um produto cartesiano.
    # Para evitar over-count, usamos COUNT(DISTINCT id) em todos os campos agregados.
    # COUNT(DISTINCT CASE(condition, id)) conta IDs únicos que satisfazem a condição.
    rows = (
        db.query(
            Sessao,
            func.count(func.distinct(ItemBase.id)).label("total_itens"),
            func.count(func.distinct(Contagem.id)).label("itens_contados"),
            func.count(func.distinct(case((Contagem.divergencia == True, Contagem.id)))).label("total_divergencias"),  # noqa
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
            "webhook_url": sessao.webhook_url,
            "filial_id": sessao.filial_id,
            "total_itens": total_itens or 0,
            "itens_contados": itens_contados or 0,
            "total_divergencias": int(total_divergencias or 0),
        }
        result.append(d)
    return result


def buscar_sessao(db: Session, sessao_id: str) -> Optional[Sessao]:
    return db.query(Sessao).filter(Sessao.id == sessao_id).first()


def buscar_sessao_com_stats(db: Session, sessao_id: str) -> Optional[dict]:
    """Busca uma sessão por ID com stats calculadas via SQL — O(1) ao contrário de listar_todas."""
    from sqlalchemy import case
    row = (
        db.query(
            Sessao,
            func.count(func.distinct(ItemBase.id)).label("total_itens"),
            func.count(func.distinct(Contagem.id)).label("itens_contados"),
            func.count(func.distinct(case((Contagem.divergencia == True, Contagem.id)))).label("total_divergencias"),  # noqa
        )
        .filter(Sessao.id == sessao_id)
        .outerjoin(ItemBase, ItemBase.sessao_id == Sessao.id)
        .outerjoin(Contagem, Contagem.sessao_id == Sessao.id)
        .group_by(Sessao.id)
        .first()
    )
    if not row:
        return None
    sessao, total_itens, itens_contados, total_divergencias = row
    return {
        "id": sessao.id,
        "codigo": sessao.codigo,
        "nome": sessao.nome,
        "status": sessao.status,
        "data_inicio": sessao.data_inicio,
        "data_fim": sessao.data_fim,
        "webhook_url": sessao.webhook_url,
        "filial_id": sessao.filial_id,
        "total_itens": total_itens or 0,
        "itens_contados": itens_contados or 0,
        "total_divergencias": int(total_divergencias or 0),
    }


def concluir_sessao(db: Session, sessao_id: str) -> Optional[Sessao]:
    from sqlalchemy import update as sa_update
    # UPDATE atômico: só transiciona se ainda estava 'ativa' no momento do lock.
    # Evita race condition entre dois workers tentando concluir ao mesmo tempo.
    rowcount = db.execute(
        sa_update(Sessao)
        .where(Sessao.id == sessao_id, Sessao.status == StatusSessao.ativa)
        .values(status=StatusSessao.concluida, data_fim=datetime.now(timezone.utc))
    ).rowcount
    db.commit()
    if rowcount == 0:
        return None
    return buscar_sessao(db, sessao_id)


def cancelar_sessao(db: Session, sessao_id: str) -> Optional[Sessao]:
    from sqlalchemy import update as sa_update
    # UPDATE atômico: só cancela sessões ativas ou pausadas.
    rowcount = db.execute(
        sa_update(Sessao)
        .where(
            Sessao.id == sessao_id,
            Sessao.status.in_([StatusSessao.ativa, StatusSessao.pausada]),
        )
        .values(status=StatusSessao.cancelada, data_fim=datetime.now(timezone.utc))
    ).rowcount
    db.commit()
    if rowcount == 0:
        return None
    return buscar_sessao(db, sessao_id)


def deletar_sessao(db: Session, sessao_id: str) -> bool:
    sessao = buscar_sessao(db, sessao_id)
    if not sessao:
        return False
    db.delete(sessao)
    db.commit()
    return True


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


def calcular_metricas_sessao(db: Session, sessao_id: str) -> dict:
    """
    Deriva KPIs de produtividade, retrabalho e rastreabilidade dos dados já existentes.

    Retorna:
      duracao_minutos        — tempo total da sessão em minutos (data_fim ou now)
      itens_por_minuto       — total de registros no histórico / duração
      taxa_divergencia_pct   — itens divergentes / total_itens * 100
      taxa_retrabalho_pct    — (entradas no histórico - itens únicos no histórico) / total_itens * 100
      pct_rastreabilidade    — contagens com operador preenchido / total_contagens * 100
      por_operador           — lista de {operador, contagens, itens_unicos, primeiro, ultimo,
                               duracao_min, itens_por_minuto}
    """
    sessao = buscar_sessao(db, sessao_id)
    if not sessao:
        return {}

    inicio = sessao.data_inicio
    fim = sessao.data_fim or datetime.now(timezone.utc)
    if inicio and inicio.tzinfo is None:
        inicio = inicio.replace(tzinfo=timezone.utc)
    if fim and fim.tzinfo is None:
        fim = fim.replace(tzinfo=timezone.utc)

    duracao_seg = (fim - inicio).total_seconds() if inicio else 0
    duracao_min = round(duracao_seg / 60, 2) if duracao_seg > 0 else 0

    # Contagens atuais (estado final de cada item)
    contagens = db.query(Contagem).filter(Contagem.sessao_id == sessao_id).all()
    total_itens = db.query(ItemBase).filter(ItemBase.sessao_id == sessao_id).count()
    total_contagens = len(contagens)

    divs = sum(1 for c in contagens if c.divergencia)
    taxa_divergencia = round(divs / total_itens * 100, 2) if total_itens > 0 else 0.0

    # Rastreabilidade: contagens com operador preenchido
    com_operador = sum(1 for c in contagens if c.operador)
    pct_rastreabilidade = round(com_operador / total_contagens * 100, 2) if total_contagens > 0 else 0.0

    # Histórico: cada tentativa individual
    historico = db.query(HistoricoContagem).filter(HistoricoContagem.sessao_id == sessao_id).all()
    total_hist = len(historico)
    codigos_unicos_hist = len({h.codigo for h in historico})

    # Retrabalho = tentativas além da 1ª por item / total_itens contados
    # (itens com mais de 1 entrada no histórico indicam recontagem)
    retrabalho_abs = total_hist - codigos_unicos_hist  # tentativas extras
    taxa_retrabalho = round(retrabalho_abs / total_itens * 100, 2) if total_itens > 0 else 0.0

    # itens/min usando total de registros no histórico (cada scan conta)
    itens_por_minuto = round(total_hist / duracao_min, 2) if duracao_min > 0 else 0.0

    # Breakdown por operador (agrupa histórico por operador)
    op_hist: dict[str, list] = defaultdict(list)
    for h in historico:
        op = h.operador or "(sem operador)"
        op_hist[op].append(h)

    por_operador = []
    for op, registros in sorted(op_hist.items()):
        # normaliza timestamps para timezone-aware
        ts_list = [
            r.timestamp.replace(tzinfo=timezone.utc) if r.timestamp and r.timestamp.tzinfo is None else r.timestamp
            for r in registros if r.timestamp
        ]
        ts_list = [t for t in ts_list if t]
        primeiro = min(ts_list).isoformat() if ts_list else None
        ultimo = max(ts_list).isoformat() if ts_list else None
        dur_op = round((max(ts_list) - min(ts_list)).total_seconds() / 60, 2) if len(ts_list) >= 2 else 0.0
        itens_unicos_op = len({r.codigo for r in registros})
        ipm_op = round(len(registros) / dur_op, 2) if dur_op > 0 else None
        por_operador.append({
            "operador": op,
            "contagens": len(registros),
            "itens_unicos": itens_unicos_op,
            "primeiro_registro": primeiro,
            "ultimo_registro": ultimo,
            "duracao_minutos": dur_op,
            "itens_por_minuto": ipm_op,
        })

    return {
        "sessao_id": sessao_id,
        "sessao_codigo": sessao.codigo,
        "sessao_nome": sessao.nome,
        "status": sessao.status.value if sessao.status else None,
        "inicio": inicio.isoformat() if inicio else None,
        "fim": fim.isoformat() if fim else None,
        "duracao_minutos": duracao_min,
        "total_itens": total_itens,
        "total_contagens_atuais": total_contagens,
        "total_tentativas_historico": total_hist,
        "itens_por_minuto": itens_por_minuto,
        "taxa_divergencia_pct": taxa_divergencia,
        "divergencias_absolutas": divs,
        "taxa_retrabalho_pct": taxa_retrabalho,
        "retrabalho_absoluto": retrabalho_abs,
        "pct_rastreabilidade": pct_rastreabilidade,
        "contagens_com_operador": com_operador,
        "por_operador": por_operador,
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
