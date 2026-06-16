import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.auth import verificar_token_admin
from app.database import get_db
from app.repositories import sessao_repo, item_repo
from app.services.sessao_service import montar_inventario_completo, montar_divergencias
from app.services.excel_service import exportar_inventario_completo, exportar_divergencias
from app.services.pdf_service import gerar_relatorio_pdf, gerar_etiquetas_pdf
from app.services.relatorio_final_service import gerar_relatorio_final_pdf, gerar_relatorio_final_excel

router = APIRouter(prefix="/sessoes", tags=["Exportações"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class AdminBody(BaseModel):
    token_admin: str


def _tentar_analise_ia(db, sessao) -> dict | None:
    """Tenta rodar análise IA; loga o erro e retorna None se falhar."""
    try:
        from app.agents.analise import AnaliseAgent
        from app.repositories.sessao_repo import stats_sessao, calcular_valor_estoque
        from app.services.sessao_service import montar_inventario_completo, montar_divergencias

        stats = stats_sessao(db, sessao.id)
        itens = montar_inventario_completo(db, sessao.id)
        divergencias_lista = montar_divergencias(db, sessao.id)
        try:
            ve = calcular_valor_estoque(db, sessao.id)
        except Exception as exc_ve:
            logger.warning("Cálculo de valor de estoque falhou — sessao=%s erro=%s", sessao.id, exc_ve)
            ve = None

        result = AnaliseAgent().analisar(
            sessao=sessao,
            stats=stats,
            divergencias=divergencias_lista[:50],
            itens_sample=itens[:30],
            valor_estoque=ve,
        )
        return result if isinstance(result, dict) else None
    except Exception as exc:
        logger.error("AnaliseAgent falhou — sessao=%s erro=%s", sessao.id, exc, exc_info=True)
        return None


@router.post("/{sessao_id}/exportar/completo")
def exportar_completo(sessao_id: str, body: AdminBody, db: Session = Depends(get_db)):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    verificar_token_admin(sessao, body.token_admin)

    itens = montar_inventario_completo(db, sessao_id)
    arquivo = exportar_inventario_completo(itens)

    nome_arquivo = f"inventario_completo_{sessao.codigo}.xlsx"
    return Response(
        content=arquivo,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


@router.post("/{sessao_id}/exportar/divergencias")
def exportar_somente_divergencias(sessao_id: str, body: AdminBody, db: Session = Depends(get_db)):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    verificar_token_admin(sessao, body.token_admin)

    divergencias = montar_divergencias(db, sessao_id)
    arquivo = exportar_divergencias(divergencias)

    nome_arquivo = f"divergencias_{sessao.codigo}.xlsx"
    return Response(
        content=arquivo,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


@router.post("/{sessao_id}/exportar/pdf")
def exportar_pdf(sessao_id: str, body: AdminBody, db: Session = Depends(get_db)):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    verificar_token_admin(sessao, body.token_admin)

    itens = montar_inventario_completo(db, sessao_id)
    stats = sessao_repo.stats_sessao(db, sessao_id)
    arquivo = gerar_relatorio_pdf(sessao, stats, itens)

    nome_arquivo = f"relatorio_{sessao.codigo}.pdf"
    return Response(
        content=arquivo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


@router.post("/{sessao_id}/exportar/relatorio-final-pdf")
def exportar_relatorio_final_pdf(sessao_id: str, body: AdminBody, db: Session = Depends(get_db)):
    """Gera PDF executivo final com análise completa, erros, acertos e impacto financeiro."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    verificar_token_admin(sessao, body.token_admin)

    itens = montar_inventario_completo(db, sessao_id)
    stats = sessao_repo.stats_sessao(db, sessao_id)

    try:
        ve_dict = sessao_repo.calcular_valor_estoque(db, sessao_id)
    except Exception:
        ve_dict = None

    analise_dict = _tentar_analise_ia(db, sessao)
    historico = item_repo.listar_historico(db, sessao_id, limit=50_000)

    arquivo = gerar_relatorio_final_pdf(sessao, stats, itens, valor_estoque=ve_dict, analise_ia=analise_dict, historico=historico)
    nome = f"relatorio_final_{sessao.codigo}.pdf"
    return Response(content=arquivo, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.post("/{sessao_id}/exportar/relatorio-final-excel")
def exportar_relatorio_final_excel_endpoint(sessao_id: str, body: AdminBody, db: Session = Depends(get_db)):
    """Gera Excel final com múltiplas abas: resumo, itens, divergências, recomendações, impacto financeiro e métricas."""
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    verificar_token_admin(sessao, body.token_admin)

    itens = montar_inventario_completo(db, sessao_id)
    stats = sessao_repo.stats_sessao(db, sessao_id)

    try:
        ve_dict = sessao_repo.calcular_valor_estoque(db, sessao_id)
    except Exception:
        ve_dict = None

    analise_dict = _tentar_analise_ia(db, sessao)
    historico = item_repo.listar_historico(db, sessao_id, limit=50_000)
    metricas_dict = sessao_repo.calcular_metricas_sessao(db, sessao_id)

    arquivo = gerar_relatorio_final_excel(sessao, stats, itens, valor_estoque=ve_dict, analise_ia=analise_dict, historico=historico, metricas=metricas_dict)
    nome = f"relatorio_final_{sessao.codigo}.xlsx"
    return Response(content=arquivo, media_type=XLSX_MEDIA_TYPE,
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.post("/{sessao_id}/exportar/etiquetas")
def exportar_etiquetas(sessao_id: str, body: AdminBody, db: Session = Depends(get_db)):
    """Gera PDF com folha de etiquetas QR Code — 14 etiquetas por página (2×7)."""
    from app.repositories import item_repo
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    verificar_token_admin(sessao, body.token_admin)

    itens_raw = item_repo.listar_itens(db, sessao_id)
    if not itens_raw:
        raise HTTPException(status_code=422, detail="Nenhum item cadastrado nesta sessão. Importe a planilha primeiro.")

    itens = [
        {"codigo": i.codigo, "produto": i.produto, "quantidade_base": i.quantidade_base}
        for i in itens_raw
    ]
    arquivo = gerar_etiquetas_pdf(itens, nome_sessao=sessao.nome)

    nome_arquivo = f"etiquetas_{sessao.codigo}.pdf"
    return Response(
        content=arquivo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )
