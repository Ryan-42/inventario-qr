---
tags: [hub]
aliases: [Home, Index, INVIQ]
---

# INVIQ — Sistema de Inventário Físico por QR Code

> [!abstract] Sistema
> **Produto:** Inventário físico em tempo real com QR Code, IA e PWA
> **Stack:** FastAPI · PostgreSQL · Vanilla JS · Claude AI · Docker · Railway
> **Status:** ✅ Produção — 395 testes passando · PWA instalável · 9 vulnerabilidades corrigidas

---

## Mapa do Sistema

```mermaid
graph TD
    HUB["⬡ INVIQ"]:::hub

    ARQ["📐 Arquitetura"]:::arq
    DB["🗄️ Banco de Dados"]:::db
    BE["⚙️ Backend"]:::be
    FE["📱 Frontend Mobile"]:::fe
    IA["🤖 Agentes IA"]:::ia
    WS["⚡ Tempo Real"]:::ws
    SEG["🔒 Segurança"]:::seg
    NEG["📋 Regras de Negócio"]:::neg
    PWA["📲 PWA & Offline"]:::pwa
    DEP["🚀 Deploy & Infra"]:::dep
    RD["🗺️ Roadmap"]:::rd
    TST["🧪 Testes"]:::tst

    HUB --> ARQ
    HUB --> DB
    HUB --> BE
    HUB --> FE
    HUB --> IA
    HUB --> WS
    HUB --> SEG
    HUB --> NEG
    HUB --> PWA
    HUB --> DEP
    HUB --> RD
    HUB --> TST

    ARQ --> DB & BE & FE & IA & WS & DEP
    BE  --> DB & FE & IA & WS & SEG & NEG
    FE  --> WS & SEG & NEG & PWA
    IA  --> DB & NEG
    WS  --> SEG
    SEG --> NEG
    PWA --> DEP
    TST --> BE & IA & DEP

classDef hub      fill:#FFD700,stroke:#B8860B,color:#000,font-weight:bold
classDef arq      fill:#4B9FFF,stroke:#1565C0,color:#fff
classDef db       fill:#9B59B6,stroke:#6A1B9A,color:#fff
classDef be       fill:#E67E22,stroke:#BF360C,color:#fff
classDef fe       fill:#1ABC9C,stroke:#00695C,color:#fff
classDef ia       fill:#F1C40F,stroke:#F57F17,color:#000
classDef ws       fill:#FF6EC7,stroke:#AD1457,color:#fff
classDef seg      fill:#E74C3C,stroke:#B71C1C,color:#fff
classDef neg      fill:#2ECC71,stroke:#1B5E20,color:#fff
classDef pwa      fill:#00BCD4,stroke:#006064,color:#fff
classDef dep      fill:#78909C,stroke:#263238,color:#fff
classDef rd       fill:#AECB39,stroke:#558B2F,color:#000
classDef tst      fill:#FF9800,stroke:#E65100,color:#fff
```

---

## Visão Executiva

| Dimensão | Detalhe |
|----------|---------|
| **Propósito** | Substituir planilhas manuais por scanner mobile com IA integrada |
| **Operadores** | Acesso via QR Code + token rotativo por rodada |
| **Contagem** | Cega (operador não vê quantidade esperada — elimina viés) |
| **Rodadas** | R1 todos os itens → R2 divergentes → R3 persistentes → Para Ajuste |
| **Tempo real** | WebSocket atualiza progresso, alertas e status para todos os clientes |
| **IA** | 10 agentes Claude para validação, análise, predição e suporte |
| **Offline** | PWA com Service Worker — conta sem internet, sincroniza ao voltar |

---

## Navegação por Área

| Área | Nota | O que encontrar |
|------|------|-----------------|
| 📐 Estrutura | [[01 - Arquitetura]] | Stack, decisões técnicas, componentes |
| 🗄️ Dados | [[02 - Banco de Dados]] | Modelos, relações, migrations |
| ⚙️ API | [[03 - Backend]] | Endpoints, serviços, autenticação |
| 📱 Scanner | [[04 - Frontend Mobile]] | Estados, câmera, lista, UX |
| 🤖 IA | [[05 - Agentes IA]] | 10 agentes, hierarquia, provider |
| ⚡ Live | [[06 - Tempo Real]] | WebSocket, eventos, broadcast |
| 🔒 Auth | [[07 - Segurança]] | Tokens, CSP, rate limit, auditoria |
| 📋 Processo | [[08 - Regras de Negócio]] | Rodadas, divergências, grupos |
| 📲 Offline | [[09 - PWA & Offline]] | Service Worker, cache, Background Sync |
| 🚀 Infra | [[10 - Deploy & Infra]] | Docker, Railway, variáveis |
| 🗺️ Futuro | [[11 - Roadmap]] | Próximas features, fases |
| 🧪 QA | [[12 - Testes]] | 395 testes, cobertura, estrutura |
