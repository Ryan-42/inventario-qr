from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional

from app.models.item_base import ItemBase
from app.models.contagem import Contagem, HistoricoContagem
from app.config import MAX_RODADAS_DIVERGENCIA


# ── Items ────────────────────────────────────────────────────────────────────

def criar_itens_bulk(db: Session, sessao_id: str, itens: list[dict]) -> int:
    # Remove itens anteriores para permitir reimport sem duplicatas.
    # Contagens são preservadas (FK para sessao_id, não para item_id).
    db.query(ItemBase).filter(ItemBase.sessao_id == sessao_id).delete()
    objetos = []
    for item in itens:
        # Normaliza local_fisico: strip + uppercase para evitar duplicatas de apresentação
        local = item.get("local_fisico")
        if local:
            local = local.strip().upper()
        # valor_estoque deve ser positivo ou None
        valor = item.get("valor_estoque")
        if valor is not None and float(valor) < 0:
            valor = None
        objetos.append(ItemBase(
            sessao_id=sessao_id,
            codigo=item["codigo"],
            produto=item["produto"],
            quantidade_base=item["quantidade_base"],
            local_fisico=local,
            valor_estoque=valor,
        ))
    try:
        db.add_all(objetos)
        db.commit()
    except IntegrityError:
        db.rollback()
        from fastapi import HTTPException
        raise HTTPException(
            status_code=409,
            detail="Conflito ao importar planilha: dois ou mais itens com o mesmo código. Verifique duplicatas e tente novamente.",
        )
    return len(objetos)


def buscar_item(db: Session, sessao_id: str, codigo: str) -> Optional[ItemBase]:
    return db.query(ItemBase).filter(
        ItemBase.sessao_id == sessao_id,
        ItemBase.codigo == codigo
    ).first()


def listar_itens(db: Session, sessao_id: str) -> list[ItemBase]:
    return db.query(ItemBase).filter(ItemBase.sessao_id == sessao_id).all()


def contar_itens(db: Session, sessao_id: str) -> int:
    from sqlalchemy import func
    return db.query(func.count(ItemBase.id)).filter(ItemBase.sessao_id == sessao_id).scalar() or 0


def buscar_itens_por_codigos(db: Session, sessao_id: str, codigos: list[str]) -> list[ItemBase]:
    """Busca itens por lista de códigos — evita carregar toda a base para poucas linhas."""
    if not codigos:
        return []
    return db.query(ItemBase).filter(
        ItemBase.sessao_id == sessao_id,
        ItemBase.codigo.in_(codigos),
    ).all()


def listar_itens_para_operador(db: Session, sessao_id: str) -> list[dict]:
    """Retorna itens sem quantidade_base para contagem cega. Ordenado por local → código."""
    itens = listar_itens(db, sessao_id)
    codigos_contados = {
        row[0] for row in db.query(Contagem.codigo).filter(Contagem.sessao_id == sessao_id)
    }
    return sorted(
        [
            {
                "codigo": item.codigo,
                "produto": item.produto,
                "local_fisico": item.local_fisico,
                "ja_contado": item.codigo in codigos_contados,
            }
            for item in itens
        ],
        key=lambda i: (i["local_fisico"] or "\xff", i["codigo"]),
    )


# ── Contagens ─────────────────────────────────────────────────────────────────

def buscar_contagem(db: Session, sessao_id: str, codigo: str) -> Optional[Contagem]:
    # Upsert garante no máximo 1 contagem por (sessao_id, codigo) — sem ORDER BY necessário
    return db.query(Contagem).filter(
        Contagem.sessao_id == sessao_id,
        Contagem.codigo == codigo
    ).first()


def _buscar_contagem_para_update(db: Session, sessao_id: str, codigo: str) -> Optional[Contagem]:
    # FOR UPDATE: PostgreSQL serializa múltiplos workers que tentam atualizar o mesmo item
    # simultaneamente — o segundo worker aguarda o commit do primeiro antes de ler.
    # SQLite ignora silenciosamente (serialização já garantida pelo file lock).
    return db.query(Contagem).filter(
        Contagem.sessao_id == sessao_id,
        Contagem.codigo == codigo
    ).with_for_update().first()


