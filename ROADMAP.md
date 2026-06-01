# Inventário QR — Roadmap Realista

> Foco: sistema funcional de inventário com leitura de QR Code.
> Simples, rápido de construir, fácil de usar.

---

## Stack (sem firula)

| Camada | Tecnologia | Por quê |
|--------|-----------|---------|
| Frontend | Next.js 15 + React + TypeScript | SSR, deploy Vercel grátis |
| Estilo | Tailwind CSS | Rápido, sem configuração complexa |
| Backend | FastAPI (Python) | Já existe, funciona bem |
| Banco (dev) | SQLite | Zero setup, arquivo local |
| Banco (prod) | PostgreSQL (Neon) | Grátis até 0.5 GB |
| Scanner | html5-qrcode | Já funciona, suporte amplo |
| Deploy | Vercel + Railway | Grátis para começar |

**Fora do escopo por agora:** Redis, Celery, JWT, multi-tenant, agentes de IA complexos.

---

## Fase 1 — Rodando (Hoje)

**Objetivo:** o sistema funciona no seu computador sem Docker.

### Checklist
- [ ] Backend roda com `uvicorn` + SQLite
- [ ] Frontend roda com `npm run dev`
- [ ] Criar sessão → aparece no dashboard
- [ ] Upload de planilha → itens aparecem
- [ ] Scanner mobile → lê QR e registra contagem
- [ ] Export XLSX funciona

### Como rodar
```bash
# Terminal 1 — Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Acesse: http://localhost:3000

---

## Fase 2 — Scanner que funciona de verdade (Semana 1)

**Objetivo:** operador pega o celular, abre o link, escaneia sem atrito.

### Melhorias
- [ ] Link mobile abre direto na câmera (sem cliques extras)
- [ ] Vibração + som no scan bem-sucedido
- [ ] Teclado numérico grande para digitar quantidade
- [ ] Funciona em HTTP simples (câmera só exige HTTPS em produção)
- [ ] Tela de "sessão concluída" ao tentar scanear em sessão fechada
- [ ] Campo de operador salvo no localStorage (não precisa digitar toda hora)

**Agente responsável:** `agent:scanner`

---

## Fase 3 — Dashboard com contexto (Semana 2)

**Objetivo:** o admin vê o que está acontecendo em tempo real.

### Features
- [ ] Barra de progresso ao vivo (WebSocket já implementado)
- [ ] Lista de operadores ativos com último scan
- [ ] Gráfico simples: itens contados por hora
- [ ] Alertas de divergência na tela (sem e-mail por enquanto)
- [ ] Filtro de itens: Todos / Pendentes / Divergentes / OK

**Agente responsável:** `agent:dashboard`

---

## Fase 4 — Relatórios úteis (Semana 3)

**Objetivo:** o gestor exporta um relatório que já pode ser usado.

### Features
- [ ] Export XLSX completo (já existe, manter)
- [ ] Export XLSX só divergências (já existe, manter)
- [ ] Resumo em PDF: capa + métricas + tabela de divergências
- [ ] Histórico de sessões com comparativo (% divergência por sessão)

**Agente responsável:** `agent:reports`

---

## Fase 5 — Deploy em produção (Semana 4)

**Objetivo:** sistema acessível pela internet, celular dos operadores aponta para URL real.

### Passos
1. Criar conta no [Neon](https://neon.tech) — PostgreSQL grátis
2. Criar conta no [Railway](https://railway.app) — backend grátis
3. Criar conta no [Vercel](https://vercel.com) — frontend grátis
4. Configurar variáveis de ambiente
5. Deploy automático via GitHub

**Agente responsável:** `agent:deploy`

---

## Agentes de Implementação

Cada agente é uma tarefa de desenvolvimento com escopo bem definido.
Execute um de cada vez — não em paralelo.

### agent:scanner
Melhorar a experiência do operador mobile.
```
Escopo:
- Salvar nome do operador no localStorage
- Vibrar no scan (navigator.vibrate)
- Aumentar área de toque dos botões
- Redirecionar se sessão estiver concluída
- Testar em 375px de largura
```

### agent:dashboard
Dashboard admin em tempo real.
```
Escopo:
- WebSocket já está no backend (usar)
- Cards de stats atualizam ao vivo
- Tabela de itens filtrável
- Indicador de operadores ativos (usar campo operador das contagens)
- Gráfico de progresso por hora (recharts já instalado)
```

### agent:reports
Relatório PDF da sessão.
```
Escopo:
- Endpoint GET /api/sessoes/:id/exportar/pdf
- Usar reportlab (já no requirements)
- Layout: capa, resumo executivo, tabela de divergências
- Frontend: botão "Exportar PDF" na página de sessão
```

### agent:deploy
Deploy completo na nuvem.
```
Escopo:
- Criar .env.production com variáveis corretas
- next.config.ts: apontar para URL do backend em prod
- Dockerfile do backend para Railway
- README com passo a passo de deploy
```

---

## Estado Atual do Código

```
backend/
  ✅ FastAPI + SQLAlchemy + SQLite (dev) / PostgreSQL (prod)
  ✅ Sessões CRUD
  ✅ Upload de planilha Excel
  ✅ Scanner: buscar item por código
  ✅ Registrar contagem + detectar divergência
  ✅ Export XLSX (completo + divergências)
  ✅ WebSocket por sessão (tempo real)
  ✅ ValidationAgent (validação IA da planilha)
  ❌ Export PDF (Fase 4)
  ❌ Autenticação JWT (pós-Fase 5, se necessário)

frontend/
  ✅ Next.js 15 + React + TypeScript
  ✅ Dashboard (lista de sessões)
  ✅ Página de detalhe da sessão
  ✅ Scanner mobile (câmera traseira, estados visuais)
  ✅ TanStack Query (cache + server state)
  ✅ WebSocket client (reconecta automático)
  ✅ PWA (manifest + ícone)
  ⚠️  Melhorias de UX mobile (Fase 2)
  ❌  Gráfico de progresso (Fase 3)
```

---

## Decisões de arquitetura

| Decisão | Escolha | Motivo |
|---------|---------|--------|
| Auth | Nenhuma por enquanto | Operadores usam link direto. Adicionar depois se necessário. |
| Banco em dev | SQLite | Zero instalação. Migrar para PostgreSQL no deploy. |
| Estado global | TanStack Query | Elimina `useEffect` para fetch de dados |
| Tempo real | WebSocket nativo | Sem biblioteca extra, já está no FastAPI |
| Scanner | html5-qrcode | Funciona no browser, sem app nativo |
| PDF | reportlab (Python) | Mais controle que bibliotecas JS |
