import secrets
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import sessao_repo, item_repo
from app.schemas import SessaoCreate, SessaoResponse, SessaoStats, RodadasInfo, ProgressoRodada, ValorEstoqueStats

router = APIRouter(prefix="/sessoes", tags=["Sessões"])


@router.get("/", response_model=list[SessaoResponse])
def listar_sessoes(db: Session = Depends(get_db)):
    return sessao_repo.listar_sessoes_com_stats(db)


@router.post("/", response_model=SessaoResponse, status_code=201)
def criar_sessao(payload: SessaoCreate, db: Session = Depends(get_db)):
    return sessao_repo.criar_sessao(db, nome=payload.nome)


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
def concluir_sessao(sessao_id: str, db: Session = Depends(get_db)):
    sessao = sessao_repo.concluir_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return sessao


@router.patch("/{sessao_id}/cancelar", response_model=SessaoResponse)
def cancelar_sessao(sessao_id: str, db: Session = Depends(get_db)):
    sessao = sessao_repo.cancelar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
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
def verificar_token(sessao_id: str, token: str, db: Session = Depends(get_db)):
    """Verifica se um token de acesso é válido para a sessão."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    valido = (sessao.token_acesso == token)
    return {"valido": valido, "rodada": sessao.rodada_token or 1}


@router.get("/{sessao_id}/qrcode-acesso")
def qrcode_acesso(sessao_id: str, base_url: str = "", db: Session = Depends(get_db)):
    """Retorna o QR Code como imagem PNG para acesso mobile.
    Parâmetro `base_url` deve ser a origem completa (ex: http://192.168.1.10:8000).
    """
    import qrcode as qrcode_lib
    from io import BytesIO
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