def registrar_contagem(
    db: Session,
    sessao_id: str,
    codigo: str,
    quantidade_encontrada: int,
    quantidade_base: int,
    operador: Optional[str] = None,
    observacao: Optional[str] = None,
) -> Contagem:
    # Verifica que o item ainda existe — protege contra race condition onde
    # criar_itens_bulk() pode ter rodado entre a validação da route e aqui.
    if not buscar_item(db, sessao_id, codigo):
        raise LookupError(f"Item '{codigo}' não encontrado — foi removido durante a contagem")

    divergencia = quantidade_encontrada != quantidade_base

    # with_for_update() serializa workers concorrentes em PostgreSQL: o segundo worker
    # espera o commit do primeiro antes de ler, evitando que dois writers leiam o mesmo
    # estado e sobreescrevam um ao outro (last-write-wins silencioso).
    existente = _buscar_contagem_para_update(db, sessao_id, codigo)
    nova_para_ajuste = False  # inicializado aqui para evitar UnboundLocalError no branch else
    if existente:
        mesma_qtd_anterior = (quantidade_encontrada == existente.quantidade_encontrada)

        # Avança rodada apenas para itens DIVERGENTE ativos (não já-confirmados como PARA_AJUSTE)
        # com nova quantidade diferente da anterior E diferente da base.
        # Itens PARA_AJUSTE não avançam rodada — já estão resolvidos.
        if (existente.divergencia and not existente.para_ajuste
                and not mesma_qtd_anterior and divergencia):
            nova_rodada = existente.rodada + 1
        elif not existente.divergencia and divergencia:
            # Item era OK mas nova contagem diverge → entra na fila de recontagem
            nova_rodada = existente.rodada
        else:
            # Mesma quantidade, item ficou OK, ou item já era PARA_AJUSTE → mantém rodada
            nova_rodada = existente.rodada

        rodada_final = nova_rodada

        # PARA_AJUSTE quando o mesmo erro divergente é confirmado pela segunda vez.
        nova_para_ajuste = (divergencia and mesma_qtd_anterior and existente.divergencia)

        # Garantia de terminação: após MAX_RODADAS rodadas com quantidades sempre diferentes,
        # força PARA_AJUSTE para impedir que o inventário fique bloqueado indefinidamente.
        if (not nova_para_ajuste and not existente.para_ajuste
                and divergencia and rodada_final >= MAX_RODADAS_DIVERGENCIA):
            nova_para_ajuste = True

        # Regras de persistência do PARA_AJUSTE:
        #   - qty bate com a base   → CERTO (correção bem-sucedida)
        #   - qualquer qty divergente → mantém PARA_AJUSTE
        #     SE a qty é diferente da confirmada: preserva o valor duplo-confirmado no registro
        #     (a tentativa nova vai apenas para o HistoricoContagem, para trilha de auditoria).
        qtd_contagem = quantidade_encontrada  # qty que será salva no registro atual
        if existente.para_ajuste and not divergencia:
            nova_para_ajuste = False  # corrigido para a base
        elif existente.para_ajuste and divergencia:
            nova_para_ajuste = True   # mantém confirmação
            if not mesma_qtd_anterior:
                # Nova qty nunca foi duplo-confirmada: preserva a qty confirmada no Contagem.
                qtd_contagem = existente.quantidade_encontrada

        existente.rodada = rodada_final
        existente.quantidade_encontrada = qtd_contagem
        existente.divergencia = (qtd_contagem != quantidade_base)
        existente.para_ajuste = nova_para_ajuste
        existente.operador = operador
        existente.observacao = observacao
        existente.timestamp = datetime.now(timezone.utc)
        contagem = existente
    else:
        rodada_final = 1
        contagem = Contagem(
            sessao_id=sessao_id,
            codigo=codigo,
            quantidade_encontrada=quantidade_encontrada,
            divergencia=divergencia,
            para_ajuste=False,
            operador=operador,
            observacao=observacao,
            rodada=rodada_final,
        )
        db.add(contagem)

    # Histórico sempre registra a tentativa ORIGINAL do operador (para auditoria completa).
    # Quando qtd_contagem difere de quantidade_encontrada (preservação PARA_AJUSTE),
    # o histórico mostra a tentativa nova com para_ajuste=False (não foi uma confirmação).
    if existente and qtd_contagem != quantidade_encontrada:
        # PARA_AJUSTE com nova qty diferente: histórico registra a tentativa, não a confirmação
        _para_ajuste_hist = False
    else:
        _para_ajuste_hist = nova_para_ajuste if existente else False
    historico = HistoricoContagem(
        sessao_id=sessao_id,
        codigo=codigo,
        quantidade_encontrada=quantidade_encontrada,
        quantidade_base=quantidade_base,
        divergencia=divergencia,
        para_ajuste=_para_ajuste_hist,
        operador=operador,
        observacao=observacao,
        rodada=rodada_final,
    )
    try:
        db.add(historico)
        db.commit()
    except IntegrityError:
        db.rollback()
        # Race condition: outro worker inseriu o mesmo (sessao_id, codigo) simultaneamente.
        # Retorna 409 em vez de 500 para que o cliente possa retentar.
        from fastapi import HTTPException
        raise HTTPException(
            status_code=409,
            detail=f"Item '{codigo}' está sendo registrado por outro operador. Aguarde um instante e tente novamente.",
        )
    except Exception:
        db.rollback()
        raise
    db.refresh(contagem)
    return contagem


