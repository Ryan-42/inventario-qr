from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional

from app.models.item_base import ItemBase
from app.models.contagem import Contagem, HistoricoContagem


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


# ── Contagens ─────────────────────────────────────────────────────────────────

def buscar_contagem(db: Session, sessao_id: str, codigo: str) -> Optional[Contagem]:
    # Upsert garante no máximo 1 contagem por (sessao_id, codigo) — sem ORDER BY necessário
    return db.query(Contagem).filter(
        Contagem.sessao_id == sessao_id,
        Contagem.codigo == codigo
    ).first()


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

    existente = buscar_contagem(db, sessao_id, codigo)
    if existente:
        mesma_qtd_anterior = (quantidade_encontrada == existente.quantidade_encontrada)

        if existente.divergencia and not mesma_qtd_anterior:
            # Item era divergente e nova quantidade é diferente → avança para próxima rodada
            nova_rodada = existente.rodada + 1
        elif not existente.divergencia and divergencia:
            # Item era OK mas nova contagem diverge → volta a requerer R2 (trata como R1 divergente)
            # Mantém rodada atual para não falsamente "avançar" — o item entra na fila de R2
            nova_rodada = existente.rodada
        else:
            # Mesma quantidade (confirma estado anterior), ou item continua OK → mantém rodada
            nova_rodada = existente.rodada

        rodada_final = min(nova_rodada, 3)

        # "Para Ajuste" quando:
        # 1. Confirmação da mesma quantidade divergente (dois registros confirmam o erro)
        # 2. Chegou à rodada 3 e ainda diverge (sem mais rodadas disponíveis)
        nova_para_ajuste = (
            (divergencia and mesma_qtd_anterior and existente.divergencia)
            or (rodada_final == 3 and divergencia)
        )

        # Se já estava "para_ajuste" E item ainda diverge → mantém flag
        # Se já estava "para_ajuste" mas agora está OK → limpa (correção bem-sucedida)
        if existente.para_ajuste and divergencia:
            nova_para_ajuste = True
        elif existente.para_ajuste and not divergencia:
            nova_para_ajuste = False  # item foi corrigido

        existente.rodada = rodada_final
        existente.quantidade_encontrada = quantidade_encontrada
        existente.divergencia = divergencia
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

    # Captura para_ajuste do estado atual (existente ou recém criado)
    _para_ajuste = nova_para_ajuste if existente else False
    historico = HistoricoContagem(
        sessao_id=sessao_id,
        codigo=codigo,
        quantidade_encontrada=quantidade_encontrada,
        quantidade_base=quantidade_base,
        divergencia=divergencia,
        para_ajuste=_para_ajuste,
        operador=operador,
        observacao=observacao,
        rodada=rodada_final,
    )
    try:
        db.add(historico)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(contagem)
    return contagem


def contar_contagens(db: Session, sessao_id: str) -> int:
    from sqlalchemy import func
    return db.query(func.count(Contagem.id)).filter(Contagem.sessao_id == sessao_id).scalar() or 0


def listar_historico(db: Session, sessao_id: str, codigo: str | None = None) -> list[HistoricoContagem]:
    q = db.query(HistoricoContagem).filter(HistoricoContagem.sessao_id == sessao_id)
    if codigo:
        q = q.filter(HistoricoContagem.codigo == codigo)
    return q.order_by(HistoricoContagem.timestamp.asc()).all()


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

    # Pendentes por rodada:
    # faltando_rN = itens cujo rodada ainda é N-1 com divergência (ainda não recontados na rodada N)
    faltando_r1 = total_itens - n                                              # itens sem nenhuma contagem
    faltando_r2 = sum(1 for c in contagens if c.rodada == 1 and c.divergencia) # aguardando recontagem em R2
    faltando_r3 = sum(1 for c in contagens if c.rodada == 2 and c.divergencia) # aguardando recontagem em R3

    # divergencias_rN = itens que foram contados na rodada N e ainda divergem
    divergencias_r1 = faltando_r2  # idêntico por definição: R1 divergentes = pendentes de R2
    divergencias_r2 = sum(1 for c in contagens if c.rodada == 2 and c.divergencia)
    divergencias_r3 = sum(1 for c in contagens if c.rodada == 3 and c.divergencia)

    if faltando_r1 > 0:
        rodada_atual = 1
        total_rodada = total_itens
        contados_rodada = n
        faltando = faltando_r1
        divergencias = divergencias_r1
    elif faltando_r2 > 0:
        rodada_atual = 2
        # escopo R2 = itens já recontados (rodada==2) + itens ainda pendentes (rodada==1, div=True)
        total_rodada = sum(1 for c in contagens if c.rodada == 2 or (c.rodada == 1 and c.divergencia))
        contados_rodada = sum(1 for c in contagens if c.rodada == 2)
        faltando = faltando_r2
        divergencias = divergencias_r2
    elif faltando_r3 > 0:
        rodada_atual = 3
        total_rodada = sum(1 for c in contagens if c.rodada == 3 or (c.rodada == 2 and c.divergencia))
        contados_rodada = sum(1 for c in contagens if c.rodada == 3)
        faltando = faltando_r3
        divergencias = divergencias_r3
    else:
        # Inventário completo: todas as rodadas zeraram
        rodada_atual = max((c.rodada for c in contagens), default=1)
        total_rodada = n          # escopo = todos os itens contados
        contados_rodada = n       # todos foram contados (progresso = 100%)
        faltando = 0
        divergencias = sum(1 for c in contagens if c.divergencia)

    completa = (faltando_r1 == 0 and faltando_r2 == 0 and faltando_r3 == 0)
    proxima_rodada_necessaria = (
        (faltando_r1 == 0 and faltando_r2 > 0) or
        (faltando_r1 == 0 and faltando_r2 == 0 and faltando_r3 > 0)
    )

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
