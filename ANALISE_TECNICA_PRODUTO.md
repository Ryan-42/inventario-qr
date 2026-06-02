
# INVIQ — Análise Técnica e Roadmap de Produto
> Diagnóstico completo para produção + estratégia de venda como SaaS
> Data: 2026-06-01 | Versão analisada: v3.1

---

## PARTE 1 — BUGS E PROBLEMAS TÉCNICOS

### 🔴 CRÍTICOS (bloqueiam produção)

| # | Problema | Arquivo | Impacto |
|---|----------|---------|---------|
| C1 | **Força bruta em `/verificar-token`** — token de 4 bytes = 65.536 combinações, sem rate limit | `routes/sessoes.py:126` | Acesso não autorizado |
| C2 | **Race condition no código de sessão** — dois creates simultâneos geram mesmo `INV-XXXX` | `repos/sessao_repo.py:13` | Dados corrompidos |
| C3 | **Nenhuma notificação de pausa/cancelamento ao operador** — WS não dispara evento de sessão pausada | `routes/grupos.py:336` | Contagens perdidas sem aviso |
| C4 | **Sessão pausada aceita novas contagens** — comparação `status.value != "ativa"` inconsistente com `!= StatusSessao.ativa` | `routes/contagens.py:39` | Contagens inválidas registradas |
| C5 | **`criar_itens_bulk` apaga contagens ao reimportar planilha** — deleta itens, histórico de contagens fica órfão | `repos/item_repo.py:15` | Perda de dados de contagem |

### 🟠 ALTOS (causam comportamento incorreto)

| # | Problema | Arquivo | Impacto |
|---|----------|---------|---------|
| A1 | **Tokens sem expiração** — token vazado é válido para sempre | `models/sessao.py:32` | Segurança permanente comprometida |
| A2 | **Token admin sem endpoint de regeneração** — se vazar, não há como mudar | Sem endpoint | Comprometimento permanente |
| A3 | **Progresso quebrado para sessão sem itens** — `total_rodada = 0` causa divisão por zero no frontend | `repos/item_repo.py:149` | Frontend crasha |
| A4 | **Validação de grupo tem fallback `True`** — `tipo_filtro` inválido libera todos os itens | `models/grupo_operador.py:36` | Operador vê itens de outros grupos |
| A5 | **Falta paginação** — sessão com 10k contagens carrega tudo de uma vez | `routes/contagens.py:18` | Timeout/crash do servidor |
| A6 | **`para_ajuste` pode ser sobrescrito** — lógica permite reabrir item já marcado para ajuste | `repos/item_repo.py:84` | Status de ajuste perdido |
| A7 | **`valor_estoque` aceita valores negativos** — sem constraint de validação | `models/item_base.py:17` | Relatórios financeiros errados |
| A8 | **Reimport de planilha sem confirmação** — apaga todos os itens sem aviso ao usuário | `repos/item_repo.py:15` | Perda acidental de dados |

### 🟡 MÉDIOS (degradam qualidade)

| # | Problema | Arquivo | Impacto |
|---|----------|---------|---------|
| M1 | **Memory leak de WebSocket** — conexões mortas acumulam sem limpeza automática | `ws/manager.py:36` | Servidor lento com o tempo |
| M2 | **Arredondamento financeiro inconsistente** — `round(...,2)` vs `round(...,4)` | `repos/sessao_repo.py:154` | Valores financeiros que não batem |
| M3 | **`local_fisico` sem normalização** — "Setor A" vs "setor a" vs "SETOR A" são diferentes | `models/item_base.py:16` | Supervisor vê locais duplicados |
| M4 | **IA silencia falhas** — `_tentar_analise_ia()` captura tudo sem log adequado | `routes/exports.py:17` | Relatório sem IA sem aviso |
| M5 | **Upload sem tamanho mínimo validado** — planilha vazia importa zero itens sem feedback | `routes/itens.py:40` | Usuário não sabe que deu errado |
| M6 | **Broadcasts WS serializam erros silenciosamente** — `default=str` converte Decimal em texto | `ws/manager.py:42` | Frontend recebe dados malformados |
| M7 | **Histórico órfão ao deletar contagem** — FK não cascata em `historico_contagens` | `routes/contagens.py:135` | Auditoria inconsistente |

