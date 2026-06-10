"""Testes: endpoints de exportação."""
from __future__ import annotations


def _registrar(client, sessao_id, codigo, qtd):
    return client.post(
        f"/api/sessoes/{sessao_id}/contagens",
        json={"codigo": codigo, "quantidade_encontrada": qtd, "operador": "Tester"},
    )


def _export(client, sid, tok, path):
    return client.post(
        f"/api/sessoes/{sid}/exportar/{path}",
        json={"token_admin": tok},
    )


def test_export_excel_completo(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _registrar(client, sid, "ABC-001", 10)
    _registrar(client, sid, "ABC-002", 3)

    r = _export(client, sid, tok, "completo")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert len(r.content) > 0


def test_export_divergencias(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _registrar(client, sid, "ABC-002", 3)  # base=5 → divergente

    r = _export(client, sid, tok, "divergencias")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]


def test_export_pdf(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _registrar(client, sid, "ABC-001", 10)

    r = _export(client, sid, tok, "pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_export_token_invalido_retorna_403(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = client.post(f"/api/sessoes/{sid}/exportar/completo", json={"token_admin": "ERRADO"})
    assert r.status_code == 403


def test_export_sem_token_retorna_422(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = client.post(f"/api/sessoes/{sid}/exportar/completo", json={})
    assert r.status_code == 422


def test_export_sessao_inexistente(client):
    r = client.post("/api/sessoes/nao-existe/exportar/completo", json={"token_admin": "X"})
    assert r.status_code == 404


def test_export_etiquetas(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    r = _export(client, sid, tok, "etiquetas")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 5000


def test_export_etiquetas_sem_itens(client, sessao):
    sid = sessao["id"]
    tok = sessao["token_admin"]
    r = client.post(f"/api/sessoes/{sid}/exportar/etiquetas", json={"token_admin": tok})
    assert r.status_code == 422
    assert "Nenhum item" in r.json()["detail"]


def test_export_etiquetas_sessao_inexistente(client):
    r = client.post("/api/sessoes/nao-existe/exportar/etiquetas", json={"token_admin": "X"})
    assert r.status_code == 404


# ── Relatório Final (PDF + Excel) ─────────────────────────────────────────────

def test_export_relatorio_final_pdf_basico(client, sessao_com_itens):
    """Relatório Final PDF gerado sem crash (sem histórico de R2)."""
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _registrar(client, sid, "ABC-001", 10)  # OK

    r = _export(client, sid, tok, "relatorio-final-pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_export_relatorio_final_pdf_com_historico_r2(client, sessao_com_itens):
    """Relatório Final PDF com R2 — não deve crashar com NameError s_h2."""
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    # R1: ABC-001 OK, ABC-002 divergente, ABC-003 OK
    _registrar(client, sid, "ABC-001", 10)
    _registrar(client, sid, "ABC-002", 3)  # base=5 → divergente → abre R2
    _registrar(client, sid, "ABC-003", 20)
    # R2: ABC-002 recontagem
    _registrar(client, sid, "ABC-002", 3)  # confirma divergência

    r = _export(client, sid, tok, "relatorio-final-pdf")
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


def test_export_relatorio_final_excel_basico(client, sessao_com_itens):
    """Relatório Final Excel retorna .xlsx com múltiplas abas."""
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _registrar(client, sid, "ABC-001", 10)
    _registrar(client, sid, "ABC-002", 3)  # divergente

    r = _export(client, sid, tok, "relatorio-final-excel")
    assert r.status_code == 200, r.text
    assert "spreadsheetml" in r.headers["content-type"]

    import io, openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "Resumo Executivo" in wb.sheetnames
    assert "Todos os Itens" in wb.sheetnames
    assert "Divergências" in wb.sheetnames
    assert "Recomendações" in wb.sheetnames


def test_export_relatorio_final_excel_com_historico_r2(client, sessao_com_itens):
    """Relatório Final Excel com R2 inclui abas de histórico."""
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _registrar(client, sid, "ABC-001", 10)
    _registrar(client, sid, "ABC-002", 3)  # divergente → R2
    _registrar(client, sid, "ABC-003", 20)
    _registrar(client, sid, "ABC-002", 3)  # R2

    r = _export(client, sid, tok, "relatorio-final-excel")
    assert r.status_code == 200, r.text

    import io, openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "Histórico Detalhado" in wb.sheetnames
    assert "Resumo por Rodadas" in wb.sheetnames


def test_export_excel_completo_inclui_local_fisico(client, sessao):
    """Excel completo deve incluir coluna Local quando item tem local_fisico."""
    import io, openpyxl
    from io import BytesIO

    # Importa planilha com coluna local
    wb_src = openpyxl.Workbook()
    ws_src = wb_src.active
    ws_src.append(["codigo", "produto", "quantidade", "local_fisico"])
    ws_src.append(["X-001", "Produto X", 5, "Prateleira A"])
    buf = BytesIO(); wb_src.save(buf); buf.seek(0)

    tok = sessao["token_admin"]
    client.post(
        f"/api/sessoes/{sessao['id']}/upload?token_admin={tok}",
        files={"file": ("itens.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    client.post(f"/api/sessoes/{sessao['id']}/contagens",
                json={"codigo": "X-001", "quantidade_encontrada": 5})

    r = client.post(f"/api/sessoes/{sessao['id']}/exportar/completo",
                    json={"token_admin": tok})
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb.active
    headers = [ws.cell(1, c + 1).value for c in range(ws.max_column)]
    assert "Local" in headers, f"Coluna Local ausente. Colunas: {headers}"
