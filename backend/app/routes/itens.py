from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import sessao_repo, item_repo
from app.services.excel_service import importar_planilha
from app.schemas import ItemBaseResponse, BuscaItemResponse, ItemComStatus
from app.services.sessao_service import montar_inventario_completo
from app.models.sessao import StatusSessao

router = APIRouter(prefix="/sessoes", tags=["Itens"])

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_EXTENSOES_XLSX = (".xlsx", ".xls")
_EXTENSOES_XLSX_CSV = (".xlsx", ".xls", ".csv")


def _validar_arquivo(file: UploadFile, permitir_csv: bool = False) -> None:
    extensoes = _EXTENSOES_XLSX_CSV if permitir_csv else _EXTENSOES_XLSX
    if not (file.filename or "").endswith(extensoes):
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo deve ser {', '.join(extensoes)}",
        )


@router.post("/{sessao_id}/validar-planilha")
async def validar_planilha(
    sessao_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Valida planilha com o ValidationAgent sem salvar no banco."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    _validar_arquivo(file, permitir_csv=True)

    conteudo = await file.read()
    if len(conteudo) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máx 10 MB)")
    try:
        itens = importar_planilha(conteudo, filename=file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from app.agents.validation import ValidationAgent
    agente = ValidationAgent()
    return agente.validate(itens)


@router.post("/{sessao_id}/upload", status_code=201)
async def upload_planilha(
    sessao_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    if sessao.status != StatusSessao.ativa:
        raise HTTPException(
            status_code=409,
            detail=f"Sessão está '{sessao.status.value}' e não aceita novos uploads",
        )

    contagens_count = item_repo.contar_contagens(db, sessao_id)
    if contagens_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Sessão já possui {contagens_count} contagem(ns) registrada(s). Remova as contagens antes de reimportar.",
        )

    _validar_arquivo(file, permitir_csv=False)

    conteudo = await file.read()
    if len(conteudo) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máx 10 MB)")
    try:
        itens = importar_planilha(conteudo, filename=file.filename or "")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erro ao processar planilha: {str(e)}")

    if not itens:
        raise HTTPException(
            status_code=400,
            detail="A planilha não contém itens válidos. Verifique se as colunas 'codigo', 'produto' e 'quantidade_base' estão presentes.",
        )

    if len(itens) > 50_000:
        raise HTTPException(
            status_code=413,
            detail=f"Planilha possui {len(itens)} itens. Máximo permitido: 50.000 por sessão.",
        )

    negativos = [i["codigo"] for i in itens if i.get("quantidade_base", 0) < 0]
    if negativos:
        raise HTTPException(
            status_code=422,
            detail=f"Quantidade base negativa detectada nos itens: {', '.join(negativos[:5])}{'…' if len(negativos) > 5 else ''}",
        )

    total = item_repo.criar_itens_bulk(db, sessao_id, itens)
    return {"mensagem": f"{total} itens importados com sucesso", "total": total}


@router.get("/{sessao_id}/itens", response_model=list[ItemComStatus])
def listar_itens_com_status(sessao_id: str, db: Session = Depends(get_db)):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return montar_inventario_completo(db, sessao_id)


@router.get("/{sessao_id}/buscar/{codigo}", response_model=BuscaItemResponse)
def buscar_item_por_codigo(sessao_id: str, codigo: str, db: Session = Depends(get_db)):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    item = item_repo.buscar_item(db, sessao_id, codigo)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{codigo}' não encontrado na base desta sessão")

    contagem = item_repo.buscar_contagem(db, sessao_id, codigo)

    return {
        "codigo": item.codigo,
        "produto": item.produto,
        "quantidade_base": item.quantidade_base,
        "ja_contado": contagem is not None,
        "rodada_atual": contagem.rodada if contagem else 0,
        "contagem_anterior": contagem,
    }
