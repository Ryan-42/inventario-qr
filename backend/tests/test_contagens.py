"""Testes: registro de contagens, divergências e bloqueio por status."""
from __future__ import annotations


def _registrar(client, sessao_id: str, codigo: str, qtd: int, operador: str = "Tester"):
    return client.post(
        f"/api/sessoes/{sessao_id}/contagens",
        json={"codigo": codigo, "quantidade_encontrada": qtd, "operador": operador},
    )


def test_registrar_contagem_ok(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = _registrar(client, sid, "ABC-001", 10)
    assert r.status_code == 201
    data = r.json()
    assert data["codigo"] == "ABC-001"
    assert data["quantidade_encontrada"] == 10
    assert data["divergencia"] is False
    assert data["operador"] == "Tester"


def test_registrar_contagem_com_divergencia(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = _registrar(client, sid, "ABC-001", 7)  # base é 10
    assert r.status_code == 201
    data = r.json()
    assert data["divergencia"] is True
    assert data["diferenca"] == -3


def test_registrar_contagem_item_inexistente(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = _registrar(client, sid, "NAO-EXISTE", 5)
    assert r.status_code == 404


def test_registrar_contagem_sessao_inexistente(client):
    r = _registrar(client, "nao-existe", "ABC-001", 10)
    assert r.status_code == 404


def test_contagem_bloqueada_sessao_concluida(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    # Conclui sessão
    client.patch(f"/api/sessoes/{sid}/concluir")
    # Tenta registrar contagem
    r = _registrar(client, sid, "ABC-001", 10)
    assert r.status_code == 409
    assert "concluida" in r.json()["detail"]


def test_contagem_bloqueada_sessao_cancelada(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    client.patch(f"/api/sessoes/{sid}/cancelar")
    r = _registrar(client, sid, "ABC-001", 10)
    assert r.status_code == 409
    assert "cancelada" in r.json()["detail"]


def test_item_marcado_como_contado(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _registrar(client, sid, "ABC-001", 10)

    r = client.get(f"/api/sessoes/{sid}/buscar/ABC-001")
    assert r.status_code == 200
    data = r.json()
    assert data["ja_contado"] is True
    assert data["contagem_anterior"] is not None
    assert data["contagem_anterior"]["quantidade_encontrada"] == 10


def test_listar_contagens(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _registrar(client, sid, "ABC-001", 10)
    _registrar(client, sid, "ABC-002", 3)

    r = client.get(f"/api/sessoes/{sid}/contagens")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_stats_apos_contagens(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _registrar(client, sid, "ABC-001", 10)   # OK (base=10)
    _registrar(client, sid, "ABC-002", 3)    # Divergente (base=5)

    r = client.get(f"/api/sessoes/{sid}/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["conferidos"] == 2
    assert data["pendentes"] == 1
    assert data["divergencias"] == 1
    assert round(data["percentual"], 1) == round(2 / 3 * 100, 1)


def test_recontagem_sobrescreve_anterior(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _registrar(client, sid, "ABC-001", 8)
    _registrar(client, sid, "ABC-001", 10)  # recontagem

    r = client.get(f"/api/sessoes/{sid}/buscar/ABC-001")
    # A contagem_anterior deve refletir a mais recente
    assert r.json()["contagem_anterior"]["quantidade_encontrada"] == 10


def test_sem_operador(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = client.post(
        f"/api/sessoes/{sid}/contagens",
        json={"codigo": "ABC-001", "quantidade_encontrada": 10},
    )
    assert r.status_code == 201
    assert r.json()["operador"] is None


def test_contagem_com_observacao(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = client.post(
        f"/api/sessoes/{sid}/contagens",
        json={"codigo": "ABC-001", "quantidade_encontrada": 10, "observacao": "caixa aberta"},
    )
    assert r.status_code == 201
    assert r.json()["observacao"] == "caixa aberta"


def test_historico_criado_apos_contagem(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _registrar(client, sid, "ABC-001", 10)
    _registrar(client, sid, "ABC-001", 8)  # recontagem → 2 entradas no historico

    r = client.get(f"/api/sessoes/{sid}/historico")
    assert r.status_code == 200
    hist = r.json()
    abc_hist = [h for h in hist if h["codigo"] == "ABC-001"]
    assert len(abc_hist) == 2
    assert abc_hist[0]["quantidade_encontrada"] == 10
    assert abc_hist[1]["quantidade_encontrada"] == 8


def test_historico_filtro_por_codigo(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _registrar(client, sid, "ABC-001", 10)
    _registrar(client, sid, "ABC-002", 3)

    r = client.get(f"/api/sessoes/{sid}/historico?codigo=ABC-001")
    assert r.status_code == 200
    hist = r.json()
    assert all(h["codigo"] == "ABC-001" for h in hist)
    assert len(hist) == 1


def test_historico_sessao_inexistente(client):
    r = client.get("/api/sessoes/nao-existe/historico")
    assert r.status_code == 404
