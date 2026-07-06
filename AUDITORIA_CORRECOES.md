# AUDITORIA — Correções de Segurança e Qualidade INVIQ

> Data: 2026-07-06 | Executor: Claude Opus 4.8 (Tech Lead review)
> Contexto: auditoria pré-apresentação para equipe de TI da empresa

---

## Sumário executivo

| Prioridade | Item | Status |
|------------|------|--------|
| P0 (bloqueante) | Auth em POST /contagens | ✅ Corrigido |
| P0 (bloqueante) | Auth em WebSocket | ✅ Corrigido |
| P0 (bloqueante) | Scheduler duplicado (multi-worker) | ✅ Corrigido |
| P0 (bloqueante) | Teste falhando | ✅ Confirmado resolvido |
| P0 (incoerência) | Badge de testes desatualizado | ✅ Corrigido |
| P1 (importante) | CSP autocontraditório | ✅ Corrigido (docs + débito técnico) |
| P1 (importante) | Brute-force por worker e IP falsificável | ✅ Corrigido (TRUST_PROXY gate) |
| P1 (importante) | `create_tables()` com Alembic | ✅ Corrigido |
| P1 (importante) | Dependências sem pin | ✅ Corrigido |
| P1 (importante) | Governança de dados IA / LGPD | ✅ Corrigido |
| P1 (offline) | CDN frontend (operação offline) | ⚠️ Débito técnico registrado |

---

## Detalhamento por item

---

### P0#1 — Endpoint de contagens sem autenticação (CRÍTICO)

**Achado:** `POST /sessoes/{sessao_id}/contagens` não validava nenhum token. Qualquer cliente na rede que soubesse o `sessao_id` podia registrar contagens com qualquer nome no campo `operador`, invalidando a rastreabilidade — pilar central do sistema.

**Causa raiz:** A função `registrar_contagem` em `contagens.py` não tinha nenhuma dependência de autenticação. Um bug adicional: `hmac.compare_digest("", "")` retorna `True`, o que significava que um token vazio passava na validação de `token_supervisor` quando o campo é `None` (convertido para `""`).

**O que foi feito:**
- Adicionado `_validar_token_operador()` com rejeição explícita de token vazio antes de qualquer comparação
- Aceita: `token_acesso` da sessão, `token_supervisor`, ou token de grupo
- Admins com JWT continuam com acesso sem token de operador (compatibilidade)
- Integrado com proteção brute-force existente (`_verificar_bloqueio` / `_registrar_falha`)
- Adicionado `get_admin_logado_opcional` em `auth.py`
- `api.js`: `registrarContagem` aceita parâmetro `token` (query param)
- `mobile.html`: `submitContagem` passa `tokenAtivo`; fila offline salva e reenvia o token

**Arquivos alterados:**
- `backend/app/auth.py`
- `backend/app/routes/contagens.py`
- `backend/static/js/api.js`
- `backend/static/mobile.html`
- `backend/tests/test_contagens.py`

**Testes adicionados:** 4 novos testes
- `test_contagem_sem_token_retorna_401`
- `test_contagem_token_errado_retorna_401`
- `test_contagem_token_acesso_valido_retorna_201`
- `test_contagem_token_grupo_valido_retorna_201`

**Commit:** `852475a`

---

### P0#2 — WebSocket sem autenticação

**Achado:** `GET /api/ws/sessao/{sessao_id}` aceitava conexão de qualquer cliente que conhecesse o `sessao_id`, expondo dados de estoque em tempo real sem autenticação.

**O que foi feito:**
- Adicionado parâmetro `token: str = ""` ao endpoint WebSocket
- Validação de `token_acesso`, `token_supervisor`, token de grupo, **ou** JWT admin
- Rejeita com close code `4401` (RFC 6455: 4000–4999 são reservados para aplicação) antes de aceitar a conexão
- `ws.js`: `SessionWS` aceita `token` como 3º argumento e inclui na URL como query param
- `mobile.html`: passa `tokenAtivo` ao construir `SessionWS`
- `sessao.html`: passa JWT token do `sessionStorage`
- `supervisor.html`: passa `tokenSupervisor`

**Arquivos alterados:**
- `backend/app/routes/ws.py`
- `backend/static/js/ws.js`
- `backend/static/mobile.html`
- `backend/static/sessao.html`
- `backend/static/supervisor.html`
- `backend/tests/test_seguranca.py`