---

## PARTE 2 — INCOERÊNCIAS E REDUNDÂNCIAS DE DESIGN

### Redundâncias
- **`ItemComStatus` vs `BuscaItemResponse`** — dois schemas quase idênticos (`schemas/__init__.py:60` e `:129`)
- **Lógica de rodada duplicada** — `item_repo.py` E `contagens.py` calculam transição de rodada independentemente
- **`SessaoCreate.senha`** — campo declarado mas nunca usado em lugar nenhum (código morto)
- **Verificação de token** — 3 implementações diferentes: `/verificar-token`, `/verificar-grupo`, `verificar-admin`; deveriam ser uma só função reutilizável

### Incoerências
- **Nomenclatura mista** — `listar_sessoes` (pt), `status` (en), `timestamp` (en), `sessao_id` (pt) sem padrão
- **Enum comparação inconsistente** — `status.value != "ativa"` em uns, `!= StatusSessao.ativa` em outros
- **Lógica de negócio em routes** — pausar/retomar sessão (`grupos.py:336`) deveria estar em `sessao_service.py`
- **Grupos criados com `cors="*"`** mas validação de token usa endpoint separado de sessão
- **`token_admin` de 16 chars (128 bits)** vs `token_acesso` de 8 chars (32 bits) — inconsistência de entropia

---

## PARTE 3 — ANÁLISE DE PRODUTO E VENDA COMO SAAS

### Gap Analysis — o que falta para vender

```
Estado atual:                   Estado SaaS:
─────────────────────           ─────────────────────────────
Single-tenant                   Multi-tenant (empresa_id em tudo)
Token mágico                    JWT + OAuth2 + roles
Sem billing                     Planos: Starter / Pro / Enterprise
Sem onboarding                  Wizard de primeira sessão
SQLite local                    PostgreSQL em cloud (Supabase/RDS)
Deploy manual                   Docker + CI/CD + auto-scale
Sem domínio próprio             app.inviq.com.br por cliente
```

### Posicionamento competitivo

**Competidores diretos no Brasil:**
- **Inventário por código de barras** (apps genéricos mobile) — sem análise IA, sem multi-operador
- **ERP interno** (TOTVS, SAP) — complexo, caro, sem experiência mobile
- **Planilha Excel manual** — ainda a realidade de 80% das médias empresas

**Diferenciais únicos do INVIQ hoje:**
1. QR Code gerado na hora (sem hardware adicional)
2. Multi-rodada com reconciliação automática (R1→R2→R3)
3. Supervisor em campo com localização em tempo real
4. Chat IA sobre o inventário (único no mercado)
5. Grupos de operadores por setor/prefixo
6. Modo offline com sync posterior

**O que nenhum concorrente tem:**
- Detecção de padrão de fraude por operador (quando implementado)
- Predição de divergências por histórico (quando implementado)
- Classificação automática de causa de divergência via IA

---

## PARTE 4 — ROADMAP COMPLETO PARA VERSÃO COMERCIAL

### 🔧 SPRINT 5 — Correções Críticas (estimado: 2 semanas)

**Segurança:**
- [ ] Rate limit em `/verificar-token`, `/verificar-grupo` (máximo 10 tentativas/min por IP)
- [ ] Aumentar entropia dos tokens: `token_acesso` de 4→8 bytes; `token_supervisor` de 4→6 bytes
- [ ] Endpoint `POST /sessoes/{id}/regenerar-token-admin`
- [ ] Validar `tipo_filtro` na criação de grupo (rejeitar valores inválidos)
- [ ] Bloquear contagem em sessão pausada (fix na comparação de enum)

**Estabilidade:**
- [ ] `FOR UPDATE` ou `INSERT IGNORE` na geração de código de sessão
- [ ] Evento WebSocket `sessao_pausada` / `sessao_cancelada` broadcast para todos os operadores
- [ ] Guard de `total_rodada == 0` no cálculo de progresso
- [ ] Paginação em `/contagens` (`?page=1&per_page=100`)
- [ ] Normalizar `local_fisico` (uppercase + trim) no import

**UX:**
- [ ] Mensagem clara "Item de outro setor" no backend (HTTP 403 + detalhe)
- [ ] Feedback de planilha vazia / mal formatada
- [ ] Confirmação antes de reimportar planilha (janela com "Você tem X contagens — reimportar apagará os itens")

