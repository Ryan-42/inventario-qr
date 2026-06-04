"""Testes de infraestrutura: headers de segurança, tokens, stats, progresso."""
from __future__ import annotations
import pytest


# ── Security Headers ──────────────────────────────────────────────────────────

def test_security_headers_em_resposta_api(client):
    """Toda resposta HTTP deve incluir os headers de segurança."""
    r = client.get("/api/sessoes")
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff", \
        "X-Content-Type-Options ausente"
    assert r.headers.get("x-frame-options") == "DENY", \
        "X-Frame-Options ausente"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin", \
        "Referrer-Policy ausente"

def test_security_headers_em_resposta_404(client):
    """Headers de segurança presentes mesmo em respostas de erro."""
    r = client.get("/api/sessoes/nao-existe-id")
    assert r.status_code == 404
    assert "nosniff" in r.headers.get("x-content-type-options", "")

def test_security_headers_em_resposta_post(client):
    """Headers presentes em POST."""
    r = client.post("/api/sessoes/", json={"nome": "Teste"})
    assert r.status_code == 201
    assert r.headers.get("x-frame-options") == "DENY"


# ── Token de acesso: entropia e formato ──────────────────────────────────────

def test_token_acesso_tem_16_chars(client, sessao):
    """token_acesso gerado com token_hex(8) = 16 caracteres hexadecimais."""
    r = client.get(f"/api/sessoes/{sessao['id']}/token-acesso")
    assert r.status_code == 200
    token = r.json()["token"]
    assert len(token) == 16, f"Token deveria ter 16 chars, tem {len(token)}"
    assert token == token.upper(), "Token deveria ser maiúsculo"
    assert all(c in "0123456789ABCDEF" for c in token), "Token deve ser hex maiúsculo"

def test_token_admin_tem_16_chars(client, sessao):
    """token_admin gerado com token_hex(8) = 16 caracteres."""
    assert len(sessao["token_admin"]) == 16
    assert sessao["token_admin"] == sessao["token_admin"].upper()

def test_dois_tokens_sao_distintos(client):
    """Tokens gerados para duas sessões diferentes são sempre distintos."""
    r1 = client.post("/api/sessoes/", json={"nome": "S1"})
    r2 = client.post("/api/sessoes/", json={"nome": "S2"})
    assert r1.json()["token_admin"] != r2.json()["token_admin"]


# ── GET /sessoes/{id} retorna stats corretos (não zeros) ─────────────────────

def test_buscar_sessao_retorna_total_itens(client, sessao_com_itens):
    """GET /sessoes/{id} deve retornar total_itens calculado via SQL."""
    sid = sessao_com_itens["id"]
    r = client.get(f"/api/sessoes/{sid}")
    assert r.status_code == 200
    data = r.json()
    assert data["total_itens"] == 3, f"Esperava 3, recebi {data['total_itens']}"