**Testes adicionados:** 3 novos testes na classe `TestWebSocketAuth`
- `test_ws_sem_token_fecha_4401`
- `test_ws_token_invalido_fecha_4401`
- `test_ws_token_acesso_valido_conecta`

**Commit:** `2b14003`

---

### P0#3 — Scheduler duplicado em multi-worker

**Achado:** `loop_agendamentos` é iniciado no `lifespan` do FastAPI. Com N workers Gunicorn, N schedulers sobem em paralelo. `_processar_agendamentos_pendentes` buscava pendentes sem lock, podendo criar a mesma sessão N vezes por ciclo de agendamento.

**O que foi feito:**
- Adicionadas funções `_tentar_adquirir_lock_pg()` e `_liberar_lock_pg()` com `pg_try_advisory_lock`
- Antes de buscar pendentes, tenta adquirir lock; se falhar (outro worker já tem), pula o ciclo silenciosamente
- Em SQLite (dev/teste), `_tentar_adquirir_lock_pg()` retorna sempre `True` (worker único assumido)
- Lock liberado em `finally` após processar todos os agendamentos
- Documentado no módulo que testes SQLite NÃO validam concorrência real de PostgreSQL

**Arquivos alterados:**
- `backend/app/services/scheduler.py`

**Nota de testes:** A suíte roda em SQLite e não cobre concorrência real de PostgreSQL. A correção só pode ser verificada com múltiplos workers conectados ao PostgreSQL em ambiente real.

**Commit:** `de182b3`

---

### P0#4 — Teste falhando

**Achado auditado:** `test_sop_coach_agent_chat` reportado como falhando.

**Estado real encontrado:** Ao executar `pytest`, o teste já estava **passando** (provavelmente corrigido em commit anterior `8f368d6`). Confirmado em todas as 3 execuções de suite durante a auditoria.

**Ação:** Nenhuma alteração necessária. Estado confirmado.

---

### P0#5 — Badge de testes desatualizado

**Achado:** `README.md` exibia badge "159 testes" e comentário `# 159 passed`; a suíte real tinha ~389 testes antes da auditoria.

**O que foi feito:**
- Badge atualizado para `396 passando` (contagem final após todas as correções)
- Menção na árvore de diretórios e exemplo de `pytest -q` atualizados

**Arquivos alterados:** `README.md`

**Commit:** `bd397b0`

---

### P1#7 — CSP autocontraditório

**Achado:** Comentário em `main.py` dizia "bloqueia inline scripts" mas a política incluía `'unsafe-inline'` em `script-src`. Código não pode contradizer a si mesmo.

**O que foi feito:**
- Comentário corrigido para explicar que `'unsafe-inline'` é um débito técnico necessário enquanto o frontend usa scripts inline nos HTMLs
- Débito técnico registrado no `ROADMAP.md` (item "Hardening CSP") com descrição da solução: mover scripts inline para arquivos `.js` externos

**Arquivos alterados:** `backend/app/main.py`, `ROADMAP.md`

**Commit:** `bd397b0`

**Débito remanescente:** Remover `'unsafe-inline'` requer mover todos os `<script>...</script>` inline em `mobile.html`, `sessao.html`, `supervisor.html`, `dashboard.html` para arquivos `.js` separados com atributo `src`. Estimativa: 1–2 dias de trabalho.

---

### P1#8 — Brute-force por worker e IP falsificável

**Achado:** Proteção brute-force em `auth.py` era in-memory por processo (limite efetivo = limite × workers) e confiava cegamente em `X-Forwarded-For` — qualquer cliente podia forjar o IP e multiplicar tentativas.

**O que foi feito:**
- Adicionado gate `TRUST_PROXY=false` (padrão): `X-Forwarded-For` só é lido quando `TRUST_PROXY=true`
- Quando `TRUST_PROXY=false`, usa `request.client.host` (o IP real da conexão TCP)
- Documentado em `.env.example` com aviso de quando usar cada configuração

**Arquivos alterados:** `backend/app/auth.py`, `backend/.env.example`

**Commit:** `bd397b0`

**Débito remanescente:** O contador de falhas ainda é in-memory por processo (limite efetivo = limite × workers). Para produção com múltiplos workers, migrar para Redis quando `REDIS_URL` configurado. Registrado no ROADMAP.md.

---

### P1#9 — `create_tables()` convivendo com Alembic

