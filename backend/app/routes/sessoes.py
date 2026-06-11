import secrets
import hmac
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from sqlalchemy.orm import Session

from app.auth import verificar_token_admin as _verificar_token_admin
from app.database import get_db
from app.limiter import limiter
from app.repositories import sessao_repo, item_repo
from app.schemas import SessaoCreate, SessaoResponse, SessaoCreateResponse, SessaoStats, RodadasInfo, ProgressoRodada, ValorEstoqueStats
from app.models.sessao import Sessao, StatusSessao

router = APIRouter(prefix="/sessoes", tags=["Sessões"])

import logging as _logging
_logger = _logging.getLogger(__name__)


def _disparar_webhook(webhook_url: str, payload: dict) -> None:
    """Dispara HTTP POST para webhook_url com o payload JSON. Falhas são apenas logadas."""
    import urllib.request, json as _json
    try:
        data = _json.dumps(payload).encode()
        req = urllib.request.Request(
            webhook_url, data=data,
            headers={"Content-Type": "application/json", "User-Agent": "INVIQ-Webhook/1.0"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        _logger.warning("webhook_failed url=%s erro=%s", webhook_url, exc)


@router.get("/", response_model=list[SessaoResponse])
def listar_sessoes(db: Session = Depends(get_db)):
    return sessao_repo.listar_sessoes_com_stats(db)


@router.post("/", response_model=SessaoCreateResponse, status_code=201)
@limiter.limit("20/hour")
async def criar_sessao(request: Request, payload: SessaoCreate, db: Session = Depends(get_db)):
    sessao = sessao_repo.criar_sessao(db, nome=payload.nome, webhook_url=payload.webhook_url)
    return {
        "id": sessao.id,
        "codigo": sessao.codigo,
        "nome": sessao.nome,
        "status": sessao.status,
        "data_inicio": sessao.data_inicio,
        "data_fim": sessao.data_fim,
        "total_itens": 0,
        "itens_contados": 0,
        "total_divergencias": 0,
        "token_admin": sessao.token_admin,
        "webhook_url": sessao.webhook_url,
    }


@router.get("/{sessao_id}/verificar-admin")
@limiter.limit("15/minute")
async def verificar_admin(request: Request, sessao_id: str, token: str, db: Session = Depends(get_db)):
    """Verifica se o token_admin é válido para esta sessão."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    # hmac.compare_digest evita timing attack
    valido = hmac.compare_digest(sessao.token_admin or "", token)
    return {"valido": valido}



@router.get("/{sessao_id}", response_model=SessaoResponse)
def buscar_sessao(sessao_id: str, db: Session = Depends(get_db)):
    sessao_dict = sessao_repo.buscar_sessao_com_stats(db, sessao_id)
    if not sessao_dict:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return sessao_dict


@router.get("/{sessao_id}/stats", response_model=SessaoStats)
def stats_sessao(sessao_id: str, db: Session = Depends(get_db)):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return sessao_repo.stats_sessao(db, sessao_id)



@router.patch("/{sessao_id}/concluir", response_model=SessaoResponse)
async def concluir_sessao(sessao_id: str, token_admin: str,
                          background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    _verificar_token_admin(sessao, token_admin)

    if sessao.status != StatusSessao.ativa:
        raise HTTPException(
            status_code=409,
            detail=f"Sessão está '{sessao.status.value}' e não pode ser concluída.",
        )

    progresso = item_repo.calcular_progresso_rodada(db, sessao_id)
    # Default False = assume sem itens se chave ausente (proteção defensiva)
    if not progresso.get("tem_itens", False):
        raise HTTPException(status_code=422, detail="Nenhum item importado. Importe a planilha antes de concluir.")
    if not progresso["completa"]:
        partes = []
        if progresso["faltando_r1"] > 0:
            partes.append(f"{progresso['faltando_r1']} item(s) ainda não foram contados")
        if progresso["faltando_r2"] > 0:
            partes.append(f"{progresso['faltando_r2']} item(s) divergentes aguardam recontagem")
        raise HTTPException(
            status_code=422,
            detail=f"Não é possível concluir: {'; '.join(partes) or 'inventário incompleto'}. "
                   "Todos os itens devem estar Certo ou Para Ajuste.",
        )

    webhook_url = sessao.webhook_url  # captura antes de concluir (sessao pode ser GCed)
    concluido = sessao_repo.concluir_sessao(db, sessao_id)
    if not concluido:
        raise HTTPException(status_code=409, detail="Sessão não pôde ser concluída (conflito). Tente novamente.")
    from app.websockets.manager import manager
    background_tasks.add_task(manager.broadcast, sessao_id, {
        "tipo": "sessao_status_alterado", "status": "concluida",
        "mensagem": "O inventário foi concluído pelo administrador.",
    })
    if webhook_url:
        stats_wh = sessao_repo.stats_sessao(db, sessao_id)
        background_tasks.add_task(_disparar_webhook, webhook_url, {
            "evento": "sessao_concluida",
            "sessao_id": sessao_id,
            "codigo": sessao.codigo,
            "nome": sessao.nome,
            "total": stats_wh.get("total", 0),
            "conferidos": stats_wh.get("conferidos", 0),
            "divergencias": stats_wh.get("divergencias", 0),
        })
    # Retorna dict com stats reais em vez do ORM sem os campos calculados
    return sessao_repo.buscar_sessao_com_stats(db, sessao_id) or concluido


@router.patch("/{sessao_id}/cancelar", response_model=SessaoResponse)
async def cancelar_sessao(sessao_id: str, token_admin: str,
                          background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    sessao_atual = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao_atual:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    _verificar_token_admin(sessao_atual, token_admin)
    if sessao_atual.status == StatusSessao.concluida:
        raise HTTPException(status_code=409, detail="Sessão já concluída não pode ser cancelada.")
    if sessao_atual.status == StatusSessao.cancelada:
        raise HTTPException(status_code=409, detail="Sessão já está cancelada.")
    cancelado = sessao_repo.cancelar_sessao(db, sessao_id)
    if not cancelado:
        raise HTTPException(status_code=409, detail="Sessão não pôde ser cancelada. Tente novamente.")
    from app.websockets.manager import manager
    background_tasks.add_task(manager.broadcast, sessao_id, {
        "tipo": "sessao_status_alterado", "status": "cancelada",
        "mensagem": "O inventário foi cancelado pelo administrador.",
    })
    return sessao_repo.buscar_sessao_com_stats(db, sessao_id) or cancelado


@router.delete("/{sessao_id}", status_code=204)
async def deletar_sessao(sessao_id: str, token_admin: str, db: Session = Depends(get_db)):
    """Remove permanentemente a sessão e todos os dados associados (itens, contagens, grupos)."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    _verificar_token_admin(sessao, token_admin)
    sessao_repo.deletar_sessao(db, sessao_id)


@router.get("/{sessao_id}/valor-estoque", response_model=ValorEstoqueStats)
def valor_estoque_sessao(sessao_id: str, db: Session = Depends(get_db)):
    """Retorna análise financeira: valor inicial vs final do inventário."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return sessao_repo.calcular_valor_estoque(db, sessao_id)


@router.get("/{sessao_id}/progresso", response_model=ProgressoRodada)
def progresso_rodada(sessao_id: str, db: Session = Depends(get_db)):
    """Retorna progresso da rodada ativa: quantos itens faltam, rodada atual, se está completa."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return item_repo.calcular_progresso_rodada(db, sessao_id)


@router.get("/{sessao_id}/metricas")
def metricas_sessao(sessao_id: str, db: Session = Depends(get_db)):
    """
    Retorna KPIs de produtividade derivados dos dados do inventário.

    Inclui: duração, itens/min, taxa de divergência, taxa de retrabalho,
    % de rastreabilidade e breakdown por operador.
    Não requer autenticação — os dados são agregados, sem PII exposta além de nomes
    de operador (que já constam nas contagens públicas da sessão).
    """
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return sessao_repo.calcular_metricas_sessao(db, sessao_id)


@router.get("/{sessao_id}/token-acesso")
def get_token_acesso(sessao_id: str, db: Session = Depends(get_db)):
    """Retorna o token e QR code de acesso mobile da sessão."""
    from sqlalchemy import update as sa_update
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if not sessao.token_acesso:
        # UPDATE atômico WHERE token_acesso IS NULL evita race condition entre dois requests
        # simultâneos gerando tokens diferentes — apenas um INSERT vence, o outro é no-op.
        novo_token = secrets.token_hex(4).upper()
        db.execute(
            sa_update(Sessao)
            .where(Sessao.id == sessao_id,
                   Sessao.token_acesso.is_(None))
            .values(token_acesso=novo_token)
        )
        db.commit()
        db.refresh(sessao)
    rodada = sessao.rodada_token or 1
    mobile_url = f"/mobile/{sessao_id}?token={sessao.token_acesso}"
    return {"token": sessao.token_acesso, "rodada": rodada, "mobile_url": mobile_url}


@router.post("/{sessao_id}/gerar-token")
def gerar_novo_token(sessao_id: str, token_admin: str, rodada: int = 1, db: Session = Depends(get_db)):
    """Gera um novo token de acesso (invalida o anterior). Requer token_admin."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    _verificar_token_admin(sessao, token_admin)
    if sessao.status.value != "ativa":
        raise HTTPException(status_code=409, detail="Sessão não está ativa")
    token = secrets.token_hex(8).upper()
    sessao.token_acesso = token
    sessao.rodada_token = max(1, rodada)
    db.commit()
    mobile_url = f"/mobile/{sessao_id}?token={token}"
    return {"token": token, "rodada": sessao.rodada_token, "mobile_url": mobile_url}


@router.get("/{sessao_id}/verificar-token")
@limiter.limit("15/minute")
async def verificar_token(request: Request, sessao_id: str, token: str, db: Session = Depends(get_db)):
    """Verifica se um token de acesso é válido para a sessão."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    valido = hmac.compare_digest(sessao.token_acesso or "", token)
    return {"valido": valido, "rodada": sessao.rodada_token or 1}


def _validar_base_url(base_url: str) -> None:
    """Garante que base_url usa scheme http ou https (previne phishing via javascript:)."""
    if not base_url:
        return
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="base_url deve usar http ou https")


@router.get("/{sessao_id}/qrcode-acesso")
def qrcode_acesso(sessao_id: str, base_url: str = "", db: Session = Depends(get_db)):
    """Retorna o QR Code como imagem PNG para acesso mobile.
    Parâmetro `base_url` deve ser a origem completa (ex: http://192.168.1.10:8000).
    """
    import qrcode as qrcode_lib
    from io import BytesIO
    from sqlalchemy import update as sa_update
    _validar_base_url(base_url)
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if not sessao.token_acesso:
        novo_token = secrets.token_hex(4).upper()
        db.execute(
            sa_update(Sessao)
            .where(Sessao.id == sessao_id,
                   Sessao.token_acesso.is_(None))
            .values(token_acesso=novo_token)
        )
        db.commit()
        db.refresh(sessao)
    # Usa a base_url passada pelo frontend para garantir URL absoluta no QR
    mobile_path = f"/mobile/{sessao_id}?token={sessao.token_acesso}"
    full_url = f"{base_url.rstrip('/')}{mobile_path}" if base_url else mobile_path
    qr = qrcode_lib.QRCode(version=None, error_correction=qrcode_lib.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(full_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F172A", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/{sessao_id}/rodadas", response_model=RodadasInfo)
def rodadas_sessao(sessao_id: str, db: Session = Depends(get_db)):
    """Retorna resumo das rodadas de contagem e itens pendentes por rodada."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    # Limite de segurança: carrega até 10k contagens para o resumo de rodadas.
    # Para sessões maiores o endpoint /progresso é mais eficiente (usa SQL agregado).
    contagens = item_repo.listar_contagens(db, sessao_id, limit=10_000)
    total_itens = item_repo.contar_itens(db, sessao_id)

    # Agrupa contagens por rodada — conta apenas DIVERGENTES ativos (não para_ajuste)
    por_rodada: dict[int, dict] = {}
    for c in contagens:
        r = getattr(c, "rodada", 1) or 1
        d = por_rodada.setdefault(r, {"total": 0, "divergencias": 0})
        d["total"] += 1
        # Divergência pendente = divergente E não confirmado como para_ajuste
        if c.divergencia and not getattr(c, 'para_ajuste', False):
            d["divergencias"] += 1

    rodada_maxima = max(por_rodada.keys(), default=0)
    total_contagens = sum(d["total"] for d in por_rodada.values())

    # pendentes_recontagem = itens divergentes sem para_ajuste (consistente com /progresso)
    pendentes_recontagem = sum(
        1 for c in contagens
        if c.divergencia and not getattr(c, 'para_ajuste', False)
    )
    r1_pendentes = pendentes_recontagem

    resumos = [
        {
            "numero": r,
            "total": d["total"],
            "divergencias": d["divergencias"],
            "concluida": (
                total_contagens == total_itens if r == 1
                else r1_pendentes == 0
            ),
        }
        for r, d in sorted(por_rodada.items())
    ]

    # Itens divergentes ativos (qualquer rodada) que precisam de recontagem
    divergentes_ativos = [
        c for c in contagens
        if c.divergencia and not getattr(c, 'para_ajuste', False)
    ]
    # Busca produto e quantidade_base apenas para os itens necessários (evita carregar tudo)
    codigos_divergentes = {c.codigo for c in divergentes_ativos}
    itens_map = {}
    if codigos_divergentes:
        itens_lista = item_repo.buscar_itens_por_codigos(db, sessao_id, list(codigos_divergentes))
        itens_map = {i.codigo: i for i in itens_lista}

    proxima_rodada = rodada_maxima + 1 if rodada_maxima > 0 else 2
    itens_segunda = [
        {
            "codigo": c.codigo,
            "produto": itens_map[c.codigo].produto if c.codigo in itens_map else c.codigo,
            "quantidade_base": itens_map[c.codigo].quantidade_base if c.codigo in itens_map else 0,
            "rodada": proxima_rodada,
        }
        for c in divergentes_ativos
    ]

    return {
        "rodada_maxima": rodada_maxima,
        "rodadas": resumos,
        "itens_segunda": itens_segunda,
        "itens_terceira": [],  # subsumido em itens_segunda (sem rodada fixa)
    }
