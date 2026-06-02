
# INVIQ — Features e Utilidades de IA

> Documento de evolução: features pensadas para o fluxo real de um inventário físico
> e utilidades de IA que resolvem problemas concretos de quem faz inventário.
> Atualizado: 2026-06-01 | v3.1 — Sprint 4 implementado

---

## Status de Implementação

| Feature | Status | Sprint |
|---------|--------|--------|
| 1.1 Modo Supervisor | ✅ **Implementado** | 4 |
| 1.2 Lista de pendências por operador | ✅ **Implementado** | 4 |
| 1.3 Pausa e Retomada de Sessão | ✅ **Implementado** | 4 |
| 1.4 Contador de velocidade | 🔜 Planejado | 5 |
| 1.5 Contagem parcial por setor (Grupos) | ✅ **Implementado** | 4 |
| 1.6 Histórico de sessões no dashboard | 🔜 Planejado | 5 |
| 1.7 Exportação para ERP | 🔜 Planejado | 6 |
| 1.8 Token de Admin (senha do inventário) | ✅ **Implementado** | 4 |
| 1.9 Etiquetas QR para itens novos | 🔜 Planejado | 6 |
| 1.10 Foto por item | 🔜 Planejado | 6 |

---

## 1. Features de Fluxo de Inventário

### 1.1 Modo Supervisor ✅ IMPLEMENTADO

**Problema:** O administrador fica preso na mesa enquanto o inventário acontece no campo. Se surgir dúvida numa prateleira, não tem como resolver sem ir até o computador.

**Solução implementada:**
```
Admin → gera QR do Supervisor (token especial via /sessoes/{id}/gerar-token-supervisor)
Supervisor (celular) → acessa /supervisor/{sessao_id}?token={token}
                     → vê em tempo real quais itens divergiram
                     → visualiza localização de cada item (local_fisico)
                     → filtros: Todos / Divergente / Para Ajuste
                     → busca por código, produto ou local
                     → atualização em tempo real via WebSocket
```

**Regras de acesso:**
- Supervisor só é liberado após a 1ª rodada concluída (`faltando_r1 == 0`)
- Acesso somente-leitura — não pode registrar contagens
- Vê apenas itens divergentes (não vê quantidade base)
- Admin gera QR Code via dashboard → `/sessoes/{id}/qrcode-supervisor`

**Endpoints:**
- `POST /sessoes/{id}/gerar-token-supervisor` — Gera/regenera token
- `GET /sessoes/{id}/itens-supervisor?token=...` — Lista itens divergentes com localização
- `GET /sessoes/{id}/qrcode-supervisor?base_url=...` — QR Code PNG (indigo)

---

### 1.2 Lista de Pendências por Operador ✅ IMPLEMENTADO

**Problema:** Em inventários grandes (500+ itens), na R2 e R3, o operador não sabe quais itens AINDA são dele para recontagem.

**Solução implementada:**
- Botão "Lista" (ícone checklist) na barra superior do scanner mobile
- Abre tela com todos os itens pendentes da rodada atual
- Mostra: código + nome do produto + localização — **SEM quantidade**
- Agrupado por `local_fisico` para facilitar o percurso
- Busca por código ou nome
- Clicar em qualquer item → abre tela de contagem direto
- Filtra automaticamente pelo grupo do operador (se token de grupo)

**Endpoint:**
```
GET /sessoes/{id}/lista-operador?rodada=1&token={token_grupo}
Resposta: [{codigo, produto, local_fisico, ja_contado, rodada}]
```

---

### 1.3 Pausa e Retomada de Sessão ✅ IMPLEMENTADO

**Problema:** Inventários grandes duram horas. Operadores precisam parar para almoçar, trocar de turno.

**Solução implementada:**
- `PATCH /sessoes/{id}/pausar?previsao_retomada=14:00` — marca `status=pausada`
- `PATCH /sessoes/{id}/retomar` — volta para `ativa`, gera novo token de acesso
- Operadores com token antigo não conseguem entrar após pausa/retomada

---

### 1.4 Contador de Velocidade por Operador

**Problema:** O gestor não sabe se o operador está contando ou parou.

**Solução planejada:** KPI em tempo real no painel admin:
```
João Silva    ████████░░  42 itens  |  8,4/min  |  último scan: 2 min atrás
Maria Santos  ██████████  78 itens  |  12,1/min |  último scan: 30s atrás
Pedro Alves   ███░░░░░░░  15 itens  |  2,1/min  |  último scan: 18 min atrás ← parou?
```
Alert automático via WS quando operador fica > 10 min sem scan.

---

### 1.5 Contagem Parcial por Setor (Grupos de Operadores) ✅ IMPLEMENTADO

**Problema:** Em depósitos grandes, faz sentido um operador fazer o setor A e outro o B. Hoje o sistema não tinha essa segregação.

