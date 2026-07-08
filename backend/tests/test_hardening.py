"""
Testes de hardening — cobrem as correções de segurança e as features novas:

A) Endpoints que passaram a exigir JWT admin (vazavam dados/tokens sem auth)
B) Guards de token vazio (hmac.compare_digest("","") == True)
C) Contagem cega real: /buscar não expõe quantidade_base para operadores
D) /auth/token com proteção brute-force + /auth/alterar-senha
E) Upload de CSV (antes: validar aceitava CSV mas upload rejeitava)
F) Reabrir sessão concluída (PATCH /reabrir)
"""
from __future__ import annotations

import io

import pytest


def _cliente_sem_jwt():
    """TestClient sem headers de admin JWT (simula operador mobile / anônimo)."""
    from fastapi.testclient import TestClient
    from app.main import app as _app
    from app.database import get_db
    from tests.conftest import override_get_db
    _app.dependency_overrides[get_db] = override_get_db
    return TestClient(_app, raise_server_exceptions=False)


def _limpar_brute_force():
    """Limpa estado in-memory de brute-force para não poluir outros testes."""
    from app.routes import auth as auth_routes
    from app import auth as app_auth
    with auth_routes._login_lock:
        auth_routes._login_falhas.clear()
    with app_auth._lock:
        app_auth._falhas.clear()
        app_auth._bloqueados.clear()


@pytest.fixture(autouse=True)
def _brute_force_isolado():
    _limpar_brute_force()
    yield
    _limpar_brute_force()


def _token_operador(client, sid: str) -> str:
    r = client.get(f"/api/sessoes/{sid}/token-acesso")
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ── A) Endpoints agora admin-only ─────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "itens", "contagens", "historico", "stats", "valor-estoque",
    "metricas", "rodadas", "segunda-aprovacao", "qrcode-acesso",
    "qrcode-supervisor", "grupos",
])
def test_endpoints_admin_retornam_401_sem_jwt(sessao_com_itens, path):
    c = _cliente_sem_jwt()
    r = c.get(f"/api/sessoes/{sessao_com_itens['id']}/{path}")
    assert r.status_code == 401, f"{path}: esperado 401, veio {r.status_code}"


def test_validar_planilha_exige_admin(sessao):
    c = _cliente_sem_jwt()
    r = c.post(
        f"/api/sessoes/{sessao['id']}/validar-planilha",
        files={"file": ("x.csv", io.BytesIO(b"codigo,produto,quantidade\nA,P,1\n"), "text/csv")},
    )
    assert r.status_code == 401


def test_webhook_url_oculta_para_nao_admin(client):
    r = client.post("/api/sessoes/", json={"nome": "S", "webhook_url": "https://example.com/hook"})
    sid = r.json()["id"]
    # Admin vê a webhook_url
    assert client.get(f"/api/sessoes/{sid}").json()["webhook_url"] == "https://example.com/hook"
    # Anônimo (página do supervisor/mobile) não vê
    c = _cliente_sem_jwt()
    assert c.get(f"/api/sessoes/{sid}").json()["webhook_url"] is None


# ── B) Guards de token vazio ──────────────────────────────────────────────────

def test_verificar_token_vazio_invalido(sessao):
    c = _cliente_sem_jwt()
    r = c.get(f"/api/sessoes/{sessao['id']}/verificar-token?token=")
    assert r.status_code == 200
    assert r.json()["valido"] is False


def test_verificar_admin_token_vazio_invalido(sessao):
    c = _cliente_sem_jwt()
    r = c.get(f"/api/sessoes/{sessao['id']}/verificar-admin?token=")
    assert r.status_code == 200
    assert r.json()["valido"] is False


def test_verificar_grupo_token_vazio_invalido(sessao):
    """Sem guard, token_supervisor=None + token='' validava como supervisor."""
    c = _cliente_sem_jwt()
    r = c.get(f"/api/sessoes/{sessao['id']}/verificar-grupo?token=")
    assert r.status_code == 200
    body = r.json()
    assert body["valido"] is False
    assert body["tipo"] is None


def test_itens_supervisor_token_vazio_403(sessao_com_itens):
    c = _cliente_sem_jwt()
    r = c.get(f"/api/sessoes/{sessao_com_itens['id']}/itens-supervisor?token=")
    assert r.status_code == 403


# ── C) Contagem cega no /buscar e /itens-operador ────────────────────────────

def test_buscar_sem_token_retorna_401(sessao_com_itens):
    c = _cliente_sem_jwt()
    r = c.get(f"/api/sessoes/{sessao_com_itens['id']}/buscar/ABC-001")
    assert r.status_code == 401


