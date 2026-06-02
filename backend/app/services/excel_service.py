import pandas as pd
import io
from fastapi import HTTPException


# Aliases aceitos para cada coluna canônica.
# Permite importar planilhas com cabeçalhos em diferentes idiomas/formatos.
_ALIASES: dict[str, set[str]] = {
    "codigo": {
        "codigo", "código", "code", "cod", "sku", "ref",
        "referencia", "referência", "item", "part", "id",
    },
    "produto": {
        "produto", "descricao", "descrição", "description",
        "nome", "name", "product", "desc", "item_name",
        "descricao_produto", "denominacao", "denominação",
    },
    "quantidade": {
        "quantidade", "qtd", "qtde", "qty", "qte",
        "estoque", "stock", "saldo", "saldo_atual",
        "estoque_atual", "estoque atual", "saldo atual",
        "qtd_estoque", "quantidade_base", "qnt",
    },
    "local_fisico": {
        "local_fisico", "local fisico", "local", "localização",
        "localizacao", "setor", "sector", "secao", "seção",
        "prateleira", "shelf", "location", "area", "corredor",
        "endereco", "endereço", "deposito", "deposito_setor",
        "galpao", "zona", "posicao", "posição",
    },
    "valor_estoque": {
        "valor_estoque", "valor estoque", "valor", "value",
        "preco_total", "preço_total", "total_valor", "total_value",
        "custo_total", "custo total", "saldo_financeiro",
        "valor_total", "valor total", "custo", "preco", "preço",
        "vlr_estoque", "vl_estoque", "vl estoque",
        "valor em estoque",  # nome exato informado pelo usuário
    },
}


def _mapear_colunas(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """
    Renomeia colunas para os nomes canônicos usando a tabela de aliases.
    Retorna o DataFrame renomeado e um mapa {coluna_original -> canônica}.
    """
    rename: dict[str, str] = {}
    for col in df.columns:
        normalizado = str(col).strip().lower()
        for canonico, aliases in _ALIASES.items():
            if normalizado in aliases and canonico not in rename.values():
                rename[col] = canonico
                break

    return df.rename(columns=rename), rename


def importar_planilha(conteudo: bytes, filename: str = "") -> list[dict]:
    """
    Lê Excel ou CSV e retorna lista de dicts prontos para inserção.
    Aceita planilhas com nomes de colunas em diferentes formatos/idiomas
    (ex: DESCRICAO, ESTOQUE, SKU, stock, qty, etc.).
    """
    _MAX_ROWS = 50_000
    try:
        fname = (filename or "").lower()
        if fname.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(conteudo), dtype=str, nrows=_MAX_ROWS + 1)
        else:
            df = pd.read_excel(io.BytesIO(conteudo), engine="openpyxl", nrows=_MAX_ROWS + 1)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {str(e)}")

    if len(df) > _MAX_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Planilha excede o limite de {_MAX_ROWS:,} linhas. Divida em partes menores.",
        )

    # Remove colunas sem nome (ex: colunas extras de células mescladas)
    df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")]

    # Mapeia para nomes canônicos via aliases
    df, mapa = _mapear_colunas(df)

    colunas_presentes = set(df.columns)
    colunas_requeridas = {"codigo", "produto", "quantidade"}
    faltando = colunas_requeridas - colunas_presentes
    if faltando:
        nomes_aceitos = {c: sorted(_ALIASES[c]) for c in faltando}
        detalhe = "; ".join(
            f"'{c}' (aceito: {', '.join(aliases[:5])}{'…' if len(aliases) > 5 else ''})"
            for c, aliases in nomes_aceitos.items()
        )
        raise HTTPException(
            status_code=422,
            detail=f"Coluna(s) não encontrada(s): {detalhe}",
        )

    # Remove linhas com campos críticos nulos
    df = df.dropna(subset=["codigo", "produto", "quantidade"])

    # Converte quantidade para inteiro
    try:
        df["quantidade"] = pd.to_numeric(df["quantidade"], errors="raise").astype(int)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Coluna de quantidade deve conter apenas números inteiros.")

    if (df["quantidade"] < 0).any():
        negativos = df.loc[df["quantidade"] < 0, "codigo"].astype(str).head(5).tolist()
        raise HTTPException(
            status_code=422,
            detail=f"Quantidade negativa detectada nos itens: {', '.join(negativos)}. Valores de estoque devem ser ≥ 0.",
        )

    # Converte valor_estoque para float (opcional)
    tem_valor = "valor_estoque" in df.columns
    if tem_valor:
        df["valor_estoque"] = pd.to_numeric(df["valor_estoque"], errors="coerce")

    # Coluna local_fisico é string opcional
    tem_local = "local_fisico" in df.columns

    colunas_base = ["codigo", "produto", "quantidade"]
    if tem_valor:
        colunas_base.append("valor_estoque")
    if tem_local:
        colunas_base.append("local_fisico")

    itens = []
    for r in df[colunas_base].to_dict(orient="records"):
        cod = str(r["codigo"]).strip()
        prod = str(r["produto"]).strip()
        if not cod or not prod:
            continue
        # NaN check explícito: pd.to_numeric com errors="coerce" produz float('nan') para células inválidas
        val_raw = r.get("valor_estoque") if tem_valor else None
        try:
            valor_estoque = float(val_raw) if (val_raw is not None and val_raw == val_raw) else None
        except (TypeError, ValueError):
            valor_estoque = None

        item: dict = {
            "codigo": cod,
            "produto": prod,
            "quantidade_base": int(r["quantidade"]),
            "local_fisico": str(r.get("local_fisico", "") or "").strip() or None,
            "valor_estoque": valor_estoque,
        }
        itens.append(item)

    if not itens:
        raise HTTPException(status_code=422, detail="Planilha não contém itens válidos.")

    return itens


def exportar_inventario_completo(itens_com_status: list[dict]) -> bytes:
    """
    Gera o Excel com todos os itens e seus status finais.
    """
    df = pd.DataFrame(itens_com_status)

    colunas = ["codigo", "produto", "quantidade_base", "quantidade_encontrada", "diferenca", "status", "operador", "rodada", "observacao", "timestamp"]
    df = df.reindex(columns=colunas)
    df.columns = ["Código", "Produto", "Base", "Encontrado", "Diferença", "Status", "Operador", "Rodada", "Observação", "Data/Hora"]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Inventário Completo")

        # Estilização básica
        ws = writer.sheets["Inventário Completo"]
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    return output.getvalue()


def exportar_divergencias(itens_divergentes: list[dict]) -> bytes:
    """
    Gera o Excel somente com itens divergentes.
    """
    if not itens_divergentes:
        # Retorna planilha vazia com cabeçalho
        df = pd.DataFrame(columns=["Código", "Produto", "Base", "Encontrado", "Diferença"])
    else:
        df = pd.DataFrame(itens_divergentes)
        colunas = ["codigo", "produto", "quantidade_base", "quantidade_encontrada", "diferenca"]
        df = df.reindex(columns=colunas)
        df.columns = ["Código", "Produto", "Base", "Encontrado", "Diferença"]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Divergências")
        ws = writer.sheets["Divergências"]
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    return output.getvalue()
