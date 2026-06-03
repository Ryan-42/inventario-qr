from sqlalchemy.orm import Session
from typing import Optional

from app.repositories import sessao_repo, item_repo
from app.schemas import ItemComStatus


def montar_inventario_completo(db: Session, sessao_id: str) -> list[dict]:
    """
    Cruza itens_base com contagens e retorna status por item.
    """
    itens = item_repo.listar_itens(db, sessao_id)
    contagens_map = {
        c.codigo: c for c in item_repo.listar_contagens(db, sessao_id)
    }

    resultado = []
    for item in itens:
        # falsy-zero fix: usar 'is not None' em vez de truthiness
        # valor_estoque=0.0 é válido (item sem valor financeiro); quantidade_base=0 causaria divisão por zero
        unit_price = (item.valor_estoque / item.quantidade_base) if (item.valor_estoque is not None and item.quantidade_base and item.quantidade_base > 0) else None
        contagem = contagens_map.get(item.codigo)
        if contagem:
            diferenca = contagem.quantidade_encontrada - item.quantidade_base
            para_ajuste = getattr(contagem, 'para_ajuste', False)
            if not contagem.divergencia:
                status = "OK"
            elif para_ajuste:
                status = "Para Ajuste"
            else:
                status = "Divergente"
            valor_final_item = round(contagem.quantidade_encontrada * unit_price, 2) if unit_price is not None else None
            resultado.append({
                "codigo": item.codigo,
                "produto": item.produto,
                "local_fisico": item.local_fisico,
                "quantidade_base": item.quantidade_base,
                "quantidade_encontrada": contagem.quantidade_encontrada,
                "diferenca": diferenca,
                "status": status,
                "para_ajuste": para_ajuste,
                "operador": contagem.operador,
                "observacao": contagem.observacao,
                "rodada": contagem.rodada,
                "timestamp": contagem.timestamp,
                "valor_estoque": item.valor_estoque,
                "valor_unitario": round(unit_price, 4) if unit_price is not None else None,
                "valor_final": valor_final_item,
                "diferenca_valor": round(valor_final_item - item.valor_estoque, 2) if (valor_final_item is not None and item.valor_estoque is not None) else None,
            })
        else:
            resultado.append({
                "codigo": item.codigo,
                "produto": item.produto,
                "local_fisico": item.local_fisico,
                "quantidade_base": item.quantidade_base,
                "quantidade_encontrada": None,
                "diferenca": None,
                "status": "Pendente",
                "operador": None,
                "observacao": None,
                "rodada": None,
                "timestamp": None,
                "valor_estoque": item.valor_estoque,
                "valor_unitario": round(unit_price, 4) if unit_price else None,
                "valor_final": None,
                "diferenca_valor": None,
            })

    return resultado


def montar_divergencias(db: Session, sessao_id: str) -> list[dict]:
    """
    Retorna apenas itens com divergência.
    Busca somente os itens relevantes (não carrega toda a base).
    """
    from app.models.item_base import ItemBase

    divergencias = item_repo.listar_divergencias(db, sessao_id)
    if not divergencias:
        return []

    codigos = [c.codigo for c in divergencias]
    itens_map = {
        i.codigo: i
        for i in db.query(ItemBase).filter(
            ItemBase.sessao_id == sessao_id,
            ItemBase.codigo.in_(codigos),
        ).all()
    }

    resultado = []
    for c in divergencias:
        item = itens_map.get(c.codigo)
        if item:
            resultado.append({
                "codigo": c.codigo,
                "produto": item.produto,
                "quantidade_base": item.quantidade_base,
                "quantidade_encontrada": c.quantidade_encontrada,
                "diferenca": c.quantidade_encontrada - item.quantidade_base,
            })
    return resultado
