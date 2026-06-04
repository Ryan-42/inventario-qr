"""Testes: grupos de operadores, supervisor, pausa/retomada."""
from __future__ import annotations


def _reg(client, sid, codigo, qtd):
    return client.post(f"/api/sessoes/{sid}/contagens",
                       json={"codigo": codigo, "quantidade_encontrada": qtd})


# ── CRUD Grupos ───────────────────────────────────────────────────────────────

def test_criar_grupo(client, sessao):
    sid = sessao["id"]
    r = client.post(f"/api/sessoes/{sid}/grupos",
                    json={"nome": "Grupo Alpha", "filtro": "ABC", "tipo_filtro": "prefixo"})
    assert r.status_code == 201
    data = r.json()
    assert data["nome"] == "Grupo Alpha"
    assert "token" in data
    assert len(data["token"]) > 0
    assert "mobile_url" in data


def test_listar_grupos_vazio(client, sessao):
    r = client.get(f"/api/sessoes/{sessao['id']}/grupos")
    assert r.status_code == 200
    assert r.json() == []


def test_listar_grupos(client, sessao):
    sid = sessao["id"]
    client.post(f"/api/sessoes/{sid}/grupos",
                json={"nome": "G1", "filtro": "*", "tipo_filtro": "todos"})
    client.post(f"/api/sessoes/{sid}/grupos",
                json={"nome": "G2", "filtro": "X", "tipo_filtro": "prefixo"})
    r = client.get(f"/api/sessoes/{sid}/grupos")
    assert len(r.json()) == 2


def test_deletar_grupo(client, sessao):
    sid = sessao["id"]
    r_create = client.post(f"/api/sessoes/{sid}/grupos",
                           json={"nome": "Tmp", "filtro": "*", "tipo_filtro": "todos"})
    gid = r_create.json()["id"]
    r_del = client.delete(f"/api/sessoes/{sid}/grupos/{gid}")
    assert r_del.status_code == 204
    r_list = client.get(f"/api/sessoes/{sid}/grupos")
    assert all(g["id"] != gid for g in r_list.json())


def test_regenerar_token_grupo(client, sessao):
    sid = sessao["id"]
    r = client.post(f"/api/sessoes/{sid}/grupos",
                    json={"nome": "G", "filtro": "*", "tipo_filtro": "todos"})
    gid = r.json()["id"]
    tok_antigo = r.json()["token"]
    r2 = client.post(f"/api/sessoes/{sid}/grupos/{gid}/regenerar-token")
    assert r2.status_code == 200
    assert r2.json()["token"] != tok_antigo


def test_criar_grupo_sessao_inativa_bloqueado(client, sessao):
    sid = sessao["id"]
    tok = sessao["token_admin"]
    client.patch(f"/api/sessoes/{sid}/cancelar?token_admin={tok}")
    r = client.post(f"/api/sessoes/{sid}/grupos",
                    json={"nome": "G", "filtro": "*", "tipo_filtro": "todos"})
    assert r.status_code == 409


# ── Novo token admin ──────────────────────────────────────────────────────────

def test_novo_token_admin_com_token_correto(client, sessao):
    sid = sessao["id"]
    tok = sessao["token_admin"]
    r = client.post(f"/api/sessoes/{sid}/novo-token-admin",
                    json={"token_atual": tok})
    assert r.status_code == 200
    novo = r.json()["token_admin"]
    assert novo != tok
    assert len(novo) == 16


def test_novo_token_admin_com_token_errado(client, sessao):
    r = client.post(f"/api/sessoes/{sessao['id']}/novo-token-admin",
                    json={"token_atual": "ERRADO"})
    assert r.status_code == 403


# ── lista_operador ────────────────────────────────────────────────────────────

def test_lista_operador_rodada1_mostra_nao_contados(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r_tok = client.get(f"/api/sessoes/{sid}/token-acesso")
    tok = r_tok.json()["token"]
    r = client.get(f"/api/sessoes/{sid}/lista-operador?token={tok}&rodada=1")
    assert r.status_code == 200
    codigos = [i["codigo"] for i in r.json()]
    assert "ABC-001" in codigos
    assert "ABC-002" in codigos
    assert "ABC-003" in codigos


def test_lista_operador_rodada1_exclui_ja_contados(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 10)  # já contado
    r_tok = client.get(f"/api/sessoes/{sid}/token-acesso")
    tok = r_tok.json()["token"]
    r = client.get(f"/api/sessoes/{sid}/lista-operador?token={tok}&rodada=1")
    codigos = [i["codigo"] for i in r.json()]
    assert "ABC-001" not in codigos
    assert "ABC-002" in codigos


def test_lista_operador_rodada2_mostra_divergentes(client, sessao_com_itens):
    """Rodada 2: só mostra itens divergentes sem para_ajuste."""
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 10)  # OK
    _reg(client, sid, "ABC-002", 3)   # divergente (base=5)
    _reg(client, sid, "ABC-003", 20)  # OK
    # Gera token para rodada 2
    tok_admin = sessao_com_itens["token_admin"]
    r_tok = client.post(f"/api/sessoes/{sid}/gerar-token?token_admin={tok_admin}&rodada=2")
    tok = r_tok.json()["token"]
    r = client.get(f"/api/sessoes/{sid}/lista-operador?token={tok}&rodada=2")
    assert r.status_code == 200
    codigos = [i["codigo"] for i in r.json()]
    assert "ABC-002" in codigos
    assert "ABC-001" not in codigos
    assert "ABC-003" not in codigos


