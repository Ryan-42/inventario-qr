"""
Testes: agendamentos de sessão — CRUD, validação e execução imediata.
"""
from __future__ import annotations

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _criar(client, **kwargs) -> dict:
    payload = {"nome_template": "Inventário Semanal", "frequencia": "diario", **kwargs}
    r = client.post("/api/agendamentos/", json=payload)
    return r


def _criar_ok(client, **kwargs) -> dict:
    r = _criar(client, **kwargs)
    assert r.status_code == 201, r.text
    return r.json()


# ── Criação ───────────────────────────────────────────────────────────────────

def test_criar_agendamento_diario(client):
    data = _criar_ok(client, frequencia="diario", hora="06:00")
    assert data["frequencia"] == "diario"
    assert data["hora"] == "06:00"
    assert data["ativo"] is True
    assert data["token_admin"] is not None
    assert data["proxima_execucao"] is not None


def test_criar_agendamento_semanal_com_dia_semana(client):
    data = _criar_ok(client, frequencia="semanal", dia_semana=1)
    assert data["frequencia"] == "semanal"
    assert data["dia_semana"] == 1


def test_criar_agendamento_mensal_com_dia_mes(client):
    data = _criar_ok(client, frequencia="mensal", dia_mes=15)
    assert data["frequencia"] == "mensal"
    assert data["dia_mes"] == 15


def test_criar_agendamento_unico_com_data(client):
    data = _criar_ok(client, frequencia="unico", data_inicio="2027-12-31T08:00:00Z")
    assert data["frequencia"] == "unico"
    assert "2027" in data["proxima_execucao"]


def test_criar_agendamento_semanal_sem_dia_semana_retorna_422(client):
    r = _criar(client, frequencia="semanal")
    assert r.status_code == 422


def test_criar_agendamento_mensal_sem_dia_mes_retorna_422(client):
    r = _criar(client, frequencia="mensal")
    assert r.status_code == 422


def test_criar_agendamento_unico_sem_data_retorna_422(client):
    r = _criar(client, frequencia="unico")
    assert r.status_code == 422


def test_criar_agendamento_hora_invalida_retorna_422(client):
    r = _criar(client, hora="25:99")
    assert r.status_code == 422


def test_criar_agendamento_dia_semana_invalido_retorna_422(client):
    r = _criar(client, frequencia="semanal", dia_semana=7)
    assert r.status_code == 422


def test_criar_agendamento_dia_mes_invalido_retorna_422(client):
    r = _criar(client, frequencia="mensal", dia_mes=29)
    assert r.status_code == 422


def test_criar_agendamento_com_template_inexistente_retorna_404(client):
    r = _criar(client, sessao_template_id="nao-existe")
    assert r.status_code == 404


# ── Listagem e busca ──────────────────────────────────────────────────────────

def test_listar_agendamentos_vazio(client):
    r = client.get("/api/agendamentos/")
    assert r.status_code == 200
    assert r.json() == []


def test_listar_agendamentos_retorna_criados(client):
    _criar_ok(client, nome_template="A1")
    _criar_ok(client, nome_template="A2")
    r = client.get("/api/agendamentos/")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_listar_apenas_ativos(client):
    a1 = _criar_ok(client, nome_template="Ativo")
    a2 = _criar_ok(client, nome_template="Inativo")
    tok = a2["token_admin"]
    client.patch(f"/api/agendamentos/{a2['id']}?token_admin={tok}", json={"ativo": False})

    r = client.get("/api/agendamentos/?apenas_ativos=true")
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert a1["id"] in ids
    assert a2["id"] not in ids


