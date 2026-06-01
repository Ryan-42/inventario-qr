# Sistema de Agentes IA — Inventário QR

> Arquitetura inspirada em [Ruflo](https://github.com/ruvnet/ruflo) — queen-led hierarchy com MCP
> Data: 2026-05-24

---

## Visão Geral da Arquitetura

```
                         ┌──────────────────────────┐
                         │     USUÁRIO / SISTEMA     │
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │    OrchestratorAgent     │  "Rainha"
                         │  (Claude Sonnet 4.6)     │
                         │  Roteamento + Contexto   │
                         └──────────┬───────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
    ┌─────────▼──────┐   ┌──────────▼──────┐   ┌─────────▼──────┐
    │  ValidationAgent│   │ AnalyticsAgent  │   │   AuditAgent   │
    │  (Haiku 4.5)   │   │ (Sonnet 4.6)    │   │  (background)  │
    └────────────────┘   └─────────────────┘   └────────────────┘
              │                     │                     │
    ┌─────────▼──────┐   ┌──────────▼──────┐   ┌─────────▼──────┐
    │Notification    │   │ PredictionAgent │   │  ExportAgent   │
    │Agent           │   │ (Sonnet 4.6)    │   │  (Haiku 4.5)   │
    └────────────────┘   └─────────────────┘   └────────────────┘
              │                     │                     │
    ┌─────────▼──────┐   ┌──────────▼──────┐   ┌─────────▼──────┐
    │  SearchAgent   │   │  ImportAgent    │   │SecurityAgent   │
    │  (pgvector)    │   │  (Sonnet 4.6)   │   │  (heuristics)  │
    └────────────────┘   └─────────────────┘   └────────────────┘
```

---

## Infraestrutura Compartilhada

```python
# Cada agente recebe este contexto base
class AgentContext:
    session_id: str
    user_id: str
    user_role: str          # admin | supervisor | operator
    tenant_id: str          # para multi-tenant futuro
    timestamp: datetime
    trace_id: str           # para observabilidade

# Comunicação entre agentes via Redis pub/sub
class AgentBus:
    publish(channel: str, event: AgentEvent)
    subscribe(channel: str, handler: Callable)

# Resultado padronizado
class AgentResult:
    success: bool
    agent: str
    data: dict
    confidence: float       # 0.0 a 1.0
    duration_ms: int
    tokens_used: int        # para cost tracking
```

---

## Agente 1: OrchestratorAgent

```
Modelo:    claude-sonnet-4-6
Função:    Coordena todos os outros agentes
Padrão:    Queen-led hierarchy (Ruflo)
```

### Responsabilidades
- Receber eventos do sistema (upload, scan, export request)
- Determinar quais agentes acionar e em qual ordem
- Gerenciar contexto entre chamadas de agentes
- Agregar e sintetizar respostas
- Retry automático em caso de falha de sub-agente
- Cost tracking (tokens usados por sessão)

### Implementação

```python
# backend/agents/orchestrator.py
import anthropic
from .bus import AgentBus
from .context import AgentContext

class OrchestratorAgent:
    def __init__(self):
        self.client = anthropic.Anthropic()
        self.bus = AgentBus()

    async def handle_event(self, event: str, context: AgentContext, data: dict):
        """Roteia eventos para agentes corretos"""
        routing_map = {
            "file_uploaded":     [ValidationAgent, ImportAgent],
            "count_registered":  [AuditAgent, SecurityAgent, NotificationAgent],
            "session_concluded": [AnalyticsAgent, ExportAgent, NotificationAgent],
            "query_received":    [SearchAgent],
            "session_started":   [PredictionAgent],
        }
        agents = routing_map.get(event, [])
        results = await self._run_agents_parallel(agents, context, data)
        return self._synthesize(results)

    async def _run_agents_parallel(self, agents, context, data):
        import asyncio
        tasks = [agent().run(context, data) for agent in agents]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

### Ferramentas MCP disponíveis
- `route_to_agent(agent_name, payload)`
- `get_session_context(session_id)`
- `publish_event(channel, event)`
- `get_agent_status(agent_name)`

---

## Agente 2: ValidationAgent

```
Modelo:    claude-haiku-4-5-20251001  (rápido + barato para validação)
Trigger:   POST /api/sessoes/:id/upload
Latência:  < 2 segundos
```

### O que valida

```python
VALIDATION_RULES = [
    "colunas_obrigatorias",      # codigo, produto, quantidade
    "duplicatas_codigo",         # mesmo código duas vezes
    "quantidades_invalidas",     # negativas, zero, não-numéricas
    "codigos_vazios",            # linhas sem código
    "nomes_produto_vazios",      # produto em branco
    "encoding_problemas",        # caracteres estranhos
    "formato_codigo",            # padrão esperado (ex: PAT:XXXX)
    "numeros_muito_altos",       # quantidade > 99999 (suspeito)
]
```

### Prompt do Agente

```python
VALIDATION_PROMPT = """
Você é um agente de validação de planilhas de inventário.
Analise os dados fornecidos e identifique:

1. Problemas críticos (impedem o import)
2. Avisos (import pode prosseguir com ressalvas)
3. Sugestões de melhoria

Responda em JSON com:
{
  "valido": bool,
  "pode_importar_com_avisos": bool,
  "problemas_criticos": [{"linha": int, "tipo": str, "descricao": str}],
  "avisos": [{"linha": int, "tipo": str, "descricao": str}],
  "sugestoes": [str],
  "total_itens_validos": int,
  "total_itens_invalidos": int,
  "confianca": float
}
"""
```

### Output para o usuário
```json
{
  "valido": false,
  "pode_importar_com_avisos": true,
  "problemas_criticos": [],
  "avisos": [
    {"linha": 47, "tipo": "duplicata", "descricao": "Código PAT:E005.156.025 aparece 2 vezes"},
    {"linha": 112, "tipo": "quantidade_zero", "descricao": "Quantidade 0 pode ser erro"}
  ],
  "sugestoes": ["Padronize os códigos para o formato PAT:XXXX.XXX.XXX"],
  "total_itens_validos": 1843,
  "total_itens_invalidos": 2,
  "confianca": 0.97
}
```

---

## Agente 3: AnalyticsAgent

```
Modelo:    claude-sonnet-4-6
Trigger:   Conclusão de sessão | solicitação manual
Latência:  5-30 segundos (análise profunda)
```

### Análises geradas

1. **Resumo Executivo** — visão de alto nível para gestores
2. **Taxa de Divergência por Categoria** — quais tipos de produto divergem mais
3. **Performance dos Operadores** — itens/hora, taxa de erro por operador
4. **Comparativo entre Sessões** — melhorou ou piorou vs sessão anterior?
5. **Itens de Risco** — produtos com histórico de divergência recorrente
6. **Gargalos de Processo** — onde o tempo foi perdido?
7. **Recomendações de Ação** — o que fazer para melhorar

### Prompt principal

```python
ANALYTICS_PROMPT = """
Você é um analista sênior de inventário e supply chain.
Dado os dados da sessão de inventário abaixo, gere:

1. Um resumo executivo em 3 parágrafos (linguagem clara para gestores)
2. Top 5 insights mais importantes
3. 3 ações recomendadas com prioridade (Alta/Média/Baixa)
4. Análise de risco para próximas sessões

Dados: {session_data}
Histórico: {historical_data}

Responda em markdown estruturado, com tabelas onde apropriado.
Seja objetivo e acionável.
"""
```

---

## Agente 4: AuditAgent

```
Modelo:    Sem LLM (regras determinísticas) + Claude para relatórios
Trigger:   Toda mutação de dados (background task)
Latência:  < 100ms (async, não bloqueia)
```

### Schema de auditoria

```sql
CREATE TABLE audit_logs (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    sessao_id       UUID REFERENCES sessoes(id),
    usuario_id      UUID REFERENCES usuarios(id),
    acao            VARCHAR(50),    -- 'contagem_registrada', 'sessao_criada', etc.
    entidade        VARCHAR(50),    -- 'contagem', 'sessao', 'item_base'
    entidade_id     UUID,
    dados_antes     JSONB,
    dados_depois    JSONB,
    ip_address      INET,
    user_agent      TEXT,
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_sessao ON audit_logs(sessao_id);
CREATE INDEX idx_audit_usuario ON audit_logs(usuario_id);
CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp DESC);
```

### Detecções automáticas

```python
SUSPICIOUS_PATTERNS = {
    "rapid_rescan": "mesmo item, mesmo operador, < 30 segundos",
    "bulk_same_quantity": "operador registra sempre quantidade == base (nunca conta?)",
    "impossible_speed": "> 10 itens/minuto sustentado",
    "off_hours_activity": "atividade entre 00h-05h",
    "session_after_conclusion": "contagem após sessão concluída",
}
```

---

## Agente 5: NotificationAgent

```
Modelo:    Sem LLM (regras de trigger) + Claude para mensagens
Trigger:   Eventos críticos e thresholds
Canais:    WebSocket (tempo real) | Email | Push (PWA)
```

### Regras de trigger

```python
NOTIFICATION_RULES = [
    # (condição, canal, destinatário, prioridade)
    ("divergencia_rate > 20%", "websocket+email", "admin", "alta"),
    ("operator_idle > 30min", "websocket", "admin", "média"),
    ("sessao_concluida", "email", "admin+supervisors", "informativa"),
    ("import_com_erros", "websocket", "admin", "alta"),
    ("sessao_sem_atividade > 2h", "email", "admin", "média"),
    ("security_alert", "websocket+email", "admin", "crítica"),
    ("all_items_counted", "websocket", "admin", "positiva"),
]
```

### Formato das notificações

```python
class Notification:
    title: str
    body: str
    priority: Literal["critica", "alta", "media", "informativa", "positiva"]
    action_url: str | None
    icon: str           # emoji ou icon name
    data: dict          # dados extras para o frontend
    expires_at: datetime
```

---

## Agente 6: ExportAgent

```
Modelo:    claude-haiku-4-5-20251001 (para narrativas) + pandas (para dados)
Trigger:   Solicitação manual | conclusão automática de sessão
Formatos:  XLSX, PDF, CSV, JSON, XML
```

### Templates de relatório PDF

```
Relatório Completo:
  ├── Capa (logo, nome da sessão, data, período)
  ├── Resumo Executivo (gerado pelo AnalyticsAgent)
  ├── Métricas Principais (cards visuais)
  ├── Tabela Completa de Itens
  ├── Página de Divergências (destaque visual)
  ├── Análise por Operador
  └── Assinatura Digital + Hash SHA256

Relatório de Divergências:
  ├── Lista de divergências com detalhes
  ├── Análise de causa provável (AI)
  └── Ações recomendadas
```

### Implementação

```python
# backend/agents/export_agent.py
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, Paragraph
import anthropic

class ExportAgent:
    async def generate_pdf(self, session_id: str, template: str = "completo"):
        session_data = await self._get_session_data(session_id)

        # Gera narrativa com Claude
        narrative = await self._generate_narrative(session_data)

        # Monta PDF
        doc = SimpleDocTemplate(f"inventario_{session_id}.pdf", pagesize=A4)
        story = self._build_story(session_data, narrative, template)
        doc.build(story)

        return self._to_bytes(doc)
```

---

## Agente 7: SearchAgent (RAG)

```
Modelo:    claude-sonnet-4-6 + pgvector
Trigger:   Query em linguagem natural
Índice:    Embeddings de produto + código (gerados no import)
```

### Configuração pgvector

```sql
CREATE EXTENSION vector;

ALTER TABLE itens_base ADD COLUMN embedding vector(1536);

CREATE INDEX ON itens_base USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

### Geração de embeddings no import

```python
async def embed_item(item: dict) -> list[float]:
    client = anthropic.Anthropic()
    text = f"{item['codigo']} {item['produto']}"
    # Usar OpenAI embeddings ou Amazon Titan (Claude não tem embedding endpoint)
    # Alternativa: sentence-transformers local (modelo leve)
    return embedding
```

### Queries suportadas

```
"Itens com código PAT:E005" → busca por prefixo
"Equipamentos de laboratório" → busca semântica
"Produtos que falharam na última sessão" → busca + filtro
"Quantos itens pendentes temos no setor B?" → NL2SQL
```

---

## Agente 8: ImportAgent

```
Modelo:    claude-sonnet-4-6
Trigger:   Upload de arquivo
Formatos:  XLSX, XLS, CSV, ODS, PDF (tabelas), JSON, XML
```

### Auto-mapeamento de colunas

```python
COLUMN_MAPPING_PROMPT = """
Dado os nomes de colunas encontrados na planilha:
{found_columns}

Mapeie para os campos do sistema:
- codigo (obrigatório): código único do item
- produto (obrigatório): nome/descrição do produto
- quantidade (obrigatório): quantidade esperada em estoque
- setor (opcional): setor/área do item

Responda em JSON: {"codigo": "col_name", "produto": "col_name", ...}
Se não conseguir mapear um campo obrigatório, informe null.
"""
```

### Fluxo com preview

```
1. Upload do arquivo
2. ImportAgent detecta formato e lê estrutura
3. Auto-mapeia colunas (ValidationAgent valida)
4. Retorna preview: primeiras 10 linhas + mapping sugerido
5. Usuário confirma ou ajusta o mapeamento
6. Import executado com bulk insert
7. AuditAgent registra o import
```

---

## Agente 9: PredictionAgent

```
Modelo:    claude-sonnet-4-6
Trigger:   Início de nova sessão | semanal automático
Requisito: >= 3 sessões históricas
```

### Previsões geradas

```python
PREDICTIONS = {
    "high_risk_items": "Itens com probabilidade > 70% de divergência",
    "estimated_duration": "Tempo estimado para concluir a sessão",
    "recommended_operators": "Número ideal de operadores para meta de tempo",
    "potential_losses": "Estimativa de valor em divergência esperada",
    "seasonal_patterns": "Padrões sazonais detectados no histórico",
}
```

### Prompt de predição

```python
PREDICTION_PROMPT = """
Você é um especialista em gestão de inventário com 20 anos de experiência.

Histórico de sessões anteriores: {historical_sessions}
Nova sessão iniciada: {new_session}
Total de itens: {total_items}

Forneça:
1. Lista dos 20 itens com maior risco de divergência (com justificativa)
2. Estimativa de tempo para conclusão da sessão
3. Número recomendado de operadores
4. Alertas de atenção especial

Seja específico e baseia-se nos dados históricos. Se dados insuficientes, informe.
"""
```

---

## Agente 10: SecurityAgent

```
Modelo:    Regras heurísticas (sem LLM para latência)
Trigger:   Background contínuo (a cada evento de contagem)
Ação:      Alerta → NotificationAgent | Bloquear → OrchestratorAgent
```

### Heurísticas de detecção

```python
class SecurityRules:

    def check_rapid_scanning(self, operator_id, scans: list) -> bool:
        """Mais de 10 scans em 1 minuto = suspeito"""
        recent = [s for s in scans if s.age_seconds < 60]
        return len(recent) > 10

    def check_no_divergences(self, operator_id, session_id) -> bool:
        """Operador com 0 divergências em 500+ itens = suspeito (não está contando?)"""
        counts = get_operator_counts(operator_id, session_id)
        if len(counts) > 500:
            return all(c.divergencia == False for c in counts)
        return False

    def check_impossible_location(self, operator_id, recent_scans) -> bool:
        """Dois scans de setores muito distantes em < 2 min"""
        if len(recent_scans) < 2:
            return False
        s1, s2 = recent_scans[-2], recent_scans[-1]
        if s1.setor != s2.setor and (s2.timestamp - s1.timestamp).seconds < 120:
            return True
        return False

    def check_post_session(self, session_id, contagem_timestamp) -> bool:
        """Contagem após sessão concluída"""
        sessao = get_sessao(session_id)
        return sessao.status == "concluida" and contagem_timestamp > sessao.data_fim
```

---

## Implementação Passo a Passo

### Estrutura de pastas

```
backend/
├── agents/
│   ├── __init__.py
│   ├── base.py              # Classe base BaseAgent
│   ├── orchestrator.py      # OrchestratorAgent
│   ├── validation.py        # ValidationAgent
│   ├── analytics.py         # AnalyticsAgent
│   ├── audit.py             # AuditAgent
│   ├── notification.py      # NotificationAgent
│   ├── export.py            # ExportAgent
│   ├── search.py            # SearchAgent
│   ├── import_agent.py      # ImportAgent
│   ├── prediction.py        # PredictionAgent
│   ├── security.py          # SecurityAgent
│   ├── bus.py               # Redis pub/sub
│   ├── context.py           # AgentContext
│   └── tools/               # MCP tools
│       ├── session_tools.py
│       ├── item_tools.py
│       └── user_tools.py
```

### BaseAgent

```python
# backend/agents/base.py
from abc import ABC, abstractmethod
import anthropic
import time
from .context import AgentContext, AgentResult

class BaseAgent(ABC):
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096
    timeout: int = 30

    def __init__(self):
        self.client = anthropic.Anthropic()
        self.name = self.__class__.__name__

    @abstractmethod
    async def run(self, context: AgentContext, data: dict) -> AgentResult:
        pass

    async def _call_claude(self, system: str, user: str, tools: list = None) -> str:
        start = time.time()
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if tools:
            kwargs["tools"] = tools

        response = self.client.messages.create(**kwargs)
        duration = int((time.time() - start) * 1000)

        return AgentResult(
            success=True,
            agent=self.name,
            data={"content": response.content[0].text},
            confidence=0.9,
            duration_ms=duration,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
        )
```

### Instalação do sistema de agentes

```bash
# Adicionar ao requirements.txt
anthropic>=0.34.0
celery[redis]>=5.4.0
redis>=5.0.0
pgvector>=0.3.0
reportlab>=4.0.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.0

# Variáveis de ambiente (.env)
ANTHROPIC_API_KEY=sk-ant-...
REDIS_URL=redis://localhost:6379/0
```

---

## Monitoramento dos Agentes

```python
# Métricas coletadas por agente
agent_metrics = {
    "calls_total": Counter,           # Total de chamadas
    "calls_failed": Counter,          # Falhas
    "duration_seconds": Histogram,    # Latência
    "tokens_used": Counter,           # Custo Claude
    "confidence_score": Gauge,        # Qualidade média
}

# Dashboard Grafana com:
# - Calls/min por agente
# - Latência P50/P95/P99
# - Taxa de erro
# - Custo Claude por dia
# - Confidence score médio
```

---

## Custo Estimado dos Agentes

| Agente | Modelo | Freq/Sessão | Tokens/Call | Custo Estimado |
|--------|--------|------------|-------------|----------------|
| ValidationAgent | Haiku 4.5 | 1x | ~2K | $0.002 |
| AnalyticsAgent | Sonnet 4.6 | 1x | ~8K | $0.24 |
| AuditAgent | N/A | n/a | 0 | $0 |
| NotificationAgent | N/A | ~5x | 0 | $0 |
| ExportAgent (narrativa) | Haiku 4.5 | 1x | ~3K | $0.003 |
| SearchAgent | Sonnet 4.6 | ~10x | ~2K | $0.60 |
| ImportAgent | Sonnet 4.6 | 1x | ~3K | $0.09 |
| PredictionAgent | Sonnet 4.6 | 1x | ~10K | $0.30 |
| SecurityAgent | N/A | n/a | 0 | $0 |
| OrchestratorAgent | Sonnet 4.6 | ~5x | ~2K | $0.30 |
| **TOTAL por sessão** | | | | **~$1.50** |
