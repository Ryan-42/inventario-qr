"""
Testes: endpoints empresariais — trilha de auditoria, comparação e relatório de operadores.
"""
from __future__ import annotations

import io
import openpyxl


def _registrar(client, sessao_id, codigo, qtd, operador="Tester"):
    return client.post(
        f"/api/sessoes/{sessao_id}/contagens",
        json={"codigo": codigo, "quantidade_encontrada": qtd, "operador": operador},
    )


def _sessao_cheia(client):
    """Cria uma sessão com itens e contagens variadas."""
    r = client.post("/api/sessoes/", json={"nome": "Sessão Auditoria"})
    assert r.status_code == 201
    dados = r.json()
    sid, tok = dados["id"], dados["token_admin"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["codigo", "produto", "quantidade"])
    ws.append(["AUD-001", "Produto Auditoria 1", 10])
    ws.append(["AUD-002", "Produto Auditoria 2", 5])
    ws.append(["AUD-003", "Produto Auditoria 3", 20])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    client.post(f"/api/sessoes/{sid}/upload?token_admin={tok}",
                files={"file": ("a.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    return sid, tok


# ── Trilha de Auditoria ───────────────────────────────────────────────────────

def test_auditoria_retorna_registros(client):
    sid, tok = _sessao_cheia(client)
    _registrar(client, sid, "AUD-001", 10, operador="Alice")
    _registrar(client, sid, "AUD-002", 3, operador="Bob")  # divergente

    r = client.get(f"/api/sessoes/{sid}/auditoria?token_admin={tok}")
    assert r.status_code == 200
    data = r.json()
    assert data["total_registros"] == 2
    assert len(data["registros"]) == 2


def test_auditoria_classifica_acoes(client):
    sid, tok = _sessao_cheia(client)
    _registrar(client, sid, "AUD-001", 10, operador="Alice")   # OK
    _registrar(client, sid, "AUD-002", 3, operador="Bob")    # divergente

    r = client.get(f"/api/sessoes/{sid}/auditoria?token_admin={tok}")
    assert r.status_code == 200
    registros = r.json()["registros"]
    acoes = {reg["codigo"]: reg["acao"] for reg in registros}
    assert acoes["AUD-001"] == "CONTAGEM_OK"
    assert acoes["AUD-002"] == "DIVERGENCIA_REGISTRADA"


def test_auditoria_filtro_apenas_divergencias(client):
    sid, tok = _sessao_cheia(client)
    _registrar(client, sid, "AUD-001", 10)   # OK
    _registrar(client, sid, "AUD-002", 3)    # divergente
    _registrar(client, sid, "AUD-003", 20)   # OK

    r = client.get(f"/api/sessoes/{sid}/auditoria?token_admin={tok}&apenas_divergencias=true")
    assert r.status_code == 200
    data = r.json()
    assert data["total_registros"] == 1
    assert data["registros"][0]["codigo"] == "AUD-002"


def test_auditoria_filtro_por_codigo(client):
    sid, tok = _sessao_cheia(client)
    _registrar(client, sid, "AUD-001", 10)
    _registrar(client, sid, "AUD-002", 3)

    r = client.get(f"/api/sessoes/{sid}/auditoria?token_admin={tok}&codigo=AUD-001")
    assert r.status_code == 200
    data = r.json()
    assert data["total_registros"] == 1
    assert data["registros"][0]["codigo"] == "AUD-001"


def test_auditoria_filtro_por_operador(client):
    sid, tok = _sessao_cheia(client)
    _registrar(client, sid, "AUD-001", 10, operador="Alice")
    _registrar(client, sid, "AUD-002", 3, operador="Bob")

    r = client.get(f"/api/sessoes/{sid}/auditoria?token_admin={tok}&operador=Alice")
    assert r.status_code == 200
    data = r.json()
    assert data["total_registros"] == 1
    assert data["registros"][0]["operador"] == "Alice"


def test_auditoria_sem_jwt_retorna_401(client):
    sid, tok = _sessao_cheia(client)
    r = client.get(f"/api/sessoes/{sid}/auditoria",
                   headers={"Authorization": "Bearer invalido"})
    assert r.status_code == 401


def test_auditoria_sessao_inexistente(client):
    r = client.get("/api/sessoes/nao-existe/auditoria?token_admin=X")
    assert r.status_code == 404


def test_auditoria_sem_contagens_retorna_zero(client):
    sid, tok = _sessao_cheia(client)
    r = client.get(f"/api/sessoes/{sid}/auditoria?token_admin={tok}")
    assert r.status_code == 200
    assert r.json()["total_registros"] == 0


def test_auditoria_inclui_campo_diferenca(client):
    sid, tok = _sessao_cheia(client)
    _registrar(client, sid, "AUD-002", 3)  # base=5, encontrado=3, diferença=-2

    r = client.get(f"/api/sessoes/{sid}/auditoria?token_admin={tok}")
    assert r.status_code == 200
    reg = r.json()["registros"][0]
    assert reg["diferenca"] == -2
    assert reg["quantidade_base"] == 5
    assert reg["quantidade_encontrada"] == 3


# ── Relatório de Operadores ───────────────────────────────────────────────────

def test_relatorio_operadores_retorna_dados(client):
    sid, tok = _sessao_cheia(client)
    _registrar(client, sid, "AUD-001", 10, operador="Alice")
    _registrar(client, sid, "AUD-002", 3, operador="Bob")
    _registrar(client, sid, "AUD-003", 20, operador="Alice")

    r = client.get(f"/api/sessoes/{sid}/relatorio-operadores?token_admin={tok}")
    assert r.status_code == 200
    data = r.json()
    assert data["total_operadores"] == 2
    nomes = {op["operador"] for op in data["operadores"]}
    assert "Alice" in nomes
    assert "Bob" in nomes


def test_relatorio_operadores_calcula_taxa_divergencia(client):
    sid, tok = _sessao_cheia(client)
    _registrar(client, sid, "AUD-001", 10, operador="Alice")  # OK
    _registrar(client, sid, "AUD-002", 3, operador="Alice")   # divergente (base=5)
    _registrar(client, sid, "AUD-003", 20, operador="Alice")  # OK

    r = client.get(f"/api/sessoes/{sid}/relatorio-operadores?token_admin={tok}")
    assert r.status_code == 200
    alice = next(op for op in r.json()["operadores"] if op["operador"] == "Alice")
    # 1 divergência em 3 tentativas = 33.3%
    assert alice["divergencias"] == 1
    assert alice["total_tentativas"] == 3
    assert alice["taxa_divergencia_pct"] > 0


def test_relatorio_operadores_sem_jwt_retorna_401(client):
    sid, tok = _sessao_cheia(client)
    r = client.get(f"/api/sessoes/{sid}/relatorio-operadores",
                   headers={"Authorization": "Bearer invalido"})
    assert r.status_code == 401


def test_relatorio_operadores_sessao_inexistente(client):
    r = client.get("/api/sessoes/nao-existe/relatorio-operadores?token_admin=X")
    assert r.status_code == 404


# ── Comparação entre Sessões ──────────────────────────────────────────────────

def _criar_sessao_com_itens(client, nome, itens_lista, contagens_lista):
    r = client.post("/api/sessoes/", json={"nome": nome})
    dados = r.json()
    sid, tok = dados["id"], dados["token_admin"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["codigo", "produto", "quantidade"])
    for cod, prod, qtd in itens_lista:
        ws.append([cod, prod, qtd])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    client.post(f"/api/sessoes/{sid}/upload?token_admin={tok}",
                files={"file": ("c.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

    for cod, qtd in contagens_lista:
        client.post(f"/api/sessoes/{sid}/contagens",
                    json={"codigo": cod, "quantidade_encontrada": qtd})
    return sid, tok


def test_comparar_sessoes_retorna_estrutura(client):
    itens = [("C001", "Produto C1", 10), ("C002", "Produto C2", 5)]
    sid1, tok1 = _criar_sessao_com_itens(client, "Sessão 1", itens, [("C001", 10), ("C002", 3)])
    sid2, tok2 = _criar_sessao_com_itens(client, "Sessão 2", itens, [("C001", 10), ("C002", 5)])

    r = client.get(f"/api/sessoes/{sid1}/comparar/{sid2}?token_admin={tok1}")
    assert r.status_code == 200
    data = r.json()
    assert "resumo" in data
    assert "itens_que_melhoraram" in data
    assert "itens_que_pioraram" in data
    assert data["resumo"]["itens_em_comum"] == 2


def test_comparar_sessoes_detecta_melhora(client):
    itens = [("C001", "Produto", 10)]
    # Sessão 1: C001 divergente; Sessão 2: C001 OK
    sid1, tok1 = _criar_sessao_com_itens(client, "S1", itens, [("C001", 7)])  # divergente
    sid2, tok2 = _criar_sessao_com_itens(client, "S2", itens, [("C001", 10)])  # OK

    r = client.get(f"/api/sessoes/{sid1}/comparar/{sid2}?token_admin={tok1}")
    assert r.status_code == 200
    data = r.json()
    # S1 tem divergência, S2 é OK → S1 "piorou" em relação a S2
    assert data["resumo"]["pioraram"] >= 1 or data["resumo"]["melhoraram"] >= 1


def test_comparar_sessoes_ref_nao_encontrada(client):
    sid1, tok1 = _sessao_cheia(client)
    r = client.get(f"/api/sessoes/{sid1}/comparar/nao-existe?token_admin={tok1}")
    assert r.status_code == 404


def test_comparar_sessoes_sem_jwt_retorna_401(client):
    sid1, tok1 = _sessao_cheia(client)
    sid2, tok2 = _sessao_cheia(client)
    r = client.get(f"/api/sessoes/{sid1}/comparar/{sid2}",
                   headers={"Authorization": "Bearer invalido"})
    assert r.status_code == 401