---

### 🏗️ SPRINT 6 — Base SaaS (estimado: 4 semanas)

**Multi-tenancy:**
- [ ] Modelo `Empresa` com campos: `id`, `nome`, `plano`, `ativo`, `criado_em`
- [ ] Adicionar `empresa_id FK` em `Sessao`, `ItemBase`, `GrupoOperador`
- [ ] Middleware que injeta `empresa_id` em todas as queries
- [ ] Isolamento total: empresa A não pode ver dados da empresa B

**Autenticação:**
- [ ] Modelo `Usuario`: `id`, `email`, `senha_hash`, `empresa_id`, `role`
- [ ] Roles: `owner` / `admin` / `supervisor` / `operador`
- [ ] JWT de curta duração (15min) + refresh token (7 dias)
- [ ] Login por email+senha no dashboard admin
- [ ] Operadores continuam usando token QR (sem login mobile — UX simplificado)

**Infraestrutura:**
- [ ] Migrar de SQLite para PostgreSQL em todos os ambientes
- [ ] Alembic para migrações versionadas
- [ ] Docker Compose com PostgreSQL + Redis + Backend

---

### 💰 SPRINT 7 — Monetização (estimado: 3 semanas)

**Onboarding:**
- [ ] Tela de cadastro de empresa (nome + plano + e-mail do gestor)
- [ ] Wizard de primeira sessão: "Importe sua planilha → Crie grupos → Distribua tokens"
- [ ] Email de boas-vindas com tutorial

**Planos:**
```
Starter (Grátis)          Pro (R$149/mês)           Enterprise (R$599/mês)
───────────────────        ─────────────────────     ────────────────────────────
1 sessão ativa             Sessões ilimitadas        Sessões ilimitadas
50 itens/sessão            10.000 itens/sessão       Sem limite
1 operador                 20 operadores             Sem limite de operadores
Sem grupos                 Grupos ilimitados         Grupos + Supervisor
Sem histórico              6 meses histórico         Histórico completo
Sem IA                     Análise IA básica         IA completa + plano de ação
Export Excel               Export Excel + PDF        ERP (TOTVS/SAP/Omie/Bling)
Sem supervisor             Supervisor incluído        Supervisor + multi-unidade
```

**Billing:**
- [ ] Integração Stripe ou Pagar.me (PIX + cartão)
- [ ] Webhook de pagamento → ativa/desativa plano automaticamente
- [ ] Trial 14 dias sem cartão para plano Pro

---

### 🚀 SPRINT 8 — Features de Alto Valor (estimado: 5 semanas)

**1. Contador de Velocidade por Operador (feature 1.4)**
- Dashboard em tempo real: `operador / itens contados / itens/min / último scan`
- Alerta automático via WS quando operador fica > 10min inativo
- Gráfico de produtividade por turno

**2. Histórico Multi-sessão + Comparação**
- Aba "Histórico" com linha do tempo
- Gráfico divergência % por inventário
- Endpoint `GET /sessoes/{id}/comparar/{id_anterior}` — diff visual
- Destaque automático: "este item diverge em 3 inventários consecutivos"

**3. Predição de Divergências (2.1) — IA**
- `PreditorAgent`: analisa N sessões anteriores, retorna probabilidade por item
- Mostra antes da R1: "Atenção — estes 12 itens têm histórico de divergência"
- Ordena itens suspeitos no topo da lista do operador

**4. Notificações Push / E-mail (feature 1.8)**
- Integração Resend para e-mail transacional
- Webhook configurável por empresa
- Eventos: R1 concluída, divergência >X%, operador inativo, sessão finalizada
- Resumo automático por e-mail ao concluir

**5. Exportação ERP (feature 1.7)**
- Templates por ERP: TOTVS, SAP, Bling, Omie
- Admin configura mapeamento de campos uma vez → salva como template
- `GET /sessoes/{id}/exportar/erp?formato=totvs`

**6. Multi-unidade**
- Empresa com múltiplas unidades físicas
- Cada sessão pertence a uma unidade
- Relatório consolidado entre unidades
- Gestor vê todas; gerente de unidade vê só a dele

