"""Testes: autenticação token_admin em rotas críticas."""
from __future__ import annotations


# ── Helpers ──────────────────────────────────────────────────────────────────

def _contar_tudo(client, sid, sessao_com_itens):
    for codigo, qtd in [("ABC-001", 10), ("ABC-002", 5), ("ABC-003", 20)]:
        client.post(f"/api/sessoes/{sid}/contagens",
                    json={"codigo": codigo, "quantidade_encontrada": qtd})


# ── token_admin em /concluir ──────────────────────────────────────────────────

def test_concluir_sem_token_retorna_422(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _contar_tudo(client, sid, sessao_com_itens)
    r = client.patch(f"/api/sessoes/{sid}/concluir")  # sem token_admin
    assert r.status_code == 422  # field required

def test_concluir_token_errado_retorna_403(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _contar_tudo(client, sid, sessao_com_itens)
    r = client.patch(f"/api/sessoes/{sid}/concluir?token_admin=TOKEN_ERRADO")
    assert r.status_code == 403

def test_concluir_token_correto_funciona(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _contar_tudo(client, sid, sessao_com_itens)
    r = client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
    assert r.status_code == 200


# ── token_admin em /cancelar ──────────────────────────────────────────────────

def test_cancelar_sem_token_retorna_422(client, sessao):
    r = client.patch(f"/api/sessoes/{sessao['id']}/cancelar")
    assert r.status_code == 422

def test_cancelar_token_errado_retorna_403(client, sessao):
    r = client.patch(f"/api/sessoes/{sessao['id']}/cancelar?token_admin=ERRADO")
    assert r.status_code == 403

def test_cancelar_token_correto_funciona(client, sessao):
    tok = sessao["token_admin"]
    r = client.patch(f"/api/sessoes/{sessao['id']}/cancelar?token_admin={tok}")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelada"


# ── token_admin em /gerar-token ───────────────────────────────────────────────

def test_gerar_token_sem_admin_retorna_422(client, sessao):
    r = client.post(f"/api/sessoes/{sessao['id']}/gerar-token")
    assert r.status_code == 422

def test_gerar_token_admin_errado_retorna_403(client, sessao):
    r = client.post(f"/api/sessoes/{sessao['id']}/gerar-token?token_admin=ERRADO&rodada=2")
    assert r.status_code == 403

def test_gerar_token_admin_correto_funciona(client, sessao):
    tok = sessao["token_admin"]
    r = client.post(f"/api/sessoes/{sessao['id']}/gerar-token?token_admin={tok}&rodada=2")
    assert r.status_code == 200
    data = r.json()
    assert data["rodada"] == 2
    assert len(data["token"]) == 16  # token_hex(8) = 16 chars maiúsculos


# ── Guardrails de estado ──────────────────────────────────────────────────────

def test_nao_pode_cancelar_sessao_concluida(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _contar_tudo(client, sid, sessao_com_itens)
    client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
    r = client.patch(f"/api/sessoes/{sid}/cancelar?token_admin={tok}")
    assert r.status_code == 409
    assert "conclu" in r.json()["detail"].lower()

def test_nao_pode_concluir_sessao_cancelada(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _contar_tudo(client, sid, sessao_com_itens)
    client.patch(f"/api/sessoes/{sid}/cancelar?token_admin={tok}")
    r = client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
    assert r.status_code == 409

def test_cancelar_duas_vezes_retorna_409(client, sessao):
    tok = sessao["token_admin"]
    client.patch(f"/api/sessoes/{sessao['id']}/cancelar?token_admin={tok}")
    r = client.patch(f"/api/sessoes/{sessao['id']}/cancelar?token_admin={tok}")
    assert r.status_code == 409
    assert "cancelada" in r.json()["detail"].lower()

def test_concluir_retorna_stats_reais(client, sessao_com_itens):
    """PATCH /concluir deve retornar total_itens real, não 0."""
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _contar_tudo(client, sid, sessao_com_itens)
    r = client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
    assert r.status_code == 200
    data = r.json()
    assert data["total_itens"] == 3, f"Esperava 3 itens, recebi {data['total_itens']}"
    assert data["status"] == "concluida"

def test_cancelar_retorna_stats_reais(client, sessao_com_itens):
    """PATCH /cancelar deve retornar total_itens real, não 0."""
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    r = client.patch(f"/api/sessoes/{sid}/cancelar?token_admin={tok}")
    assert r.status_code == 200
    data = r.json()
    assert data["total_itens"] == 3, f"Esperava 3 itens, recebi {data['total_itens']}"
    assert data["status"] == "cancelada"

def test_concluir_sessao_sem_itens_retorna_422(client, sessao):
    """Sessão sem nenhum item importado não pode ser concluída."""
    tok = sessao["token_admin"]
    r = client.patch(f"/api/sessoes/{sessao['id']}/concluir?token_admin={tok}")
    assert r.status_code == 422
    assert "item" in r.json()["detail"].lower()