def test_buscar_sessao_retorna_itens_contados(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-001", "quantidade_encontrada": 10})
    r = client.get(f"/api/sessoes/{sid}")
    assert r.json()["itens_contados"] == 1

def test_buscar_sessao_retorna_divergencias(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-002", "quantidade_encontrada": 3})  # base=5 → diverge
    r = client.get(f"/api/sessoes/{sid}")
    assert r.json()["total_divergencias"] == 1


# ── Progresso de rodada ───────────────────────────────────────────────────────

def test_progresso_sessao_sem_itens(client, sessao):
    """Sessão sem itens importados: completa=False, tem_itens=False."""
    r = client.get(f"/api/sessoes/{sessao['id']}/progresso")
    assert r.status_code == 200
    data = r.json()
    assert data["tem_itens"] is False
    assert data["completa"] is False

def test_progresso_todos_corretos(client, sessao_com_itens):
    """Todos os itens contados corretamente: completa=True."""
    sid = sessao_com_itens["id"]
    for codigo, qtd in [("ABC-001", 10), ("ABC-002", 5), ("ABC-003", 20)]:
        client.post(f"/api/sessoes/{sid}/contagens",
                    json={"codigo": codigo, "quantidade_encontrada": qtd})
    r = client.get(f"/api/sessoes/{sid}/progresso")
    data = r.json()
    assert data["faltando_r1"] == 0
    assert data["faltando_r2"] == 0
    assert data["completa"] is True

def test_progresso_com_item_divergente(client, sessao_com_itens):
    """Item divergente: completa=False, faltando_r2 > 0."""
    sid = sessao_com_itens["id"]
    for codigo, qtd in [("ABC-001", 10), ("ABC-002", 3), ("ABC-003", 20)]:
        client.post(f"/api/sessoes/{sid}/contagens",
                    json={"codigo": codigo, "quantidade_encontrada": qtd})
    r = client.get(f"/api/sessoes/{sid}/progresso")
    data = r.json()
    assert data["faltando_r1"] == 0
    assert data["faltando_r2"] == 1  # ABC-002 divergente
    assert data["completa"] is False

def test_progresso_rodada_atual_durante_recontagem(client, sessao_com_itens):
    """Quando R1 completa com divergências, rodada_atual deve ser >= 2."""
    sid = sessao_com_itens["id"]
    for codigo, qtd in [("ABC-001", 10), ("ABC-002", 3), ("ABC-003", 20)]:
        client.post(f"/api/sessoes/{sid}/contagens",
                    json={"codigo": codigo, "quantidade_encontrada": qtd})
    r = client.get(f"/api/sessoes/{sid}/progresso")
    assert r.json()["rodada_atual"] >= 2, (
        "rodada_atual deve ser pelo menos 2 quando R1 completa e há divergências"
    )


# ── Histórico paginado ────────────────────────────────────────────────────────

def test_historico_paginado_limit(client, sessao_com_itens):
    """GET /historico com limit=1 retorna apenas 1 entrada."""
    sid = sessao_com_itens["id"]
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-001", "quantidade_encontrada": 10})
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-002", "quantidade_encontrada": 5})
    r = client.get(f"/api/sessoes/{sid}/historico?limit=1")
    assert r.status_code == 200
    assert len(r.json()) == 1

def test_historico_paginado_offset(client, sessao_com_itens):
    """GET /historico com offset=1 pula o primeiro registro."""
    sid = sessao_com_itens["id"]
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-001", "quantidade_encontrada": 10})
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-002", "quantidade_encontrada": 5})
    r_todos = client.get(f"/api/sessoes/{sid}/historico")
    r_offset = client.get(f"/api/sessoes/{sid}/historico?offset=1")
    assert len(r_offset.json()) == len(r_todos.json()) - 1


# ── /rodadas consistência ─────────────────────────────────────────────────────

def test_rodadas_divergencias_exclui_para_ajuste(client, sessao_com_itens):
    """Divergências em /rodadas não devem contar itens PARA_AJUSTE."""
    sid = sessao_com_itens["id"]
    # ABC-001: para_ajuste (duplo erro confirmado)
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-001", "quantidade_encontrada": 7})
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-001", "quantidade_encontrada": 7})
    # ABC-002 e ABC-003: corretos
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-002", "quantidade_encontrada": 5})
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-003", "quantidade_encontrada": 20})

    r = client.get(f"/api/sessoes/{sid}/rodadas")
    data = r.json()
    # ABC-001 é PARA_AJUSTE: não deve aparecer em divergencias da rodada 1
    rodada_1 = next((rd for rd in data["rodadas"] if rd["numero"] == 1), None)
    assert rodada_1 is not None
    assert rodada_1["divergencias"] == 0, (
        f"PARA_AJUSTE não deveria contar como divergência, recebi {rodada_1['divergencias']}"
    )

def test_rodadas_lista_divergentes_ativos(client, sessao_com_itens):
    """Itens divergentes ativos (sem para_ajuste) aparecem em itens_segunda."""
    sid = sessao_com_itens["id"]
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-001", "quantidade_encontrada": 10})  # OK
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-002", "quantidade_encontrada": 3})   # divergente
    client.post(f"/api/sessoes/{sid}/contagens",
                json={"codigo": "ABC-003", "quantidade_encontrada": 20})  # OK

    r = client.get(f"/api/sessoes/{sid}/rodadas")
    codigos = [i["codigo"] for i in r.json()["itens_segunda"]]
    assert "ABC-002" in codigos
    assert "ABC-001" not in codigos
    assert "ABC-003" not in codigos
