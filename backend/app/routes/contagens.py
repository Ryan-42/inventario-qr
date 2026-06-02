from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.repositories import sessao_repo, item_repo
from app.schemas import ContagemCreate, ContagemResponse, HistoricoContagemResponse
from app.models.sessao import StatusSessao
from app.websockets.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessoes", tags=["Contagens"])


@router.get("/{sessao_id}/contagens", response_model=list[ContagemResponse])
def listar_contagens_sessao(
    sessao_id: str,
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    # Paginação real via SQLAlchemy — não carrega tudo em memória
    limit_safe = max(1, min(limit, 2000))  # caps entre 1 e 2000
    return item_repo.listar_contagens(db, sessao_id, skip=skip, limit=limit_safe)


@router.post("/{sessao_id}/contagens", response_model=ContagemResponse, status_code=201)
@limiter.limit("150/minute")
async def registrar_contagem(request: Request,
    sessao_id: str,
    payload: ContagemCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if sessao.status != StatusSessao.ativa:
        raise HTTPException(
            status_code=409,
            detail=f"Sessão está '{sessao.status.value}' e não aceita novas contagens",
        )

    item = item_repo.buscar_item(db, sessao_id, payload.codigo)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{payload.codigo}' não encontrado na base desta sessão")

    # Captura progresso ANTES da contagem para detectar transição de rodada
    progresso_antes = item_repo.calcular_progresso_rodada(db, sessao_id)

    try:
        contagem = item_repo.registrar_contagem(
            db=db,
            sessao_id=sessao_id,
            codigo=payload.codigo,
            quantidade_encontrada=payload.quantidade_encontrada,
            quantidade_base=item.quantidade_base,
            operador=payload.operador,
            observacao=payload.observacao,
        )
    except LookupError as exc:
        # Item foi deletado entre a validação acima e o registro (race condition)
        raise HTTPException(status_code=409, detail=str(exc))

    # Enriquece resposta com dados do item
    contagem.produto = item.produto
    contagem.quantidade_base = item.quantidade_base
    contagem.diferenca = payload.quantidade_encontrada - item.quantidade_base

    # Calcula progresso DEPOIS da contagem
    progresso_depois = item_repo.calcular_progresso_rodada(db, sessao_id)

    # ── Evento principal: contagem registrada
    para_ajuste = getattr(contagem, 'para_ajuste', False)
    evento_contagem = {
        "tipo": "contagem_registrada",
        "codigo": contagem.codigo,
        "quantidade_encontrada": contagem.quantidade_encontrada,
        "diferenca": contagem.diferenca,
        "divergencia": contagem.divergencia,
        "para_ajuste": para_ajuste,
        "produto": item.produto,
        "local_fisico": item.local_fisico,
        "operador": contagem.operador,
        "rodada": contagem.rodada,
        "timestamp": contagem.timestamp.isoformat() if contagem.timestamp else None,
    }
    background_tasks.add_task(_broadcast_safe, sessao_id, evento_contagem)

    # ── Progresso atualizado — scanner exibe contador em tempo real
    background_tasks.add_task(_broadcast_safe, sessao_id, {
        "tipo": "progresso_atualizado",
        "rodada_atual": progresso_depois["rodada_atual"],
        "faltando": progresso_depois["faltando"],
        "total_rodada": progresso_depois["total_rodada"],
        "contados_rodada": progresso_depois["contados_rodada"],
        "completa": progresso_depois["completa"],
    })

    # ── Detecta transição de rodada: antes tinha ≥1 faltando, agora chegou a 0.
    # Usar > 0 (não == 1) cobre concorrência: dois operadores contando os últimos
    # dois itens simultaneamente — ambos veem faltando=2 no "antes", mas apenas
    # o último commit vê faltando=0 no "depois" e dispara o evento.
    for rodada_num, campo in [(1, "faltando_r1"), (2, "faltando_r2"), (3, "faltando_r3")]:
        if progresso_antes[campo] > 0 and progresso_depois[campo] == 0:
            div_campo = f"divergencias_r{rodada_num}"
            divs = progresso_depois[div_campo]
            proxima_necessaria = divs > 0 and rodada_num < 3
            tudo_concluido = not proxima_necessaria and progresso_depois["faltando"] == 0
            background_tasks.add_task(_broadcast_safe, sessao_id, {
                "tipo": "rodada_completa",
                "rodada_concluida": rodada_num,
                "divergencias_pendentes": divs,
                "proxima_rodada": rodada_num + 1 if proxima_necessaria else None,
                "proxima_rodada_necessaria": proxima_necessaria,
                "tudo_concluido": tudo_concluido,
            })
            break  # só uma rodada pode completar por vez

    if contagem.divergencia:
        background_tasks.add_task(
            _rodar_alerta, sessao_id, contagem.codigo,
            contagem.quantidade_encontrada, item.quantidade_base, contagem.operador,
        )

    return contagem


@router.get("/{sessao_id}/historico", response_model=list[HistoricoContagemResponse])
def listar_historico(sessao_id: str, codigo: str | None = None, db: Session = Depends(get_db)):
    """Retorna histórico append-only de todas as contagens da sessão (ou de um código específico)."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return item_repo.listar_historico(db, sessao_id, codigo=codigo)


@router.delete("/{sessao_id}/contagens/{codigo}", status_code=204)
async def deletar_contagem(sessao_id: str, codigo: str,
                           background_tasks: BackgroundTasks,
                           db: Session = Depends(get_db)):
    """Remove a contagem atual de um item (mantém histórico). Libera o item para recontagem."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if sessao.status != StatusSessao.ativa:
        raise HTTPException(status_code=409, detail=f"Sessão está '{sessao.status.value}'")
    contagem = item_repo.buscar_contagem(db, sessao_id, codigo)
    if not contagem:
        raise HTTPException(status_code=404, detail=f"Contagem do item '{codigo}' não encontrada")
    db.delete(contagem)
    db.commit()
    # Notifica operadores mobile em tempo real que o item voltou para "não contado"
    progresso = item_repo.calcular_progresso_rodada(db, sessao_id)
    background_tasks.add_task(_broadcast_safe, sessao_id, {
        "tipo": "contagem_deletada",
        "codigo": codigo,
        "rodada_atual": progresso["rodada_atual"],
        "faltando": progresso["faltando"],
        "total_rodada": progresso["total_rodada"],
        "contados_rodada": progresso["contados_rodada"],
    })


async def _broadcast_safe(sessao_id: str, data: dict) -> None:
    try:
        await manager.broadcast(sessao_id, data)
    except Exception as exc:
        logger.warning("Falha no broadcast WebSocket — sessao=%s erro=%s", sessao_id, exc)


def _rodar_alerta(sessao_id: str, codigo: str, qtd_encontrada: int, qtd_base: int, operador: str | None) -> None:
    try:
        from app.agents.alerta import AlertaAgent
        resultado = AlertaAgent().analisar(
            codigo=codigo,
            quantidade_encontrada=qtd_encontrada,
            quantidade_base=qtd_base,
            operador=operador,
            contagens=[],
        )
        if resultado.get("tem_alertas"):
            logger.info("AlertaAgent — sessao=%s codigo=%s alertas=%s", sessao_id, codigo, resultado["alertas"])
    except Exception as exc:
        logger.warning("AlertaAgent falhou — sessao=%s erro=%s", sessao_id, exc)
