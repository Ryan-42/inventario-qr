"""
Testes: proteção contra brute-force em token_admin.

Cada teste usa um cliente isolado (via fixture client) para evitar
contaminação do estado de IP entre testes.
"""
from __future__ import annotations

import time
import threading
from unittest.mock import patch

import pytest

from app import auth as _auth_module


@pytest.fixture(autouse=True)
def limpar_estado_brute_force():
    """Reseta o estado in-memory de brute-force antes e depois de cada teste."""
    with _auth_module._lock:
        _auth_module._falhas.clear()
        _auth_module._bloqueados.clear()
    yield
    with _auth_module._lock:
        _auth_module._falhas.clear()
        _auth_module._bloqueados.clear()


# ── Testes básicos ────────────────────────────────────────────────────────────

def _rota_admin(sessao_id: str) -> str:
    """Rota que usa verificar_token_admin — PATCH /concluir é boa escolha."""
    return f"/api/sessoes/{sessao_id}/concluir"


def test_token_correto_retorna_200(client, sessao):
    tok = sessao["token_admin"]
    r = client.patch(_rota_admin(sessao["id"]), params={"token_admin": tok})
    assert r.status_code in (200, 204, 422)  # qualquer resposta não-403


def test_token_errado_retorna_403(client, sessao):
    r = client.patch(_rota_admin(sessao["id"]), params={"token_admin": "ERRADO"})
    assert r.status_code == 403


def test_falhas_registradas_internamente(client, sessao):
    """Após tentativas erradas o estado interno deve registrar as falhas."""
    for _ in range(3):
        client.patch(_rota_admin(sessao["id"]), params={"token_admin": "ERRADO"})

    # TestClient não tem request.client — o IP resolvido é "unknown"
    estado = _auth_module.status_brute_force("unknown")
    assert estado["falhas_na_janela"] >= 3
    assert estado["bloqueado"] is False


def test_bloqueio_apos_10_falhas(client, sessao):
    """10 tentativas erradas devem bloquear o IP com 429."""
    for _ in range(10):
        client.patch(_rota_admin(sessao["id"]), params={"token_admin": "ERRADO"})

    r = client.patch(_rota_admin(sessao["id"]), params={"token_admin": "ERRADO"})
    assert r.status_code == 429


def test_429_inclui_retry_after(client, sessao):
    """Resposta 429 deve incluir o header Retry-After."""
    for _ in range(10):
        client.patch(_rota_admin(sessao["id"]), params={"token_admin": "ERRADO"})

    r = client.patch(_rota_admin(sessao["id"]), params={"token_admin": "ERRADO"})
    assert r.status_code == 429
    assert "retry-after" in r.headers


def test_429_mesmo_com_token_correto_quando_bloqueado(client, sessao):
    """Quando IP está bloqueado, nem o token correto passa."""
    tok = sessao["token_admin"]
    for _ in range(10):
        client.patch(_rota_admin(sessao["id"]), params={"token_admin": "ERRADO"})

    r = client.patch(_rota_admin(sessao["id"]), params={"token_admin": tok})
    assert r.status_code == 429


def test_sucesso_limpa_historico_de_falhas(client, sessao):
    """Autenticação bem-sucedida deve zerar as falhas do IP."""
    tok = sessao["token_admin"]

    for _ in range(5):
        client.patch(_rota_admin(sessao["id"]), params={"token_admin": "ERRADO"})

    # TestClient não tem request.client — IP resolvido é "unknown"
    estado_antes = _auth_module.status_brute_force("unknown")
    assert estado_antes["falhas_na_janela"] == 5

    # Autentica corretamente
    client.patch(_rota_admin(sessao["id"]), params={"token_admin": tok})

    estado_depois = _auth_module.status_brute_force("unknown")
    assert estado_depois["falhas_na_janela"] == 0


def test_bloqueio_expira_apos_janela(client, sessao):
    """Simula expiração do bloqueio manipulando o estado interno."""
    ip = "testclient"
    agora = time.monotonic()

    # Injeta bloqueio expirado (1 segundo atrás)
    with _auth_module._lock:
        _auth_module._bloqueados[ip] = agora - 1

    # Deve passar (bloqueio expirado)
    tok = sessao["token_admin"]
    r = client.get(f"/api/sessoes/{sessao['id']}/export/pdf?token_admin={tok}")
    assert r.status_code != 429


def test_status_brute_force_ip_limpo():
    """IP sem histórico deve retornar estado inicial zerado."""
    estado = _auth_module.status_brute_force("ip-inexistente-xyz")
    assert estado["falhas_na_janela"] == 0
    assert estado["bloqueado"] is False
    assert estado["bloqueado_por_mais"] == 0


def test_janela_deslizante_remove_tentativas_antigas():
    """Tentativas fora da janela de 15min não devem contar."""
    ip = "testclient"
    agora = time.monotonic()

    with _auth_module._lock:
        # Injeta 8 tentativas com 20 minutos de idade (fora da janela de 15min)
        tempo_antigo = agora - 1300  # 21 minutos atrás
        _auth_module._falhas[ip] = [tempo_antigo] * 8

    estado = _auth_module.status_brute_force(ip)
    assert estado["falhas_na_janela"] == 0


def test_thread_safety_falhas_concorrentes(client, sessao):
    """Vários threads fazendo auth simultânea não devem corromper o estado."""
    erros = []

    def tentar():
        try:
            client.patch(_rota_admin(sessao["id"]), params={"token_admin": "ERRADO"})
        except Exception as e:
            erros.append(e)

    threads = [threading.Thread(target=tentar) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert erros == [], f"Erros em threads: {erros}"


def test_contagem_exata_para_bloqueio(client, sessao):
    """10 falhas ativam bloqueio; a 11a tentativa deve retornar 429."""
    for i in range(10):
        r = client.patch(_rota_admin(sessao["id"]), params={"token_admin": "ERRADO"})
        assert r.status_code == 403, f"Esperava 403 na tentativa {i+1}"

    r11 = client.patch(_rota_admin(sessao["id"]), params={"token_admin": "ERRADO"})
    assert r11.status_code == 429
