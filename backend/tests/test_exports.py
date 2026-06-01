"""Testes: endpoints de exportação."""
from __future__ import annotations


def _registrar(client, sessao_id, codigo, qtd):
    return client.post(
        f"/api/sessoes/{sessao_id}/contagens",
        json={"codigo": codigo, "quantidade_encontrada": qtd, "operador": "Tester"},
    )


def test_export_excel_completo(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _registrar(client, sid, "ABC-001", 10)
    _registrar(client, sid, "ABC-002", 3)

    r = client.get(f"/api/sessoes/{sid}/exportar/completo")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert len(r.content) > 0


def test_export_divergencias(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _registrar(client, sid, "ABC-002", 3)  # base=5 → divergente

    r = client.get(f"/api/sessoes/{sid}/exportar/divergencias")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]


def test_export_pdf(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _registrar(client, sid, "ABC-001", 10)

    r = client.get(f"/api/sessoes/{sid}/exportar/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_export_sessao_inexistente(client):
    r = client.get("/api/sessoes/nao-existe/exportar/completo")
    assert r.status_code == 404


def test_export_etiquetas(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = client.get(f"/api/sessoes/{sid}/exportar/etiquetas")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 5000  # real content, not trivial


def test_export_etiquetas_sem_itens(client, sessao):
    sid = sessao["id"]
    r = client.get(f"/api/sessoes/{sid}/exportar/etiquetas")
    assert r.status_code == 422
    assert "Nenhum item" in r.json()["detail"]


def test_export_etiquetas_sessao_inexistente(client):
    r = client.get("/api/sessoes/nao-existe/exportar/etiquetas")
    assert r.status_code == 404