def contar_contagens(db: Session, sessao_id: str) -> int:
    from sqlalchemy import func
    return db.query(func.count(Contagem.id)).filter(Contagem.sessao_id == sessao_id).scalar() or 0


def listar_historico(
    db: Session,
    sessao_id: str,
    codigo: str | None = None,
    limit: int | None = 500,
    offset: int = 0,
    operador: str | None = None,
    apenas_divergencias: bool = False,
) -> list[HistoricoContagem]:
    from sqlalchemy import func as sa_func
    q = db.query(HistoricoContagem).filter(HistoricoContagem.sessao_id == sessao_id)
    if codigo:
        q = q.filter(HistoricoContagem.codigo == codigo)
    if operador:
        q = q.filter(sa_func.lower(HistoricoContagem.operador) == operador.lower())
    if apenas_divergencias:
        q = q.filter(HistoricoContagem.divergencia == True)  # noqa: E712
    q = q.order_by(HistoricoContagem.timestamp.asc())
    if offset:
        q = q.offset(offset)
    if limit is not None:
        q = q.limit(limit)
    return q.all()


def listar_contagens(db: Session, sessao_id: str,
                     skip: int = 0, limit: int | None = None) -> list[Contagem]:
    """
    Retorna contagens da sessão com paginação opcional.
    limit=None (default) → carrega tudo (uso interno em cálculos).
    limit=N → retorna no máximo N registros.
    """
    q = db.query(Contagem).filter(Contagem.sessao_id == sessao_id).order_by(Contagem.timestamp.asc())
    if skip:
        q = q.offset(skip)
    if limit is not None:
        q = q.limit(limit)
    return q.all()


def listar_itens_pendentes_r1(
    db: Session, sessao_id: str, codigos_filtro: set[str] | None = None
) -> list[ItemBase]:
    """R1: itens sem nenhuma contagem. Usa NOT EXISTS — não carrega contagens em memória."""
    from sqlalchemy import exists
    q = db.query(ItemBase).filter(
        ItemBase.sessao_id == sessao_id,
        ~exists().where(
            Contagem.sessao_id == sessao_id,
            Contagem.codigo == ItemBase.codigo,
        ),
    ).order_by(ItemBase.local_fisico.asc().nulls_last(), ItemBase.codigo.asc())
    itens = q.all()
    if codigos_filtro is not None:
        itens = [i for i in itens if i.codigo in codigos_filtro]
    return itens


def listar_itens_divergentes_ativos(
    db: Session, sessao_id: str, codigos_filtro: set[str] | None = None
) -> list[tuple]:
    """R2+: itens com divergência ativa (não para_ajuste). Retorna (ItemBase, Contagem)."""
    rows = (
        db.query(ItemBase, Contagem)
        .join(Contagem, (Contagem.sessao_id == ItemBase.sessao_id)
              & (Contagem.codigo == ItemBase.codigo))
        .filter(
            ItemBase.sessao_id == sessao_id,
            Contagem.divergencia == True,   # noqa: E712
            Contagem.para_ajuste == False,  # noqa: E712
        )
        .order_by(ItemBase.local_fisico.asc().nulls_last(), ItemBase.codigo.asc())
        .all()
    )
    if codigos_filtro is not None:
        rows = [(i, c) for i, c in rows if i.codigo in codigos_filtro]
    return rows


def listar_divergencias(db: Session, sessao_id: str) -> list[Contagem]:
    return db.query(Contagem).filter(
        Contagem.sessao_id == sessao_id,
        Contagem.divergencia == True  # noqa
    ).all()


