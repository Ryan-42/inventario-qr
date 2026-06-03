import secrets
import hmac
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.repositories import sessao_repo, item_repo
from app.schemas import SessaoCreate, SessaoResponse, SessaoCreateResponse, SessaoStats, RodadasInfo, ProgressoRodada, ValorEstoqueStats
from app.models.sessao import StatusSessao

router = APIRouter(prefix="/sessoes", tags=["Sessões"])


@router.get("/", response_model=list[SessaoResponse])
def listar_sessoes(db: Session = Depends(get_db)):
    return sessao_repo.listar_sessoes_com_stats(db)


@router.post("/", response_model=SessaoCreateResponse, status_code=201)
@limiter.limit("20/hour")
async def criar_sessao(request: Request, payload: SessaoCreate, db: Session = Depends(get_db)):
    sessao = sessao_repo.criar_sessao(db, nome=payload.nome)
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
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return sessao


@router.get("/{sessao_id}/stats", response_model=SessaoStats)
def stats_sessao(sessao_id: str, db: Session = Depends(get_db)):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return sessao_repo.stats_sessao(db, sessao_id)


@router.patch("/{sessao_id}/concluir", response_model=SessaoResponse)
async def concluir_sessao(sessao_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    sessao = sessao_repo.concluir_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    from app.websockets.manager import manager
    background_tasks.add_task(manager.broadcast, sessao_id, {
        "tipo": "sessao_status_alterado", "status": "concluida",
        "mensagem": "O inventário foi concluído pelo administrador.",
    })
    return sessao


@router.patch("/{sessao_id}/cancelar", response_model=SessaoResponse)
async def cancelar_sessao(sessao_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    sessao = sessao_repo.cancelar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    from app.websockets.manager import manager
    background_tasks.add_task(manager.broadcast, sessao_id, {
        "tipo": "sessao_status_alterado", "status": "cancelada",
        "mensagem": "O inventário foi cancelado pelo administrador.",
    })
    return sessao


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


@router.get("/{sessao_id}/token-acesso")
def get_token_acesso(sessao_id: str, db: Session = Depends(get_db)):
    """Retorna o token e QR code de acesso mobile da sessão."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    token = sessao.token_acesso
    if not token:
        token = secrets.token_hex(4).upper()
        sessao.token_acesso = token
        db.commit()
        db.refresh(sessao)  # evita DetachedInstanceError ao acessar rodada_token após commit
    rodada = sessao.rodada_token or 1
    mobile_url = f"/mobile/{sessao_id}?token={token}"
    return {"token": token, "rodada": rodada, "mobile_url": mobile_url}


@router.post("/{sessao_id}/gerar-token")
def gerar_novo_token(sessao_id: str, rodada: int = 1, db: Session = Depends(get_db)):
    """Gera um novo token de acesso (invalida o anterior). Usado para cada nova rodada."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if sessao.status.value != "ativa":
        raise HTTPException(status_code=409, detail="Sessão não está ativa")
    token = secrets.token_hex(4).upper()
    sessao.token_acesso = token
    sessao.rodada_token = rodada
    db.commit()
    mobile_url = f"/mobile/{sessao_id}?token={token}"
    return {"token": token, "rodada": rodada, "mobile_url": mobile_url}


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
    _validar_base_url(base_url)
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    token = sessao.token_acesso
    if not token:
        token = secrets.token_hex(4).upper()
        sessao.token_acesso = token
        db.commit()
    # Usa a base_url passada pelo frontend para garantir URL absoluta no QR
    mobile_path = f"/mobile/{sessao_id}?token={token}"
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

    contagens = item_repo.listar_contagens(db, sessao_id)
    itens = item_repo.listar_itens(db, sessao_id)
    itens_map = {i.codigo: i for i in itens}
    total_itens = len(itens)

    # Agrupa contagens por rodada
    por_rodada: dict[int, dict] = {}
    for c in contagens:
        r = getattr(c, "rodada", 1) or 1
        d = por_rodada.setdefault(r, {"total": 0, "divergencias": 0})
        d["total"] += 1
        if c.divergencia:
            d["divergencias"] += 1

    rodada_maxima = max(por_rodada.keys(), default=0)

    total_contagens = sum(d["total"] for d in por_rodada.values())
    r1_pendentes = por_rodada.get(1, {"divergencias": 0})["divergencias"]
    r2_pendentes = por_rodada.get(2, {"divergencias": 0})["divergencias"]

    resumos = [
        {
            "numero": r,
            "total": d["total"],
            "divergencias": d["divergencias"],
            "concluida": (
                total_contagens == total_itens if r == 1
                else r1_pendentes == 0 if r == 2
                else r2_pendentes == 0
            ),
        }
        for r, d in sorted(por_rodada.items())
    ]

    # Itens divergentes da rodada 1 → precisam de 2ª contagem
    divergentes_r1 = [
        c for c in contagens if (getattr(c, "rodada", 1) or 1) == 1 and c.divergencia
    ]
    itens_segunda = [
        {
            "codigo": c.codigo,
            "produto": itens_map[c.codigo].produto if c.codigo in itens_map else c.codigo,
            "quantidade_base": itens_map[c.codigo].quantidade_base if c.codigo in itens_map else 0,
            "rodada": 2,
        }
        for c in divergentes_r1
    ]

    # Itens divergentes da rodada 2 → precisam de 3ª contagem
    divergentes_r2 = [
        c for c in contagens if (getattr(c, "rodada", 1) or 1) == 2 and c.divergencia
    ]
    itens_terceira = [
        {
            "codigo": c.codigo,
            "produto": itens_map[c.codigo].produto if c.codigo in itens_map else c.codigo,
            "quantidade_base": itens_map[c.codigo].quantidade_base if c.codigo in itens_map else 0,
            "rodada": 3,
        }
        for c in divergentes_r2
    ]

    return {
        "rodada_maxima": rodada_maxima,
        "rodadas": resumos,
        "itens_segunda": itens_segunda,
        "itens_terceira": itens_terceira,
    }
