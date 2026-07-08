from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.orm import Session

from app.auth import get_admin_logado, get_admin_logado_opcional
from app.database import get_db
from app.limiter import limiter
from app.repositories import sessao_repo, item_repo, grupo_repo
from app.services.excel_service import importar_planilha
from app.schemas import ItemBaseResponse, BuscaItemResponse, ItemComStatus, ItemListaOperador
from app.services.sessao_service import montar_inventario_completo
from app.models.sessao import StatusSessao


def _filtrar_por_grupo(itens: list[dict], grupo) -> list[dict]:
    prefixos = [p.strip().upper() for p in (grupo.filtro or '').split(',') if p.strip()]
    tipo = grupo.tipo_filtro or 'todos'
    if tipo == 'todos' or '*' in prefixos:
        return itens
    return [
        i for i in itens
        if (tipo == 'prefixo' and any(i['codigo'].upper().startswith(p) for p in prefixos))
        or (tipo == 'lista' and i['codigo'].upper() in prefixos)
    ]


router = APIRouter(prefix="/sessoes", tags=["Itens"])

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_EXTENSOES_XLSX = (".xlsx", ".xls")
_EXTENSOES_XLSX_CSV = (".xlsx", ".xls", ".csv")


_TIPOS_MIME_ACEITOS = frozenset({
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/octet-stream",
    "text/csv",
    "application/csv",
    "",  # ausente / não informado pelo cliente
})


def _validar_arquivo(file: UploadFile, permitir_csv: bool = False) -> None:
    extensoes = _EXTENSOES_XLSX_CSV if permitir_csv else _EXTENSOES_XLSX
    if not (file.filename or "").endswith(extensoes):
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo deve ser {', '.join(extensoes)}",
        )
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in _TIPOS_MIME_ACEITOS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de arquivo não aceito: {mime}. Use .xlsx, .xls ou .csv.",
        )


@router.post("/{sessao_id}/validar-planilha")
async def validar_planilha(
    sessao_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin=Depends(get_admin_logado),
):
    """Valida planilha com o ValidationAgent sem salvar no banco. Requer JWT admin."""
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
    resultado = agente.validate(itens)
    # Inclui preview das primeiras 5 linhas para o frontend mostrar antes de confirmar o import
    resultado["preview_rows"] = [
        {
            "codigo": it.get("codigo", ""),
            "produto": it.get("produto", ""),
            "quantidade": it.get("quantidade_base", it.get("quantidade", 0)),
            "local_fisico": it.get("local_fisico", ""),
            "valor_estoque": it.get("valor_estoque"),
        }
        for it in itens[:5]
    ]
    resultado["total_rows"] = len(itens)
    return resultado


@router.post("/{sessao_id}/upload", status_code=201)
@limiter.limit("10/hour")
async def upload_planilha(
    request: Request,
    sessao_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin=Depends(get_admin_logado),
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

    # CSV também é aceito — importar_planilha já trata; antes só o
    # /validar-planilha aceitava CSV e o upload rejeitava (inconsistência).
    _validar_arquivo(file, permitir_csv=True)

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
@limiter.limit("60/minute")
async def listar_itens_com_status(request: Request, sessao_id: str, db: Session = Depends(get_db),
                                  _admin=Depends(get_admin_logado)):
    """Inventário completo com quantidade_base. Requer JWT admin — para
    operadores existe o /itens-operador (contagem cega, sem quantidades)."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return montar_inventario_completo(db, sessao_id)


@router.get("/{sessao_id}/itens-operador", response_model=list[ItemListaOperador])
@limiter.limit("60/minute")
async def listar_itens_operador(
    request: Request,
    sessao_id: str,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
    admin=Depends(get_admin_logado_opcional),
):
    """Lista itens para o operador (contagem cega): código, descrição e local — sem quantidade.
    Requer token de operador (geral, supervisor ou grupo) ou JWT admin."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if sessao.status != StatusSessao.ativa:
        raise HTTPException(status_code=409, detail="Sessão não está ativa")
    grupo = None
    if not admin:
        from app.routes.contagens import _validar_token_operador
        _validar_token_operador(sessao, token or "", request, db)
    if token:
        grupo = grupo_repo.buscar_grupo_por_token(db, sessao_id, token)
    itens = item_repo.listar_itens_para_operador(db, sessao_id)
    if grupo:
        itens = _filtrar_por_grupo(itens, grupo)
    return itens


@router.get("/{sessao_id}/buscar/{codigo}", response_model=BuscaItemResponse)
@limiter.limit("200/minute")
async def buscar_item_por_codigo(request: Request, sessao_id: str, codigo: str,
                                 token: str = "",
                                 db: Session = Depends(get_db),
                                 admin=Depends(get_admin_logado_opcional)):
    """Busca um item pelo código (usado pelo scanner mobile e pelo painel admin).

    Contagem cega: operadores (token) NÃO recebem quantidade_base nem a
    contagem anterior — apenas admins (JWT) veem esses campos.
    """
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    if not admin:
        from app.routes.contagens import _validar_token_operador
        _validar_token_operador(sessao, token, request, db)

    item = item_repo.buscar_item(db, sessao_id, codigo)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{codigo}' não encontrado na base desta sessão")

    contagem = item_repo.buscar_contagem(db, sessao_id, codigo)

    return {
        "codigo": item.codigo,
        "produto": item.produto,
        "quantidade_base": item.quantidade_base if admin else None,
        "ja_contado": contagem is not None,
        "rodada_atual": contagem.rodada if contagem else 0,
        "para_ajuste": bool(contagem.para_ajuste) if contagem else False,
        "contagem_anterior": contagem if admin else None,
    }
