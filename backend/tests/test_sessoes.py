"""Testes: CRUD de Sessões."""
from __future__ import annotations


def test_criar_sessao(client):
    r = client.post("/api/sessoes", json={"nome": "Inventário Geral"})
    assert r.status_code == 201
    data = r.json()
    assert data["nome"] == "Inventário Geral"
    assert data["status"] == "ativa"
    assert data["codigo"].startswith("INV-")
    assert data["id"]


def test_listar_sessoes_vazio(client):
    r = client.get("/api/sessoes")
    assert r.status_code == 200
    assert r.json() == []


def test_listar_sessoes_com_dados(client, sessao):
    r = client.get("/api/sessoes")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == sessao["id"]


def test_buscar_sessao_existente(client, sessao):
    r = client.get(f"/api/sessoes/{sessao['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == sessao["id"]


def test_buscar_sessao_inexistente(client):
    r = client.get("/api/sessoes/nao-existe-00000")
    assert r.status_code == 404


def test_concluir_sessao(client, sessao_com_itens):
    """Sessão só pode ser concluída quando todos os itens são CERTO ou PARA_AJUSTE."""
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    # Tenta concluir sem contar nenhum item — deve falhar (sem token também falha por auth)
    r_sem_itens = client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
    assert r_sem_itens.status_code == 422

    # Conta todos os itens com quantidade correta
    for codigo, qtd in [("ABC-001", 10), ("ABC-002", 5), ("ABC-003", 20)]:
        client.post(f"/api/sessoes/{sid}/contagens",
                    json={"codigo": codigo, "quantidade_encontrada": qtd})
    # Agora pode concluir
    r = client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
    assert r.status_code == 200
    assert r.json()["status"] == "concluida"


def test_cancelar_sessao(client, sessao):
    tok = sessao["token_admin"]
    r = client.patch(f"/api/sessoes/{sessao['id']}/cancelar?token_admin={tok}")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelada"


def test_stats_sessao_vazia(client, sessao):
    r = client.get(f"/api/sessoes/{sessao['id']}/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["conferidos"] == 0
    assert data["percentual"] == 0.0


def test_codigo_unico_por_sessao(client):
    r1 = client.post("/api/sessoes", json={"nome": "Sessão A"})
    r2 = client.post("/api/sessoes", json={"nome": "Sessão B"})
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["codigo"] != r2.json()["codigo"]


def test_listar_sessoes_com_stats(client, sessao_com_itens):
    """listar_sessoes retorna campos de stats corretamente."""
    r = client.get("/api/sessoes")
    assert r.status_code == 200
    data = r.json()[0]
    assert data["total_itens"] == 3
    assert data["itens_contados"] == 0
    assert data["total_divergencias"] == 0


def test_listar_sessoes_stats_apos_contagem(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    client.post(f"/api/sessoes/{sid}/contagens", json={"codigo": "ABC-002", "quantidade_encontrada": 3})
    r = client.get("/api/sessoes")
    data = r.json()[0]
    assert data["itens_contados"] == 1
    assert data["total_divergencias"] == 1  # base=5, encontrado=3


def test_stats_pendentes_nao_negativo(client, sessao_com_itens):
    """Reimportar planilha menor não deve gerar pendentes negativo."""
    import io, openpyxl
    sid = sessao_com_itens["id"]

    # Conta todos os 3 itens originais
    for codigo, qtd in [("ABC-001", 10), ("ABC-002", 5), ("ABC-003", 20)]:
        client.post(f"/api/sessoes/{sid}/contagens", json={"codigo": codigo, "quantidade_encontrada": qtd})

    # Reimporta planilha com apenas 1 item
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["codigo", "produto", "quantidade"])
    ws.append(["ABC-001", "Produto Alpha", 10])
    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    client.post(
        f"/api/sessoes/{sid}/upload",
        files={"file": ("itens.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    r = client.get(f"/api/sessoes/{sid}/stats")
    assert r.status_code == 200
    assert r.json()["pendentes"] >= 0
