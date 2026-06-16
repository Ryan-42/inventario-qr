"""
Testes: proteção contra brute-force no endpoint de login JWT.
"""
from __future__ import annotations

import threading

import pytest

from app.routes.auth import _login_falhas, _login_lock


@pytest.fixture(autouse=True)
def limpar_estado_login():
    """Reseta o estado in-memory de rate limit de login antes e depois de cada teste."""
    with _login_lock:
        _login_falhas.clear()
    yield
    with _login_lock:
        _login_falhas.clear()


# ── Testes básicos ────────────────────────────────────────────────────────────

def test_login_correto_retorna_200(client):
    """Login com credenciais corretas retorna token."""
    r = client.post("/auth/login", json={"email": "teste@inviq.local", "senha": "senha_teste_123"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_errado_retorna_401(client):
    r = client.post("/auth/login", json={"email": "teste@inviq.local", "senha": "senha_errada"})
    assert r.status_code == 401


def test_login_email_inexistente_retorna_401(client):
    r = client.post("/auth/login", json={"email": "nao_existe@inviq.local", "senha": "qualquer"})
    assert r.status_code == 401


def test_falhas_registradas_internamente(client):
    """Após tentativas erradas o estado interno deve registrar as falhas."""
    for _ in range(3):
        client.post("/auth/login", json={"email": "teste@inviq.local", "senha": "errada"})

    with _login_lock:
        falhas = _login_falhas.get("testclient", _login_falhas.get("127.0.0.1", []))
    # Pode ser "testclient" ou "127.0.0.1" dependendo do TestClient
    total = sum(len(v) for v in _login_falhas.values())
    assert total >= 3


def test_bloqueio_apos_5_falhas(client):
    """5 tentativas erradas devem bloquear com 429."""
    for _ in range(5):
        client.post("/auth/login", json={"email": "teste@inviq.local", "senha": "errada"})

    r = client.post("/auth/login", json={"email": "teste@inviq.local", "senha": "errada"})
    assert r.status_code == 429


def test_429_inclui_retry_after(client):
    """Resposta de bloqueio deve incluir header Retry-After."""
    for _ in range(5):
        client.post("/auth/login", json={"email": "x@x.com", "senha": "e"})
    r = client.post("/auth/login", json={"email": "x@x.com", "senha": "e"})
    assert r.status_code == 429
    assert "Retry-After" in r.headers or "retry-after" in r.headers


def test_sucesso_limpa_historico_de_falhas(client):
    """Login bem-sucedido após falhas limpa o histórico de brute-force."""
    for _ in range(3):
        client.post("/auth/login", json={"email": "teste@inviq.local", "senha": "errada"})

    r = client.post("/auth/login", json={"email": "teste@inviq.local", "senha": "senha_teste_123"})
    assert r.status_code == 200

    with _login_lock:
        total = sum(len(v) for v in _login_falhas.values())
    assert total == 0


def test_me_sem_token_retorna_401(client):
    """GET /auth/me sem JWT retorna 401."""
    r = client.get("/auth/me", headers={"Authorization": "Bearer invalido"})
    assert r.status_code == 401


def test_me_com_token_retorna_admin(client):
    """GET /auth/me com JWT válido retorna dados do admin."""
    r = client.get("/auth/me")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "teste@inviq.local"
    assert data["nome"] == "Admin Teste"


def test_thread_safety_falhas_concorrentes(client):
    """Múltiplas threads registrando falhas simultaneamente não corrompe estado."""
    erros = []

    def tentar():
        try:
            client.post("/auth/login", json={"email": "t@t.com", "senha": "e"})
        except Exception as e:
            erros.append(e)

    threads = [threading.Thread(target=tentar) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not erros, f"Erros em threads: {erros}"
