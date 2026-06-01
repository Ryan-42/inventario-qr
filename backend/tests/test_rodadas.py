"""Testes: sistema de rodadas (contagem cega com 1ª/2ª/3ª contagem)."""
from __future__ import annotations


def _reg(client, sessao_id: str, codigo: str, qtd: int, op: str = "T"):
    return client.post(
        f"/api/sessoes/{sessao_id}/contagens",
        json={"codigo": codigo, "quantidade_encontrada": qtd, "operador": op},
    )


def test_primeira_contagem_rodada_1(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = _reg(client, sid, "ABC-001", 10)  # base=10, sem divergência
    assert r.status_code == 201
    assert r.json()["rodada"] == 1


def test_recontagem_sem_divergencia_mantem_rodada(client, sessao_com_itens):
    """Se 1ª contagem foi OK, uma 2ª contagem não deve avançar rodada."""
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 10)   # OK, rodada=1
    r = _reg(client, sid, "ABC-001", 10)  # OK de novo
    assert r.json()["rodada"] == 1


def test_divergencia_avanca_para_segunda_rodada(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 7)    # divergente na rodada 1
    r = _reg(client, sid, "ABC-001", 9)  # 2ª contagem
    data = r.json()
    assert data["rodada"] == 2


def test_segunda_divergencia_avanca_para_terceira_rodada(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 7)   # divergente rodada 1
    _reg(client, sid, "ABC-001", 8)   # divergente rodada 2
    r = _reg(client, sid, "ABC-001", 10)  # 3ª contagem
    assert r.json()["rodada"] == 3


def test_rodada_maxima_capped_em_3(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 7)   # div rodada 1
    _reg(client, sid, "ABC-001", 8)   # div rodada 2
    _reg(client, sid, "ABC-001", 6)   # div rodada 3
    r = _reg(client, sid, "ABC-001", 5)  # tentar 4ª — deve permanecer em 3
    assert r.json()["rodada"] == 3


def test_endpoint_rodadas_vazio(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = client.get(f"/api/sessoes/{sid}/rodadas")
    assert r.status_code == 200
    data = r.json()
    assert data["rodada_maxima"] == 0
    assert data["rodadas"] == []
    assert data["itens_segunda"] == []
    assert data["itens_terceira"] == []


def test_endpoint_rodadas_apos_primeira_contagem(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 10)  # OK
    _reg(client, sid, "ABC-002", 3)   # divergente (base=5)

    r = client.get(f"/api/sessoes/{sid}/rodadas")
    assert r.status_code == 200
    data = r.json()
    assert data["rodada_maxima"] == 1
    assert len(data["rodadas"]) == 1
    assert data["rodadas"][0]["numero"] == 1
    assert data["rodadas"][0]["divergencias"] == 1
    # ABC-002 deve aparecer na lista de 2ª contagem
    codigos_segunda = [i["codigo"] for i in data["itens_segunda"]]
    assert "ABC-002" in codigos_segunda


def test_endpoint_rodadas_segunda_concluida(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 10)  # OK rodada 1
    _reg(client, sid, "ABC-002", 3)   # divergente rodada 1 → vai para 2ª
    _reg(client, sid, "ABC-003", 20)  # OK rodada 1

    # 2ª contagem do divergente
    _reg(client, sid, "ABC-002", 4)   # ainda divergente (base=5)

    r = client.get(f"/api/sessoes/{sid}/rodadas")
    data = r.json()
    assert data["rodada_maxima"] == 2
    # ABC-002 agora deve estar em itens_terceira
    codigos_terceira = [i["codigo"] for i in data["itens_terceira"]]
    assert "ABC-002" in codigos_terceira


def test_buscar_item_retorna_rodada_atual(client, sessao_com_itens):
    sid = sessao_com_itens["id"]

    # Antes de contar
    r = client.get(f"/api/sessoes/{sid}/buscar/ABC-001")
    assert r.json()["rodada_atual"] == 0
    assert r.json()["ja_contado"] is False

    # Após 1ª contagem divergente
    _reg(client, sid, "ABC-001", 7)
    r = client.get(f"/api/sessoes/{sid}/buscar/ABC-001")
    data = r.json()
    assert data["ja_contado"] is True
    assert data["rodada_atual"] == 1
