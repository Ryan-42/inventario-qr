import hmac
import json
import logging
import secrets
import urllib.request
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from sqlalchemy.orm import Session

from app.auth import verificar_token_admin as _verificar_token_admin, get_admin_logado
from app.database import get_db
from app.limiter import limiter
from app.repositories import sessao_repo, item_repo
from app.schemas import SessaoCreate, SessaoResponse, SessaoCreateResponse, SessaoStats, RodadasInfo, ProgressoRodada, ValorEstoqueStats
from app.models.sessao import Sessao, StatusSessao

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessoes", tags=["Sessões"])


def _webhook_url_segura(url: str) -> bool:
    """Valida URL do webhook em tempo de dispatch — previne SSRF com IPs privados."""
    import ipaddress as _ip
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        if not host or host in ("localhost", "localhost.localdomain"):
            return False
        try:
            addr = _ip.ip_address(host)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_unspecified:
                return False
        except ValueError:
            pass  # hostname, not an IP — allow
        return True
    except Exception:
        return False


def _disparar_webhook(webhook_url: str, payload: dict) -> None:
    """Dispara HTTP POST para webhook_url com o payload JSON. Falhas são apenas logadas."""
    if not _webhook_url_segura(webhook_url):
        logger.warning("webhook_bloqueado url=%s (endereço privado ou inválido)", webhook_url)
        return
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            webhook_url, data=data,
            headers={"Content-Type": "application/json", "User-Agent": "INVIQ-Webhook/1.0"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.warning("webhook_failed url=%s erro=%s", webhook_url, exc)


@router.get("/", response_model=list[SessaoResponse])
@limiter.limit("60/minute")
async def listar_sessoes(request: Request, db: Session = Depends(get_db), _admin=Depends(get_admin_logado)):
    return sessao_repo.listar_sessoes_com_stats(db)


@router.post("/", response_model=SessaoCreateResponse, status_code=201)
@limiter.limit("20/hour")
async def criar_sessao(request: Request, payload: SessaoCreate, db: Session = Depends(get_db), _admin=Depends(get_admin_logado)):
    # Valida filial se informada
    if getattr(payload, "filial_id", None):
        from app.models.filial import Filial
        if not db.query(Filial).filter(Filial.id == payload.filial_id).first():
            raise HTTPException(status_code=404, detail="Filial não encontrada.")
    sessao = sessao_repo.criar_sessao(db, nome=payload.nome, webhook_url=payload.webhook_url, filial_id=getattr(payload, "filial_id", None))
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
@limiter.limit("120/minute")
async def buscar_sessao(request: Request, sessao_id: str, db: Session = Depends(get_db)):
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
async def concluir_sessao(sessao_id: str, background_tasks: BackgroundTasks,
                          db: Session = Depends(get_db), _admin=Depends(get_admin_logado)):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

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
    # Notificação por e-mail ao concluir
    try:
        stats_email = sessao_repo.stats_sessao(db, sessao_id)
        total_email = stats_email.get("total", 0)
        divs_email  = stats_email.get("divergencias", 0)
        taxa_email  = round((total_email - divs_email) / total_email * 100, 1) if total_email else 0
        ops_email   = list({c.operador for c in item_repo.listar_contagens(db, sessao_id) if c.operador})
        from app.services.email_service import notificar_sessao_concluida, notificar_alta_divergencia
        from app.services.sessao_service import montar_divergencias
        background_tasks.add_task(
            notificar_sessao_concluida,
            sessao_id, sessao.nome, sessao.codigo,
            total_email, divs_email, taxa_email, ops_email,
        )
        if divs_email > 0:
            taxa_div = round(divs_email / total_email * 100, 1) if total_email else 0
            background_tasks.add_task(
                notificar_alta_divergencia,
                sessao_id, sessao.nome, sessao.codigo,
                taxa_div, montar_divergencias(db, sessao_id),
            )
    except Exception as _exc:
        logger.warning("Email notification failed (non-fatal): %s", _exc)
    stats = sessao_repo.buscar_sessao_com_stats(db, sessao_id)
    if stats is None:
        raise HTTPException(status_code=500, detail="Erro interno ao buscar sessão concluída.")
    return stats


@router.patch("/{sessao_id}/cancelar", response_model=SessaoResponse)
async def cancelar_sessao(sessao_id: str, background_tasks: BackgroundTasks,
                          db: Session = Depends(get_db), _admin=Depends(get_admin_logado)):
    sessao_atual = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao_atual:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
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
    stats = sessao_repo.buscar_sessao_com_stats(db, sessao_id)
    if stats is None:
        raise HTTPException(status_code=500, detail="Erro interno ao buscar sessão cancelada.")
    return stats


@router.delete("/{sessao_id}", status_code=204)
async def deletar_sessao(sessao_id: str, db: Session = Depends(get_db), _admin=Depends(get_admin_logado)):
    """Remove permanentemente a sessão e todos os dados associados (itens, contagens, grupos)."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if sessao.status == StatusSessao.concluida:
        raise HTTPException(
            status_code=409,
            detail="Sessão concluída não pode ser deletada — os dados fazem parte do registro de auditoria.",
        )
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
def get_token_acesso(sessao_id: str, db: Session = Depends(get_db), _admin=Depends(get_admin_logado)):
    """Retorna o token e QR code de acesso mobile da sessão."""
    from sqlalchemy import update as sa_update
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if not sessao.token_acesso:
        # UPDATE atômico WHERE token_acesso IS NULL evita race condition entre dois requests
        # simultâneos gerando tokens diferentes — apenas um INSERT vence, o outro é no-op.
        novo_token = secrets.token_hex(8).upper()
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
def gerar_novo_token(sessao_id: str, rodada: int = 1, db: Session = Depends(get_db), _admin=Depends(get_admin_logado)):
    """Gera um novo token de acesso (invalida o anterior). Requer JWT admin."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
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
        novo_token = secrets.token_hex(8).upper()
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


# ── Aprovação 4 olhos ─────────────────────────────────────────────────────────

@router.get("/{sessao_id}/segunda-aprovacao")
def status_segunda_aprovacao(sessao_id: str, db: Session = Depends(get_db)) -> dict:
    """
    Retorna o status da segunda aprovação.
    Expõe o token para que o gestor envie ao segundo aprovador (por e-mail, etc.)
    """
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    status_map = {0: "pendente", 1: "aprovada", 2: "rejeitada"}
    ok_val = getattr(sessao, "segunda_aprovacao_ok", 0) or 0
    return {
        "sessao_id": sessao_id,
        "status": status_map.get(ok_val, "pendente"),
        "aprovada": ok_val == 1,
        "rejeitada": ok_val == 2,
        "segunda_aprovacao_por": getattr(sessao, "segunda_aprovacao_por", None),
        "segunda_aprovacao_em": (
            sessao.segunda_aprovacao_em.isoformat()
            if getattr(sessao, "segunda_aprovacao_em", None) else None
        ),
        "token_segunda_aprovacao": getattr(sessao, "token_segunda_aprovacao", None),
    }


@router.post("/{sessao_id}/segunda-aprovacao/aprovar")
def aprovar_segunda_vez(
    sessao_id: str,
    token_segunda_aprovacao: str,
    aprovador: str = "Segundo Aprovador",
    db: Session = Depends(get_db),
) -> dict:
    """
    Segundo aprovador confirma o inventário, liberando o envio ao TOTVS.
    Usa token_segunda_aprovacao (diferente do token_admin do criador).

    Workflow:
    1. Gestor 1 conclui a sessão (PATCH /concluir com token_admin)
    2. Gestor 2 acessa este endpoint com token_segunda_aprovacao para aprovar
    3. Apenas sessões concluídas e com segunda_aprovacao_ok == 0 podem ser aprovadas
    """
    from datetime import datetime, timezone as _tz
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    status_sessao = str(sessao.status.value if hasattr(sessao.status, "value") else sessao.status)
    if status_sessao != "concluida":
        raise HTTPException(
            status_code=422,
            detail="Só é possível aprovar sessões com status 'concluida'."
        )

    ok_val = getattr(sessao, "segunda_aprovacao_ok", 0) or 0
    if ok_val == 1:
        raise HTTPException(status_code=409, detail="Esta sessão já foi aprovada pelo segundo aprovador.")
    if ok_val == 2:
        raise HTTPException(status_code=409, detail="Esta sessão foi rejeitada. Não pode ser aprovada.")

    token_esperado = getattr(sessao, "token_segunda_aprovacao", None)
    if not token_esperado:
        raise HTTPException(status_code=409, detail="Sessão sem token de segunda aprovação configurado.")
    if not hmac.compare_digest(token_esperado, token_segunda_aprovacao or ""):
        raise HTTPException(status_code=403, detail="Token de segunda aprovação inválido.")

    sessao.segunda_aprovacao_ok = 1
    sessao.segunda_aprovacao_por = aprovador
    sessao.segunda_aprovacao_em = datetime.now(_tz.utc)
    db.commit()

    logger.info("segunda_aprovacao aprovada sessao=%s por=%s", sessao_id, aprovador)
    return {
        "mensagem": "Segunda aprovação confirmada. O inventário está liberado para envio ao ERP.",
        "aprovador": aprovador,
        "aprovado_em": sessao.segunda_aprovacao_em.isoformat(),
    }


@router.post("/{sessao_id}/segunda-aprovacao/rejeitar")
def rejeitar_segunda_vez(
    sessao_id: str,
    token_segunda_aprovacao: str,
    motivo: str = "Divergências não justificadas",
    aprovador: str = "Segundo Aprovador",
    db: Session = Depends(get_db),
) -> dict:
    """
    Segundo aprovador rejeita o inventário, impedindo o envio ao TOTVS.
    A sessão pode ser reaberta pelo gestor para correções.
    """
    from datetime import datetime, timezone as _tz
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    status_sessao = str(sessao.status.value if hasattr(sessao.status, "value") else sessao.status)
    if status_sessao != "concluida":
        raise HTTPException(status_code=422, detail="Só é possível rejeitar sessões com status 'concluida'.")

    ok_val = getattr(sessao, "segunda_aprovacao_ok", 0) or 0
    if ok_val == 1:
        raise HTTPException(status_code=409, detail="Esta sessão já foi aprovada. Não pode ser rejeitada.")
    if ok_val == 2:
        raise HTTPException(status_code=409, detail="Esta sessão já foi rejeitada.")

    token_esperado = getattr(sessao, "token_segunda_aprovacao", None)
    if not token_esperado:
        raise HTTPException(status_code=409, detail="Sessão sem token de segunda aprovação configurado.")
    if not hmac.compare_digest(token_esperado, token_segunda_aprovacao or ""):
        raise HTTPException(status_code=403, detail="Token de segunda aprovação inválido.")

    sessao.segunda_aprovacao_ok = 2
    sessao.segunda_aprovacao_por = aprovador
    sessao.segunda_aprovacao_em = datetime.now(_tz.utc)
    db.commit()

    logger.info("segunda_aprovacao rejeitada sessao=%s por=%s motivo=%s", sessao_id, aprovador, motivo)
    return {
        "mensagem": f"Segunda aprovação rejeitada: {motivo}",
        "aprovador": aprovador,
        "rejeitado_em": sessao.segunda_aprovacao_em.isoformat(),
    }
