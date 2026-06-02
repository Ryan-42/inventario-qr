from sqlalchemy.orm import Session
from typing import Optional
from app.models.grupo_operador import GrupoOperador


def listar_grupos(db: Session, sessao_id: str) -> list[GrupoOperador]:
    return db.query(GrupoOperador).filter(GrupoOperador.sessao_id == sessao_id).all()


def buscar_grupo(db: Session, sessao_id: str, grupo_id: str) -> Optional[GrupoOperador]:
    return db.query(GrupoOperador).filter(
        GrupoOperador.sessao_id == sessao_id,
        GrupoOperador.id == grupo_id,
    ).first()


def buscar_grupo_por_token(db: Session, sessao_id: str, token: str) -> Optional[GrupoOperador]:
    return db.query(GrupoOperador).filter(
        GrupoOperador.sessao_id == sessao_id,
        GrupoOperador.token == token,
    ).first()


def criar_grupo(db: Session, sessao_id: str, nome: str, filtro: str,
                tipo_filtro: str = "prefixo", cor: Optional[str] = None) -> GrupoOperador:
    grupo = GrupoOperador(
        sessao_id=sessao_id,
        nome=nome,
        filtro=filtro.upper(),
        tipo_filtro=tipo_filtro,
        cor=cor,
    )
    db.add(grupo)
    db.commit()
    db.refresh(grupo)
    return grupo


def atualizar_grupo(db: Session, grupo: GrupoOperador, nome: str = None,
                    filtro: str = None, tipo_filtro: str = None, cor: str = None) -> GrupoOperador:
    if nome is not None:
        grupo.nome = nome
    if filtro is not None:
        grupo.filtro = filtro.upper()
    if tipo_filtro is not None:
        grupo.tipo_filtro = tipo_filtro
    if cor is not None:
        grupo.cor = cor
    db.commit()
    db.refresh(grupo)
    return grupo


def regenerar_token_grupo(db: Session, grupo: GrupoOperador) -> GrupoOperador:
    import secrets
    grupo.token = secrets.token_hex(4).upper()
    db.commit()
    db.refresh(grupo)
    return grupo


def deletar_grupo(db: Session, grupo: GrupoOperador) -> None:
    db.delete(grupo)
    db.commit()
