"""
Testes de cenários não cobertos pelos 298 testes existentes.

Cenários cobertos:
  A) Delete de sessão com historico_contagens — bug corrigido (FK violation)
  B) Segunda aprovação — workflow completo (aprovar, token errado, token NULL)
  C) Filiais CRUD — criar, listar, buscar, atualizar, desativar, deletar, sessoes_da_filial
  D) Grupos de operadores — criar, listar, deletar, filtro por prefixo, verificar-grupo
  E) Progresso de rodada — cálculo correto com divergências e resolução
  F) Webhook URL validation via API — URL privada → 422, pública → 201
  G) Concluir sessão sem itens → 422 com mensagem correta
  H) Delete de contagem — libera item para recontagem
  I) Lista operador — token obrigatório, filtro por grupo
  J) Pausar/retomar sessão
"""
from __future__ import annotations

import io
import openpyxl
import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _upload_itens(client, sessao_id: str, token_admin: str,
                  itens: list[tuple[str, str, int]] | None = None):
    """Importa itens via Excel. itens = [(codigo, produto, quantidade), ...]"""
    if itens is None:
        itens = [
            ("ABC-001", "Produto Alpha", 10),
            ("ABC-002", "Produto Beta",  5),
            ("ABC-003", "Produto Gamma", 20),
        ]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["codigo", "produto", "quantidade"])
    for row in itens:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    r = client.post(
        f"/api/sessoes/{sessao_id}/upload?token_admin={token_admin}",
        files={"file": ("itens.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 201, f"Upload falhou: {r.text}"
    return r.json()


def _registrar(client, sessao_id: str, codigo: str, qtd: int, operador: str = "Tester"):
    return client.post(
        f"/api/sessoes/{sessao_id}/contagens",
        json={"codigo": codigo, "quantidade_encontrada": qtd, "operador": operador},
    )


def _concluir_todos(client, sessao_id: str, token_admin: str,
                    itens: list[tuple[str, int]]):
    """Registra contagens e conclui a sessão."""
    for codigo, qtd in itens:
        _registrar(client, sessao_id, codigo, qtd)
    return client.patch(f"/api/sessoes/{sessao_id}/concluir?token_admin={token_admin}")


# ─── A) Delete com historico_contagens ────────────────────────────────────────

class TestDeleteComHistorico:
    """
    Bug corrigido: deletar sessão com HistoricoContagem gerava FK violation em PostgreSQL
    porque o ORM não tinha cascade para HistoricoContagem.
    O repo agora deleta explicitamente: db.query(HistoricoContagem)...delete()
    """

    def test_delete_sessao_sem_historico(self, client, sessao):
        """Sessão sem itens/contagens deve deletar com 204."""
        sid = sessao["id"]
        tok = sessao["token_admin"]
        r = client.delete(f"/api/sessoes/{sid}?token_admin={tok}")
        assert r.status_code == 204

    def test_delete_sessao_com_itens_sem_contagem(self, client, sessao_com_itens):
        """Sessão com itens mas sem nenhuma contagem deve deletar com 204."""
        sid = sessao_com_itens["id"]
        tok = sessao_com_itens["token_admin"]
        r = client.delete(f"/api/sessoes/{sid}?token_admin={tok}")
        assert r.status_code == 204

    def test_delete_sessao_com_uma_contagem_e_historico(self, client, sessao_com_itens):
        """Registrar 1 contagem gera 1 HistoricoContagem — delete deve ser 204 (não FK error)."""
        sid = sessao_com_itens["id"]
        tok = sessao_com_itens["token_admin"]
        # Registra 1 contagem → cria 1 Contagem + 1 HistoricoContagem
        r_cnt = _registrar(client, sid, "ABC-001", 10)
        assert r_cnt.status_code == 201
        # Delete da sessão deve limpar HistoricoContagem antes de deletar a sessão
        r = client.delete(f"/api/sessoes/{sid}?token_admin={tok}")
        assert r.status_code == 204

    def test_delete_sessao_com_recontagem_e_multiplos_historicos(self, client, sessao_com_itens):
        """Recontagem gera 2 entradas no histórico — delete deve funcionar."""
        sid = sessao_com_itens["id"]
        tok = sessao_com_itens["token_admin"]
        _registrar(client, sid, "ABC-001", 10)
        _registrar(client, sid, "ABC-001", 8)   # recontagem → 2 entradas no historico
        _registrar(client, sid, "ABC-002", 5)
        r = client.delete(f"/api/sessoes/{sid}?token_admin={tok}")
        assert r.status_code == 204

    def test_sessao_deletada_nao_encontrada_depois(self, client, sessao_com_itens):
        """Após delete, sessão não deve mais existir."""
        sid = sessao_com_itens["id"]
        tok = sessao_com_itens["token_admin"]
        _registrar(client, sid, "ABC-001", 10)
        client.delete(f"/api/sessoes/{sid}?token_admin={tok}")
        r = client.get(f"/api/sessoes/{sid}")
        assert r.status_code == 404


# ─── B) Segunda aprovação ─────────────────────────────────────────────────────

class TestSegundaAprovacao:
    """Workflow 4-olhos: concluir → obter token → aprovar/rejeitar."""

    def _preparar_sessao_concluida(self, client):
        """Cria sessão com 3 itens, conta todos, conclui. Retorna (sessao_id, token_admin)."""
        r_s = client.post("/api/sessoes/", json={"nome": "Sessão 4 Olhos"})
        assert r_s.status_code == 201
        sid = r_s.json()["id"]
        tok = r_s.json()["token_admin"]
        _upload_itens(client, sid, tok)
        r_c = _concluir_todos(client, sid, tok,
                              [("ABC-001", 10), ("ABC-002", 5), ("ABC-003", 20)])
        assert r_c.status_code == 200, f"Falha ao concluir: {r_c.text}"
        return sid, tok

    def test_status_segunda_aprovacao_pendente_apos_conclusao(self, client):
        """Após concluir a sessão, segunda aprovação deve estar pendente."""
        sid, _ = self._preparar_sessao_concluida(client)
        r = client.get(f"/api/sessoes/{sid}/segunda-aprovacao")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "pendente"
        assert data["aprovada"] is False
        assert data["rejeitada"] is False

    def test_status_segunda_aprovacao_expoe_token(self, client):
        """O status deve expor o token_segunda_aprovacao para que o gestor o envie ao aprovador."""
        sid, _ = self._preparar_sessao_concluida(client)
        r = client.get(f"/api/sessoes/{sid}/segunda-aprovacao")
        assert r.status_code == 200
        data = r.json()
        token = data.get("token_segunda_aprovacao")
        assert token is not None and len(token) >= 8

    def test_aprovar_com_token_correto(self, client):
        """Aprovação com token correto deve retornar 200 e mensagem de confirmação."""
        sid, _ = self._preparar_sessao_concluida(client)
        token = client.get(f"/api/sessoes/{sid}/segunda-aprovacao").json()["token_segunda_aprovacao"]
        r = client.post(
            f"/api/sessoes/{sid}/segunda-aprovacao/aprovar",
            params={"token_segunda_aprovacao": token, "aprovador": "Gestor B"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "aprovada" in data["mensagem"].lower() or "confirmada" in data["mensagem"].lower()
        assert data["aprovador"] == "Gestor B"

    def test_aprovar_com_token_errado_retorna_403(self, client):
        """Token incorreto deve retornar 403."""
        sid, _ = self._preparar_sessao_concluida(client)
        r = client.post(
            f"/api/sessoes/{sid}/segunda-aprovacao/aprovar",
            params={"token_segunda_aprovacao": "TOKEN-ERRADO", "aprovador": "Impostor"},
        )
        assert r.status_code == 403
        assert "inválido" in r.json()["detail"].lower()

    def test_aprovar_duas_vezes_retorna_409(self, client):
        """Aprovar uma sessão já aprovada deve retornar 409."""
        sid, _ = self._preparar_sessao_concluida(client)
        token = client.get(f"/api/sessoes/{sid}/segunda-aprovacao").json()["token_segunda_aprovacao"]
        client.post(
            f"/api/sessoes/{sid}/segunda-aprovacao/aprovar",
            params={"token_segunda_aprovacao": token},
        )
        r2 = client.post(
            f"/api/sessoes/{sid}/segunda-aprovacao/aprovar",
            params={"token_segunda_aprovacao": token},
        )
        assert r2.status_code == 409
        assert "aprovada" in r2.json()["detail"].lower()

    def test_rejeitar_com_token_correto(self, client):
        """Rejeição com token correto deve retornar 200."""
        sid, _ = self._preparar_sessao_concluida(client)
        token = client.get(f"/api/sessoes/{sid}/segunda-aprovacao").json()["token_segunda_aprovacao"]
        r = client.post(
            f"/api/sessoes/{sid}/segunda-aprovacao/rejeitar",
            params={
                "token_segunda_aprovacao": token,
                "motivo": "Divergências não justificadas",
                "aprovador": "Gestor B",
            },
        )
        assert r.status_code == 200

    def test_rejeitar_com_token_errado_retorna_403(self, client):
        """Token incorreto na rejeição deve retornar 403."""
        sid, _ = self._preparar_sessao_concluida(client)
        r = client.post(
            f"/api/sessoes/{sid}/segunda-aprovacao/rejeitar",
            params={"token_segunda_aprovacao": "TOKEN-ERRADO"},
        )
        assert r.status_code == 403

    def test_status_apos_aprovacao_e_aprovada(self, client):
        """Após aprovação, status deve ser 'aprovada'."""
        sid, _ = self._preparar_sessao_concluida(client)
        token = client.get(f"/api/sessoes/{sid}/segunda-aprovacao").json()["token_segunda_aprovacao"]
        client.post(
            f"/api/sessoes/{sid}/segunda-aprovacao/aprovar",
            params={"token_segunda_aprovacao": token},
        )
        r = client.get(f"/api/sessoes/{sid}/segunda-aprovacao")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "aprovada"
        assert data["aprovada"] is True

    def test_aprovar_sessao_ativa_retorna_422(self, client, sessao_com_itens):
        """Tentar aprovar sessão ainda ativa deve retornar 422."""
        sid = sessao_com_itens["id"]
        # Cria token qualquer — a validação de status vem antes da validação de token
        r = client.post(
            f"/api/sessoes/{sid}/segunda-aprovacao/aprovar",
            params={"token_segunda_aprovacao": "QUALQUER"},
        )
        assert r.status_code == 422
        assert "concluida" in r.json()["detail"].lower()

    def test_segunda_aprovacao_sessao_inexistente_retorna_404(self, client):
        r = client.get("/api/sessoes/nao-existe-00/segunda-aprovacao")
        assert r.status_code == 404


# ─── C) Filiais CRUD ──────────────────────────────────────────────────────────

class TestFiliaisCRUD:
    def test_criar_filial(self, client):
        r = client.post("/api/filiais/", json={"nome": "Filial SP", "codigo": "SP01"})
        assert r.status_code == 201
        data = r.json()
        assert data["nome"] == "Filial SP"
        assert data["codigo"] == "SP01"
        assert data["ativo"] is True
        assert data["id"]

    def test_criar_filial_codigo_uppercase(self, client):
        """Código deve ser normalizado para uppercase."""
        r = client.post("/api/filiais/", json={"nome": "Filial RJ", "codigo": "rj02"})
        assert r.status_code == 201
        assert r.json()["codigo"] == "RJ02"

    def test_criar_filial_codigo_duplicado_retorna_409(self, client):
        client.post("/api/filiais/", json={"nome": "Filial A", "codigo": "SP01"})
        r = client.post("/api/filiais/", json={"nome": "Filial B", "codigo": "SP01"})
        assert r.status_code == 409
        assert "SP01" in r.json()["detail"]

    def test_listar_filiais_vazio(self, client):
        r = client.get("/api/filiais/")
        assert r.status_code == 200
        assert r.json() == []

    def test_listar_filiais_com_dados(self, client):
        client.post("/api/filiais/", json={"nome": "Filial SP", "codigo": "SP01"})
        client.post("/api/filiais/", json={"nome": "Filial RJ", "codigo": "RJ01"})
        r = client.get("/api/filiais/")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_listar_filiais_apenas_ativas(self, client):
        r1 = client.post("/api/filiais/", json={"nome": "Ativa", "codigo": "AT01"})
        r2 = client.post("/api/filiais/", json={"nome": "Inativa", "codigo": "IN01"})
        fid_inativa = r2.json()["id"]
        # Desativa a segunda
        client.patch(f"/api/filiais/{fid_inativa}", json={"ativo": False})
        r = client.get("/api/filiais/?apenas_ativas=true")
        assert r.status_code == 200
        codigos = [f["codigo"] for f in r.json()]
        assert "AT01" in codigos
        assert "IN01" not in codigos

    def test_buscar_filial_existente(self, client):
        fid = client.post("/api/filiais/", json={"nome": "Filial SP", "codigo": "SP01"}).json()["id"]
        r = client.get(f"/api/filiais/{fid}")
        assert r.status_code == 200
        assert r.json()["codigo"] == "SP01"

    def test_buscar_filial_inexistente(self, client):
        r = client.get("/api/filiais/nao-existe-id")
        assert r.status_code == 404

    def test_atualizar_filial_nome(self, client):
        fid = client.post("/api/filiais/", json={"nome": "Antigo", "codigo": "XX01"}).json()["id"]
        r = client.patch(f"/api/filiais/{fid}", json={"nome": "Novo Nome"})
        assert r.status_code == 200
        assert r.json()["nome"] == "Novo Nome"
        assert r.json()["codigo"] == "XX01"   # código não muda

    def test_atualizar_filial_desativar(self, client):
        fid = client.post("/api/filiais/", json={"nome": "F", "codigo": "F001"}).json()["id"]
        r = client.patch(f"/api/filiais/{fid}", json={"ativo": False})
        assert r.status_code == 200
        assert r.json()["ativo"] is False

    def test_atualizar_filial_inexistente(self, client):
        r = client.patch("/api/filiais/nao-existe", json={"nome": "X"})
        assert r.status_code == 404

    def test_deletar_filial(self, client):
        fid = client.post("/api/filiais/", json={"nome": "F del", "codigo": "DL01"}).json()["id"]
        r = client.delete(f"/api/filiais/{fid}")
        assert r.status_code == 204
        assert client.get(f"/api/filiais/{fid}").status_code == 404

    def test_deletar_filial_inexistente(self, client):
        r = client.delete("/api/filiais/nao-existe")
        assert r.status_code == 404

    def test_criar_sessao_com_filial_valida(self, client):
        """Sessão pode ser criada vinculando uma filial existente."""
        fid = client.post("/api/filiais/", json={"nome": "Filial MG", "codigo": "MG01"}).json()["id"]
        r = client.post("/api/sessoes/", json={"nome": "Inventário MG", "filial_id": fid})
        assert r.status_code == 201

    def test_criar_sessao_com_filial_inexistente_retorna_404(self, client):
        r = client.post("/api/sessoes/", json={"nome": "X", "filial_id": "nao-existe"})
        assert r.status_code == 404

    def test_sessoes_da_filial(self, client):
        """Endpoint /filiais/{id}/sessoes deve listar sessões vinculadas."""
        fid = client.post("/api/filiais/", json={"nome": "Filial BA", "codigo": "BA01"}).json()["id"]
        client.post("/api/sessoes/", json={"nome": "Inv BA 1", "filial_id": fid})
        client.post("/api/sessoes/", json={"nome": "Inv BA 2", "filial_id": fid})
        client.post("/api/sessoes/", json={"nome": "Inv Sem Filial"})  # não vinculada
        r = client.get(f"/api/filiais/{fid}/sessoes")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert data["filial"]["codigo"] == "BA01"


# ─── D) Grupos de operadores ──────────────────────────────────────────────────

class TestGruposOperadores:
    def test_criar_grupo(self, client, sessao):
        sid = sessao["id"]
        tok = sessao["token_admin"]
        r = client.post(
            f"/api/sessoes/{sid}/grupos?token_admin={tok}",
            json={"nome": "Grupo A", "filtro": "ABC", "tipo_filtro": "prefixo"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["nome"] == "Grupo A"
        assert data["filtro"] == "ABC"
        assert data["tipo_filtro"] == "prefixo"
        assert data["token"]
        assert len(data["token"]) >= 16

    def test_listar_grupos_vazio(self, client, sessao):
        sid = sessao["id"]
        r = client.get(f"/api/sessoes/{sid}/grupos")
        assert r.status_code == 200
        assert r.json() == []

    def test_listar_grupos_com_dados(self, client, sessao):
        sid = sessao["id"]
        tok = sessao["token_admin"]
        client.post(
            f"/api/sessoes/{sid}/grupos?token_admin={tok}",
            json={"nome": "Grupo A", "filtro": "A", "tipo_filtro": "prefixo"},
        )
        client.post(
            f"/api/sessoes/{sid}/grupos?token_admin={tok}",
            json={"nome": "Grupo B", "filtro": "B", "tipo_filtro": "prefixo"},
        )
        r = client.get(f"/api/sessoes/{sid}/grupos")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_criar_grupo_sem_jwt_retorna_401(self, client, sessao):
        r = client.post(f"/api/sessoes/{sessao['id']}/grupos",
                        json={"nome": "G", "filtro": "*", "tipo_filtro": "todos"},
                        headers={"Authorization": "Bearer invalido"})
        assert r.status_code == 401

    def test_deletar_grupo(self, client, sessao):
        sid = sessao["id"]
        tok = sessao["token_admin"]
        gid = client.post(
            f"/api/sessoes/{sid}/grupos?token_admin={tok}",
            json={"nome": "Grupo Temp", "filtro": "*", "tipo_filtro": "todos"},
        ).json()["id"]
        r = client.delete(f"/api/sessoes/{sid}/grupos/{gid}?token_admin={tok}")
        assert r.status_code == 204
        grupos = client.get(f"/api/sessoes/{sid}/grupos").json()
        assert all(g["id"] != gid for g in grupos)

    def test_verificar_token_grupo(self, client, sessao):
        """Token do grupo deve ser reconhecido pelo endpoint verificar-grupo."""
        sid = sessao["id"]
        tok = sessao["token_admin"]
        grupo_tok = client.post(
            f"/api/sessoes/{sid}/grupos?token_admin={tok}",
            json={"nome": "Grupo X", "filtro": "X", "tipo_filtro": "prefixo"},
        ).json()["token"]
        r = client.get(f"/api/sessoes/{sid}/verificar-grupo?token={grupo_tok}")
        assert r.status_code == 200
        data = r.json()
        assert data["valido"] is True
        assert data["tipo"] == "grupo"
        assert data["grupo"]["nome"] == "Grupo X"

    def test_verificar_token_invalido(self, client, sessao):
        sid = sessao["id"]
        r = client.get(f"/api/sessoes/{sid}/verificar-grupo?token=TOKEN-INVALIDO")
        assert r.status_code == 200
        assert r.json()["valido"] is False

    def test_lista_operador_sem_token_retorna_401(self, client, sessao_com_itens):
        sid = sessao_com_itens["id"]
        r = client.get(f"/api/sessoes/{sid}/lista-operador")
        assert r.status_code == 401

    def test_lista_operador_com_token_acesso(self, client, sessao_com_itens):
        """Token de acesso geral permite ver todos os itens pendentes."""
        sid = sessao_com_itens["id"]
        # Busca ou gera token de acesso
        r_tok = client.get(f"/api/sessoes/{sid}/token-acesso")
        assert r_tok.status_code == 200
        tok = r_tok.json()["token"]
        r = client.get(f"/api/sessoes/{sid}/lista-operador?token={tok}")
        assert r.status_code == 200
        assert len(r.json()) == 3   # 3 itens da fixture sessao_com_itens

    def test_lista_operador_grupo_filtra_por_prefixo(self, client, sessao_com_itens):
        """Grupo com prefixo 'ABC-001' deve retornar apenas 1 item."""
        sid = sessao_com_itens["id"]
        tok_admin = sessao_com_itens["token_admin"]
        # Cria grupo filtrando apenas ABC-001
        grupo_tok = client.post(
            f"/api/sessoes/{sid}/grupos?token_admin={tok_admin}",
            json={"nome": "G1", "filtro": "ABC-001", "tipo_filtro": "prefixo"},
        ).json()["token"]
        r = client.get(f"/api/sessoes/{sid}/lista-operador?token={grupo_tok}")
        assert r.status_code == 200
        codigos = [i["codigo"] for i in r.json()]
        assert "ABC-001" in codigos
        assert "ABC-002" not in codigos
        assert "ABC-003" not in codigos

    def test_regenerar_token_grupo(self, client, sessao):
        """Regenerar token do grupo deve invalidar o token anterior."""
        sid = sessao["id"]
        tok = sessao["token_admin"]
        grupo = client.post(
            f"/api/sessoes/{sid}/grupos?token_admin={tok}",
            json={"nome": "G Regen", "filtro": "*", "tipo_filtro": "todos"},
        ).json()
        gid = grupo["id"]
        token_antigo = grupo["token"]
        r = client.post(f"/api/sessoes/{sid}/grupos/{gid}/regenerar-token?token_admin={tok}")
        assert r.status_code == 200
        token_novo = r.json()["token"]
        assert token_novo != token_antigo


# ─── E) Progresso de rodada ───────────────────────────────────────────────────

class TestProgressoRodada:
    """Verifica que calcular_progresso_rodada() e o endpoint /progresso retornam valores corretos."""

    def test_progresso_sessao_sem_itens(self, client, sessao):
        r = client.get(f"/api/sessoes/{sessao['id']}/progresso")
        assert r.status_code == 200
        data = r.json()
        assert data["tem_itens"] is False
        assert data["completa"] is False
        assert data["total_rodada"] == 0

    def test_progresso_inicial_todos_pendentes(self, client, sessao_com_itens):
        sid = sessao_com_itens["id"]
        r = client.get(f"/api/sessoes/{sid}/progresso")
        assert r.status_code == 200
        data = r.json()
        assert data["tem_itens"] is True
        assert data["rodada_atual"] == 1
        assert data["faltando_r1"] == 3
        assert data["completa"] is False

    def test_progresso_apos_contar_parcialmente(self, client, sessao_com_itens):
        sid = sessao_com_itens["id"]
        _registrar(client, sid, "ABC-001", 10)  # correto
        r = client.get(f"/api/sessoes/{sid}/progresso")
        data = r.json()
        assert data["faltando_r1"] == 2   # 2 ainda não contados
        assert data["completa"] is False

    def test_progresso_todos_corretos_completo(self, client, sessao_com_itens):
        """Contar todos certos → completa=True, faltando=0."""
        sid = sessao_com_itens["id"]
        _registrar(client, sid, "ABC-001", 10)
        _registrar(client, sid, "ABC-002", 5)
        _registrar(client, sid, "ABC-003", 20)
        r = client.get(f"/api/sessoes/{sid}/progresso")
        data = r.json()
        assert data["completa"] is True
        assert data["faltando"] == 0
        assert data["faltando_r1"] == 0
        assert data["faltando_r2"] == 0

    def test_progresso_com_divergencias_exige_r2(self, client, sessao_com_itens):
        """Itens divergentes em R1 geram faltando_r2 > 0 após contagem completa de R1."""
        sid = sessao_com_itens["id"]
        _registrar(client, sid, "ABC-001", 10)    # correto
        _registrar(client, sid, "ABC-002", 3)     # divergente (base=5)
        _registrar(client, sid, "ABC-003", 20)    # correto
        r = client.get(f"/api/sessoes/{sid}/progresso")
        data = r.json()
        assert data["faltando_r1"] == 0    # todos foram contados
        assert data["faltando_r2"] == 1    # 1 divergente pendente de recontagem
        assert data["completa"] is False
        assert data["proxima_rodada_necessaria"] is True

    def test_progresso_divergente_resolvido_por_confirmacao(self, client, sessao_com_itens):
        """Confirmar a mesma quantidade divergente 2× → para_ajuste → inventário completo."""
        sid = sessao_com_itens["id"]
        _registrar(client, sid, "ABC-001", 10)
        _registrar(client, sid, "ABC-002", 3)   # divergente
        _registrar(client, sid, "ABC-003", 20)
        # Recontar ABC-002 com a mesma quantidade → para_ajuste = True
        _registrar(client, sid, "ABC-002", 3)
        r = client.get(f"/api/sessoes/{sid}/progresso")
        data = r.json()
        assert data["faltando_r2"] == 0
        assert data["completa"] is True

    def test_progresso_divergente_resolvido_por_correcao(self, client, sessao_com_itens):
        """Corrigir um divergente para bater com a base → não diverge mais."""
        sid = sessao_com_itens["id"]
        _registrar(client, sid, "ABC-001", 10)
        _registrar(client, sid, "ABC-002", 3)   # divergente (base=5)
        _registrar(client, sid, "ABC-003", 20)
        # Recontar ABC-002 com quantidade certa (5) → CERTO, sem divergência
        _registrar(client, sid, "ABC-002", 5)
        r = client.get(f"/api/sessoes/{sid}/progresso")
        data = r.json()
        assert data["faltando_r2"] == 0
        assert data["completa"] is True

    def test_rodadas_endpoint_retorna_resumo(self, client, sessao_com_itens):
        """Endpoint /rodadas deve retornar a estrutura correta de resumo."""
        sid = sessao_com_itens["id"]
        _registrar(client, sid, "ABC-001", 10)
        _registrar(client, sid, "ABC-002", 3)  # divergente
        r = client.get(f"/api/sessoes/{sid}/rodadas")
        assert r.status_code == 200
        data = r.json()
        assert "rodadas" in data
        assert "itens_segunda" in data
        assert len(data["itens_segunda"]) == 1   # 1 divergente


# ─── F) Webhook URL validation via API ───────────────────────────────────────

class TestWebhookURLValidacaoAPI:
    """Testa a rejeição de URLs privadas no schema SessaoCreate via endpoint POST /sessoes/."""

    @pytest.mark.parametrize("url", [
        "http://192.168.1.1/callback",
        "http://10.0.0.1/api",
        "http://127.0.0.1/hook",
        "http://172.16.0.5/notify",
        "http://localhost/callback",
        "http://0.0.0.0/test",
        "http://169.254.169.254/meta-data/",
    ])
    def test_webhook_url_privada_retorna_422(self, client, url):
        """URLs privadas devem ser rejeitadas pelo schema Pydantic antes de chegar ao handler."""
        r = client.post("/api/sessoes/", json={"nome": "X", "webhook_url": url})
        assert r.status_code == 422, f"Esperado 422, got {r.status_code} para {url}"

    def test_webhook_url_publica_retorna_201(self, client):
        r = client.post("/api/sessoes/", json={
            "nome": "Sessão Webhook",
            "webhook_url": "https://hooks.example.com/inventory",
        })
        assert r.status_code == 201
        assert r.json()["webhook_url"] == "https://hooks.example.com/inventory"

    def test_webhook_url_none_retorna_201(self, client):
        r = client.post("/api/sessoes/", json={"nome": "Sem Webhook", "webhook_url": None})
        assert r.status_code == 201
        assert r.json()["webhook_url"] is None

    def test_webhook_ftp_retorna_422(self, client):
        """Schema deve rejeitar schemes não-HTTP."""
        r = client.post("/api/sessoes/", json={
            "nome": "FTP",
            "webhook_url": "ftp://example.com/hook",
        })
        assert r.status_code == 422


# ─── G) Concluir sessão sem itens ─────────────────────────────────────────────

class TestConcluirSessaoSemItens:
    def test_concluir_sem_itens_retorna_422(self, client, sessao):
        """Sessão sem nenhum item importado não pode ser concluída."""
        sid = sessao["id"]
        tok = sessao["token_admin"]
        r = client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
        assert r.status_code == 422
        assert "item" in r.json()["detail"].lower() or "planilha" in r.json()["detail"].lower()

    def test_concluir_com_itens_pendentes_retorna_422(self, client, sessao_com_itens):
        """Sessão com itens mas nenhum contado não pode ser concluída."""
        sid = sessao_com_itens["id"]
        tok = sessao_com_itens["token_admin"]
        r = client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
        assert r.status_code == 422
        detail = r.json()["detail"].lower()
        assert "não" in detail or "nao" in detail or "itens" in detail

    def test_concluir_com_divergentes_nao_resolvidos_retorna_422(self, client, sessao_com_itens):
        """Sessão com todos R1 contados mas divergentes pendentes de R2 não pode concluir."""
        sid = sessao_com_itens["id"]
        tok = sessao_com_itens["token_admin"]
        _registrar(client, sid, "ABC-001", 10)  # correto
        _registrar(client, sid, "ABC-002", 3)   # divergente, base=5
        _registrar(client, sid, "ABC-003", 20)  # correto
        r = client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
        assert r.status_code == 422

    def test_concluir_sem_jwt_retorna_401(self, client, sessao_com_itens):
        sid = sessao_com_itens["id"]
        r = client.patch(f"/api/sessoes/{sid}/concluir",
                         headers={"Authorization": ""})
        assert r.status_code == 401

class TestDeleteContagem:
    def test_deletar_contagem_libera_item(self, client, sessao_com_itens):
        """Após deletar contagem, o item volta a aparecer como pendente."""
        sid = sessao_com_itens["id"]
        # Registra contagem de ABC-001
        _registrar(client, sid, "ABC-001", 10)
        stats = client.get(f"/api/sessoes/{sid}/stats").json()
        assert stats["conferidos"] == 1

        # Deleta a contagem
        r = client.delete(f"/api/sessoes/{sid}/contagens/ABC-001")
        assert r.status_code == 204

        # Item voltou a ser pendente
        stats_depois = client.get(f"/api/sessoes/{sid}/stats").json()
        assert stats_depois["conferidos"] == 0
        assert stats_depois["pendentes"] == 3

    def test_deletar_contagem_inexistente_retorna_404(self, client, sessao_com_itens):
        sid = sessao_com_itens["id"]
        r = client.delete(f"/api/sessoes/{sid}/contagens/NAO-EXISTE")
        assert r.status_code == 404

    def test_deletar_contagem_sessao_concluida_retorna_409(self, client, sessao_com_itens):
        """Não é possível deletar contagem de sessão já concluída."""
        sid = sessao_com_itens["id"]
        tok = sessao_com_itens["token_admin"]
        _registrar(client, sid, "ABC-001", 10)
        _registrar(client, sid, "ABC-002", 5)
        _registrar(client, sid, "ABC-003", 20)
        client.patch(f"/api/sessoes/{sid}/concluir?token_admin={tok}")
        r = client.delete(f"/api/sessoes/{sid}/contagens/ABC-001")
        assert r.status_code == 409

    def test_deletar_contagem_permite_recontagem(self, client, sessao_com_itens):
        """Após deletar, é possível registrar nova contagem para o mesmo item."""
        sid = sessao_com_itens["id"]
        _registrar(client, sid, "ABC-001", 7)   # errado
        client.delete(f"/api/sessoes/{sid}/contagens/ABC-001")
        r = _registrar(client, sid, "ABC-001", 10)  # recontagem correta
        assert r.status_code == 201
        assert r.json()["divergencia"] is False


# ─── I) Pausar/retomar sessão ────────────────────────────────────────────────

class TestPausarRetomar:
    def test_pausar_sessao_ativa(self, client, sessao):
        sid = sessao["id"]
        tok = sessao["token_admin"]
        r = client.patch(f"/api/sessoes/{sid}/pausar?token_admin={tok}")
        assert r.status_code == 200
        assert r.json()["status"] == "pausada"

    def test_pausar_retorna_previsao_retomada(self, client, sessao):
        sid = sessao["id"]
        tok = sessao["token_admin"]
        r = client.patch(
            f"/api/sessoes/{sid}/pausar?token_admin={tok}&previsao_retomada=15:00",
        )
        assert r.status_code == 200
        assert r.json()["previsao_retomada"] == "15:00"

    def test_pausar_sessao_ja_pausada_retorna_409(self, client, sessao):
        sid = sessao["id"]
        tok = sessao["token_admin"]
        client.patch(f"/api/sessoes/{sid}/pausar?token_admin={tok}")
        r = client.patch(f"/api/sessoes/{sid}/pausar?token_admin={tok}")
        assert r.status_code == 409

    def test_retomar_sessao_pausada(self, client, sessao):
        sid = sessao["id"]
        tok = sessao["token_admin"]
        client.patch(f"/api/sessoes/{sid}/pausar?token_admin={tok}")
        r = client.patch(f"/api/sessoes/{sid}/retomar?token_admin={tok}")
        assert r.status_code == 200
        assert r.json()["status"] == "ativa"
        assert r.json()["novo_token"]

    def test_retomar_gera_novo_token(self, client, sessao):
        sid = sessao["id"]
        tok = sessao["token_admin"]
        tok_inicial = client.get(f"/api/sessoes/{sid}/token-acesso").json()["token"]
        client.patch(f"/api/sessoes/{sid}/pausar?token_admin={tok}")
        r = client.patch(f"/api/sessoes/{sid}/retomar?token_admin={tok}")
        assert r.status_code == 200
        tok_novo = r.json()["novo_token"]
        assert tok_novo != tok_inicial

    def test_retomar_sessao_nao_pausada_retorna_409(self, client, sessao):
        sid = sessao["id"]
        tok = sessao["token_admin"]
        r = client.patch(f"/api/sessoes/{sid}/retomar?token_admin={tok}")
        assert r.status_code == 409

    def test_contagem_bloqueada_durante_pausa(self, client, sessao_com_itens):
        """Sessão pausada não deve aceitar contagens."""
        sid = sessao_com_itens["id"]
        tok = sessao_com_itens["token_admin"]
        client.patch(f"/api/sessoes/{sid}/pausar?token_admin={tok}")
        r = _registrar(client, sid, "ABC-001", 10)
        assert r.status_code == 409

    def test_contagem_liberada_apos_retomada(self, client, sessao_com_itens):
        """Após retomar, sessão aceita novas contagens normalmente."""
        sid = sessao_com_itens["id"]
        tok = sessao_com_itens["token_admin"]
        client.patch(f"/api/sessoes/{sid}/pausar?token_admin={tok}")
        client.patch(f"/api/sessoes/{sid}/retomar?token_admin={tok}")
        r = _registrar(client, sid, "ABC-001", 10)
        assert r.status_code == 201


# ─── J) Metricas e valor estoque ─────────────────────────────────────────────

class TestMetricasValorEstoque:
    def test_metricas_sessao_vazia(self, client, sessao):
        r = client.get(f"/api/sessoes/{sessao['id']}/metricas")
        assert r.status_code == 200
        data = r.json()
        assert data["total_itens"] == 0
        assert data["taxa_divergencia_pct"] == 0.0

    def test_metricas_sessao_com_contagens(self, client, sessao_com_itens):
        sid = sessao_com_itens["id"]
        _registrar(client, sid, "ABC-001", 10, "Alice")
        _registrar(client, sid, "ABC-002", 3, "Bob")   # divergente
        r = client.get(f"/api/sessoes/{sid}/metricas")
        assert r.status_code == 200
        data = r.json()
        assert data["total_contagens_atuais"] == 2
        assert data["divergencias_absolutas"] == 1
        assert "por_operador" in data
        operadores = {op["operador"] for op in data["por_operador"]}
        assert "Alice" in operadores
        assert "Bob" in operadores

    def test_valor_estoque_sem_dados_financeiros(self, client, sessao_com_itens):
        """Itens sem valor_estoque → tem_dados_financeiros=False."""
        sid = sessao_com_itens["id"]
        r = client.get(f"/api/sessoes/{sid}/valor-estoque")
        assert r.status_code == 200
        data = r.json()
        assert data["tem_dados_financeiros"] is False
        assert data["valor_inicial"] == 0.0

    def test_valor_estoque_sessao_inexistente(self, client):
        r = client.get("/api/sessoes/nao-existe/valor-estoque")
        assert r.status_code == 404


# ─── K) Supervisor ────────────────────────────────────────────────────────────

class TestSupervisor:
    def test_get_token_supervisor(self, client, sessao):
        sid = sessao["id"]
        admin_tok = sessao["token_admin"]
        r = client.get(f"/api/sessoes/{sid}/token-supervisor?token_admin={admin_tok}")
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert len(data["token"]) >= 16

    def test_gerar_token_supervisor_invalida_anterior(self, client, sessao):
        sid = sessao["id"]
        admin_tok = sessao["token_admin"]
        tok1 = client.get(f"/api/sessoes/{sid}/token-supervisor?token_admin={admin_tok}").json()["token"]
        tok2 = client.post(f"/api/sessoes/{sid}/gerar-token-supervisor?token_admin={admin_tok}").json()["token"]
        assert tok1 != tok2

    def test_itens_supervisor_sem_token_retorna_403(self, client, sessao_com_itens):
        sid = sessao_com_itens["id"]
        r = client.get(f"/api/sessoes/{sid}/itens-supervisor?token=TOKEN-ERRADO")
        assert r.status_code == 403

    def test_itens_supervisor_antes_de_r1_completa_nao_ativo(self, client, sessao_com_itens):
        """Supervisor só fica ativo após todos itens da R1 serem contados."""
        sid = sessao_com_itens["id"]
        admin_tok = sessao_com_itens["token_admin"]
        tok_sup = client.get(f"/api/sessoes/{sid}/token-supervisor?token_admin={admin_tok}").json()["token"]
        r = client.get(f"/api/sessoes/{sid}/itens-supervisor?token={tok_sup}")
        assert r.status_code == 200
        assert r.json()["ativo"] is False

    def test_supervisor_ativo_apos_r1_com_divergencias(self, client, sessao_com_itens):
        """Após R1 completa com divergências, supervisor fica ativo."""
        sid = sessao_com_itens["id"]
        admin_tok = sessao_com_itens["token_admin"]
        tok_sup = client.get(f"/api/sessoes/{sid}/token-supervisor?token_admin={admin_tok}").json()["token"]
        _registrar(client, sid, "ABC-001", 10)   # correto
        _registrar(client, sid, "ABC-002", 3)    # divergente (base=5)
        _registrar(client, sid, "ABC-003", 20)   # correto
        r = client.get(f"/api/sessoes/{sid}/itens-supervisor?token={tok_sup}")
        assert r.status_code == 200
        data = r.json()
        assert data["ativo"] is True
        assert data["total_divergentes"] == 1
        codigos = [i["codigo"] for i in data["itens"]]
        assert "ABC-002" in codigos


# ─── L) Paginação de contagens ────────────────────────────────────────────────

class TestPaginacaoContagens:
    def test_listar_contagens_com_limit(self, client, sessao_com_itens):
        sid = sessao_com_itens["id"]
        _registrar(client, sid, "ABC-001", 10)
        _registrar(client, sid, "ABC-002", 5)
        _registrar(client, sid, "ABC-003", 20)
        r = client.get(f"/api/sessoes/{sid}/contagens?limit=2")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_listar_contagens_com_skip(self, client, sessao_com_itens):
        sid = sessao_com_itens["id"]
        _registrar(client, sid, "ABC-001", 10)
        _registrar(client, sid, "ABC-002", 5)
        _registrar(client, sid, "ABC-003", 20)
        r_todos = client.get(f"/api/sessoes/{sid}/contagens?limit=500").json()
        r_skip = client.get(f"/api/sessoes/{sid}/contagens?skip=1&limit=500").json()
        assert len(r_skip) == len(r_todos) - 1

    def test_listar_historico_com_limit_e_offset(self, client, sessao_com_itens):
        sid = sessao_com_itens["id"]
        _registrar(client, sid, "ABC-001", 8)
        _registrar(client, sid, "ABC-001", 10)  # gera 2 entradas no histórico
        r = client.get(f"/api/sessoes/{sid}/historico?limit=1")
        assert r.status_code == 200
        assert len(r.json()) == 1
        r2 = client.get(f"/api/sessoes/{sid}/historico?limit=1&offset=1")
        assert r2.status_code == 200
        assert len(r2.json()) == 1
        # As duas entradas devem ser diferentes
        assert r.json()[0]["quantidade_encontrada"] != r2.json()[0]["quantidade_encontrada"]
