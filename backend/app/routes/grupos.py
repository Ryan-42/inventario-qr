"""
Endpoints para gestão de grupos de operadores e supervisor.

Grupos: permitem dividir o inventário por prefixo de código entre operadores.
Supervisor: acesso somente-leitura aos itens divergentes com localização.
"""
from __future__ import annotations

import secrets
from io import BytesIO

import hmac
import logging
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.auth import verificar_token_admin
from app.database import get_db
from app.limiter import limiter
from app.repositories import sessao_repo, item_repo, grupo_repo
from app.models.sessao import StatusSessao
from app.websockets.manager import manager

logger = logging.getLogger(__name__)


def _validar_base_url(base_url: str) -> None:
    if not base_url:
        return
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="base_url deve usar http ou https")

router = APIRouter(prefix="/sessoes", tags=["Grupos"])

_CORES_PADRAO = ["#ef4444", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6", "#ec4899", "#06b6d4"]


# ── Schemas ───────────────────────────────────────────────────────────────────

class GrupoCreate(BaseModel):
    nome: str
    filtro: str = "*"
    tipo_filtro: str = "prefixo"  # prefixo | lista | todos
    cor: Optional[str] = None


class GrupoUpdate(BaseModel):
    nome: Optional[str] = None
    filtro: Optional[str] = None
    tipo_filtro: Optional[str] = None
    cor: Optional[str] = None


# ── Grupos de operadores ──────────────────────────────────────────────────────

@router.get("/{sessao_id}/grupos")
def listar_grupos(sessao_id: str, db: Session = Depends(get_db)):
    """Lista todos os grupos de operadores da sessão."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    grupos = grupo_repo.listar_grupos(db, sessao_id)
    return [_grupo_dict(g, sessao_id) for g in grupos]


@router.post("/{sessao_id}/grupos", status_code=201)
def criar_grupo(sessao_id: str, payload: GrupoCreate, db: Session = Depends(get_db)):
    """Cria um novo grupo de operadores com token de acesso próprio."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if sessao.status != StatusSessao.ativa:
        raise HTTPException(status_code=409, detail="Sessão não está ativa")

    grupos_existentes = grupo_repo.listar_grupos(db, sessao_id)
    cor = payload.cor or _CORES_PADRAO[len(grupos_existentes) % len(_CORES_PADRAO)]

    grupo = grupo_repo.criar_grupo(
        db, sessao_id,
        nome=payload.nome,
        filtro=payload.filtro,
        tipo_filtro=payload.tipo_filtro,
        cor=cor,
    )
    return _grupo_dict(grupo, sessao_id)


@router.put("/{sessao_id}/grupos/{grupo_id}")
def atualizar_grupo(sessao_id: str, grupo_id: str, payload: GrupoUpdate,
                    db: Session = Depends(get_db)):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    grupo = grupo_repo.buscar_grupo(db, sessao_id, grupo_id)
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    grupo = grupo_repo.atualizar_grupo(db, grupo, **payload.model_dump(exclude_none=True))
    return _grupo_dict(grupo, sessao_id)


@router.post("/{sessao_id}/grupos/{grupo_id}/regenerar-token")
def regenerar_token_grupo(sessao_id: str, grupo_id: str, db: Session = Depends(get_db)):
    """Gera novo token para o grupo (invalida o anterior)."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    grupo = grupo_repo.buscar_grupo(db, sessao_id, grupo_id)
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    grupo = grupo_repo.regenerar_token_grupo(db, grupo)
    return _grupo_dict(grupo, sessao_id)


@router.get("/{sessao_id}/grupos/{grupo_id}/qrcode")
def qrcode_grupo(sessao_id: str, grupo_id: str, base_url: str = "",
                 db: Session = Depends(get_db)):
    """Retorna QR Code PNG do grupo para compartilhar com operadores."""
    import qrcode as qrcode_lib
    _validar_base_url(base_url)
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    grupo = grupo_repo.buscar_grupo(db, sessao_id, grupo_id)
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")

    mobile_path = f"/mobile/{sessao_id}?token={grupo.token}&grupo={grupo_id}"
    full_url = f"{base_url.rstrip('/')}{mobile_path}" if base_url else mobile_path

    qr = qrcode_lib.QRCode(version=None, error_correction=qrcode_lib.constants.ERROR_CORRECT_M,
                            box_size=10, border=2)
    qr.add_data(full_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F172A", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.delete("/{sessao_id}/grupos/{grupo_id}", status_code=204)
def deletar_grupo(sessao_id: str, grupo_id: str, db: Session = Depends(get_db)):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    grupo = grupo_repo.buscar_grupo(db, sessao_id, grupo_id)
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    grupo_repo.deletar_grupo(db, grupo)


class RegenerarAdminBody(BaseModel):
    token_atual: str


@router.post("/{sessao_id}/novo-token-admin")
def novo_token_admin(sessao_id: str, body: RegenerarAdminBody, db: Session = Depends(get_db)):
    """Regenera o token_admin. Requer o token atual no body para provar propriedade."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if not hmac.compare_digest(sessao.token_admin or "", body.token_atual):
        raise HTTPException(status_code=403, detail="Token admin atual inválido")
    sessao.token_admin = secrets.token_hex(8).upper()
    db.commit()
    return {"token_admin": sessao.token_admin}


@router.get("/{sessao_id}/verificar-grupo")
@limiter.limit("15/minute")
async def verificar_token_grupo(request: Request, sessao_id: str, token: str, db: Session = Depends(get_db)):
    """Verifica se o token pertence a um grupo e retorna as informações do grupo."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    # Verifica token de supervisor — hmac.compare_digest previne timing attack
    if hmac.compare_digest(sessao.token_supervisor or "", token):
        return {"tipo": "supervisor", "valido": True, "grupo": None}

    # Verifica token geral da sessão
    if hmac.compare_digest(sessao.token_acesso or "", token):
        return {"tipo": "geral", "valido": True, "grupo": None}

    # Verifica token de grupo
    grupo = grupo_repo.buscar_grupo_por_token(db, sessao_id, token)
    if grupo:
        return {
            "tipo": "grupo",
            "valido": True,
            "grupo": {
                "id": grupo.id,
                "nome": grupo.nome,
                "filtro": grupo.filtro,
                "tipo_filtro": grupo.tipo_filtro,
                "cor": grupo.cor,
            }
        }

    return {"tipo": None, "valido": False, "grupo": None}


# ── Lista de itens (operador — sem quantidade) ────────────────────────────────

@router.get("/{sessao_id}/lista-operador")
def lista_operador(sessao_id: str, token: str = "", rodada: int = 1,
                   db: Session = Depends(get_db)):
    """
    Retorna lista de itens para o operador, SEM quantidade base.
    Token obrigatório — pode ser geral, de grupo ou de supervisor (supervisor vê tudo).
    """
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if sessao.status == StatusSessao.cancelada:
        raise HTTPException(status_code=409, detail="Sessão cancelada — lista indisponível")

    # Token obrigatório — valida contra token geral, grupo ou supervisor
    if not token:
        raise HTTPException(status_code=401, detail="Token obrigatório para acessar a lista de itens")

    token_valido = (
        hmac.compare_digest(sessao.token_acesso or "", token)
        or hmac.compare_digest(sessao.token_supervisor or "", token)
    )
    grupo = grupo_repo.buscar_grupo_por_token(db, sessao_id, token)
    if not token_valido and not grupo:
        raise HTTPException(status_code=403, detail="Token inválido")

    todos_itens = item_repo.listar_itens(db, sessao_id)
    contagens_map = {c.codigo: c for c in item_repo.listar_contagens(db, sessao_id)}

    resultado = []
    for item in todos_itens:
        # Filtro de grupo
        if grupo and not grupo.valida_codigo(item.codigo):
            continue

        contagem = contagens_map.get(item.codigo)

        # Rodada 1: todos os itens não contados do grupo
        # Rodada 2+: itens DIVERGENTES ativos (qualquer rodada < atual, sem para_ajuste)
        if rodada == 1:
            if contagem is not None:
                continue  # já contado, não aparece na lista
        else:
            # Pendentes de recontagem = divergente E não para_ajuste (independente da rodada exata)
            if not (contagem and contagem.divergencia
                    and not getattr(contagem, 'para_ajuste', False)):
                continue

        resultado.append({
            "codigo": item.codigo,
            "produto": item.produto,
            "local_fisico": item.local_fisico,
            # quantidade_base INTENCIONALMENTE OMITIDA
            "ja_contado": contagem is not None,
            "rodada": rodada,
        })

    return sorted(resultado, key=lambda x: (x.get("local_fisico") or "zzz", x["codigo"]))


# ── Supervisor ────────────────────────────────────────────────────────────────

@router.get("/{sessao_id}/token-supervisor")
def get_token_supervisor(sessao_id: str, db: Session = Depends(get_db)):
    """Retorna o token do supervisor (cria se não existir)."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if not sessao.token_supervisor:
        sessao.token_supervisor = secrets.token_hex(4).upper()
        db.commit()
        db.refresh(sessao)
    return {
        "token": sessao.token_supervisor,
        "supervisor_url": f"/supervisor/{sessao_id}?token={sessao.token_supervisor}",
    }


@router.post("/{sessao_id}/gerar-token-supervisor")
def gerar_token_supervisor(sessao_id: str, db: Session = Depends(get_db)):
    """Regenera o token do supervisor (invalida o anterior)."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    sessao.token_supervisor = secrets.token_hex(4).upper()
    db.commit()
    db.refresh(sessao)
    return {
        "token": sessao.token_supervisor,
        "supervisor_url": f"/supervisor/{sessao_id}?token={sessao.token_supervisor}",
    }


@router.get("/{sessao_id}/qrcode-supervisor")
def qrcode_supervisor(sessao_id: str, base_url: str = "", db: Session = Depends(get_db)):
    """QR Code PNG para acesso do supervisor."""
    import qrcode as qrcode_lib
    _validar_base_url(base_url)
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if not sessao.token_supervisor:
        sessao.token_supervisor = secrets.token_hex(4).upper()
        db.commit()
        db.refresh(sessao)

    path = f"/supervisor/{sessao_id}?token={sessao.token_supervisor}"
    full_url = f"{base_url.rstrip('/')}{path}" if base_url else path

    qr = qrcode_lib.QRCode(version=None, error_correction=qrcode_lib.constants.ERROR_CORRECT_M,
                            box_size=10, border=2)
    qr.add_data(full_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#4F46E5", back_color="white")  # indigo para diferenciar
    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/{sessao_id}/itens-supervisor")
def itens_supervisor(sessao_id: str, token: str, db: Session = Depends(get_db)):
    """
    Itens para o supervisor: SOMENTE divergentes/para-ajuste, COM local_fisico.
    Ativado a partir da R2 (quando faltando_r2 > 0).
    NÃO inclui quantidade base.
    """
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if not hmac.compare_digest(sessao.token_supervisor or "", token):
        raise HTTPException(status_code=403, detail="Token de supervisor inválido")

    logger.info("supervisor_access sessao=%s", sessao_id)
    progresso = item_repo.calcular_progresso_rodada(db, sessao_id)

    # Supervisor só tem acesso a partir da R2
    if progresso.get("faltando_r1", 1) > 0:
        return {
            "ativo": False,
            "motivo": "Supervisor liberado após conclusão da 1ª rodada",
            "itens": [],
        }

    itens = item_repo.listar_itens(db, sessao_id)
    contagens_map = {c.codigo: c for c in item_repo.listar_contagens(db, sessao_id)}

    resultado = []
    for item in itens:
        contagem = contagens_map.get(item.codigo)
        # Supervisor vê apenas DIVERGENTES ativos — PARA_AJUSTE já está resolvido
        if not contagem or not contagem.divergencia:
            continue
        if getattr(contagem, 'para_ajuste', False):
            continue  # já aceito para ajuste — não precisa de ação do supervisor

        resultado.append({
            "codigo": item.codigo,
            "produto": item.produto,
            "local_fisico": item.local_fisico,  # localização para o supervisor encontrar
            # sem quantidade_base
            "rodada": contagem.rodada,
            "para_ajuste": getattr(contagem, 'para_ajuste', False),
            "operador": contagem.operador,
            "status": "Para Ajuste" if getattr(contagem, 'para_ajuste', False) else "Divergente",
        })

    return {
        "ativo": True,
        "total_divergentes": len(resultado),
        "itens": sorted(resultado, key=lambda x: (x.get("local_fisico") or "zzz", x["codigo"])),
    }


# ── Pausa e retomada ──────────────────────────────────────────────────────────

@router.patch("/{sessao_id}/pausar")
async def pausar_sessao(sessao_id: str, token_admin: str, background_tasks: BackgroundTasks,
                        previsao_retomada: Optional[str] = None, db: Session = Depends(get_db)):
    """Pausa a sessão. Operadores veem tela 'Sessão Pausada' via WS."""
    from datetime import datetime, timezone
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    verificar_token_admin(sessao, token_admin)
    if sessao.status != StatusSessao.ativa:
        raise HTTPException(status_code=409, detail="Sessão não está ativa")
    sessao.status = StatusSessao.pausada
    sessao.pausada_em = datetime.now(timezone.utc)
    sessao.previsao_retomada = previsao_retomada
    db.commit()
    db.refresh(sessao)
    background_tasks.add_task(manager.broadcast, sessao_id, {
        "tipo": "sessao_status_alterado", "status": "pausada",
        "mensagem": "Sessão pausada pelo administrador. Aguarde retomada.",
        "previsao_retomada": previsao_retomada,
    })
    return {"status": "pausada", "pausada_em": sessao.pausada_em, "previsao_retomada": previsao_retomada}


@router.patch("/{sessao_id}/retomar")
async def retomar_sessao(sessao_id: str, token_admin: str, background_tasks: BackgroundTasks,
                         db: Session = Depends(get_db)):
    """Retoma a sessão pausada. Gera novo token de acesso e avisa operadores via WS."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    verificar_token_admin(sessao, token_admin)
    if sessao.status != StatusSessao.pausada:
        raise HTTPException(status_code=409, detail="Sessão não está pausada")
    sessao.status = StatusSessao.ativa
    sessao.pausada_em = None
    sessao.previsao_retomada = None
    # Gera novo token (operadores com token antigo de pausa não entram)
    # Mantém rodada_token atual — operadores voltam à mesma rodada que estava antes da pausa
    sessao.token_acesso = secrets.token_hex(8).upper()
    if not sessao.rodada_token:
        sessao.rodada_token = 1
    db.commit()
    db.refresh(sessao)
    background_tasks.add_task(manager.broadcast, sessao_id, {
        "tipo": "sessao_status_alterado", "status": "ativa",
        "mensagem": "Sessão retomada! Use o novo token para continuar.",
        "novo_token": sessao.token_acesso,
    })
    return {
        "status": "ativa",
        "novo_token": sessao.token_acesso,
        "mobile_url": f"/mobile/{sessao_id}?token={sessao.token_acesso}",
    }


# ── Helper ────────────────────────────────────────────────────────────────────

def _grupo_dict(grupo, sessao_id: str) -> dict:
    return {
        "id": grupo.id,
        "sessao_id": grupo.sessao_id,
        "nome": grupo.nome,
        "filtro": grupo.filtro,
        "tipo_filtro": grupo.tipo_filtro,
        "token": grupo.token,
        "cor": grupo.cor,
        "mobile_url": f"/mobile/{sessao_id}?token={grupo.token}&grupo={grupo.id}",
    }
