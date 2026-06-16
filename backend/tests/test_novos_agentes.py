"""
Testes unitários e de integração para os 5 novos agentes do INVIQ.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, PropertyMock
from fastapi.testclient import TestClient

from app.agents.preditor import PredictionAgent
from app.agents.antifraude import AntiFraudeAgent
from app.agents.sync_erp import SyncERPAgent
from app.agents.sop_coach import SopCoachAgent
from app.agents.plano_acao import PlanoAcaoAgent
from app.database import SessionLocal
from tests.conftest import TestingSession


# ---------------------------------------------------------------------------
# Testes do PredictionAgent
# ---------------------------------------------------------------------------

def test_prediction_agent_basico():
    db = TestingSession()
    try:
        from app.models.sessao import Sessao
        from app.models.item_base import ItemBase

        # Criar sessão de teste
        sessao = Sessao(nome="Teste Predição", codigo="INV-2026-9999")
        db.add(sessao)
        db.commit()

        # Adicionar itens
        item = ItemBase(sessao_id=sessao.id, codigo="SKU-99", produto="Produto Teste", quantidade_base=100, valor_estoque=1000.0)
        db.add(item)
        db.commit()

        agent = PredictionAgent()
        # Mocking provider para forçar caminho sem IA
        with patch("app.agents.provider.AIProvider.disponivel", new_callable=PropertyMock) as mock_disp:
            mock_disp.return_value = False
            res = agent.prever(sessao.id, db)

        assert res["sessao_codigo"] == "INV-2026-9999"
        assert res["total_itens_sessao"] == 1
        assert res["fonte"] == "basico"
        assert len(res["itens_alto_risco"]) == 0  # Nenhum histórico ainda
        assert res["estimativas"]["duracao_estimada_minutos"] > 0
    finally:
        db.close()


def test_prediction_agent_endpoint(client, sessao_com_itens):
    # Endpoint POST /api/agentes/predicao/{sessao_id}
    with patch("app.agents.provider.AIProvider.disponivel", new_callable=PropertyMock) as mock_disp:
        mock_disp.return_value = False
        r = client.post(f"/api/agentes/predicao/{sessao_com_itens['id']}")

    assert r.status_code == 200
    res = r.json()
    assert res["sessao_codigo"] == sessao_com_itens["codigo"]
    assert res["total_itens_sessao"] == 3
    assert res["fonte"] == "basico"


# ---------------------------------------------------------------------------
# Testes do AntiFraudeAgent
# ---------------------------------------------------------------------------

def test_antifraude_agent_sem_anomalias():
    db = TestingSession()
    try:
        from app.models.sessao import Sessao
        from app.models.contagem import HistoricoContagem
        from datetime import datetime, timedelta

        sessao = Sessao(nome="Teste Fraude", codigo="INV-2026-8888")
        db.add(sessao)
        db.commit()

        # Adicionar contagens com intervalos longos (sem fraude)
        for idx in range(5):
            h = HistoricoContagem(
                sessao_id=sessao.id,
                codigo=f"SKU-{idx}",
                quantidade_encontrada=10,
                quantidade_base=10,
                operador="Joao",
                timestamp=datetime.now() + timedelta(minutes=idx * 5)
            )
            db.add(h)
        db.commit()

        agent = AntiFraudeAgent()
        with patch("app.agents.provider.AIProvider.disponivel", new_callable=PropertyMock) as mock_disp:
            mock_disp.return_value = False
            res = agent.auditar(sessao.id, db)

        assert res["total_operadores_analisados"] == 1
        assert res["risco_geral"] == "baixo"
        assert len(res["anomalias_detectadas"]) == 0
    finally:
        db.close()


def test_antifraude_agent_ghost_counting():
    db = TestingSession()
    try:
        from app.models.sessao import Sessao
        from app.models.contagem import HistoricoContagem
        from datetime import datetime, timedelta

        sessao = Sessao(nome="Teste Fraude", codigo="INV-2026-8887")
        db.add(sessao)
        db.commit()

        # Adicionar contagens com intervalos de 1 segundo (Ghost Counting)
        base_time = datetime.now()
        for idx in range(12):
            h = HistoricoContagem(
                sessao_id=sessao.id,
                codigo=f"SKU-{idx}",
                quantidade_encontrada=10,
                quantidade_base=10,  # Acerto exato
                operador="Joao",
                timestamp=base_time + timedelta(seconds=idx)
            )
            db.add(h)
        db.commit()

        agent = AntiFraudeAgent()
        with patch("app.agents.provider.AIProvider.disponivel", new_callable=PropertyMock) as mock_disp:
            mock_disp.return_value = False
            res = agent.auditar(sessao.id, db)

        assert res["total_operadores_analisados"] == 1
        assert res["risco_geral"] == "alto"
        assert len(res["anomalias_detectadas"]) > 0
        assert res["anomalias_detectadas"][0]["tipo"] == "ghost_counting"
    finally:
        db.close()


def test_antifraude_endpoint(client, sessao_com_itens):
    r = client.post(f"/api/agentes/antifraude/{sessao_com_itens['id']}")
    assert r.status_code == 200
    res = r.json()
    assert "total_operadores_analisados" in res
    assert "risco_geral" in res


# ---------------------------------------------------------------------------
# Testes do SyncERPAgent
# ---------------------------------------------------------------------------

def test_sync_erp_agent_ajuste(client, sessao_com_itens):
    # Registrar contagem com divergência
    r_tok = client.get(f"/api/sessoes/{sessao_com_itens['id']}/token-acesso")
    assert r_tok.status_code == 200
    tok = r_tok.json()["token"]
    r_count = client.post(
        f"/api/sessoes/{sessao_com_itens['id']}/contagens?token={tok}",
        json={"codigo": "ABC-001", "quantidade_encontrada": 12, "operador": "Joao", "observacao": "Divergência"}
    )
    assert r_count.status_code == 201

    # Marcar para ajuste
    db = TestingSession()
    try:
        from app.models.contagem import Contagem
        c = db.query(Contagem).filter(Contagem.sessao_id == sessao_com_itens["id"], Contagem.codigo == "ABC-001").first()
        c.para_ajuste = True
        db.commit()
    finally:
        db.close()

    # Chamar endpoint de Sync ERP para Bling
    with patch("app.agents.provider.AIProvider.disponivel", new_callable=PropertyMock) as mock_disp:
        mock_disp.return_value = False
        r_sync = client.post(
            f"/api/agentes/sync-erp/{sessao_com_itens['id']}",
            json={"erp_nome": "bling"}
        )

    assert r_sync.status_code == 200
    res = r_sync.json()
    assert res["erp"] == "bling"
    assert res["total_itens_ajustados"] == 1
    assert "payload_integracao" in res
    assert len(res["payload_integracao"]["estoque"]) == 1
    assert res["payload_integracao"]["estoque"][0]["codigo"] == "ABC-001"


# ---------------------------------------------------------------------------
# Testes do SopCoachAgent
# ---------------------------------------------------------------------------

def test_sop_coach_agent_chat():
    agent = SopCoachAgent()
    
    # Pergunta sobre etiqueta danificada
    res = agent.responder([{"role": "user", "content": "A etiqueta está rasgada, o que fazer?"}])
    assert "etiqueta" in res["resposta"].lower() or "manual" in res["resposta"].lower()

    # Pergunta sobre rede offline
    res_offline = agent.responder([{"role": "user", "content": "Ficou offline, vou perder as contagens?"}])
    assert "offline" in res_offline["resposta"].lower() or "local" in res_offline["resposta"].lower()


def test_sop_coach_endpoint(client, sessao_com_itens):
    r = client.post(
        f"/api/agentes/sop-coach/{sessao_com_itens['id']}",
        json={
            "mensagens": [{"role": "user", "content": "Como funciona a recontagem?"}],
            "contexto_extra": "Item: ABC-001"
        }
    )
    assert r.status_code == 200
    res = r.json()
    assert "resposta" in res
    assert res["contexto_verificado"] is True


# ---------------------------------------------------------------------------
# Testes do PlanoAcaoAgent
# ---------------------------------------------------------------------------

def test_plano_acao_agent_gerar(client, sessao_com_itens):
    with patch("app.agents.provider.AIProvider.disponivel", new_callable=PropertyMock) as mock_disp:
        mock_disp.return_value = False
        r = client.post(f"/api/agentes/plano-acao/{sessao_com_itens['id']}")

    assert r.status_code == 200
    res = r.json()
    assert res["sessao_codigo"] == sessao_com_itens["codigo"]
    assert len(res["plano_5w2h"]) >= 2
    assert "o_que" in res["plano_5w2h"][0]
    assert "por_que" in res["plano_5w2h"][0]
