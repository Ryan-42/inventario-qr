---
tags: [negocio]
aliases: [Regras, Business Rules, Contagem, Rodadas, Divergências]
---

# Regras de Negócio — INVIQ

> [!abstract] O Processo de Inventário
> O INVIQ opera em **até 3 rodadas** por sessão.
> A contagem é **cega** — operadores não veem quantidades esperadas.
> Divergências persistentes viram **Para Ajuste** (consenso de erro de estoque).

---

## Fluxo de Rodadas

```mermaid
flowchart TD
    START["Sessão Criada\n+ planilha importada"] --> R1

    R1["Rodada 1\nTodos os itens"] --> R1OK{{"Todos contados?"}}
    R1OK -- não --> R1
    R1OK -- sim --> DIV1{{"Divergências?"}}
    DIV1 -- não --> CONCLUIDO
    DIV1 -- sim --> R2

    R2["Rodada 2\nApenas divergentes"] --> R2CHK{{"Item recontado\ncom mesmo valor?"}}
    R2CHK -- sim --> AJUSTE["Para Ajuste\n(consenso de divergência)"]
    R2CHK -- não --> R2DIV{{"Ainda divergente?"}}
    R2DIV -- não --> R2
    R2DIV -- sim --> R3

    R3["Rodada 3\nÚltimos divergentes"] --> R3CHK{{"Mesmo valor?"}}
    R3CHK -- sim --> AJUSTE
    R3CHK -- não --> AJUSTE

    AJUSTE --> CONCLUIDO["Sessão Concluída\n+ PDF + Excel gerados"]

    classDef rodada fill:#4B9FFF,stroke:#1565C0,color:#fff
    classDef ok fill:#2ECC71,stroke:#1B5E20,color:#fff
    classDef ajuste fill:#F1C40F,stroke:#F57F17,color:#000
    classDef fim fill:#9B59B6,stroke:#6A1B9A,color:#fff
    class R1,R2,R3 rodada
    class R1OK,DIV1,R2DIV ok
    class AJUSTE ajuste
    class CONCLUIDO fim
```

---

## Regras de Sessão

| Código | Regra |
|--------|-------|
| **RN-01** | Sessão aceita contagens apenas com status `ativa` |
| **RN-02** | Código único automático: `INV-AAAA-NNNN` |
| **RN-03** | Sessão concluída é imutável — não pode ser reaberta |
| **RN-04** | Reimport de planilha preserva contagens existentes |
| **RN-05** | Conclusão gera PDF executivo + Excel automaticamente |

---

## Regras de Contagem (Cega)

| Código | Regra |
|--------|-------|
| **RN-11** | Máximo 3 rodadas por sessão |
| **RN-12** | Item avança de rodada só se: foi divergente **e** nova qty ≠ qty anterior |
| **RN-13** | Mesmo valor na recontagem → Para Ajuste imediato (consenso) |
| **RN-14** | Após rodada 3, divergência persistente → Para Ajuste automático |
| **RN-15** | Operador não vê quantidade esperada (contagem cega — elimina viés) |

---

## Grupos de Operadores

```mermaid
graph LR
    ADMIN["Admin"] -->|cria grupo| G1["Grupo A\nPrefixo: MOV,EST\nCor: azul"]
    ADMIN -->|cria grupo| G2["Grupo B\nTipo: lista\nCor: verde"]
    ADMIN -->|cria grupo| G3["Grupo C\ntodos os itens"]

    G1 -->|token único| OP1["Operadores A\nveem só MOV*, EST*"]
    G2 -->|token único| OP2["Operadores B\nveem lista específica"]
    G3 -->|token único| OP3["Operadores C\nveem tudo"]
```

| Campo | Valores | Efeito |
|-------|---------|--------|
| `tipo_filtro` | `prefixo` | filtra por início do código SKU |
| `tipo_filtro` | `lista` | filtra por lista exata de códigos |
| `tipo_filtro` | `todos` | sem filtro |
| `filtro` | `*` | sem filtro (independente do tipo) |
| `filtro` | `MOV,EST` | CSV de prefixos ou códigos |

---

## Divergências Críticas

> [!warning] Requer Supervisor
> Item com divergência **> 100%** do estoque esperado **ou** valor financeiro **≥ R$ 5.000**
> → AlertaAgent notifica o painel do supervisor imediatamente
> → Supervisor deve testemunhar a recontagem presencialmente

---

## Glossário

| Termo | Definição |
|-------|-----------|
| **Sessão** | Evento único de inventário |
| **Item Base** | Produto importado da planilha (código, produto, qtd esperada, valor) |
| **Contagem** | Registro do operador para um item em uma sessão (upsert) |
| **Rodada** | Ciclo: R1=todos, R2/R3=divergentes |
| **Divergência** | `qty_encontrada ≠ qty_base` |
| **Para Ajuste** | Divergência confirmada — ajuste direto no ERP |
| **Contagem Cega** | Operador conta sem saber o esperado |

---

## Conexões

- [[02 - Banco de Dados]] — schema implementa estas regras (upsert, UNIQUE)
- [[03 - Backend]] — services aplicam as regras no CRUD
- [[04 - Frontend Mobile]] — scanner respeita contagem cega e grupos
- [[05 - Agentes IA]] — AlertaAgent e AjusteAgent implementam regras avançadas
- [[07 - Segurança]] — token de rodada controla progressão
- [[00 - INVIQ]] — visão geral