def calcular_progresso_rodada(db: Session, sessao_id: str) -> dict:
    """
    Calcula o progresso da rodada de contagem ativa.

    Lógica de rodadas:
      - Rodada 1: todos os itens da sessão precisam ser contados ao menos 1 vez.
      - Rodada 2: apenas itens que divergiram na rodada 1.
      - Rodada 3: apenas itens que ainda divergiram na rodada 2 (máximo 3 rodadas).
    """
    total_itens = db.query(ItemBase).filter(ItemBase.sessao_id == sessao_id).count()

    # Guard: sessão sem itens — evita divisão por zero no frontend
    # completa=False (não False) porque sessão vazia não tem inventário pronto
    if total_itens == 0:
        return {
            "rodada_atual": 1, "total_rodada": 0, "contados_rodada": 0,
            "faltando": 0, "completa": False, "tem_itens": False, "divergencias": 0,
            "proxima_rodada_necessaria": False,
            "faltando_r1": 0, "faltando_r2": 0, "faltando_r3": 0,
            "divergencias_r1": 0, "divergencias_r2": 0, "divergencias_r3": 0,
        }

    contagens = db.query(Contagem).filter(Contagem.sessao_id == sessao_id).all()
    n = len(contagens)

    # faltando_r1 = itens sem nenhuma contagem
    faltando_r1 = total_itens - n

    # Itens pendentes de recontagem = divergente E ainda não confirmado como para_ajuste.
    # Incluem itens em qualquer rodada que ainda não foram resolvidos (CERTO ou PARA_AJUSTE).
    # Um item só sai daqui quando bate com a base (CERTO) ou confirma o mesmo erro (PARA_AJUSTE).
    pendentes_recontagem = sum(1 for c in contagens if c.divergencia and not c.para_ajuste)
    faltando_r2 = pendentes_recontagem
    faltando_r3 = 0  # sem terceira rodada fixa — subsumir em faltando_r2

    # divergencias_r1 = quantos divergiram na primeira contagem (para estatística do R1)
    divergencias_r1 = sum(1 for c in contagens if c.rodada == 1 and c.divergencia)
    # divergencias_r2 = itens que já foram recontados mas ainda não foram resolvidos
    divergencias_r2 = sum(1 for c in contagens if c.rodada >= 2 and c.divergencia and not c.para_ajuste)
    divergencias_r3 = 0

    if faltando_r1 > 0:
        rodada_atual = 1
        total_rodada = total_itens
        contados_rodada = n
        faltando = faltando_r1
        divergencias = divergencias_r1
    elif faltando_r2 > 0:
        # Fase de recontagem: itens divergentes pendentes de resolução (CERTO ou PARA_AJUSTE).
        # rodada_atual é no mínimo 2 — se todos os divergentes ainda estão em rodada=1 (nenhuma
        # recontagem feita ainda), max() retornaria 1, o que é enganoso. Garantimos mínimo de 2.
        rodada_atual = max(2, max((c.rodada for c in contagens), default=2))
        # Escopo = já recontados ao menos 1x (rodada>=2) + ainda aguardando 1ª recontagem (rodada==1 div)
        divergentes_r1_pendentes = sum(1 for c in contagens if c.rodada == 1 and c.divergencia)
        ja_recontados = sum(1 for c in contagens if c.rodada >= 2)
        total_rodada = divergentes_r1_pendentes + ja_recontados
        # Resolvidos na recontagem = recontados e já OK (CERTO ou PARA_AJUSTE)
        contados_rodada = sum(
            1 for c in contagens if c.rodada >= 2 and (not c.divergencia or c.para_ajuste)
        )
        faltando = faltando_r2
        divergencias = faltando_r2
    else:
        # Inventário completo: todos os itens são CERTO ou PARA_AJUSTE
        rodada_atual = max((c.rodada for c in contagens), default=1)
        total_rodada = n
        contados_rodada = n
        faltando = 0
        divergencias = 0

    # completa = todos contados na R1 E nenhum pendente de recontagem
    completa = (faltando_r1 == 0 and faltando_r2 == 0)
    proxima_rodada_necessaria = (faltando_r1 == 0 and faltando_r2 > 0)

    return {
        "rodada_atual": rodada_atual,
        "total_rodada": total_rodada,
        "contados_rodada": contados_rodada,
        "faltando": faltando,
        "completa": completa,
        "tem_itens": True,
        "divergencias": divergencias,
        "proxima_rodada_necessaria": proxima_rodada_necessaria,
        "faltando_r1": faltando_r1,
        "faltando_r2": faltando_r2,
        "faltando_r3": faltando_r3,
        "divergencias_r1": divergencias_r1,
        "divergencias_r2": divergencias_r2,
        "divergencias_r3": divergencias_r3,
    }
