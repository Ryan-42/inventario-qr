# INVIQ — Inventário Físico por QR Code

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![SQLite/PostgreSQL](https://img.shields.io/badge/SQLite%2FPostgreSQL-003B57?style=flat-square&logo=sqlite&logoColor=white)]()
[![Claude AI](https://img.shields.io/badge/Claude%20AI-Anthropic-D97706?style=flat-square)](https://anthropic.com)
[![WebSocket](https://img.shields.io/badge/WebSocket-Tempo%20Real-10eb8a?style=flat-square)]()
[![Mobile](https://img.shields.io/badge/Mobile-Scanner%20QR-7AD0FF?style=flat-square)]()

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
- **Modo manual** com busca fuzzy por código, produto ou local físico
- **Funciona offline** — contagens salvas localmente e sincronizadas ao reconectar
- **Token de acesso por rodada** — QR Code gerado pelo admin controla qual rodada o operador pode contar
- Vibração ao detectar QR · Proteção contra duplo-scan · Long-press para incremento rápido

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

### Análise por IA (Claude)
- **Análise de sessão** — padrões, itens críticos, recomendações, relatório executivo
- **Chat IA** — perguntas em linguagem natural sobre a sessão
- **Validação de planilha** — detecta problemas antes de importar
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

### Impacto Financeiro
Quando a planilha tem a coluna `valor em estoque`, o sistema calcula automaticamente:
- Valor inicial vs valor apurado
- Variação em R$ e porcentagem
- Top 5 maiores perdas e ganhos por item

---

## Stack Técnica

**Backend**
```
Python 3.11+      FastAPI + Uvicorn (ASGI)
SQLAlchemy 2.x    SQLite (dev) / PostgreSQL (produção)
WebSocket nativo  Tempo real com heartbeat + backoff exponencial
Anthropic SDK     Claude Haiku — análise, chat, validação
ReportLab         Geração de PDF
pandas + openpyxl Import/export de planilhas Excel
qrcode[pil]       Geração de QR Code PNG
slowapi           Rate limiting nos endpoints de IA
```

**Frontend**
```
HTML5 + Tailwind CDN   Sem build step — servido pelo FastAPI
Material Symbols       Ícones Google
Inter + JetBrains Mono Tipografia
jsQR                   Leitura de QR Code via câmera
WebSocket nativo        Tempo real sem dependências externas
localStorage           Fila offline + persistência do operador
```

---

## Estrutura do Projeto

```
inventario-qr/
├── backend/
│   ├── app/
│   │   ├── models/           # Sessao, ItemBase, Contagem, Historico
│   │   ├── repositories/     # sessao_repo, item_repo
│   │   ├── routes/           # sessoes, contagens, exports, agentes, ws
│   │   ├── services/         # pdf_service, excel_service, relatorio_final_service
│   │   ├── agents/           # AnaliseAgent, ChatAgent, ValidationAgent, AlertaAgent
│   │   ├── websockets/       # ConnectionManager (broadcast por sessão)
│   │   ├── database.py       # Engine + migração automática SQLite
│   │   └── main.py           # FastAPI app
│   ├── static/
│   │   ├── index.html        # Dashboard admin
│   │   ├── sessao.html       # Detalhe da sessão
│   │   ├── mobile.html       # Scanner mobile
│   │   ├── css/app.css       # Utilitários compartilhados
│   │   └── js/               # api.js + ws.js
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
└── REGRAS_NEGOCIO.md          # 39 RN + 60 RF + 20 RNF + roadmap
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
# Edite o .env para usar PostgreSQL ou Claude AI
```

### 3. Rodar

```bash
uvicorn app.main:app --reload --port 8000
```

Acesse: **http://localhost:8000**

Para liberar acesso na rede local (celulares na mesma rede):

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Fluxo de teste

1. Acesse `http://localhost:8000`
2. Crie uma nova sessão
3. Importe uma planilha `.xlsx` com colunas `codigo`, `produto`, `quantidade`
4. Clique **"QR Acesso"** → copie o link com token
5. Abra o link no celular → escaneie os produtos
6. Acompanhe ao vivo no painel admin

---

## Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `DATABASE_URL` | Não | URL do banco (default: SQLite local) |
| `ANTHROPIC_API_KEY` | Não | Chave Claude AI (sem ela, análise local) |
| `ALLOWED_ORIGINS` | Não | Origens CORS permitidas |

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
GET  /api/sessoes                            Lista sessões
POST /api/sessoes                            Cria sessão
GET  /api/sessoes/{id}/stats                 KPIs (total, conferidos, %)
GET  /api/sessoes/{id}/progresso             Rodada atual, itens faltando
POST /api/sessoes/{id}/contagens             Registra contagem
GET  /api/sessoes/{id}/token-acesso          Token mobile atual
POST /api/sessoes/{id}/gerar-token?rodada=N  Novo token (invalida anterior)
GET  /api/sessoes/{id}/qrcode-acesso         PNG do QR Code
GET  /api/sessoes/{id}/valor-estoque         Impacto financeiro
GET  /api/sessoes/{id}/exportar/relatorio-final-pdf
GET  /api/sessoes/{id}/exportar/relatorio-final-excel
ws://host/api/ws/sessao/{id}                WebSocket tempo real
```

Documentação interativa: `http://localhost:8000/docs`

---

## WebSocket — Eventos em Tempo Real

```json
{ "tipo": "contagem_registrada", "codigo": "SKU-01", "divergencia": true, "para_ajuste": false, "rodada": 1 }
{ "tipo": "progresso_atualizado", "rodada_atual": 1, "faltando": 12, "total_rodada": 100 }
{ "tipo": "rodada_completa", "rodada_concluida": 1, "divergencias_pendentes": 4, "proxima_rodada_necessaria": true }
```

O cliente envia `{"tipo":"ping"}` a cada 25s para manter a conexão viva.

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
  → exporta divergências para ajuste no ERP
```

---

## Deploy

Pronto para **Railway** com `backend/railway.toml` já configurado:

```bash
# Variáveis necessárias no Railway:
DATABASE_URL       # provisionar PostgreSQL plugin (auto-injetado)
ANTHROPIC_API_KEY  # opcional
ALLOWED_ORIGINS    # https://seu-app.railway.app
```

---

## Roadmap

| Sprint | Status | Descrição |
|--------|--------|-----------|
| Sprint 1 | ✅ | Backend + Scanner + WebSocket base |
| Sprint 2 | ✅ | Design Stitch + Modo Manual + Rodadas |
| Sprint 3 | ✅ | Token de Rodada + Para Ajuste + Relatórios Finais |
| Sprint 4 | 🔭 | Autenticação JWT + Dashboard multi-sessão |
| Sprint 5 | 🔭 | Integração ERP + Notificações Push |
| Sprint 6 | 🔭 | Contagem por foto (Computer Vision) |

---

## Licença

MIT

---

<p align="center">Feito por <a href="https://github.com/Ryan-42">Ryan Monteiro</a></p>