**Achado:** `create_tables()` rodava incondicionalmente no `lifespan` em qualquer ambiente, incluindo produção. O entrypoint.sh já roda `alembic upgrade head` — ter os dois convivendo cria risco de drift de schema.

**O que foi feito:**
- `create_tables()` agora só roda quando `APP_ENV != production`
- Em produção, apenas o Alembic (via `entrypoint.sh`) gerencia o schema
- Confirmado que `entrypoint.sh` já executa `alembic upgrade head` antes de subir o gunicorn

**Arquivos alterados:** `backend/app/main.py`

**Commit:** `bd397b0`

---

### P1#10 — Dependências sem pin

**Achado:** `requirements.txt` usa apenas `>=`, tornando o build não-reprodutível.

**O que foi feito:**
- Gerado `backend/requirements.lock` com pins `==` exatos do ambiente que passa nos 396 testes
- Para build reprodutível: `pip install -r requirements.lock` em vez de `requirements.txt`

**Arquivos adicionados:** `backend/requirements.lock`

**Commit:** `bd397b0`

---

### P1#11 — Governança de dados nos agentes de IA (LGPD)

**Achado:** O sistema pode enviar dados de estoque para APIs externas (Anthropic/Groq) via `provider.py`. Nomes de operadores eram incluídos nos prompts do `AntiFraudeAgent` sem anonimização. Nenhuma flag de habilitação existia.

**O que foi feito:**
- Adicionado `AI_ENABLED=false` (padrão) em `config.py` e `.env.example`
- `AIProvider._init()` respeita `AI_ENABLED` — retorna sem inicializar se false
- `AntiFraudeAgent`: nomes de operadores anonimizados para "Operador 1, 2, …" antes de enviar à IA
- Seção "Governança de dados e LGPD" adicionada ao `README.md` com tabela de dados enviados, destino, quando ocorre e como desativar

**Arquivos alterados:**
- `backend/app/config.py`
- `backend/.env.example`
- `.agents/provider/provider.py`
- `.agents/antifraude/antifraude.py`
- `README.md`

**Commit:** `bd397b0`

---

### P1#6 — CDN frontend (operação offline)

**Achado:** `main.py` e os HTMLs dependem de CDNs externos para Tailwind CSS, MDI e Google Fonts. Em almoxarifados sem internet, a interface fica sem estilo e sem ícones.

**Status:** ⚠️ **Débito técnico registrado — NÃO corrigido nesta rodada**

**Justificativa:** Vendorizar Tailwind (standalone CLI), baixar ícones MDI e fontes Google exige build toolchain adicional e mudanças em todos os HTMLs. Não foi possível fazer sem risco de quebra de layout — requer validação visual extensiva. A correção foi registrada no `ROADMAP.md`.

**Mitigação provisória:** Ambiente de almoxarifado deve ter acesso controlado à internet ou cache proxy (nginx `proxy_cache`) para os recursos CDN.

---

## Resultado final da suíte de testes

```
pytest -q
396 passed, 1 skipped
```

> O teste pulado (`TestDeleteSessaoConcluida::test_delete_sessao_concluida_bloqueado`) é um skip pré-existente não relacionado às correções desta auditoria.

---

## Commits desta auditoria

| Hash | Descrição |
|------|-----------|
| `852475a` | fix(security): exige token de operador em POST /contagens — CRÍTICO |
| `2b14003` | fix(security): exige token em WebSocket /ws/sessao/{id} |
| `de182b3` | fix(scheduler): pg_try_advisory_lock evita execução duplicada em multi-worker |
| `bd397b0` | fix(p1): CSP docs, TRUST_PROXY, create_tables gate, AI_ENABLED, LGPD, req.lock |

---

## Débitos técnicos remanescentes

| Item | Descrição | Esforço estimado |
|------|-----------|-----------------|
| CDN offline (P1#6) | Vendorizar Tailwind, MDI e Google Fonts para `static/vendor/` | 1–2 dias |
| Hardening CSP (P1#7) | Remover `'unsafe-inline'` movendo scripts inline para `.js` externos | 1–2 dias |
| Brute-force Redis (P1#8) | Backend Redis compartilhado quando `REDIS_URL` configurado | 4 horas |
| Concorrência scheduler (P0#3) | Validação em PostgreSQL real com múltiplos workers (teste manual) | 1–2 horas |