**Solução implementada:**
- Admin cria grupos pelo dashboard (`POST /sessoes/{id}/grupos`)
- Cada grupo tem: nome, filtro de prefixo/lista, cor e token próprio
- Operador entra com o token do grupo (não o token geral)
- O scanner bloqueia automaticamente itens de outros grupos: "Item de outro grupo"
- Lista de itens (`/lista-operador?token={token_grupo}`) já filtra por grupo
- Admin gera QR Code por grupo via `GET /sessoes/{id}/grupos/{grupo_id}/qrcode`

**Exemplos de filtro:**
- `filtro="A", tipo_filtro="prefixo"` → Só itens com código começando por "A"
- `filtro="A,B,C", tipo_filtro="prefixo"` → Itens dos setores A, B e C
- `filtro="SKU-001,SKU-002", tipo_filtro="lista"` → Lista exata de códigos
- `filtro="*", tipo_filtro="todos"` → Todos os itens

---

### 1.6 Histórico de Sessões Anteriores no Dashboard

**Problema:** Não há como comparar o inventário atual com o anterior.

**Solução planejada:**
- Aba "Histórico" no dashboard com linha do tempo de sessões
- Gráfico de evolução: divergência % por mês
- Destacar itens que divergem em múltiplos inventários consecutivos
- Endpoint `GET /sessoes/{id}/comparar/{id_anterior}` para diff entre dois inventários

---

### 1.7 Exportação para ERP (formato configurável)

**Problema:** Após o inventário, o ajuste no ERP é manual.

**Solução planejada:**
```
GET /sessoes/{id}/exportar/erp?formato=totvs
GET /sessoes/{id}/exportar/erp?formato=sap
GET /sessoes/{id}/exportar/erp?formato=bling
GET /sessoes/{id}/exportar/erp?formato=omie
```
Templates de exportação por ERP com mapeamento configurável de campos.

---

### 1.8 Token de Admin (Senha do Inventário) ✅ IMPLEMENTADO

**Problema:** Sem autenticação, qualquer pessoa com a URL do painel pode ver o inventário.

**Solução implementada:**
- Ao criar sessão, o sistema gera automaticamente um `token_admin` (16 hex chars)
- O token é exibido UMA VEZ no modal de criação — o criador deve salvar
- Armazenado em `localStorage` do navegador como chave de acesso
- Sessões "minhas" aparecem com badge 🔑 na listagem
- Ao navegar para o painel, o token é passado via URL (`/sessao/{id}?ta={token}`)
- Endpoint de verificação: `GET /sessoes/{id}/verificar-admin?token=...`

**Fluxo:**
```
Admin cria sessão → recebe token_admin (ex: "A3B9C2D14E5F6G7H")
                 → token armazenado localmente
                 → navega para painel com token na URL
                 → badge "Meu" aparece na listagem
```

---

### 1.9 Etiquetas QR para Itens Novos (durante o inventário)

**Problema:** O operador encontra um item que não está na planilha.

**Solução planejada:**
- Botão "Item não encontrado" no scanner mobile
- Operador digita código e produto → sistema cria item com `quantidade_base = 0`
- Gera etiqueta QR na hora (PDF download no celular)
- Esses itens aparecem no relatório final com flag "Encontrado em campo"

---

### 1.10 Foto por Item (evidência de divergência)

**Problema:** Um item diverge mas não há evidência física.

**Solução planejada:**
- Câmera do celular captura foto ao confirmar divergência
- Foto comprimida (< 500KB) enviada como `multipart/form-data`
- Armazenada com link no `observacao` do item
- Galeria de evidências na tela de detalhe da sessão

---

## 2. Utilidades de IA para o Inventário

### 2.1 Predição de Divergências (PreditorAgent)

**Problema:** O operador conta 500 itens sem saber quais merecem mais atenção.

**Como funciona:**
```python
class PreditorAgent:
    def prever(self, historico_sessoes: list[dict], itens_atuais: list[dict]) -> list[dict]:
        """
        Analisa histórico de N sessões anteriores.
        Retorna lista de itens com probabilidade estimada de divergência.
        """
```

**Interface:** Antes de iniciar a R1, o admin vê:
```
⚠️  Itens com histórico de divergência — recomendamos atenção extra:
    SKU-042  Motor 5cv      [██████████] 87% chance de divergir
    SKU-099  Filtro HQ      [███████░░░] 65% chance
    SKU-210  Bomba 1/4cv    [████░░░░░░] 38% chance
```

---

### 2.2 Detecção de Padrão de Fraude (AlertaFraudeAgent)

**Problema:** Um operador pode registrar contagens falsas.

**Sinais detectados por IA:**
- Operador registrando > 20 itens/minuto (fisicamente impossível)
- Quantidades sempre exatamente iguais à base (suspeito)
- Todas as divergências sempre positivas
- Múltiplas contagens do mesmo item em segundos

