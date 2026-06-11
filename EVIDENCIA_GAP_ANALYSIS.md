# EVIDENCIA_GAP_ANALYSIS.md
# Auditoria de Capacidades — Preparação para Inventário Real
_Gerado em 2026-06-11. Baseline: 164 testes passando._

---

## Legenda

| Status | Significado |
|--------|-------------|
| **JÁ EXISTE** | Implementado, testado, exposto na API |
| **EXISTE PARCIAL** | Lógica presente, mas incompleta ou não coberta para o cenário de evidência |
| **NÃO EXISTE** | Capacidade ausente — requer implementação |

---

## P0 — INTEGRIDADE DE DADOS

### P0.1 — Persistência imediata (nenhuma contagem se perde)
| Status | Arquivo/Linha |
|--------|--------------|
| **JÁ EXISTE** | `backend/app/repositories/item_repo.py:189` — `db.commit()` imediato a cada `registrar_contagem`. Banco é a única fonte de verdade; WebSocket é notificação, nunca estado. |

### P0.2 — Recuperação de sessão (retomar com estado intacto)
| Status | Arquivo/Linha |
|--------|--------------|
| **JÁ EXISTE** | `GET /sessoes/{id}/progresso` → progresso completo (faltando_r1/r2, rodada atual). `GET /sessoes/{id}/contagens` → todos os itens contados. `GET /sessoes/{id}/lista-operador?token=X` → itens pendentes filtrados por grupo. A API fornece todos os dados necessários para o frontend reconstituir o estado — sem dado em memória volátil. |

### P0.3 — Concorrência multi-operador: escrita segura
| Status | Arquivo/Linha |
|--------|--------------|
| **EXISTE PARCIAL** | `item_repo.py:80-86` — `buscar_contagem` sem lock. Para **INSERT** novo (contagem inexistente), a `UniqueConstraint("uq_contagens_sessao_codigo")` + `except IntegrityError → 409` já garante segurança. Para **UPDATE** de contagem existente, dois workers simultâneos podem ler o mesmo `existente`, calcular `nova_rodada` com base nos mesmos dados e o último commit vence sem erro — race condition silencioso em PostgreSQL. **Ação: adicionar `with_for_update()` na busca pré-UPDATE.** |

### P0.4 — Robustez de leitura (código inválido não derruba sessão)
| Status | Arquivo/Linha |
|--------|--------------|
| **JÁ EXISTE** | `routes/contagens.py:53-54` → 404 se código não está na base. `item_repo.py:99-100` → `LookupError` se item removido durante race condition → 409 na rota. Código malformado é rejeitado pelo schema validator (`Field(max_length=100)` + `strip()`). |

---

## P1 — RASTREABILIDADE E AUDITORIA

### P1.5 — QUEM / QUANDO / O QUÊ / RODADA por contagem
| Status | Arquivo/Linha |
|--------|--------------|
| **JÁ EXISTE** | `models/contagem.py:23-26` — `operador`, `timestamp(timezone=True)`, `rodada` em `Contagem`. `models/contagem.py:41-48` — `HistoricoContagem` replica todos esses campos em registro append-only. `GET /sessoes/{id}/historico` expõe paginado. |

### P1.6 — Audit trail de correções (valor anterior → novo)
| Status | Arquivo/Linha |
|--------|--------------|
| **JÁ EXISTE** (para fins de evidência) | `HistoricoContagem` registra **cada tentativa individual** do operador com `quantidade_encontrada`, `rodada`, `operador`, `timestamp`. Para reconstruir "o que mudou": comparar entradas consecutivas pelo mesmo `codigo` ordenadas por `timestamp`. Não há campos `qtd_anterior`/`qtd_nova` explícitos, mas a sequência histórica é equivalente para auditoria. |

### P1.7 — Log de eventos de sessão (início, pausa, retomada, conclusão)
| Status | Arquivo/Linha |
|--------|--------------|
| **EXISTE PARCIAL** | Campos existentes em `Sessao`: `data_inicio`, `data_fim`, `pausada_em`, `status`. Permitem derivar os eventos, mas não estão expostos como log de eventos ordenados e consultáveis. Sem implementação de tabela dedicada — os dados existentes são suficientes para os KPIs pedidos (tempo total, duração). **Não requer nova tabela; o endpoint de métricas (P2.8) consolida esses dados.** |

---

## P2 — MÉTRICAS AUTOMÁTICAS

### P2.8 — Endpoint de métricas derivadas
| Status | Arquivo/Linha |
|--------|--------------|
| **NÃO EXISTE** | Não há `GET /sessoes/{id}/metricas`. Os dados brutos existem (histórico, contagens, sessao.data_inicio), mas não há endpoint que calcule e sirva: tempo total, itens/min geral e por operador, taxa de divergência, taxa de retrabalho, % rastreabilidade. **Requer implementação.** |

### P2.9a — Export brutos por item (código, operador, timestamp, rodada, status)
| Status | Arquivo/Linha |
|--------|--------------|
| **JÁ EXISTE** | `relatorio_final_service.py:492-496` — aba "Todos os Itens" inclui: Código, Produto, Base, Contado, Diferença, Status, Operador, Rodada, Observação, Local, Data/Hora. `relatorio_final_service.py:528-578` — aba "Histórico Detalhado" com cada tentativa. |

### P2.9b — Aba de métricas agregadas no Excel
| Status | Arquivo/Linha |
|--------|--------------|
| **NÃO EXISTE** | O Excel final não tem aba de KPIs de produtividade (itens/min, taxa retrabalho, % rastreabilidade, breakdown por operador). **Requer implementação no `gerar_relatorio_final_excel`.** |

---

## RESUMO DE IMPLEMENTAÇÃO NECESSÁRIA

| Prioridade | Item | Arquivo(s) a modificar | Complexidade |
|------------|------|------------------------|-------------|
| **P0.3** | `with_for_update()` no UPDATE de contagem | `item_repo.py` | Baixa (1 linha) |
| **P2.8** | Endpoint `GET /metricas` | `routes/sessoes.py` + `repositories/sessao_repo.py` | Média |
| **P2.9b** | Aba métricas no Excel final | `services/relatorio_final_service.py` + `routes/exports.py` | Média |

---

## O QUE **NÃO** SERÁ IMPLEMENTADO (JÁ EXISTE OU FORA DO ESCOPO)

- Timestamp por contagem → JÁ EXISTE
- Histórico append-only (auditoria) → JÁ EXISTE  
- Rastreamento operador/grupo → JÁ EXISTE
- Exportação dados brutos (Excel/PDF) → JÁ EXISTE
- Cálculo de divergência + índices → JÁ EXISTE
- Recuperação de sessão via múltiplos endpoints → JÁ EXISTE
- Robustez de código inválido → JÁ EXISTE
- Tabela de eventos de sessão separada → DERIVÁVEL dos campos existentes; P2.8 consolida
