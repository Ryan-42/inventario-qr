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
    """Item divergente com nova quantidade diferente avança rodada a cada recontagem."""
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 7)   # divergente rodada 1
    _reg(client, sid, "ABC-001", 8)   # nova qtd divergente → rodada 2
    r = _reg(client, sid, "ABC-001", 6)  # nova qtd divergente → rodada 3
    assert r.json()["rodada"] == 3
    # Ao bater com a base (qty=10) o item fica CERTO e a rodada NÃO avança
    r2 = _reg(client, sid, "ABC-001", 10)
    assert r2.json()["divergencia"] is False
    assert r2.json()["rodada"] == 3  # mantém rodada da última contagem divergente


def test_rodada_sem_limite_fixo(client, sessao_com_itens):
    """Sem cap de rodadas: item divergente com nova qtd a cada vez continua avançando."""
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 7)   # div rodada 1
    _reg(client, sid, "ABC-001", 8)   # div rodada 2
    _reg(client, sid, "ABC-001", 6)   # div rodada 3
    r = _reg(client, sid, "ABC-001", 5)  # nova qtd divergente → rodada 4 (sem cap)
    assert r.json()["rodada"] == 4
    assert r.json()["divergencia"] is True
    assert r.json()["para_ajuste"] is False


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
    _reg(client, sid, "ABC-002", 3)   # divergente rodada 1 → vai para recontagem
    _reg(client, sid, "ABC-003", 20)  # OK rodada 1

    # 2ª contagem do divergente — nova qtd diferente, continua divergente
    _reg(client, sid, "ABC-002", 4)

    r = client.get(f"/api/sessoes/{sid}/rodadas")
    data = r.json()
    assert data["rodada_maxima"] == 2
    # ABC-002 ainda divergente: aparece em itens_segunda (lista unificada de pendentes)
    codigos_segunda = [i["codigo"] for i in data["itens_segunda"]]
    assert "ABC-002" in codigos_segunda


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


def test_para_ajuste_somente_com_mesmo_erro_confirmado(client, sessao_com_itens):
    """Para Ajuste só ocorre quando o mesmo erro divergente é confirmado na recontagem."""
    sid = sessao_com_itens["id"]
    # 1ª contagem divergente
    _reg(client, sid, "ABC-001", 7)  # div rodada 1

    # 2ª contagem com quantidade DIFERENTE → ainda DIVERGENTE, NOT para_ajuste
    r = _reg(client, sid, "ABC-001", 8)
    assert r.json()["divergencia"] is True
    assert r.json()["para_ajuste"] is False

    # 3ª contagem repete o mesmo erro da anterior (qty=8) → PARA_AJUSTE confirmado
    r = _reg(client, sid, "ABC-001", 8)
    assert r.json()["divergencia"] is True
    assert r.json()["para_ajuste"] is True


def test_para_ajuste_nao_ocorre_na_rodada_3_automaticamente(client, sessao_com_itens):
    """Sem auto-para_ajuste na rodada 3: nova qtd divergente continua DIVERGENTE."""
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 7)   # div rodada 1
    _reg(client, sid, "ABC-001", 8)   # nova qtd div → rodada 2
    r = _reg(client, sid, "ABC-001", 6)  # nova qtd div → rodada 3, NÃO para_ajuste
    assert r.json()["rodada"] == 3
    assert r.json()["divergencia"] is True
    assert r.json()["para_ajuste"] is False  # ainda precisa recontagem


def test_inventario_nao_pode_concluir_com_divergencias(client, sessao_com_itens):
    """Inventário não pode ser concluído enquanto há itens DIVERGENTE."""
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    _reg(client, sid, "ABC-001", 10)  # certo
    _reg(client, sid, "ABC-002", 3)   # divergente (base=5)
    _reg(client, sid, "ABC-003", 20)  # certo

    r = client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
    assert r.status_code == 422
    assert "divergentes" in r.json()["detail"]

    # Confirma o mesmo erro → vira PARA_AJUSTE, agora pode concluir
    _reg(client, sid, "ABC-002", 3)
    r = client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
    assert r.status_code == 200
