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
