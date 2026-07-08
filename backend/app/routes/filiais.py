"""
CRUD de filiais — suporte multi-filial para uso em redes de lojas ou múltiplas unidades.
"""
from __future__ import annotations
from app.auth import get_admin_logado

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.filial import Filial

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/filiais", tags=["Filiais"], dependencies=[Depends(get_admin_logado)])


class FilialCreate(BaseModel):
    nome: str
    codigo: str
    empresa: str | None = None
    cidade: str | None = None


class FilialUpdate(BaseModel):
    nome: str | None = None
    empresa: str | None = None
    cidade: str | None = None
    ativo: bool | None = None


def _to_dict(f: Filial) -> dict:
    return {
        "id": f.id,
        "nome": f.nome,
        "codigo": f.codigo,
        "empresa": f.empresa,
        "cidade": f.cidade,
        "ativo": f.ativo,
        "criado_em": f.criado_em.isoformat() if f.criado_em else None,
    }


@router.post("/", status_code=201)
def criar_filial(payload: FilialCreate, db: Session = Depends(get_db)) -> dict:
    """Cria uma nova filial. O código deve ser único (ex: SP01, RJ02)."""
    codigo = payload.codigo.upper().strip()
    existente = db.query(Filial).filter(Filial.codigo == codigo).first()
    if existente:
        raise HTTPException(status_code=409, detail=f"Já existe uma filial com o código '{codigo}'.")

    f = Filial(
        nome=payload.nome,
        codigo=codigo,
        empresa=payload.empresa,
        cidade=payload.cidade,
    )
    db.add(f)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Já existe uma filial com o código '{payload.codigo}'.")
    db.refresh(f)
    logger.info("Filial criada id=%s codigo=%s", f.id, f.codigo)
    return _to_dict(f)


@router.get("/")
def listar_filiais(
    apenas_ativas: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Lista todas as filiais. Use apenas_ativas=true para filtrar apenas ativas."""
    q = db.query(Filial)
    if apenas_ativas:
        q = q.filter(Filial.ativo == True)  # noqa: E712
    return [_to_dict(f) for f in q.order_by(Filial.codigo).all()]


@router.get("/{filial_id}")
def buscar_filial(filial_id: str, db: Session = Depends(get_db)) -> dict:
    f = db.query(Filial).filter(Filial.id == filial_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="Filial não encontrada.")
    return _to_dict(f)


@router.patch("/{filial_id}")
def atualizar_filial(
    filial_id: str,
    payload: FilialUpdate,
    db: Session = Depends(get_db),
) -> dict:
    """Atualiza nome, empresa, cidade ou status da filial."""
    f = db.query(Filial).filter(Filial.id == filial_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="Filial não encontrada.")

    if payload.nome is not None:
        f.nome = payload.nome
    if payload.empresa is not None:
        f.empresa = payload.empresa
    if payload.cidade is not None:
        f.cidade = payload.cidade
    if payload.ativo is not None:
        f.ativo = payload.ativo

    db.commit()
    db.refresh(f)
    return _to_dict(f)


@router.delete("/{filial_id}", status_code=204)
def deletar_filial(filial_id: str, db: Session = Depends(get_db)):
    """Remove uma filial. Sessões vinculadas não são excluídas — apenas a referência é removida."""
    f = db.query(Filial).filter(Filial.id == filial_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="Filial não encontrada.")
    db.delete(f)
    db.commit()


@router.get("/{filial_id}/sessoes")
def sessoes_da_filial(
    filial_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Lista todas as sessões de inventário vinculadas a esta filial."""
    from app.models.sessao import Sessao
    f = db.query(Filial).filter(Filial.id == filial_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="Filial não encontrada.")

    sessoes = (
        db.query(Sessao)
        .filter(Sessao.filial_id == filial_id)
        .order_by(Sessao.data_inicio.desc())
        .all()
    )
    return {
        "filial": _to_dict(f),
        "sessoes": [
            {
                "id": s.id,
                "codigo": s.codigo,
                "nome": s.nome,
                "status": str(s.status.value if hasattr(s.status, "value") else s.status),
                "data_inicio": s.data_inicio.isoformat() if s.data_inicio else None,
                "data_fim": s.data_fim.isoformat() if s.data_fim else None,
            }
            for s in sessoes
        ],
        "total": len(sessoes),
    }
