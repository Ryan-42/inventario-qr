"""Testes unitários: ValidationAgent (validação básica, sem IA)."""
from __future__ import annotations

import pytest
from unittest.mock import patch
from app.agents.validation import ValidationAgent


@pytest.fixture()
def agent():
    return ValidationAgent()


def _itens(*rows):
    return [{"codigo": c, "produto": p, "quantidade": q} for c, p, q in rows]


def test_validacao_basica_lista_valida(agent):
    itens = _itens(("A001", "Produto A", 10), ("A002", "Produto B", 5))
    with patch("app.agents.validation.ValidationAgent._enriquecer_com_ia", return_value=None) as mock_ia, \
         patch("app.agents.provider.AIProvider.disponivel", new_callable=lambda: property(lambda self: False)):
        r = agent.validate(itens)
    assert r["valido"] is True
    assert r["total_validos"] == 2
    assert r["total_invalidos"] == 0
    assert r["problemas"] == []
    assert r["fonte"] == "basico"


def test_validacao_codigo_vazio(agent):
    itens = _itens(("", "Produto A", 10))
    r = agent.validate(itens)
    assert r["valido"] is False
    assert any(p["tipo"] == "codigo_vazio" for p in r["problemas"])


def test_validacao_codigo_duplicado(agent):
    itens = _itens(("A001", "Produto A", 10), ("A001", "Produto B", 5))
    r = agent.validate(itens)
    # Duplicata é aviso, não problema crítico
    assert any(a["tipo"] == "duplicata" for a in r["avisos"])


def test_validacao_quantidade_negativa(agent):
    itens = _itens(("A001", "Produto A", -5))
    r = agent.validate(itens)
    assert r["valido"] is False
    assert any(p["tipo"] == "quantidade_negativa" for p in r["problemas"])


def test_validacao_quantidade_zero_e_aviso(agent):
    itens = _itens(("A001", "Produto A", 0))
    r = agent.validate(itens)
    assert any(a["tipo"] == "quantidade_zero" for a in r["avisos"])


def test_validacao_quantidade_invalida(agent):
    itens = [{"codigo": "A001", "produto": "Produto A", "quantidade": "nao-numero"}]
    r = agent.validate(itens)
    assert r["valido"] is False
    assert any(p["tipo"] == "quantidade_invalida" for p in r["problemas"])


def test_validacao_produto_vazio_e_aviso(agent):
    itens = _itens(("A001", "", 10))
    r = agent.validate(itens)
    assert any(a["tipo"] == "produto_vazio" for a in r["avisos"])


def test_validacao_lista_vazia(agent):
    r = agent.validate([])
    # Lista vazia não passa no excel_service antes de chegar aqui,
    # mas o agent deve lidar graciosamente
    assert r["total_validos"] == 0
    assert r["total_invalidos"] == 0


def test_validacao_retorna_campos_obrigatorios(agent):
    itens = _itens(("A001", "Produto A", 10))
    r = agent.validate(itens)
    campos = {"valido", "pode_importar_com_avisos", "problemas", "avisos",
              "total_validos", "total_invalidos", "fonte", "confianca"}
    assert campos.issubset(set(r.keys()))


def test_pode_importar_com_avisos_sem_problemas(agent):
    itens = _itens(("A001", "Produto A", 0))  # aviso (zero) mas sem problema crítico
    r = agent.validate(itens)
    assert r["pode_importar_com_avisos"] is True
    assert r["valido"] is True
