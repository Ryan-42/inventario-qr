# INVIQ — Inventário Físico por QR Code

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-produção-336791?style=flat-square&logo=postgresql&logoColor=white)]()
[![Claude AI](https://img.shields.io/badge/Claude%20AI-Haiku-D97706?style=flat-square)](https://anthropic.com)
[![WebSocket](https://img.shields.io/badge/WebSocket-Tempo%20Real-10eb8a?style=flat-square)]()
[![Tests](https://img.shields.io/badge/Testes-396%20passando-4CAF50?style=flat-square)]()
[![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?style=flat-square&logo=railway&logoColor=white)]()

> Sistema de contagem de inventário físico com scanner mobile, tempo real via WebSocket, análise por IA e relatórios financeiros automáticos.

O INVIQ resolve um problema real: inventários físicos são lentos, sujeitos a erros humanos e não oferecem visibilidade ao gestor durante a contagem.

Com o INVIQ, cada produto tem um QR Code. O operador aponta o celular, informa a quantidade e o sistema registra instantaneamente — o gestor acompanha tudo ao vivo no painel, com atualizações em tempo real sem recarregar a página.

Divergências são detectadas e recontadas automaticamente em até 3 rodadas. Ao final, o sistema gera relatórios executivos em PDF e Excel com impacto financeiro calculado.

---

## Telas

| Tela | Quem usa | URL |
|------|----------|-----|
| **Dashboard** | Administrador | `/` |
| **Sessão** | Administrador | `/sessao/{id}` |
| **Scanner Mobile** | Operador | `/mobile/{id}?token=XXXX` |

---

## Funcionalidades

### Scanner Mobile
- **QR Code via câmera** — sem instalar app, funciona em qualquer browser mobile
- **Barcode nativo** — EAN-13/8, Code 128/39, UPC-A/E, ITF, PDF417, Aztec via BarcodeDetector API
- **Modo manual** com busca fuzzy por código, produto ou local físico
- **Funciona offline** — contagens salvas localmente e sincronizadas ao reconectar
- **Token de acesso por rodada** — QR Code gerado pelo admin controla qual rodada o operador pode contar
- Vibração ao detectar · Proteção contra duplo-scan · Câmera persistente ao mudar de estado

### Sistema de Rodadas
- **Rodada 1** — todos os itens contados ao menos uma vez
- **Rodada 2** — recontagem automática dos itens divergentes
- **Rodada 3** — recontagem final dos que ainda divergem
- **Para Ajuste** — mesma quantidade confirmada em recontagem vai direto para ajuste (sem nova rodada)

### Painel Admin em Tempo Real
- KPIs atualizados via WebSocket sem recarregar a página
- Gráfico de contagens por intervalo de 5 minutos
- Live feed de cada leitura dos operadores
- Banner automático ao concluir rodada com botão "Gerar QR Próxima Rodada"
- Tabela com filtros: OK / Divergente / **Para Ajuste** / Pendente
- Botão de excluir sessão com confirmação

### Grupos de Operadores
- Cada grupo tem token próprio + QR Code — operador é bloqueado fora do seu setor
- **Supervisor Mobile** — acesso somente-leitura pós-R1 com itens divergentes + localização
- **Lista do Operador** — itens pendentes filtrados por grupo no mobile

### Análise por IA (Claude Haiku)
- **Análise de sessão** — padrões, itens críticos, recomendações, relatório executivo
- **Chat IA** — perguntas em linguagem natural sobre a sessão
- **Validação de planilha** — detecta problemas antes de importar (prévia de 5 linhas)
- **Alerta em tempo real** — anomalias por regras após cada leitura
- Funciona sem API Key com análise local básica como fallback

### Exportações

| Tipo | Formato | Descrição |
|------|---------|-----------|
| Completo | `.xlsx` | Todos os itens com status, operadores e rodadas |
| Divergências | `.xlsx` | Só itens divergentes (para ajuste no ERP) |
| PDF Relatório | `.pdf` | Relatório executivo colorido por status |
| Etiquetas QR | `.pdf` | 14 etiquetas por folha A4 para impressão |
| **PDF Final** | `.pdf` | KPIs + impacto financeiro + análise IA + tabela completa |
| **Excel Final** | `.xlsx` | 4 abas: Resumo, Todos os Itens, Divergências com Impacto R$, Recomendações |

Exports via `fetch + blob` com token no body — token nunca aparece em URL ou logs.

### Impacto Financeiro
Quando a planilha tem a coluna `valor_estoque`, o sistema calcula automaticamente:
- Valor inicial vs valor apurado
- Variação em R$ e porcentagem
- Top 5 maiores perdas e ganhos por item

### Webhook
Ao concluir uma sessão, o sistema dispara automaticamente um `POST` para a URL configurada com payload JSON completo — para integração com ERPs, Slack, ou qualquer sistema externo.

---

## Stack Técnica

**Backend**
```
Python 3.12        FastAPI + Uvicorn/Gunicorn (ASGI)
SQLAlchemy 2.x     SQLite (dev) / PostgreSQL (produção)
Alembic            Migrations versionadas (0001 → 0005)
WebSocket nativo   Tempo real com heartbeat + backoff exponencial
Anthropic SDK      Claude Haiku — análise, chat, validação, alerta
ReportLab          Geração de PDF
pandas + openpyxl  Import/export de planilhas Excel
qrcode[pil]        Geração de QR Code PNG
slowapi            Rate limiting por token (não por IP)
gunicorn           Servidor WSGI/ASGI para produção
```

**Frontend**
```
HTML5 + Tailwind CDN   Sem build step — servido pelo FastAPI
Material Symbols       Ícones Google (Outlined, FILL 0/1)
Inter + JetBrains Mono Tipografia
jsQR                   Fallback de leitura QR Code via câmera
BarcodeDetector API    Scanner nativo no browser (EAN, Code128, etc.)
WebSocket nativo       Tempo real sem dependências externas
localStorage           Fila offline + persistência do operador
```

---

## Estrutura do Projeto

```
inventario-qr/
├── backend/
│   ├── app/
│   │   ├── models/           # Sessao, ItemBase, Contagem, HistoricoContagem
│   │   ├── repositories/     # sessao_repo, item_repo
│   │   ├── routes/           # sessoes, contagens, exports, agentes, ws
│   │   ├── services/         # pdf_service, excel_service, relatorio_final_service
│   │   ├── agents/           # AnaliseAgent, ChatAgent, ValidationAgent, AlertaAgent
│   │   ├── websockets/       # ConnectionManager (broadcast por sessão)
│   │   ├── database.py       # Engine + SQLite → PostgreSQL automático
│   │   └── main.py           # FastAPI app + CORS + health check
│   ├── alembic/              # Migrations 0001 → 0005
│   ├── static/
│   │   ├── index.html        # Dashboard admin
│   │   ├── sessao.html       # Detalhe da sessão
│   │   ├── mobile.html       # Scanner mobile
│   │   ├── css/app.css       # Design system compartilhado
│   │   └── js/               # api.js + ws.js
│   ├── tests/                # 396 testes (pytest + SQLite in-memory)
│   ├── requirements.txt
│   ├── .env.example
│   ├── Dockerfile            # Multi-stage, usuário não-root
│   ├── entrypoint.sh         # Aguarda DB + alembic upgrade head + gunicorn
│   └── railway.toml          # Deploy Railway (Dockerfile builder)
├── docker-compose.yml        # Dev local com hot-reload
├── docker-compose.prod.yml   # Produção com PostgreSQL
├── render.yaml               # Blueprint Render (alternativo ao Railway)
└── REGRAS_NEGOCIO.md         # 39 RN + 60 RF + 20 RNF
```

---

## Como rodar

### Pré-requisitos
- Python 3.11+

### 1. Clonar e instalar

```bash
git clone https://github.com/Ryan-42/inventario-qr.git
cd inventario-qr/backend

python -m venv venv

# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configurar (opcional)

```bash
# Windows:
copy .env.example .env
# Linux/Mac:
cp .env.example .env
# Edite .env para usar PostgreSQL ou Claude AI
```

### 3. Rodar

```bash
uvicorn app.main:app --reload --port 8000
```

Acesse: **http://localhost:8000**

Para liberar acesso a celulares na mesma rede Wi-Fi:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Docker (dev)

```bash
# Na raiz do projeto:
docker compose up --build
```

### 5. Testes

```bash
cd backend
pytest tests/ -q
# 396 passed, 1 skipped
```

### 6. Fluxo de uso

1. Acesse `http://localhost:8000`
2. Crie uma nova sessão
3. Importe uma planilha `.xlsx` com colunas `codigo`, `produto`, `quantidade`
4. Clique **"QR Acesso"** → copie o link com token
5. Abra o link no celular → escaneie os produtos
6. Acompanhe ao vivo no painel admin

---

## Variáveis de Ambiente

| Variável | Obrigatória | Padrão | Descrição |
|----------|-------------|--------|-----------|
| `DATABASE_URL` | Não | SQLite local | URL do banco (`postgresql://...` em produção) |
| `ANTHROPIC_API_KEY` | Não | — | Chave Claude AI (sem ela, análise local) |
| `ALLOWED_ORIGINS` | Não | localhost | Origens CORS permitidas (separadas por vírgula) |
| `SECRET_KEY` | Não | gerado | Chave de assinatura de tokens |
| `GUNICORN_WORKERS` | Não | 2 | Workers em produção (recomendado: 2×núcleos+1) |

---

## Planilha de Importação

Formato `.xlsx` ou `.csv`. O sistema aceita 20+ nomes de coluna por campo:

| Campo | Nomes aceitos |
|-------|---------------|
| Código | `codigo`, `código`, `sku`, `ref`, `code`, `id` |
| Produto | `produto`, `descricao`, `nome`, `name`, `description` |
| Quantidade | `quantidade`, `qtd`, `qty`, `estoque`, `stock` |
| Local | `local`, `setor`, `prateleira`, `corredor`, `area` |
| Valor | `valor`, `valor em estoque`, `custo`, `vl_estoque` |

---

## Principais Endpoints

```
GET  /api/sessoes                             Lista sessões
POST /api/sessoes                             Cria sessão
DELETE /api/sessoes/{id}                      Remove sessão (token_admin)
GET  /api/sessoes/{id}/stats                  KPIs (total, conferidos, %)
GET  /api/sessoes/{id}/progresso              Rodada atual, itens faltando
POST /api/sessoes/{id}/contagens              Registra contagem
GET  /api/sessoes/{id}/token-acesso           Token mobile atual
POST /api/sessoes/{id}/gerar-token?rodada=N   Novo token (invalida anterior)
GET  /api/sessoes/{id}/qrcode-acesso          PNG do QR Code
GET  /api/sessoes/{id}/valor-estoque          Impacto financeiro
POST /api/sessoes/{id}/validar-planilha       Valida + preview (IA)
GET  /api/sessoes/{id}/exportar/relatorio-final-pdf
GET  /api/sessoes/{id}/exportar/relatorio-final-excel
ws://host/api/ws/sessao/{id}                 WebSocket tempo real
GET  /health                                  Health check
```

Documentação interativa: `http://localhost:8000/docs`

---

## WebSocket — Eventos em Tempo Real

```json
{ "tipo": "contagem_registrada", "codigo": "SKU-01", "divergencia": true, "para_ajuste": false, "rodada": 1 }
{ "tipo": "progresso_atualizado", "rodada_atual": 1, "faltando": 12, "total_rodada": 100 }
{ "tipo": "rodada_completa", "rodada_concluida": 1, "divergencias_pendentes": 4, "proxima_rodada_necessaria": true }
{ "tipo": "contagem_deletada", "codigo": "SKU-01" }
{ "tipo": "sessao_pausada" }
```

O cliente envia `{"tipo":"ping"}` a cada 25s para manter a conexão viva.  
Reconexão com backoff exponencial: 2s → 4s → 8s → 15s máx.

---

## Regras de Negócio

Documento completo em [`REGRAS_NEGOCIO.md`](./REGRAS_NEGOCIO.md) com 39 regras de negócio, 60 requisitos funcionais e 20 não funcionais.

**Fluxo resumido:**

```
Admin cria sessão → importa planilha → gera QR Code + token por rodada

Operadores abrem o link com token → scanner liberado
  → escaneiam produtos → informam quantidade
  → painel atualiza em tempo real (WebSocket)

Divergências vão para recontagem (R2 → R3)
  → mesma quantidade confirmada → Para Ajuste (sem nova rodada)
  → quantidade diferente → próxima rodada

Admin conclui sessão
  → PDF Final + Excel Final gerados automaticamente
  → webhook disparado para sistemas externos
  → exporta divergências para ajuste no ERP
```

---

## Deploy (Render) — Em produção

O projeto está no ar em **https://inventario-qr-api.onrender.com** via Render Blueprint.

O `render.yaml` na raiz do projeto configura tudo automaticamente: PostgreSQL + web service Docker.

**Para fazer o seu próprio deploy:**

1. Acesse [render.com](https://render.com) → **Blueprints** → **New Blueprint Instance**
2. Conecte o repo `inventario-qr` → branch `main`
3. Render lê o `render.yaml` e cria o banco e o serviço automaticamente
4. Preencha as variáveis solicitadas:

| Variável | Valor |
|----------|-------|
| `ALLOWED_ORIGINS` | `https://SEU-APP.onrender.com` |
| `ANTHROPIC_API_KEY` | `sk-ant-...` *(opcional)* |

5. Clique **Deploy Blueprint** — o `entrypoint.sh` aguarda o banco, roda `alembic upgrade head` e sobe o gunicorn

**Após o deploy, adicione via Environment:**

| Variável | Valor |
|----------|-------|
| `APP_ENV` | `production` |
| `ALLOWED_ORIGINS` | URL real gerada pelo Render |

> **Limitação free tier:** o serviço dorme após 15min de inatividade e acorda em ~30–50s na primeira requisição. Para uso contínuo, upgrade para o plano pago ($7/mês).  
> WebSocket (`wss://`) funciona nativamente no Render sem configuração extra.

---

## Roadmap

| Sprint | Status | Descrição |
|--------|--------|-----------|
| Sprint 1 | ✅ | Backend + Scanner + WebSocket base |
| Sprint 2 | ✅ | Design System + Modo Manual + Rodadas |
| Sprint 3 | ✅ | Token de Rodada + Para Ajuste + Relatórios Finais |
| Sprint 4 | ✅ | Grupos de Operadores + Supervisor + Token Admin + QA (70+ bugs) |
| Sprint 5 | ✅ | Deploy + Barcode Scanner + Webhook + Rate Limit + UI Polimento |
| Sprint 6 | 🔭 | Autenticação JWT + Operadores ao Vivo + Service Worker |
| Sprint 7 | 🔭 | Integração ERP + IA Avançada (predição, classificação) |
| Sprint 8 | 🔭 | Multi-tenant + PWA instalável + OCR etiquetas |

---

## Governança de dados e LGPD

O INVIQ pode opcionalmente enviar dados para APIs de IA externas (Anthropic/Groq) quando os agentes inteligentes estão habilitados. Esta seção documenta o que sai, para onde, quando e como desativar.

### O que é enviado

| Agente | Dados enviados | Destino |
|--------|---------------|---------|
| `AntiFraudeAgent` | Telemetria comportamental de contagem **anonimizada** (Operador 1, 2, …) | Anthropic ou Groq |
| `SopCoachAgent` | Mensagem de texto do operador + contexto operacional | Anthropic ou Groq |
| `PredictionAgent` | Estatísticas agregadas de contagem (sem dados pessoais) | Anthropic ou Groq |
| `PlanoAcaoAgent` | Divergências de estoque (códigos, quantidades) | Anthropic ou Groq |
| `SyncERPAgent` | Itens divergentes para ajuste (códigos, quantidades) | Anthropic ou Groq |
| `ChatAgent` | Histórico de mensagens + status da sessão | Anthropic ou Groq |

**Nomes de operadores nunca são enviados diretamente à IA** — o `AntiFraudeAgent` anonimiza para "Operador 1, 2, …" antes de montar o prompt.

### Quando acontece

Apenas quando `AI_ENABLED=true` **E** uma chave de API está configurada (`ANTHROPIC_API_KEY` ou `GROQ_API_KEY`). Por padrão, `AI_ENABLED=false` — nenhuma chamada a APIs externas é feita.

### Como desativar

```bash
# .env
AI_ENABLED=false   # padrão — garante modo local mesmo com chave configurada
```

Com `AI_ENABLED=false`, todos os agentes operam em modo determinístico local sem enviar nenhum dado a APIs externas.

---

## Licença

MIT

---

<p align="center">Feito por <a href="https://github.com/Ryan-42">Ryan Monteiro</a></p>