def test_lista_operador_rodada2_exclui_para_ajuste(client, sessao_com_itens):
    """Para_ajuste não deve aparecer na lista de recontagem."""
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 7)
    _reg(client, sid, "ABC-001", 7)  # PARA_AJUSTE
    _reg(client, sid, "ABC-002", 3)  # divergente ativo
    _reg(client, sid, "ABC-003", 20)
    tok_admin = sessao_com_itens["token_admin"]
    r_tok = client.post(f"/api/sessoes/{sid}/gerar-token?token_admin={tok_admin}&rodada=2")
    tok = r_tok.json()["token"]
    r = client.get(f"/api/sessoes/{sid}/lista-operador?token={tok}&rodada=2")
    codigos = [i["codigo"] for i in r.json()]
    assert "ABC-002" in codigos
    assert "ABC-001" not in codigos, "ABC-001 esta PARA_AJUSTE, nao deve aparecer em recontagem"


# ── Supervisor ────────────────────────────────────────────────────────────────

def test_supervisor_so_ve_divergentes_ativos(client, sessao_com_itens):
    """Supervisor deve ver apenas divergentes sem para_ajuste."""
    sid = sessao_com_itens["id"]
    _reg(client, sid, "ABC-001", 7)
    _reg(client, sid, "ABC-001", 7)  # PARA_AJUSTE
    _reg(client, sid, "ABC-002", 3)  # divergente ativo
    _reg(client, sid, "ABC-003", 20) # OK

    # Cria token supervisor
    r_tok = client.get(f"/api/sessoes/{sid}/token-supervisor")
    tok = r_tok.json()["token"]

    r = client.get(f"/api/sessoes/{sid}/itens-supervisor?token={tok}")
    assert r.status_code == 200
    data = r.json()
    assert data["ativo"] is True
    codigos = [i["codigo"] for i in data["itens"]]
    assert "ABC-002" in codigos
    assert "ABC-001" not in codigos, "ABC-001 esta PARA_AJUSTE e nao deveria aparecer"
    assert data["total_divergentes"] == 1


def test_supervisor_token_invalido_retorna_403(client, sessao_com_itens):
    sid = sessao_com_itens["id"]
    r = client.get(f"/api/sessoes/{sid}/itens-supervisor?token=INVALIDO")
    assert r.status_code == 403


def test_supervisor_inativo_em_r1(client, sessao_com_itens):
    """Supervisor só fica ativo após conclusão da 1ª rodada."""
    sid = sessao_com_itens["id"]
    r_tok = client.get(f"/api/sessoes/{sid}/token-supervisor")
    tok = r_tok.json()["token"]
    r = client.get(f"/api/sessoes/{sid}/itens-supervisor?token={tok}")
    assert r.json()["ativo"] is False


# ── Pausa e retomada ──────────────────────────────────────────────────────────

def test_pausar_e_retomar_sessao(client, sessao):
    sid = sessao["id"]
    tok = sessao["token_admin"]
    r_pausar = client.patch(f"/api/sessoes/{sid}/pausar?token_admin={tok}")
    assert r_pausar.status_code == 200
    assert r_pausar.json()["status"] == "pausada"

    r_get = client.get(f"/api/sessoes/{sid}")
    assert r_get.json()["status"] == "pausada"

    r_retomar = client.patch(f"/api/sessoes/{sid}/retomar?token_admin={tok}")
    assert r_retomar.status_code == 200
    assert r_retomar.json()["status"] == "ativa"
    assert "novo_token" in r_retomar.json()


def test_retomar_preserva_rodada_token(client, sessao_com_itens):
    """Após retomada, rodada_token deve ser mantido (não zerado)."""
    sid = sessao_com_itens["id"]
    tok_admin = sessao_com_itens["token_admin"]
    client.post(f"/api/sessoes/{sid}/gerar-token?token_admin={tok_admin}&rodada=2")
    client.patch(f"/api/sessoes/{sid}/pausar?token_admin={tok_admin}")
    r_retomar = client.patch(f"/api/sessoes/{sid}/retomar?token_admin={tok_admin}")
    assert r_retomar.status_code == 200
    r_tok = client.get(f"/api/sessoes/{sid}/token-acesso")
    assert r_tok.json()["rodada"] == 2


def test_pausar_sessao_ja_pausada_bloqueado(client, sessao):
    sid = sessao["id"]
    tok = sessao["token_admin"]
    client.patch(f"/api/sessoes/{sid}/pausar?token_admin={tok}")
    r = client.patch(f"/api/sessoes/{sid}/pausar?token_admin={tok}")
    assert r.status_code == 409


def test_retomar_sessao_nao_pausada_bloqueado(client, sessao):
    tok = sessao["token_admin"]
    r = client.patch(f"/api/sessoes/{sessao['id']}/retomar?token_admin={tok}")
    assert r.status_code == 409


def test_pausar_token_invalido_retorna_403(client, sessao):
    r = client.patch(f"/api/sessoes/{sessao['id']}/pausar?token_admin=ERRADO")
    assert r.status_code == 403


def test_retomar_token_invalido_retorna_403(client, sessao):
    tok = sessao["token_admin"]
    client.patch(f"/api/sessoes/{sessao['id']}/pausar?token_admin={tok}")
    r = client.patch(f"/api/sessoes/{sessao['id']}/retomar?token_admin=ERRADO")
    assert r.status_code == 403
