"""
Endpoints de integração com sistemas externos (TOTVS Protheus, futuro SAP).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import verificar_token_admin
from app.database import get_db
from app.repositories import sessao_repo
from app.services.sessao_service import montar_divergencias, montar_inventario_completo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integracoes", tags=["Integrações ERP"])


# ── TOTVS ─────────────────────────────────────────────────────────────────────

@router.get("/totvs/status")
def status_totvs() -> dict:
    """
    Verifica a configuração da integração TOTVS.
    Mostra se está pronta, em dry-run ou aguardando configuração.
    Não expõe credenciais.
    """
    from app.integrations.totvs import info_configuracao
    info = info_configuracao()
    return {
        **info,
        "instrucoes": (
            "Configure TOTVS_URL, TOTVS_USER e TOTVS_PASSWORD no .env para ativar a integração real. "
            "Com TOTVS_DRY_RUN=true o payload é gerado mas nenhum dado é enviado ao ERP."
        ) if not info["configurado"] else "Integração TOTVS configurada e pronta.",
    }


@router.post("/totvs/sessao/{sessao_id}/enviar-ajuste")
def enviar_ajuste_totvs(
    sessao_id: str,
    token_admin: str = Query(...),
    apenas_divergentes: bool = Query(default=True, description="true = envia só os divergentes; false = envia todos os itens"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Envia os ajustes de estoque da sessão ao TOTVS Protheus.

    Em modo dry-run (padrão enquanto TOTVS não estiver configurado), retorna
    o payload exato que SERIA enviado — ideal para validar antes de ativar.

    O TOTVS recebe um documento de ajuste de estoque com:
    - Código do produto (campo PRODUTO no Protheus)
    - Quantidade encontrada no inventário
    - Diferença em relação à base
    - Referência ao documento de origem (código da sessão INVIQ)
    """
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    verificar_token_admin(sessao, token_admin)

    status_str = str(sessao.status.value if hasattr(sessao.status, "value") else sessao.status)
    if status_str not in ("concluida", "ativa"):
        raise HTTPException(
            status_code=422,
            detail="Só é possível enviar ajustes de sessões ativas ou concluídas."
        )

    # Bloqueia envio ao ERP apenas em sessões concluídas que ainda aguardam segunda aprovação
    if status_str == "concluida":
        ok_val = getattr(sessao, "segunda_aprovacao_ok", None)
        if ok_val == 0:
            raise HTTPException(
                status_code=403,
                detail="Este inventário requer segunda aprovação antes do envio ao ERP. "
                       "Aguarde a confirmação do segundo aprovador via POST /segunda-aprovacao/aprovar."
            )
        if ok_val == 2:
            raise HTTPException(
                status_code=403,
                detail="Este inventário foi rejeitado na segunda aprovação e não pode ser enviado ao ERP."
            )

    if apenas_divergentes:
        itens = montar_divergencias(db, sessao_id)
    else:
        itens = [
            i for i in montar_inventario_completo(db, sessao_id)
            if i.get("quantidade_encontrada") is not None
        ]

    if not itens:
        raise HTTPException(
            status_code=422,
            detail="Nenhum item para enviar. "
                   + ("Não há divergências registradas." if apenas_divergentes else "Nenhum item foi contado ainda.")
        )

    from app.integrations.totvs import enviar_ajuste_estoque
    resultado = enviar_ajuste_estoque(
        sessao_codigo=sessao.codigo,
        sessao_nome=sessao.nome,
        itens_divergentes=itens,
        data_inventario=sessao.data_inicio.strftime("%Y%m%d") if sessao.data_inicio else None,
    )

    logger.info(
        "TOTVS envio sessao=%s itens=%d sucesso=%s dry_run=%s",
        sessao_id, len(itens), resultado["sucesso"], resultado["dry_run"],
    )
    return {
        **resultado,
        "sessao_id": sessao_id,
        "sessao_codigo": sessao.codigo,
        "total_itens_enviados": len(itens),
    }


@router.get("/totvs/ajuste/{protocolo}/status")
def consultar_ajuste_totvs(
    protocolo: str,
    token_admin: str = Query(...),
    sessao_id: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    """Consulta o status de um ajuste já enviado ao TOTVS pelo protocolo retornado."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    verificar_token_admin(sessao, token_admin)

    from app.integrations.totvs import consultar_status_ajuste
    return consultar_status_ajuste(protocolo)


@router.get("/totvs/sessao/{sessao_id}/preview-payload")
def preview_payload_totvs(
    sessao_id: str,
    token_admin: str = Query(...),
    apenas_divergentes: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict:
    """
    Gera e retorna o payload TOTVS sem enviar nada.
    Use para revisar o mapeamento antes de ativar a integração real.
    """
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    verificar_token_admin(sessao, token_admin)

    itens = montar_divergencias(db, sessao_id) if apenas_divergentes else [
        i for i in montar_inventario_completo(db, sessao_id)
        if i.get("quantidade_encontrada") is not None
    ]

    from app.integrations.totvs import _montar_payload_ajuste, info_configuracao
    payload = _montar_payload_ajuste(
        sessao_codigo=sessao.codigo,
        sessao_nome=sessao.nome,
        itens_divergentes=itens,
        data_inventario=sessao.data_inicio.strftime("%Y%m%d") if sessao.data_inicio else None,
    )
    return {
        "payload": payload,
        "total_linhas": len(payload["itens"]),
        "configuracao_totvs": info_configuracao(),
        "aviso": "Este é apenas um preview — nenhum dado foi enviado ao TOTVS.",
    }
