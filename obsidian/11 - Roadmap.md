---
tags: [roadmap]
aliases: [Próximas Features, Backlog, Fases, Planejamento]
---

# Roadmap — INVIQ

> [!success] Entregues
> ✅ Scanner mobile PWA · ✅ Contagem cega · ✅ 3 rodadas · ✅ 10 agentes IA
> ✅ WebSocket real-time · ✅ Grupos de operadores · ✅ Export PDF + Excel
> ✅ Service Worker + offline · ✅ 395 testes · ✅ 9 vulnerabilidades corrigidas

---

## Estado das Fases

```mermaid
timeline
    title INVIQ — Linha do Tempo
    section Fase 1 — MVP
        Mai 2026 : Scanner mobile
                 : Upload planilha
                 : Registro de contagem
                 : WebSocket básico
    section Fase 2 — Inteligência
        Jun 2026 : 10 Agentes IA (Claude)
                 : Grupos de operadores
                 : Contagem cega
                 : Auditoria
                 : 395 testes
    section Fase 3 — PWA
        Jun 2026 : Service Worker
                 : Offline queue
                 : Background Sync
                 : Ícones + manifest
                 : 9 vulns corrigidas
    section Fase 4 — Em Planejamento
        Jul 2026 : Templates de sessão
                 : Histórico comparativo
                 : Notificações push
                 : Sugestão de rota
```

---

## Próximas Features por Prioridade

### Alta Prioridade (Impacto Imediato)

| Feature | Impacto | Esforço | Depende de |
|---------|---------|---------|-----------|
| **Templates de sessão** | Admin reutiliza planilha sem re-upload | Médio | [[02 - Banco de Dados]] |
| **Histórico comparativo** | Diff SKU a SKU entre inventários | Médio | [[02 - Banco de Dados]] |
| **Audit trail imutável** | Log com hash — requisito fiscal | Médio | [[07 - Segurança]] |

### Média Prioridade (Experiência)

| Feature | Impacto | Esforço | Depende de |
|---------|---------|---------|-----------|
| **Sugestão de rota** | Ordena lista por caminho físico no depósito | Médio | [[04 - Frontend Mobile]] |
| **Notificações push** | Avisar operador sem aba aberta | Médio | [[09 - PWA & Offline]] |
| **Câmera DataMatrix/Code128** | Leitura de código de barras linear | Alto | [[04 - Frontend Mobile]] |

### Qualidade Técnica

| Feature | Impacto | Esforço |
|---------|---------|---------|
| **Testes E2E (Playwright)** | Fluxo scan→conta→export testado | Alto |
| **Testes frontend** | 1.650 linhas JS sem cobertura | Alto |
| **IndexedDB para offline** | Substitui localStorage (limite 5MB) | Médio |

### Escalabilidade

| Feature | Impacto | Esforço |
|---------|---------|---------|
| **Webhook de conclusão** | Notifica ERP automaticamente | Baixo |
| **API Key para integração** | Parceiros sem acesso humano | Baixo |
| **Multi-tenancy** | Isolar por empresa (SaaS) | Alto |

---

## Recomendação de Próxima Sprint

```mermaid
graph LR
    T1["📁 Templates de sessão\n(clona sessão existente)"]
    T2["📊 Histórico comparativo\n(diff entre inventários)"]
    T3["🔒 Audit trail imutável\n(hash + append-only)"]
    W1["🔗 Webhook conclusão\n(notifica ERP)"]
    W2["🗝️ API Key\n(integração B2B)"]

    T1 --> T2 --> T3
    T3 --> W1 --> W2

    classDef sprint fill:#2ECC71,stroke:#1B5E20,color:#fff
    classDef next fill:#4B9FFF,stroke:#1565C0,color:#fff
    class T1,T2,T3 sprint
    class W1,W2 next
```

**Sprint recomendada:** Templates + Histórico + Audit Trail
→ 3 features complementares, esforço médio, resolvem dor real do segundo inventário em diante

---

## Conexões

- [[00 - INVIQ]] — visão geral do sistema
- [[05 - Agentes IA]] — novos agentes planejados (RouteAgent, TemplateAgent)
- [[09 - PWA & Offline]] — IndexedDB, notificações push
- [[12 - Testes]] — E2E e testes frontend pendentes
- [[02 - Banco de Dados]] — novas tabelas para templates e histórico
