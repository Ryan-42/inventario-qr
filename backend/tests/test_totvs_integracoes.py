"""
Testes: integração TOTVS (dry-run) e endpoints de integração.
"""
from __future__ import annotations

import io
import openpyxl


def _upload_itens(client, sessao, itens_lista):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["codigo", "produto", "quantidade"])
    for cod, prod, qtd in itens_lista:
        ws.append([cod, prod, qtd])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    tok = sessao["token_admin"]
    r = client.post(
        f"/api/sessoes/{sessao['id']}/upload?token_admin={tok}",
        files={"file": ("i.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 201


def _registrar(client, sessao_id, codigo, qtd):
    return client.post(f"/api/sessoes/{sessao_id}/contagens",
                       json={"codigo": codigo, "quantidade_encontrada": qtd})


# ── Status da configuração TOTVS ──────────────────────────────────────────────

def test_totvs_status_sem_configuracao(client):
    """Sem TOTVS_URL configurado deve retornar dry_run=True."""
    r = client.get("/api/integracoes/totvs/status")
    assert r.status_code == 200
    data = r.json()
    assert data["dry_run"] is True
    assert data["configurado"] is False
    assert "instrucoes" in data


# ── Preview de payload ────────────────────────────────────────────────────────

def test_preview_payload_retorna_estrutura(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _registrar(client, sid, "ABC-002", 3)  # divergente (base=5)

    r = client.get(f"/api/integracoes/totvs/sessao/{sid}/preview-payload?token_admin={tok}")
    assert r.status_code == 200
    data = r.json()
    assert "payload" in data
    assert "itens" in data["payload"]
    assert data["payload"]["empresa"] is not None
    assert data["total_linhas"] >= 1


def test_preview_payload_token_invalido(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = client.get(f"/api/integracoes/totvs/sessao/{sid}/preview-payload?token_admin=ERRADO")
    assert r.status_code == 403


def test_preview_payload_sessao_inexistente(client):
    r = client.get("/api/integracoes/totvs/sessao/nao-existe/preview-payload?token_admin=X")
    assert r.status_code == 404


# ── Envio de ajuste (dry-run) ─────────────────────────────────────────────────

def test_enviar_ajuste_dry_run_retorna_payload(client, sessao_com_itens):
    """Em modo dry-run retorna o payload sem erros."""
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _registrar(client, sid, "ABC-001", 10)  # OK
    _registrar(client, sid, "ABC-002", 3)   # divergente

    r = client.post(f"/api/integracoes/totvs/sessao/{sid}/enviar-ajuste?token_admin={tok}")
    assert r.status_code == 200
    data = r.json()
    assert data["dry_run"] is True
    assert data["sucesso"] is True
    assert data["payload_enviado"] is not None
    assert data["total_itens_enviados"] >= 1  # pelo menos ABC-002 divergente


def test_enviar_ajuste_todos_itens(client, sessao_com_itens):
    """Com apenas_divergentes=false envia todos os itens contados."""
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _registrar(client, sid, "ABC-001", 10)
    _registrar(client, sid, "ABC-002", 5)
    _registrar(client, sid, "ABC-003", 20)

    r = client.post(
        f"/api/integracoes/totvs/sessao/{sid}/enviar-ajuste?token_admin={tok}&apenas_divergentes=false"
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total_itens_enviados"] == 3


def test_enviar_ajuste_sem_divergencias_retorna_422(client, sessao_com_itens):
    """Sem divergências e com apenas_divergentes=true deve retornar 422."""
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _registrar(client, sid, "ABC-001", 10)  # OK
    _registrar(client, sid, "ABC-002", 5)   # OK
    _registrar(client, sid, "ABC-003", 20)  # OK

    r = client.post(f"/api/integracoes/totvs/sessao/{sid}/enviar-ajuste?token_admin={tok}")
    assert r.status_code == 422


def test_enviar_ajuste_token_invalido(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = client.post(f"/api/integracoes/totvs/sessao/{sid}/enviar-ajuste?token_admin=ERRADO")
    assert r.status_code == 403


def test_enviar_ajuste_sessao_inexistente(client):
    r = client.post("/api/integracoes/totvs/sessao/nao-existe/enviar-ajuste?token_admin=X")
    assert r.status_code == 404


# ── Mapeamento do payload ─────────────────────────────────────────────────────

def test_payload_totvs_mapeia_campos_corretos(client, sessao):
    """Verifica que o payload TOTVS tem todos os campos obrigatórios."""
    itens = [("P001", "Produto X", 10), ("P002", "Produto Y", 5)]
    _upload_itens(client, sessao, itens)
    _registrar(client, sessao["id"], "P001", 8)  # divergente

    r = client.get(
        f"/api/integracoes/totvs/sessao/{sessao['id']}/preview-payload?token_admin={sessao['token_admin']}"
    )
    assert r.status_code == 200
    payload = r.json()["payload"]

    # Campos obrigatórios do Protheus
    assert "empresa" in payload
    assert "filial" in payload
    assert "documentoOrigem" in payload
    assert "dataInventario" in payload
    assert "itens" in payload

    item = payload["itens"][0]
    assert "produto" in item
    assert "quantidadeAnterior" in item
    assert "quantidadeInventario" in item
    assert "diferenca" in item
    assert "tipoMovimento" in item


def test_payload_totvs_diferenca_correta(client, sessao):
    """Diferença calculada no payload deve ser quantidade_encontrada - quantidade_base."""
    itens = [("Q001", "Item Q", 10)]
    _upload_itens(client, sessao, itens)
    _registrar(client, sessao["id"], "Q001", 7)  # base=10, encontrado=7, diferença=-3

    r = client.get(
        f"/api/integracoes/totvs/sessao/{sessao['id']}/preview-payload?token_admin={sessao['token_admin']}&apenas_divergentes=false"
    )
    assert r.status_code == 200
    item = r.json()["payload"]["itens"][0]
    assert item["quantidadeAnterior"] == 10.0
    assert item["quantidadeInventario"] == 7.0
    assert item["diferenca"] == -3.0
