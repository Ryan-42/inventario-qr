---
tags: [backend]
aliases: [API, FastAPI, Endpoints, Routes, Services]
---

# Backend — INVIQ

> [!info] FastAPI
> **Framework:** FastAPI 0.115 · **Python:** 3.12
> **Processo:** Uvicorn (ASGI) · **Rate Limit:** SlowAPI
> **Rotas:** 17 módulos · Arquitetura: Routes → Services → Repositories → Models

---

## Mapa de Endpoints

```mermaid
graph LR
    subgraph Sessoes["/api/sessoes"]
        S1["POST / — criar"]
        S2["GET / — listar"]
        S3["GET /{id} — detalhe"]
        S4["PATCH /{id}/status"]
        S5["GET /{id}/progresso"]
    end

    subgraph Itens["/api/sessoes/{id}"]
        I1["POST /upload — planilha"]
        I2["GET /itens — admin"]
        I3["GET /itens-operador — cego"]
        I4["GET /buscar/{codigo}"]
        I5["POST /validar-planilha"]
    end

    subgraph Contagens["/api/sessoes/{id}/contagens"]
        C1["POST / — registrar"]
        C2["DELETE /{codigo}"]
        C3["GET /historico"]
    end

    subgraph Grupos["/api/sessoes/{id}/grupos"]
        G1["POST / — criar grupo"]
        G2["GET / — listar grupos"]
        G3["POST /{gid}/token — gerar token"]
        G4["POST /verificar-token"]
    end

    subgraph Agentes["/api/agentes/{id}"]
        A1["GET /analise"]
        A2["GET /relatorio"]
        A3["POST /chat"]
        A4["GET /alertas"]
        A5["GET /predicao"]
    end

    subgraph Exports["/api/sessoes/{id}/exportar"]
        E1["GET /xlsx"]
        E2["GET /pdf"]
        E3["GET /divergencias"]
    end
```

---

## Camadas da Aplicação

```mermaid
flowchart TD
    REQ["HTTP Request"] --> RT["Routes\n(FastAPI Router)"]
    RT --> SVC["Services\n(lógica de negócio)"]
    SVC --> REPO["Repositories\n(acesso a dados)"]
    REPO --> DB["PostgreSQL"]
    RT --> AGENT["Agentes IA\n(.agents/)"]
    AGENT --> DB
    RT --> WS["WebSocket\nManager"]
    WS --> CLIENTS["Clientes conectados"]
```

---

## Repositórios

| Arquivo | Responsabilidade |
|---------|-----------------|
| `sessao_repo.py` | CRUD de sessões, busca, status |
| `item_repo.py` | Import bulk, busca, lista operador (cega) |
| `contagem_repo.py` | Upsert contagem, histórico, deletar |
| `grupo_repo.py` | Grupos de operadores, `buscar_grupo_por_token()` |
| `auditoria_repo.py` | Log append-only de ações |

---

## Middleware e Segurança

```python
# main.py — camadas em ordem de execução
app
  → GZipMiddleware          # compressão automática
  → SecurityHeadersMiddleware  # CSP, HSTS, X-Frame
  → CORSMiddleware          # origens permitidas
  → SlowAPI (rate limiter)  # 60/min operadores, 10/h uploads
```

---

## Padrões de Código

### Endpoint padrão (com limiter + auth)
```python
@router.post("/{sessao_id}/contagens", response_model=ContagemResponse)
@limiter.limit("120/minute")
async def registrar_contagem(
    request: Request,
    sessao_id: str,
    payload: ContagemCreate,
    db: Session = Depends(get_db),
):
    sessao = sessao_repo.buscar_sessao(db, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if sessao.status != StatusSessao.ativa:
        raise HTTPException(status_code=409, detail="Sessão não está ativa")
    # ...
```

### Filtro de grupo (contagem cega)
```python
# /itens-operador respeita o grupo do token
if token:
    grupo = grupo_repo.buscar_grupo_por_token(db, sessao_id, token)
    if grupo:
        itens = _filtrar_por_grupo(itens, grupo)
```

---

## Conexões

- [[01 - Arquitetura]] — estrutura geral e decisões
- [[02 - Banco de Dados]] — repositories e models
- [[04 - Frontend Mobile]] — consome esta API
- [[05 - Agentes IA]] — chamados pelos routes
- [[06 - Tempo Real]] — WebSocket emitido pelos routes
- [[07 - Segurança]] — middleware, tokens, CSP
- [[08 - Regras de Negócio]] — implementadas nos services
- [[12 - Testes]] — testes de integração por endpoint
- [[00 - INVIQ]] — visão geral