```python
class AlertaFraudeAgent:
    _ITENS_POR_MIN_LIMITE = 20
    _PCT_EXATO_SUSPEITO = 0.95
    
    def analisar(self, contagens_operador: list, janela_minutos: int = 60) -> dict:
        return {
            "velocidade_suspeita": bool,
            "acerto_excessivo": bool,
            "divergencias_sistematicas": bool,
            "nivel_alerta": "baixo" | "medio" | "alto",
            "detalhes": str
        }
```

---

### 2.3 Classificação Automática de Causa de Divergência (ClassificadorAgent)

**Problema:** Após o inventário, o gestor precisa entender POR QUÊ divergiu.

**Causas classificadas:**
- `erro_operador`, `erro_cadastro`, `produto_em_transito`
- `avaria_fisica`, `possivel_furto`, `consumo_nao_registrado`

**Integração:** Aparece no PDF Final como coluna "Causa Provável".

---

### 2.4 Geração de Plano de Ação (PlanoAcaoAgent)

**Problema:** O relatório mostra o problema. O gestor não sabe qual ação tomar.

**O que o agente gera ao final da sessão:**
```markdown
## Plano de Ação — Inventário INV-2026-0012

### Ação imediata (hoje)
- [ ] Ajustar no ERP os 4 itens "Para Ajuste"
- [ ] Investigar SKU-042: -15 unidades, R$ 12.450 de impacto

### Investigar esta semana
- [ ] Setor A-07 tem 68% de divergência — auditar processo de recebimento
```

---

### 2.5 Chat com Contexto Histórico (HistoricoAgent)

**Problema:** O Chat IA atual responde só sobre a sessão atual.

**O que muda:**
- Chat recebe contexto de N sessões anteriores
- Responde: "Este SKU já divergiu antes?", "Qual setor é mais problemático?"

---

### 2.6 OCR de Etiquetas Antigas (OCRAgent)

**Problema:** Produtos antigos sem QR Code — etiquetas manuscritas ou desgastadas.

**Solução:**
1. Operador fotografa a etiqueta
2. OCR extrai texto (Claude Vision ou PaddleOCR)
3. Sistema faz fuzzy match contra itens cadastrados
4. Operador confirma o match

---

### 2.7 Resumo Automático por WhatsApp ao Concluir

**Problema:** O gestor precisa explicar o inventário para a diretoria.

**O que a IA gera:**
```
✅ *Inventário Concluído — INV-2026-0012*
📦 500 itens | ✅ 487 OK | ⚠️ 8 divergentes | 🟣 5 para ajuste
💰 *Impacto financeiro:* -R$ 8.420,00 (-1,8% do estoque)
```

---

### 2.8 Análise de Causa-Raiz por Setor (SetorAgent)

Detecta setores problemáticos com análise histórica e recomendações de processo.

---

### 2.9 Auto-preenchimento por Câmera (VisionAgent)

Para paletes, barris e granel — IA estima a quantidade visível pela foto.

---

### 2.10 Validação Cruzada entre Operadores (ValidacaoParAgent)

Modo "Par": dois operadores contam o mesmo item independentemente. Discordância → R2 imediata.

---

## 3. Priorização

### Sprint 4 — Implementado ✅
| # | Feature | Status |
|---|---------|--------|
| 1 | Grupos de Operadores (1.5) | ✅ Backend + Mobile |
| 2 | Lista de itens por operador (1.2) | ✅ Mobile UI + Endpoint |
| 3 | Modo Supervisor (1.1) | ✅ supervisor.html + Endpoints |
| 4 | Token de Admin (1.8) | ✅ Geração + Modal + LocalStorage |
| 5 | Pausa e Retomada (1.3) | ✅ Endpoints |

### Sprint 5 — Próximo
| # | Feature/IA | Impacto | Esforço |
|---|-----------|---------|---------|
| 1 | Contador de velocidade + alerta inativo (1.4) | 🔴 Alto | Baixo |
| 2 | Notificações WhatsApp ao concluir (1.8 + 2.7) | 🟡 Alto | Médio |
| 3 | Classificador de causa de divergência (2.3) | 🟡 Alto | Médio |
| 4 | Plano de ação automático (2.4) | 🟡 Alto | Baixo |
| 5 | Histórico de sessões no dashboard (1.6) | 🟡 Alto | Médio |

### Sprint 6 — Recursos avançados
| # | Feature/IA | Impacto | Esforço |
|---|-----------|---------|---------|
| 1 | Exportação ERP (1.7) | 🔴 Alto | Médio |
| 2 | OCR de etiquetas antigas (2.6) | 🟢 Médio | Alto |
| 3 | Foto por item (1.10) | 🟢 Médio | Médio |
| 4 | Detecção de padrão de fraude (2.2) | 🟢 Médio | Médio |
| 5 | Etiquetas QR para itens em campo (1.9) | 🟢 Médio | Baixo |

---

*Documento atualizado em 2026-06-01 — INVIQ v3.1 | Sprint 4 concluído*
