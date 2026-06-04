"""Testes: comportamento avançado do estado PARA_AJUSTE e garantia de terminação."""
from __future__ import annotations


def _reg(client, sid, codigo, qtd):
    return client.post(f"/api/sessoes/{sid}/contagens",
                       json={"codigo": codigo, "quantidade_encontrada": qtd})


# ── Garantia de terminação (MAX_RODADAS = 5) ──────────────────────────────────

def test_max_rodadas_divergencia_forca_para_ajuste(client, sessao_com_itens):
    """Após 5 rodadas com quantidades sempre diferentes, item deve ser forçado para PARA_AJUSTE."""
    sid = sessao_com_itens["id"]
    # 5 quantidades diferentes — nunca a mesma duas vezes consecutivas
    for qtd in [7, 8, 6, 9, 3]:
        _reg(client, sid, "ABC-001", qtd)

    # BuscaItemResponse: para_ajuste está no campo raiz; contagem em contagem_anterior
    r = client.get(f"/api/sessoes/{sid}/buscar/ABC-001")
    data = r.json()
    assert data["para_ajuste"] is True, (
        f"Esperava para_ajuste=True após 5 rodadas diferentes. Resposta: {data}"
    )
    assert data["contagem_anterior"]["divergencia"] is True

def test_item_nao_forca_para_ajuste_antes_de_5_rodadas(client, sessao_com_itens):
    """4 rodadas com qtds diferentes: ainda DIVERGENTE, não forçado."""
    sid = sessao_com_itens["id"]
    for qtd in [7, 8, 6, 9]:  # 4 qtds diferentes
        _reg(client, sid, "ABC-001", qtd)

    r = client.get(f"/api/sessoes/{sid}/buscar/ABC-001")
    data = r.json()
    assert data["para_ajuste"] is False
    assert data["contagem_anterior"]["divergencia"] is True
    assert data["contagem_anterior"]["rodada"] == 4

def test_inventario_pode_concluir_apos_max_rodadas(client, sessao_com_itens):
    """Após MAX_RODADAS, item vira PARA_AJUSTE → inventário pode ser concluído."""
    sid = sessao_com_itens["id"]
    tok = sessao_com_itens["token_admin"]
    # Conta ABC-002 e ABC-003 corretamente
    _reg(client, sid, "ABC-002", 5)
    _reg(client, sid, "ABC-003", 20)
    # ABC-001: 5 rodadas diferentes → forçado para para_ajuste
    for qtd in [7, 8, 6, 9, 3]:
        _reg(client, sid, "ABC-001", qtd)

    # Agora todos os itens devem estar Certo ou Para Ajuste
    r = client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
    assert r.status_code == 200, f"Esperava 200, got {r.status_code}: {r.text}"


# ── PARA_AJUSTE preserva quantidade confirmada ────────────────────────────────

def test_para_ajuste_preserva_qty_confirmada(client, sessao_com_itens):
    """Quando PARA_AJUSTE e nova qty diferente chega, Contagem mantém a qty duplo-confirmada."""
    sid = sessao_com_itens["id"]
    # Confirma erro: ABC-001 qty=7 duas vezes → PARA_AJUSTE com qty=7
    _reg(client, sid, "ABC-001", 7)
    _reg(client, sid, "ABC-001", 7)

    r = client.get(f"/api/sessoes/{sid}/buscar/ABC-001")
    assert r.json()["para_ajuste"] is True
    assert r.json()["contagem_anterior"]["quantidade_encontrada"] == 7

    # Operador envia qty=8 (nova tentativa diferente)
    _reg(client, sid, "ABC-001", 8)

    # Deve continuar PARA_AJUSTE mas preservar qty=7 (a confirmada)
    r2 = client.get(f"/api/sessoes/{sid}/buscar/ABC-001")
    qty_atual = r2.json()["contagem_anterior"]["quantidade_encontrada"]
    assert r2.json()["para_ajuste"] is True
    assert qty_atual == 7, (
        f"Esperava qty=7 (confirmada), recebi {qty_atual}"
    )

def test_para_ajuste_corrigido_para_base(client, sessao_com_itens):
    """PARA_AJUSTE pode ser corrigido se operador acertar a quantidade base."""
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 7)
    _reg(client, sid, "ABC-001", 7)  # → PARA_AJUSTE

    # Operador acerta: qty=10 = base → deve virar CERTO
    r = _reg(client, sid, "ABC-001", 10)
    assert r.json()["divergencia"] is False
    assert r.json()["para_ajuste"] is False

def test_para_ajuste_nao_aparece_em_progresso_faltando(client, sessao_com_itens):
    """Itens PARA_AJUSTE devem aparecer como resolvidos em /progresso."""
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 7)
    _reg(client, sid, "ABC-001", 7)  # PARA_AJUSTE
    _reg(client, sid, "ABC-002", 5)  # OK
    _reg(client, sid, "ABC-003", 20)  # OK

    r = client.get(f"/api/sessoes/{sid}/progresso")
    data = r.json()
    assert data["faltando_r1"] == 0
    assert data["faltando_r2"] == 0
    assert data["completa"] is True

def test_para_ajuste_nao_aparece_em_rodadas_pendentes(client, sessao_com_itens):
    """Itens PARA_AJUSTE não devem aparecer em itens_segunda de /rodadas."""
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 7)
    _reg(client, sid, "ABC-001", 7)  # PARA_AJUSTE
    _reg(client, sid, "ABC-002", 5)
    _reg(client, sid, "ABC-003", 20)

    r = client.get(f"/api/sessoes/{sid}/rodadas")
    assert r.status_code == 200
    codigos_pendentes = [i["codigo"] for i in r.json()["itens_segunda"]]
    assert "ABC-001" not in codigos_pendentes, (
        "ABC-001 está PARA_AJUSTE e não deveria aparecer como pendente em itens_segunda"
    )