**7. Detecção de Fraude (2.2) — IA**
- `AlertaFraudeAgent`: detecta velocidade impossível, acerto excessivo, padrões sistêmicos
- Alerta vermelho discreto no painel admin (sem acusar publicamente)
- Log permanente com contexto para investigação posterior

---

### 🎯 SPRINT 9 — Experiência Premium (estimado: 4 semanas)

**8. App Nativo PWA**
- Converter `mobile.html` em PWA instalável
- Ícone na tela inicial do celular
- Notificações push nativas (Service Worker)
- Cache offline completo dos itens antes de entrar no depósito

**9. Foto por Item (1.10)**
- Câmera do celular ao confirmar divergência
- Compressão automática < 500KB
- Galeria de evidências no painel
- Foto no PDF do relatório final

**10. OCR de Etiquetas (2.6)**
- Fotografar etiqueta sem QR Code → Claude Vision extrai código
- Fuzzy match contra itens cadastrados
- Operador confirma → registra contagem

**11. Plano de Ação Automático (2.4)**
- `PlanoAcaoAgent`: ao concluir sessão, gera plano de ação em markdown
- Divide em: ação imediata / investigar esta semana / melhorias de processo
- PDF exportável do plano
- Pode ser enviado por e-mail automaticamente

**12. Dashboard Executivo**
- KPIs consolidados por período: % divergência, tendência, top itens problemáticos
- Benchmark entre unidades
- Projeção: "Se manter tendência, próximo inventário terá X% divergência"

---

## PARTE 5 — O QUE TORNA O INVIQ VENDÁVEL

### Proposta de valor resumida (elevator pitch)

> *"INVIQ é o sistema de inventário físico que substitui a planilha e a prancheta. Operadores escaneiam com o celular, o sistema organiza por setores, detecta divergências automaticamente e entrega um relatório com causa provável e plano de ação — tudo em tempo real, sem hardware especial."*

### Público-alvo prioritário

1. **Distribuidoras e atacados** — estoques grandes, múltiplos operadores, pressão de auditoria
2. **Redes de varejo** — múltiplas unidades, operadores temporários, necessidade de velocidade
3. **Indústrias** — almoxarifado, matéria-prima, controle de ativo imobilizado
4. **Transportadoras** — contagem de frota, pneus, ferramentas de campo

### Modelo de vendas sugerido

- **Self-service**: cadastro no site → trial 14 dias → upgrade por Pix/cartão
- **Inside sales**: para contas Enterprise (> 500 itens/mês)
- **Parceiros**: contadores e consultores de ERP que fazem inventário para clientes

### Métricas de sucesso (para pitch de investidor)

- **ARR (Annual Recurring Revenue)** como principal métrica
- **NPS de operadores** — se o operador ama, o gestor renova
- **Tempo para primeiro inventário concluído** — onboarding de 10 minutos é possível
- **Taxa de divergência média dos clientes** — INVIQ melhora esse número = retenção

---

## RESUMO EXECUTIVO

### O que consertar ANTES de qualquer usuário real

1. **Rate limit em verificação de token** (2h) — segurança básica
2. **Evento WS de sessão pausada** (3h) — operadores ficam sem saber
3. **Reimport com confirmação** (2h) — perda de dados
4. **Guard de sessão sem itens** (1h) — crash garantido
5. **Comparação de enum unificada** (1h) — bug silencioso

**Total: ~9 horas de trabalho para proteger o MVP**

### O que implementar para primeiro cliente pagante

1. Autenticação por e-mail (sem login mobile) — Sprint 6
2. Multi-tenant básico — Sprint 6
3. Plano Free e Pro — Sprint 7
4. Notificações por e-mail — Sprint 8
5. Histórico multi-sessão — Sprint 8

**Total: ~8 semanas de trabalho para SaaS v1**

### Estimativa de valor de mercado

- Com 50 clientes Pro pagando R$149/mês = **R$7.450/mês ARR R$89.400**
- Com 10 clientes Enterprise = **+R$5.990/mês**
- Múltiplo SaaS B2B Brasil: 5-8x ARR → **valuation entre R$750k e R$1,2M em 12 meses**

---

*Documento gerado em 2026-06-01 — INVIQ Product Analysis*