def test_buscar_operador_nao_ve_quantidade_base(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    token = _token_operador(client, sid)
    c = _cliente_sem_jwt()
    r = c.get(f"/api/sessoes/{sid}/buscar/ABC-001?token={token}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["quantidade_base"] is None
    assert body["contagem_anterior"] is None
    assert body["produto"] == "Produto Alpha"


def test_buscar_admin_ve_quantidade_base(client, sessao_com_itens):
    r = client.get(f"/api/sessoes/{sessao_com_itens['id']}/buscar/ABC-001")
    assert r.status_code == 200
    assert r.json()["quantidade_base"] == 10


def test_itens_operador_sem_token_401(sessao_com_itens):
    c = _cliente_sem_jwt()
    r = c.get(f"/api/sessoes/{sessao_com_itens['id']}/itens-operador")
    assert r.status_code == 401


def test_itens_operador_com_token_200(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    token = _token_operador(client, sid)
    c = _cliente_sem_jwt()
    r = c.get(f"/api/sessoes/{sid}/itens-operador?token={token}")
    assert r.status_code == 200
    itens = r.json()
    assert len(itens) == 3
    assert all("quantidade_base" not in i for i in itens)


# ── D) /auth/token brute-force + alterar-senha ───────────────────────────────

def test_auth_token_form_bloqueia_apos_falhas(client):
    c = _cliente_sem_jwt()
    for _ in range(5):
        r = c.post("/auth/token", data={"username": "x@x.com", "password": "errada"})
        assert r.status_code == 401
    r = c.post("/auth/token", data={"username": "x@x.com", "password": "errada"})
    assert r.status_code == 429


def test_alterar_senha_exige_senha_atual_correta(client):
    r = client.post("/auth/alterar-senha", json={"senha_atual": "errada", "senha_nova": "NovaSenha123"})
    assert r.status_code == 403


def test_alterar_senha_curta_recusada(client):
    r = client.post("/auth/alterar-senha", json={"senha_atual": "senha_teste_123", "senha_nova": "abc"})
    assert r.status_code == 422


def test_alterar_senha_sucesso_e_login(client):
    r = client.post("/auth/alterar-senha", json={"senha_atual": "senha_teste_123", "senha_nova": "NovaSenha123!"})
    assert r.status_code == 200, r.text
    c = _cliente_sem_jwt()
    r = c.post("/auth/login", json={"email": "teste@inviq.local", "senha": "NovaSenha123!"})
    assert r.status_code == 200
    assert r.json()["access_token"]


# ── E) Upload CSV ─────────────────────────────────────────────────────────────

def test_upload_csv_aceito(client, sessao):
    csv_bytes = b"codigo,produto,quantidade\nCSV-001,Produto CSV,7\nCSV-002,Outro,3\n"
    r = client.post(
        f"/api/sessoes/{sessao['id']}/upload",
        files={"file": ("itens.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["total"] == 2


# ── F) Reabrir sessão ─────────────────────────────────────────────────────────

def _concluir_sessao(client, sessao_com_itens) -> str:
    """Conta todos os itens batendo com a base e conclui a sessão."""
    sid = sessao_com_itens["id"]
    for codigo, qtd in [("ABC-001", 10), ("ABC-002", 5), ("ABC-003", 20)]:
        r = client.post(f"/api/sessoes/{sid}/contagens",
                        json={"codigo": codigo, "quantidade_encontrada": qtd})
        assert r.status_code == 201, r.text
    r = client.patch(f"/api/sessoes/{sid}/concluir")
    assert r.status_code == 200, r.text
    return sid


def test_reabrir_sessao_concluida(client, sessao_com_itens):
    sid = _concluir_sessao(client, sessao_com_itens)
    r = client.patch(f"/api/sessoes/{sid}/reabrir")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ativa"
    assert r.json()["data_fim"] is None
    # Aceita novas contagens após reabrir
    r = client.post(f"/api/sessoes/{sid}/contagens",
                    json={"codigo": "ABC-001", "quantidade_encontrada": 9})
    assert r.status_code == 201


def test_reabrir_sessao_ativa_conflito(client, sessao):
    r = client.patch(f"/api/sessoes/{sessao['id']}/reabrir")
    assert r.status_code == 409


def test_reabrir_sem_jwt_401(client, sessao_com_itens):
    sid = _concluir_sessao(client, sessao_com_itens)
    c = _cliente_sem_jwt()
    r = c.patch(f"/api/sessoes/{sid}/reabrir")
    assert r.status_code == 401


def test_reabrir_aprovada_recusado(client, sessao_com_itens):
    sid = _concluir_sessao(client, sessao_com_itens)
    token = client.get(f"/api/sessoes/{sid}/segunda-aprovacao").json()["token_segunda_aprovacao"]
    r = client.post(f"/api/sessoes/{sid}/segunda-aprovacao/aprovar",
                    params={"token_segunda_aprovacao": token})
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/sessoes/{sid}/reabrir")
    assert r.status_code == 409


def test_reabrir_rejeitada_permite_e_reseta_aprovacao(client, sessao_com_itens):
    sid = _concluir_sessao(client, sessao_com_itens)
    token = client.get(f"/api/sessoes/{sid}/segunda-aprovacao").json()["token_segunda_aprovacao"]
    r = client.post(f"/api/sessoes/{sid}/segunda-aprovacao/rejeitar",
                    params={"token_segunda_aprovacao": token})
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/sessoes/{sid}/reabrir")
    assert r.status_code == 200, r.text
    status = client.get(f"/api/sessoes/{sid}/segunda-aprovacao").json()
    assert status["status"] == "pendente"


# ── Auditoria: filtros aplicados antes da paginação ───────────────────────────

def test_auditoria_filtro_operador_no_sql(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    for codigo, op in [("ABC-001", "Alice"), ("ABC-002", "Bob"), ("ABC-003", "Alice")]:
        client.post(f"/api/sessoes/{sid}/contagens",
                    json={"codigo": codigo, "quantidade_encontrada": 1, "operador": op})
    r = client.get(f"/api/sessoes/{sid}/auditoria?operador=alice&limit=1")
    assert r.status_code == 200
    body = r.json()
    # limit=1 com filtro: 1 registro na página e tem_mais aponta o segundo da Alice
    assert len(body["registros"]) == 1
    assert body["registros"][0]["operador"] == "Alice"
    assert body["tem_mais"] is True
