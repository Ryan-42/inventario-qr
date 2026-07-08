# INVIQ — Inventário Físico por QR Code

[![CI](https://github.com/Ryan-42/inventario-qr/actions/workflows/ci.yml/badge.svg)](https://github.com/Ryan-42/inventario-qr/actions/workflows/ci.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-336791?style=flat-square&logo=postgresql&logoColor=white)]()
[![WebSocket](https://img.shields.io/badge/WebSocket-Tempo%20Real-10eb8a?style=flat-square)]()
[![Tests](https://img.shields.io/badge/Testes-436%20passando-4CAF50?style=flat-square)]()
[![Deploy](https://img.shields.io/badge/Deploy-Render-46E3B7?style=flat-square&logo=render&logoColor=white)](https://inventario-qr-api.onrender.com)
[![IA](https://img.shields.io/badge/IA%20opcional-Claude%20%2F%20Groq-D97706?style=flat-square)](https://anthropic.com)

> Sistema de contagem de inventário físico com scanner mobile, **contagem cega garantida no servidor**, tempo real via WebSocket, recontagem automática de divergências, aprovação em 4 olhos e relatórios financeiros — sem app para instalar e sem login para o operador.

O INVIQ resolve um problema real: inventários físicos são lentos, sujeitos a erros humanos e não oferecem visibilidade ao gestor durante a contagem.

O celular do próprio operador vira o coletor de dados: ele escaneia um QR Code, digita o token e já está contando — sem cadastro, sem app, sem treinamento. O operador **nunca vê a quantidade esperada** (contagem cega imposta pela API, não pela tela), o que elimina a contagem "viciada". O gestor acompanha tudo ao vivo no painel, e as divergências entram automaticamente em rodadas de recontagem.

**Em produção:** https://inventario-qr-api.onrender.com

---

## Telas

| Tela | Quem usa | Autenticação | URL |
|------|----------|--------------|-----|
| **Login** | Administrador | e-mail + senha | `/login` |
| **Sessões** | Administrador | JWT | `/` |
| **Dashboard gerencial** | Administrador | JWT | `/dashboard` |
| **Sessão (painel ao vivo)** | Administrador | JWT | `/sessao/{id}` |
| **Scanner Mobile** | Operador | token da sessão/grupo (sem login) | `/mobile/{id}?token=XXXX` |
| **Supervisor** | Supervisor | token de supervisor (sem login) | `/supervisor/{id}?token=XXXX` |

---

## Funcionalidades

### Scanner Mobile (PWA)
- **QR Code e código de barras via câmera** — EAN-13/8, Code 128/39, UPC-A/E, ITF, PDF417 e Aztec via BarcodeDetector API, com fallback jsQR
- **Sem instalar nada** — abre no navegador; instalável como PWA
- **Modo manual** com busca por código, produto ou local físico
- **Funciona offline** — contagens salvas localmente e sincronizadas ao reconectar (rejeições permanentes são descartadas com aviso, sem travar a fila)
- **Token por rodada** — o admin gera um novo QR para a 2ª contagem; o token antigo expira e o operador é guiado a escanear o novo
- Vibração ao detectar · proteção contra duplo-scan · lista de pendentes filtrada por grupo

### Contagem cega de verdade
A API **não envia** `quantidade_base` nem contagem anterior para operadores — apenas admins autenticados com JWT recebem esses campos. Não é um "esconder na tela": é impossível para o operador obter o número esperado.

### Sistema de Rodadas
- **Rodada 1** — todos os itens contados ao menos uma vez
- **Rodadas seguintes** — recontagem automática apenas dos itens divergentes
- **Para Ajuste** — mesma quantidade divergente confirmada duas vezes vai direto para a fila de ajuste (com teto de rodadas como garantia de terminação)

### Painel Admin em Tempo Real
- KPIs, live feed e barra de progresso atualizados via WebSocket (token obrigatório; conexões inválidas fecham com código `4401`)
- Banner automático ao concluir rodada com botão "Gerar QR Próxima Rodada"
- Filtros: OK / Divergente / Para Ajuste / Pendente
- Reabrir sessão concluída (bloqueado se já aprovada em 4 olhos), cancelar e excluir com confirmação

### Grupos de Operadores e Supervisor
- Divida a contagem por corredor/setor: cada grupo tem token + QR próprios e só enxerga os itens do seu filtro (prefixo ou lista de códigos)
- UI completa no painel: criar, listar, QR, regenerar token e excluir grupos
- **Supervisor** — acesso somente-leitura pós-R1 aos itens divergentes agrupados por localização

### Aprovação em 4 olhos
Sessão concluída pode exigir segunda aprovação por outra pessoa, com token próprio (protegido por rate-limit e bloqueio de brute-force). Depois de aprovada, a sessão é **imutável** e libera o envio ao ERP.

### Agentes de IA (opcionais, LGPD-first)
11 agentes carregados dinamicamente de `backend/.agents/`: análise de sessão, validação de planilha, alertas em tempo real, anti-fraude, plano de ação, predição, relatórios, SOP coach, ajuste, sync ERP e o provider Anthropic/Groq.
**Por padrão `AI_ENABLED=false`** — nenhum dado sai do servidor sem opt-in explícito; todos os agentes têm fallback local determinístico.

### Exportações

| Tipo | Formato | Descrição |
|------|---------|-----------|
| Completo | `.xlsx` | Todos os itens com status, operadores e rodadas |
| Divergências | `.xlsx` | Só itens divergentes (para ajuste no ERP) |
| PDF Relatório | `.pdf` | Relatório executivo colorido por status |
| Etiquetas QR | `.pdf` | 14 etiquetas por folha A4 para impressão |
| **PDF Final** | `.pdf` | KPIs + impacto financeiro + análise IA + tabela completa |
| **Excel Final** | `.xlsx` | Abas: Resumo, Itens, Divergências com Impacto R$, Recomendações, Métricas |

Exports autenticados com JWT no header — nenhum token aparece em URL ou logs.

### Impacto Financeiro
Com a coluna `valor_estoque` na planilha, o sistema calcula valor inicial vs apurado, variação em R$ e %, e top 5 perdas/ganhos por item.

### Integração TOTVS + Webhook + Agendamentos
- Envio de ajustes de estoque ao **TOTVS Protheus** (com modo dry-run para validar o payload antes de ativar) — bloqueado enquanto a sessão aguarda a segunda aprovação
- **Webhook** `POST` disparado ao concluir a sessão (com proteção SSRF) — integre com ERP, Slack ou qualquer sistema
- **Agendamentos** — sessões recorrentes (diária/semanal/mensal) criadas automaticamente por um scheduler com advisory lock do PostgreSQL (seguro com múltiplos workers)
- **Multi-filial** — sessões vinculadas a filiais/unidades

---

## Segurança

- **Dois sistemas de autenticação independentes:** JWT para admins (com blacklist de logout) e tokens por sessão/grupo/supervisor para operadores — comparados com `hmac.compare_digest` e guardas explícitas contra token vazio
- Contagem cega e tokens de acesso **impostos pela API**, não pela interface
- Proteção brute-force por IP em todos os endpoints com token + rate limiting (slowapi)
- `X-Forwarded-For` só é confiado com `TRUST_PROXY=true`
- Headers de segurança (CSP, HSTS em produção, X-Frame-Options DENY), CORS restrito, formula-injection neutralizada no import/export de planilhas
- Docs interativas (`/docs`) desativadas em produção

---

## Stack Técnica

**Backend**
```
Python 3.12        FastAPI + Uvicorn (dev) / Gunicorn (produção)
SQLAlchemy 2.x     SQLite (dev/testes) / PostgreSQL Neon (produção)
Alembic            Migrations versionadas (0001 → 0008, head único)
WebSocket nativo   Tempo real com heartbeat + backoff exponencial
Anthropic/Groq SDK Agentes de IA (opcionais, desligados por padrão)
ReportLab          Geração de PDF
pandas + openpyxl  Import/export de planilhas Excel e CSV
qrcode[pil]        Geração de QR Code PNG
slowapi            Rate limiting por IP
```

**Frontend**
```
HTML5 + Tailwind CDN   Sem build step — servido pelo próprio FastAPI
Vanilla JS (ES6)       api.js / auth.js / ws.js — sem framework
BarcodeDetector + jsQR Scanner de códigos via câmera
Service Worker (PWA)   Cache offline + fila de sincronização
sessionStorage JWT     Sessão do admin; operador não tem login
```

---

## Estrutura do Projeto

```
inventario-qr/
├── backend/
│   ├── app/
│   │   ├── models/           # Sessao, ItemBase, Contagem, HistoricoContagem, Admin, GrupoOperador…
│   │   ├── repositories/     # sessao_repo, item_repo, grupo_repo
│   │   ├── routes/           # sessoes, itens, contagens, grupos, exports, auth, ws, dashboard…
│   │   ├── services/         # scheduler, excel/pdf/relatorio_final, email, token_blacklist
│   │   ├── agents/           # loader dinâmico → backend/.agents/{nome}/{nome}.py
│   │   ├── websockets/       # ConnectionManager (broadcast por sessão)
│   │   ├── auth.py           # JWT + brute-force + tokens por sessão
│   │   └── main.py           # FastAPI app + CSP/CORS + health + páginas estáticas
│   ├── .agents/              # 11 agentes de IA (dentro de backend/ por causa do Docker context)
│   ├── alembic/              # Migrations 0001 → 0008
│   ├── static/               # index, login, dashboard, sessao, mobile, supervisor + js/ + sw.js
│   ├── tests/                # 436 testes (pytest + SQLite in-memory)
│   ├── Dockerfile            # Multi-stage, usuário não-root
│   └── entrypoint.sh         # Aguarda DB → detect_schema_state → alembic upgrade → gunicorn
├── .github/workflows/ci.yml  # pytest + validações de deploy a cada push/PR
├── docker-compose.yml        # Dev local com hot-reload
├── docker-compose.prod.yml   # Produção-like com PostgreSQL
├── render.yaml               # Blueprint Render (web service; banco é Neon externo)
└── REGRAS_NEGOCIO.md         # 39 RN + 60 RF + 20 RNF
```

---

## Como rodar

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

### 2. Criar o primeiro admin

```bash
python criar_admin.py                                        # interativo
# ou, sem prompts:
ADMIN_EMAIL=voce@empresa.com ADMIN_SENHA='Senha123!' python criar_admin.py
```

### 3. Rodar

```bash
uvicorn app.main:app --reload --port 8000
```

Acesse **http://localhost:8000** e faça login. Para liberar acesso a celulares na mesma rede Wi-Fi:

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
# 436 passed, 1 skipped
```

### 6. Fluxo de uso

1. Faça login e crie uma nova sessão
2. Importe a planilha (`.xlsx` ou `.csv`) com `codigo`, `produto`, `quantidade`
3. Clique **"QR Acesso"** → projete o QR ou compartilhe o link
4. Operadores escaneiam com o celular e começam a contar (sem login)
5. Acompanhe ao vivo; divergências entram em recontagem automática
6. Conclua → segunda aprovação (opcional) → exporte relatórios / envie ao TOTVS

---

## Variáveis de Ambiente

| Variável | Obrigatória | Padrão | Descrição |
|----------|-------------|--------|-----------|
| `DATABASE_URL` | Não | SQLite local | `postgresql://...` em produção (conexão **direta**, sem pooler — o scheduler usa advisory lock) |
| `SECRET_KEY` | **Sim** em prod | — | Assinatura JWT — gere com `openssl rand -hex 32` |
| `APP_ENV` | Não | — | `production` desativa `create_tables()` (schema só via Alembic) e exige Postgres |
| `ALLOWED_ORIGINS` | Não | localhost | Origens CORS permitidas (separadas por vírgula) |
| `TRUST_PROXY` | Não | `false` | `true` apenas atrás de proxy confiável (Render) |
| `AI_ENABLED` | Não | `false` | Habilita chamadas a APIs de IA externas (LGPD) |
| `ANTHROPIC_API_KEY` | Não | — | Chave Claude (Anthropic) |
| `GROQ_API_KEY` | Não | — | Chave Groq (alternativa gratuita) |
| `GUNICORN_WORKERS` | Não | 2 | Workers em produção |

---

## Planilha de Importação

Formato `.xlsx`, `.xls` ou `.csv` — o parser aceita **separador `,` ou `;`** (padrão do Excel PT-BR), UTF-8 com ou sem BOM e latin-1, e preserva códigos numéricos corretamente. Mais de 20 nomes de coluna são reconhecidos por campo:

| Campo | Obrigatório | Nomes aceitos (exemplos) |
|-------|-------------|--------------------------|
| Código | Sim | `codigo`, `código`, `sku`, `ref`, `code`, `id` |
| Produto | Sim | `produto`, `descricao`, `nome`, `name`, `description` |
| Quantidade | Sim | `quantidade`, `qtd`, `qty`, `estoque`, `stock`, `saldo` |
| Local | Não | `local`, `setor`, `prateleira`, `corredor`, `endereco` |
| Valor | Não | `valor`, `valor em estoque`, `custo`, `vl_estoque` |

Use `POST /api/sessoes/{id}/validar-planilha` para validar e ver um preview antes de importar.

---

## Principais Endpoints

```
POST /auth/login                              Login do admin (JWT)
POST /auth/logout                             Revoga o JWT (blacklist por jti)
POST /auth/alterar-senha                      Troca a própria senha

GET  /api/sessoes                             Lista sessões                      [JWT]
POST /api/sessoes                             Cria sessão                        [JWT]
PATCH /api/sessoes/{id}/concluir|cancelar|reabrir                                [JWT]
GET  /api/sessoes/{id}/progresso              Rodada atual, itens faltando       [público]
GET  /api/sessoes/{id}/buscar/{codigo}        Busca item (cega p/ operador)      [token|JWT]
POST /api/sessoes/{id}/contagens?token=X      Registra contagem                  [token|JWT]
GET  /api/sessoes/{id}/itens-operador?token=X Lista p/ operador (sem quantidades)[token|JWT]
GET  /api/sessoes/{id}/token-acesso           Token mobile atual                 [JWT]
POST /api/sessoes/{id}/gerar-token?rodada=N   Novo token (invalida anterior)     [JWT]
GET  /api/sessoes/{id}/qrcode-acesso          PNG do QR Code                     [JWT]
GET  /api/sessoes/{id}/grupos                 Grupos de operadores               [JWT]
POST /api/sessoes/{id}/segunda-aprovacao/aprovar|rejeitar                        [token 2º aprovador]
GET  /api/sessoes/{id}/valor-estoque          Impacto financeiro                 [JWT]
GET  /api/sessoes/{id}/auditoria              Trilha completa filtrável          [JWT]
POST /api/sessoes/{id}/exportar/...           Excel/PDF/etiquetas                [JWT]
POST /api/integracoes/totvs/sessao/{id}/enviar-ajuste                            [JWT]
GET  /api/dashboard/resumo|tendencias|operadores                                 [JWT]
ws://host/api/ws/sessao/{id}?token=X          WebSocket tempo real (4401 sem token)
GET  /health                                  Health check (valida o banco)
```

Documentação interativa em dev: `http://localhost:8000/docs`

---

## WebSocket — Eventos em Tempo Real

```json
{ "tipo": "contagem_registrada", "codigo": "SKU-01", "divergencia": true, "para_ajuste": false, "rodada": 1 }
{ "tipo": "progresso_atualizado", "rodada_atual": 1, "faltando": 12, "total_rodada": 100 }
{ "tipo": "rodada_completa", "rodada_concluida": 1, "divergencias_pendentes": 4, "proxima_rodada_necessaria": true }
{ "tipo": "contagem_deletada", "codigo": "SKU-01" }
{ "tipo": "sessao_status_alterado", "status": "concluida" }
```

Token obrigatório na query string (mesmos tokens do `/contagens` ou JWT admin) — conexões inválidas fecham com código `4401`. O cliente envia `{"tipo":"ping"}` a cada 25s; reconexão com backoff exponencial 2s → 15s.

---

## Regras de Negócio

Documento completo em [`REGRAS_NEGOCIO.md`](./REGRAS_NEGOCIO.md) com 39 regras de negócio, 60 requisitos funcionais e 20 não funcionais.

**Fluxo resumido:**

```
Admin faz login → cria sessão → importa planilha → gera QR Code + token

Operadores abrem o link/QR (sem login) → scanner liberado
  → escaneiam produtos → informam quantidade (sem ver a esperada)
  → painel atualiza em tempo real (WebSocket)

Divergências vão para recontagem automática
  → mesma quantidade confirmada → Para Ajuste (sem nova rodada)
  → quantidade diferente → nova rodada (com teto de segurança)

Admin conclui a sessão
  → segunda aprovação em 4 olhos (opcional; aprovada = imutável)
  → PDF/Excel finais + webhook + envio de ajustes ao TOTVS
```

---

## CI e Deploy

### CI (GitHub Actions)
Cada push/PR roda a suíte completa (436 testes em SQLite in-memory), valida que o Alembic tem exatamente 1 head e que `entrypoint.sh` está em LF (CRLF quebra o boot do container). O deploy no Render é automático a partir do `main` — **o CI é o único gate antes de produção**.

### Produção (Render + Neon)
No ar em **https://inventario-qr-api.onrender.com**: web service Docker no Render (`render.yaml`, contexto `./backend`) + PostgreSQL gerenciado no **Neon** (o free tier do Postgres do Render expira em ~90 dias; o do Neon não).

**Para fazer o seu próprio deploy:**

1. Crie um banco no [neon.tech](https://neon.tech) e copie a **connection string direta** (não pooled — o scheduler usa `pg_try_advisory_lock`)
2. No [render.com](https://render.com): **Blueprints** → **New Blueprint Instance** → conecte o repo (branch `main`)
3. Preencha as variáveis: `DATABASE_URL` (Neon), `SECRET_KEY`, `APP_ENV=production`, `ALLOWED_ORIGINS=https://SEU-APP.onrender.com`, `TRUST_PROXY=true`
4. Deploy — o `entrypoint.sh` aguarda o banco, detecta/carimba o estado do schema, roda `alembic upgrade head` e sobe o gunicorn (cada etapa falha com diagnóstico claro em vez de um 502 mudo)
5. Crie o primeiro admin: **Shell** do serviço → `python criar_admin.py`

> **Free tier:** o serviço dorme após 15min de inatividade e acorda em ~30–50s. WebSocket (`wss://`) funciona nativamente.

---

## Roadmap

| Sprint | Status | Descrição |
|--------|--------|-----------|
| 1–3 | ✅ | Backend + Scanner + WebSocket + Rodadas + Para Ajuste + Relatórios |
| 4 | ✅ | Grupos de Operadores + Supervisor + QA (70+ bugs) |
| 5 | ✅ | Deploy + Barcode + Webhook + Rate Limit |
| 6 | ✅ | Auth JWT + PWA offline + agentes IA + auditoria de segurança |
| 7 | ✅ | Hardening (contagem cega na API, 4 olhos, brute-force) + UI de grupos + reabrir sessão + CI |
| 8 | 🔭 | UI de agendamentos/filiais + tela "Para Ajuste" + fuso horário nos agendamentos |
| 9 | 🔭 | Multi-tenant + predição IA + OCR de etiquetas |

---

## Governança de dados e LGPD

O INVIQ pode opcionalmente enviar dados a APIs de IA externas (Anthropic/Groq). **Por padrão não envia nada**: é preciso `AI_ENABLED=true` **e** uma chave configurada.

| Agente | Dados enviados | Destino |
|--------|---------------|---------|
| `AntiFraudeAgent` | Telemetria de contagem **anonimizada** ("Operador 1, 2…") | Anthropic ou Groq |
| `SopCoachAgent` | Mensagem do operador + contexto operacional | Anthropic ou Groq |
| `PreditorAgent` | Estatísticas agregadas (sem dados pessoais) | Anthropic ou Groq |
| `PlanoAcaoAgent` / `SyncERPAgent` | Divergências (códigos e quantidades) | Anthropic ou Groq |

Nomes de operadores nunca são enviados diretamente à IA. Com `AI_ENABLED=false` (padrão), todos os agentes operam em modo local determinístico.

---

## Licença

MIT

---

<p align="center">Feito por <a href="https://github.com/Ryan-42">Ryan Monteiro</a></p>