def test_buscar_agendamento_por_id(client):
    a = _criar_ok(client)
    r = client.get(f"/api/agendamentos/{a['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == a["id"]


def test_buscar_agendamento_inexistente_retorna_404(client):
    r = client.get("/api/agendamentos/nao-existe")
    assert r.status_code == 404


# ── Atualização ───────────────────────────────────────────────────────────────

def test_atualizar_agendamento_nome(client):
    a = _criar_ok(client)
    tok = a["token_admin"]
    r = client.patch(f"/api/agendamentos/{a['id']}?token_admin={tok}",
                     json={"nome_template": "Novo Nome"})
    assert r.status_code == 200
    assert r.json()["nome_template"] == "Novo Nome"


def test_atualizar_agendamento_desativar(client):
    a = _criar_ok(client)
    tok = a["token_admin"]
    r = client.patch(f"/api/agendamentos/{a['id']}?token_admin={tok}",
                     json={"ativo": False})
    assert r.status_code == 200
    assert r.json()["ativo"] is False


def test_atualizar_agendamento_token_invalido_retorna_403(client):
    a = _criar_ok(client)
    r = client.patch(f"/api/agendamentos/{a['id']}?token_admin=ERRADO",
                     json={"nome_template": "X"})
    assert r.status_code == 403


def test_atualizar_agendamento_inexistente_retorna_404(client):
    r = client.patch("/api/agendamentos/nao-existe?token_admin=X", json={"ativo": False})
    assert r.status_code == 404


# ── Deleção ───────────────────────────────────────────────────────────────────

def test_deletar_agendamento(client):
    a = _criar_ok(client)
    tok = a["token_admin"]
    r = client.delete(f"/api/agendamentos/{a['id']}?token_admin={tok}")
    assert r.status_code == 204

    r2 = client.get(f"/api/agendamentos/{a['id']}")
    assert r2.status_code == 404


def test_deletar_agendamento_token_invalido_retorna_403(client):
    a = _criar_ok(client)
    r = client.delete(f"/api/agendamentos/{a['id']}?token_admin=ERRADO")
    assert r.status_code == 403


def test_deletar_agendamento_inexistente_retorna_404(client):
    r = client.delete("/api/agendamentos/nao-existe?token_admin=X")
    assert r.status_code == 404


# ── Execução imediata ─────────────────────────────────────────────────────────

def test_executar_agora_cria_sessao(client):
    a = _criar_ok(client, nome_template="Inventário Imediato")
    tok = a["token_admin"]

    r = client.post(f"/api/agendamentos/{a['id']}/executar-agora?token_admin={tok}")
    assert r.status_code == 200
    data = r.json()
    assert data["sessao_criada_id"] is not None
    assert data["agendamento_id"] == a["id"]


def test_executar_agora_sessao_aparece_na_listagem(client):
    a = _criar_ok(client, nome_template="Inventário Auto")
    tok = a["token_admin"]
    r = client.post(f"/api/agendamentos/{a['id']}/executar-agora?token_admin={tok}")
    sessao_id = r.json()["sessao_criada_id"]

    r2 = client.get("/api/sessoes/")
    assert r2.status_code == 200
    ids = [s["id"] for s in r2.json()]
    assert sessao_id in ids


def test_executar_agora_token_invalido_retorna_403(client):
    a = _criar_ok(client)
    r = client.post(f"/api/agendamentos/{a['id']}/executar-agora?token_admin=ERRADO")
    assert r.status_code == 403


def test_executar_agora_inexistente_retorna_404(client):
    r = client.post("/api/agendamentos/nao-existe/executar-agora?token_admin=X")
    assert r.status_code == 404


def test_executar_agora_com_template_copia_itens(client, sessao_com_itens):
    """Quando sessao_template_id é fornecido, a nova sessão deve herdar os itens."""
    template_id = sessao_com_itens["id"]

    a = _criar_ok(client, nome_template="Com Template", sessao_template_id=template_id)
    tok = a["token_admin"]

    r = client.post(f"/api/agendamentos/{a['id']}/executar-agora?token_admin={tok}")
    assert r.status_code == 200
    nova_sessao_id = r.json()["sessao_criada_id"]

    r2 = client.get(f"/api/sessoes/{nova_sessao_id}/itens")
    assert r2.status_code == 200
    itens = r2.json()
    assert len(itens) == 3  # mesmos 3 itens do template


def test_proxima_execucao_respeita_fuso_brasilia():
    """hora='08:00' significa 08:00 em America/Sao_Paulo (UTC-3) → 11:00 UTC.
    Sem o SCHEDULER_TZ, a sessão nasceria às 05:00 no horário local."""
    from datetime import timezone as _tz
    from app.services.scheduler import calcular_proxima_execucao_inicial
    p = calcular_proxima_execucao_inicial("diario", "08:00", None, None)
    assert p.tzinfo is not None
    assert p.astimezone(_tz.utc).hour == 11


def test_pagina_agendamentos_existe(client):
    r = client.get("/agendamentos")
    assert r.status_code == 200
    assert "Agendamentos" in r.text
