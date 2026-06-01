# INVIQ — Regras de Negócio, Requisitos Funcionais e Não Funcionais

> Versão 3.0 — Junho 2026  
> Reflete o estado real do sistema após revisão completa de usabilidade

---

## 1. Visão Geral

O **INVIQ** é um sistema de inventário físico por QR Code que combina:
- Painel administrativo desktop para coordenar sessões e analisar resultados em tempo real
- Scanner mobile para operadores de campo, com suporte offline
- Análise por IA (Claude) para detectar padrões, riscos e gerar relatórios executivos
- Controle de acesso por rodada via QR Code + token rotativo

O sistema foi projetado para **agilizar o inventário físico**, eliminar retrabalho e fornecer **impacto financeiro imediato** ao gestor.

---

## 2. Glossário

| Termo | Definição |
|-------|-----------|
| **Sessão** | Evento único de inventário. Agrupa itens, contagens, rodadas e todos os registros de um inventário específico |
| **Item Base** | Produto importado da planilha de estoque. Define código, nome, quantidade esperada e valor |
| **Contagem** | Registro do operador: quantidade física encontrada para um item em uma sessão |
| **Rodada** | Ciclo de contagem. R1 = todos os itens; R2/R3 = somente divergentes |
| **Divergência** | `quantidade_encontrada ≠ quantidade_base` |
| **Para Ajuste** | Item divergente confirmado: mesmo valor contado em recontagem, ou divergente após R3. Não gera nova rodada — vai direto para planilha de ajuste de estoque |
| **Operador** | Usuário de campo com smartphone. Acessa via QR Code + token |
| **Administrador** | Usuário que gerencia sessões, importa planilhas, visualiza dashboards e encerra sessões |
| **Token de Rodada** | Código de 8 caracteres gerado pelo administrador. Controla o acesso de operadores à rodada específica |
| **Histórico** | Registro imutável (append-only) de cada contagem individual. Base de auditoria |

---

## 3. Regras de Negócio

### 3.1 Sessão

**RN-01** — Uma sessão aceita contagens apenas com status `ativa`. Sessões `concluída` ou `cancelada` bloqueiam novos registros com erro 409.

**RN-02** — Toda sessão recebe código único sequencial `INV-AAAA-NNNN` gerado automaticamente (ex: `INV-2026-0001`).

**RN-03** — A sessão pode ser concluída pelo administrador a qualquer momento. Sessões concluídas são imutáveis — não podem ser reabertas.

**RN-04** — Planilha de itens base só pode ser importada enquanto a sessão estiver `ativa`. A reimportação substitui todos os itens anteriores **mas preserva todas as contagens existentes** (não há perda de trabalho já realizado).

**RN-05** — Ao concluir uma sessão, o sistema gera automaticamente:
- PDF Executivo com KPIs, impacto financeiro e análise de IA
- Excel completo com abas: Resumo, Todos os Itens, Divergências, Recomendações

---

### 3.2 Controle de Acesso Mobile (Token de Rodada)

**RN-06** — O acesso ao scanner mobile é protegido por **token alfanumérico de 8 caracteres**, gerado pelo sistema e exibido apenas para o administrador via QR Code.

**RN-07** — O administrador gera o QR Code de cada rodada explicitamente. Isso garante que operadores só iniciem a rodada seguinte após autorização do administrador.

**RN-08** — Quando o administrador gera um novo token (rodada 2, 3 ou regeneração), o token anterior é automaticamente invalidado. Operadores com o link antigo precisarão inserir o novo token.

**RN-09** — O token é exibido no modal de QR Code em tamanho grande para facilitar ditado verbal ("token três-a-sete-efe-dois...") quando o operador não tem acesso ao QR físico.

**RN-10** — A URL completa com token `(/mobile/{id}?token=XXXX)` pode ser copiada e enviada via WhatsApp, e-mail ou qualquer mensageiro.

---

### 3.3 Rodadas de Contagem

**RN-11** — O sistema opera com até **3 rodadas** por sessão:
- **Rodada 1:** todos os itens da sessão devem ser contados ao menos uma vez
- **Rodada 2:** apenas itens divergentes da rodada 1
- **Rodada 3:** apenas itens ainda divergentes após a rodada 2

**RN-12 — Progressão de rodada:** um item avança para a próxima rodada **somente** se:
1. Estava divergente na rodada anterior, E
2. A nova quantidade registrada é **diferente** da quantidade anterior

**RN-13 — Confirmação de divergência (Para Ajuste):** se o operador recontagem um item divergente e registra a **mesma quantidade** da contagem anterior, o item é imediatamente marcado como **"Para Ajuste"** e não gera nova rodada. Isso sinaliza que dois operadores (ou duas tentativas) chegaram ao mesmo resultado — a divergência é confirmada e deve ir direto ao ajuste de estoque.

**RN-14** — Itens divergentes após a rodada 3 são automaticamente marcados como **"Para Ajuste"**, independente da quantidade (esgotou as tentativas disponíveis).

**RN-15** — Quando uma rodada é concluída:
- **No mobile:** exibe tela "Rodada N Concluída" com resumo e botão "Iniciar próxima rodada"
- **No admin:** exibe banner com número de divergências pendentes e botão "Gerar QR Próxima Rodada"
- O evento WebSocket `rodada_completa` é emitido para todos os clientes conectados

**RN-16** — O sistema não bloqueia rescans de itens já contados. Um rescan de item **sem divergência** mantém a rodada atual e atualiza o registro. Um rescan de item **com divergência** avança a rodada (exceto se confirmar a mesma quantidade — aplica RN-13).

---

### 3.4 Entrada de Dados

**RN-17** — O sistema aceita dois modos de entrada no mobile:
- **Câmera QR:** leitura por câmera traseira. Anti-duplo-scan: mesmo código ignorado por 3 segundos
- **Modo Manual:** tela dedicada com busca fuzzy nos itens cadastrados (sugestões em tempo real)

**RN-18** — Itens sem etiqueta QR (diesel, ARLA a granel, pneus, materiais a granel) devem ser registrados pelo Modo Manual. O código digitado deve estar cadastrado na planilha importada.

**RN-19** — O campo `observação` é opcional (máx. 500 caracteres). Registros típicos: "caixa danificada", "item em trânsito", "embalagem diferente", "contado com avaria".

**RN-20** — O nome do operador é salvo localmente no dispositivo (`localStorage`) e reutilizado em todas as leituras subsequentes. O operador pode alterar seu nome a qualquer momento pelo ícone de perfil.

---

### 3.5 Funcionamento Offline

**RN-21** — O scanner mobile funciona em modo **offline completo**: contagens são enfileiradas localmente quando não há conectividade com o servidor.

**RN-22** — A sincronização offline ocorre automaticamente ao reconectar o WebSocket. O botão "Enviar offline" aparece quando há contagens pendentes e permite sincronização manual.

**RN-23** — Em caso de falha de rede durante o envio, a contagem é salva localmente com timestamp. Ao reconectar, é enviada na ordem cronológica de registro.

**RN-24** — Quando a página volta do background (celular bloqueado, troca de app), o sistema reconecta o WebSocket automaticamente e recarrega o progresso atual via REST como fallback.

---

### 3.6 Tempo Real e Sincronização

**RN-25** — O sistema usa WebSocket (ws://) para comunicação bidirecional em tempo real. Eventos emitidos:

| Evento | Destinatário | Descrição |
|--------|-------------|-----------|
| `contagem_registrada` | Todos | Nova contagem: código, quantidade, divergência, para_ajuste |
| `progresso_atualizado` | Todos | Estado atual da rodada: itens contados, faltando, rodada |
| `rodada_completa` | Todos | Rodada concluída: divergências pendentes, próxima rodada |

**RN-26** — A conexão WebSocket mantém-se ativa via heartbeat (ping a cada 25 segundos). Em caso de queda, reconecta com backoff exponencial (2s → 15s máximo).

**RN-27** — O painel admin atualiza stats de itens imediatamente via chamada REST ao receber qualquer evento `contagem_registrada` ou `progresso_atualizado`. A tabela de itens atualiza o item específico inline sem recarregar a página.

---

### 3.7 Exportações

**RN-28** — O sistema oferece 6 tipos de exportação:

| Tipo | Formato | Descrição |
|------|---------|-----------|
| Excel Completo | .xlsx | Todos os itens com status, quantidades, operadores, rodadas |
| Excel Divergências | .xlsx | Apenas divergentes (alimenta ajuste de estoque no ERP) |
| PDF Relatório | .pdf | Relatório executivo com tabela de itens e legenda |
| Etiquetas QR | .pdf | Folha A4 com 14 etiquetas por página (2×7), QR + nome + código |
| **PDF Relatório Final** | .pdf | Executivo completo: KPIs, impacto financeiro, análise IA, recomendações, todos os itens |
| **Excel Relatório Final** | .xlsx | 4 abas: Resumo Executivo, Todos os Itens, Divergências, Recomendações |

**RN-29** — O PDF usa `Paragraph` com quebra automática de linha para nomes de produtos longos. Não há truncamento.

**RN-30** — Exportações podem ser geradas durante a sessão ativa ou após conclusão.

---

### 3.8 Análise por IA

**RN-31** — Ao clicar em "IA Analisar", o sistema envia dados da sessão para o Claude (Haiku) e retorna:
- Resumo executivo em linguagem natural
- Padrões de divergência detectados
- Itens críticos (maior desvio)
- Recomendações de melhoria

**RN-32** — O Chat IA permite perguntas em linguagem natural sobre a sessão (ex: "Quais itens têm mais de 20% de diferença?", "Quem foi o operador com mais divergências?").

**RN-33** — A análise IA é **não-bloqueante**: se a API Claude não estiver disponível (sem chave, rate limit), o sistema retorna análise básica local (sem IA) com métricas calculadas internamente.

**RN-34** — Os relatórios finais (PDF + Excel) incluem a análise de IA automaticamente quando disponível. Se a API não estiver disponível, os relatórios são gerados sem a seção de IA.

---

### 3.9 Impacto Financeiro

**RN-35** — O painel financeiro é ativado automaticamente quando a planilha importada contém a coluna `valor em estoque` (ou variações: `valor`, `custo_total`, `vl_estoque`).

**RN-36** — Cálculo: `valor_final = Σ(quantidade_encontrada × preço_unitário)` onde `preço_unitário = valor_estoque / quantidade_base`. Itens não contados mantêm o valor base.

**RN-37** — O painel exibe: valor inicial, valor apurado, variação (R$ e %), maiores perdas (top 5) e maiores ganhos (top 5).

---

### 3.10 Auditoria

**RN-38** — Toda contagem registrada gera um registro append-only no `historico_contagens`. Mesmo que uma contagem seja refeita, todos os registros anteriores são preservados integralmente.

**RN-39** — O histórico registra: código, quantidade encontrada, quantidade base, divergência, operador, observação, rodada e timestamp UTC.

---

## 4. Requisitos Funcionais

### 4.1 Dashboard Principal (Admin Desktop)

| ID | Requisito |
|----|-----------|
| RF-01 | Listar todas as sessões com status (badge colorido), progresso (% com barra), divergências e data de criação |
| RF-02 | Criar sessão com nome descritivo; código gerado automaticamente |
| RF-03 | Filtrar sessões por status: Todas, Ativas, Concluídas, Canceladas |
| RF-04 | Busca em tempo real por nome ou código da sessão |
| RF-05 | Contadores globais: total de sessões, ativas, concluídas |
| RF-06 | Acesso à sessão com um clique; abrir em nova aba disponível |

### 4.2 Detalhe da Sessão (Admin Desktop)

| ID | Requisito |
|----|-----------|
| RF-10 | Cards de KPIs: Total, Conferidos, Pendentes, Divergências, % Concluído — atualizados em tempo real |
| RF-11 | Barra de progresso animada com gradiente, atualizada via WebSocket |
| RF-12 | Gráfico de barras: contagens por intervalo de 5 minutos (OK vs Divergente) |
| RF-13 | Lista de operadores ativos: nome, última leitura (tempo relativo), total e divergências |
| RF-14 | Live Feed: stream em tempo real de cada leitura com código, quantidade e status |
| RF-15 | Seção "Rodadas": cards por rodada (itens contados, divergências, status concluída/andamento) + tabelas de itens pendentes por rodada |
| RF-16 | **Banner de rodada completa**: aparece ao receber evento `rodada_completa` com ação "Gerar QR Próxima Rodada" |
| RF-17 | Tabela de itens: filtros Todos / OK / Divergente / **Para Ajuste** / Pendente + busca por código/nome |
| RF-18 | Tabela de itens: atualização inline ao receber `contagem_registrada` (sem reload) |
| RF-19 | Coluna "Rodada" na tabela de itens; badge "AJUSTE" em roxo para itens Para Ajuste |
| RF-20 | Importar planilha (xlsx/csv) com validação por IA antes da importação |
| RF-21 | **Seção "Acesso Mobile"**: exibe link com token incluído, botão copiar |
| RF-22 | **Botão "QR Acesso"**: abre modal com QR Code imprimível, token em destaque, link copiável |
| RF-23 | **Modal QR Code**: botão "Gerar QR para Nª Contagem" gera novo token e invalida o anterior |
| RF-24 | Análise por IA: modal expandido (720px) com resumo, padrões, itens críticos e recomendações numeradas |
| RF-25 | Chat IA para perguntas em linguagem natural; histórico de mensagens na sessão |
| RF-26 | Botão "Concluir Sessão" com modal de confirmação mostrando preview de stats |
| RF-27 | Após concluir: modal exibe links para download do PDF Final e Excel Final |
| RF-28 | Seção Exportar: 6 opções (Excel completo, Excel divergências, PDF relatório, Etiquetas QR, PDF Final, Excel Final) |
| RF-29 | Painel Financeiro: valor inicial, valor apurado, variação R$ e %, top 5 perdas, top 5 ganhos |
| RF-30 | Indicador de status WebSocket (Ao vivo / Reconectando) com ponto animado |

### 4.3 Scanner Mobile (Operador)

| ID | Requisito |
|----|-----------|
| RF-40 | **Tela de token**: antes de acessar o scanner, operador digita ou tem token na URL. Token validado contra sessão no servidor |
| RF-41 | Token na URL é validado automaticamente; se inválido, exibe tela para digitar |
| RF-42 | Scanner de QR Code via câmera traseira com linha de scan animada |
| RF-43 | Modo Manual: tela dedicada com busca fuzzy (sugestões em tempo real conforme digitação) |
| RF-44 | Histórico dos últimos 8 códigos digitados (chips clicáveis) |
| RF-45 | Tela de item: nome do produto, código, badge de rodada (1ª/2ª/3ª contagem) |
| RF-46 | Controles de quantidade: botões +/- com long-press acelerado, edição direta ao clicar no número |
| RF-47 | Confirmação de divergência antes de registrar (sem revelar quantidade esperada ao operador) |
| RF-48 | Feedback de sucesso (verde) com contagem regressiva 3s e retorno automático ao scanner |
| RF-49 | **Barra de progresso**: rodada atual + "Faltam N itens" — atualizada via WebSocket e via REST após cada registro |
| RF-50 | **Tela de rodada completa**: exibe resumo, divergências pendentes e botões "Iniciar próxima rodada" / "Aguardar próximos passos" |
| RF-51 | Indicador WebSocket com pulsação; reconecta automaticamente ao voltar do background |
| RF-52 | Nome do operador salvo localmente; modal de identificação exibe ao primeiro acesso |
| RF-53 | Campo de observação opcional por item (máx. 500 caracteres) |
| RF-54 | Botão "Enviar offline": aparece com contador de contagens pendentes |
| RF-55 | Sincronização automática da fila offline ao reconectar |
| RF-56 | Busca de progresso via REST ao retornar do background (garante dados atualizados sem depender de WS) |
| RF-57 | Estado "Sessão Encerrada": tela de bloqueio com mensagem personalizada por status |

### 4.4 Relatórios e Exportações

| ID | Requisito |
|----|-----------|
| RF-60 | PDF Relatório Final: capa com dados da sessão e duração, KPIs, impacto financeiro (se disponível), análise IA (se disponível), tabela completa de itens com Paragraph/wrap |
| RF-61 | Excel Relatório Final: aba Resumo Executivo, aba Todos os Itens (colorida por status), aba Divergências, aba Recomendações |
| RF-62 | Etiquetas QR: 14 labels por página A4, layout com barra de acento, QR Code, nome do produto (2 linhas), chip com código |
| RF-63 | Nomes longos de produtos não são truncados no PDF — usam quebra automática de linha |

---

## 5. Requisitos Não Funcionais

### 5.1 Performance

| ID | Requisito | Métrica |
|----|-----------|---------|
| RNF-01 | Registro de contagem | < 500ms resposta HTTP em rede local |
| RNF-02 | Busca de item por código | < 200ms |
| RNF-03 | Propagação de evento WebSocket | < 100ms após commit no banco |
| RNF-04 | Scanner mobile: processamento de frames | ≥ 24fps sem travamento visível |
| RNF-05 | Geração de Excel completo | < 5s para sessões com até 10.000 itens |
| RNF-06 | Geração de PDF Final | < 10s (inclui análise IA quando disponível) |
| RNF-07 | Carregamento inicial do dashboard | < 2s com itens em lazy load |

### 5.2 Disponibilidade e Resiliência

| ID | Requisito |
|----|-----------|
| RNF-10 | Scanner mobile funciona completamente offline (fila em localStorage) |
| RNF-11 | Dados offline não são perdidos mesmo após fechamento e reabertura do browser |
| RNF-12 | Reconexão WebSocket automática com backoff exponencial: 2s → 4s → 8s → 15s (máx.) |
| RNF-13 | Fallback REST: após registrar contagem, busca progresso via API mesmo que WS não confirme |
| RNF-14 | Ao voltar do background: WS reconecta automaticamente e progresso é recarregado via REST |
| RNF-15 | Análise IA com fallback: se API Claude indisponível, relatório é gerado com análise local básica |

### 5.3 Segurança

| ID | Requisito |
|----|-----------|
| RNF-20 | Inputs de usuário sanitizados com `escapeHtml()` antes de inserir no DOM (prevenção XSS) |
| RNF-21 | Upload de planilha validado: tipo de arquivo (xlsx/csv), tamanho máximo, estrutura de colunas |
| RNF-22 | Endpoints de IA com rate limiting (60 req/min por IP via slowapi) |
| RNF-23 | Token de acesso mobile: 8 chars hex gerado com `secrets.token_hex(4)` — adequado para contexto de inventário interno |
| RNF-24 | Token invalidado automaticamente ao gerar novo (uma sessão, um token ativo por vez) |
| RNF-25 | Autenticação completa de administrador: a implementar (JWT + bcrypt conforme TECH_STACK.md) |

### 5.4 Usabilidade

| ID | Requisito |
|----|-----------|
| RNF-30 | Interface mobile otimizada para uso com uma mão; botões mínimo 44×44px |
| RNF-31 | Feedback tátil (vibração 50ms) ao detectar QR Code |
| RNF-32 | Tela de scanner sem scroll; todos os controles acessíveis sem rolar |
| RNF-33 | Retorno automático ao scanner em 3 segundos após registro bem-sucedido |
| RNF-34 | Toasts de feedback com duração de 4 segundos; ícones semânticos (✓ ✕ ⚠ ℹ) |
| RNF-35 | Barra de progresso no mobile sempre visível durante a contagem |
| RNF-36 | Modais com ESC ou clique fora para fechar |
| RNF-37 | Status "Para Ajuste" com badge roxo distinto de "Divergente" (vermelho) — comunicação visual clara |
| RNF-38 | Banner de rodada completa no admin é dismissível mas não some sozinho — admin precisa ler e agir |

### 5.5 Compatibilidade

| ID | Requisito |
|----|-----------|
| RNF-40 | Mobile: Chrome/Safari mobile com `getUserMedia`, `localStorage`, WebSocket |
| RNF-41 | Desktop admin: Chrome, Firefox, Edge Chromium ≥ 90 |
| RNF-42 | Backend: Python 3.11+, FastAPI, SQLite (dev) / PostgreSQL (produção) |
| RNF-43 | Sem dependências de CDN críticas para funcionamento do scanner (apenas para estilos) |

### 5.6 Observabilidade

| ID | Requisito |
|----|-----------|
| RNF-50 | Logs estruturados no backend para: registros de contagem, eventos WebSocket, falhas de broadcast, erros IA |
| RNF-51 | Indicador visual de conectividade WS em ambos os clientes (admin e mobile) |
| RNF-52 | Histórico de auditoria append-only no banco; não pode ser deletado via API |

---

## 6. Fluxo Completo de Negócio (Estado Atual)

```
[ADMINISTRADOR]                        [OPERADORES MOBILE]
      |                                        |
      |─ Cria sessão (INV-2026-0001)           |
      |─ Importa planilha (N itens)            |
      |─ Clica "QR Acesso"                     |
      |─ Gera QR + Token da Rodada 1           |
      |─ Compartilha QR / Link com token ─────>|
      |                                        |─ Abre URL com token
      |                                        |─ Token validado → acessa scanner
      |                                        |─ Escaneia QR / digita código
      |                                        |─ Informa quantidade
      |                                        |─ [WS] contagem_registrada
      |                                        |─ [WS] progresso_atualizado
      |                                        |─ [REST] busca progresso (fallback)
      |<─ Live Feed atualiza                   |
      |<─ Stats atualizam                      |
      |<─ Tabela de itens atualiza inline      |
      |                                        |
      |           ... N itens contados ...     |
      |                                        |
      |<─ [WS] rodada_completa (R1)            |─ Tela "Rodada 1 Concluída"
      |<─ Banner: "12 itens para R2"           |─ "Iniciar próxima rodada"
      |─ Clica "Gerar QR Próxima Rodada"       |
      |─ Novo token gerado (R1 invalidado)     |
      |─ Compartilha novo QR/token ───────────>|
      |                                        |─ Novo token → acessa scanner R2
      |                                        |─ Escaneia 12 itens divergentes
      |                                        |─ 8 resolvidos, 4 divergentes
      |                                        |─ 2 confirmam mesma qtd → Para Ajuste
      |                                        |─ 2 divergem com qtd diferente → avança R3
      |<─ [WS] rodada_completa (R2)            |─ Tela "Rodada 2 Concluída"
      |─ Gera QR Rodada 3                     |
      |                                        |─ 2 itens recontados (R3)
      |                                        |─ [WS] rodada_completa (tudo_concluido)
      |<─ Banner: "Inventário Concluído"       |─ "Aguardar próximos passos"
      |─ Revisa 4 itens "Para Ajuste"          |
      |─ Clica "Concluir Sessão"               |
      |─ PDF Final gerado automaticamente      |
      |─ Excel Final gerado automaticamente    |
      |─ Baixa Excel Divergências              |
      |─ Submete ajuste ao ERP                 |
```

---

## 7. Estados de um Item ao Longo do Inventário

```
Pendente → (1ª contagem)
  ├── quantidade == base       → OK (encerrado)
  └── quantidade != base       → Divergente (aguarda R2)
                                    ├── R2 com MESMA qtd do R1  → Para Ajuste (encerrado)
                                    ├── R2 com qtd == base      → OK (encerrado)
                                    └── R2 com DIFERENTE qtd, ainda != base → Divergente R2 (aguarda R3)
                                                                                  ├── R3 (qualquer resultado)
                                                                                  │     se divergente → Para Ajuste
                                                                                  │     se == base   → OK
```

---

## 8. Próximas Evoluções Prioritárias

### Curto prazo (implementar antes de produção)

**EV-01 — Autenticação de Administrador**
JWT + bcrypt. Sessões protegidas por login. Sem autenticação, qualquer pessoa na rede pode ver e modificar inventários. Referência: `TECH_STACK.md` seção JWT Auth.

**EV-02 — Multi-empresa / Multi-usuário**
Separar inventários por empresa (tenant). Um administrador por empresa, múltiplos operadores com perfis.

**EV-03 — Página de Histórico de Sessões**
O dashboard mostra sessões mas não permite ver o histórico detalhado de contagem de sessões passadas. Adicionar visualização de auditoria.

### Médio prazo (próxima versão)

**EV-04 — Predição de Divergências (IA)**
Com dados históricos de múltiplos inventários, prever quais itens têm maior probabilidade de divergir na R1. Operador vê alerta "item historicamente problemático" antes de contar.

**EV-05 — OCR de Etiquetas (sem QR)**
Usar visão computacional para ler texto de etiquetas antigas, codigos de barras 1D (EAN, Code128), sem QR Code impresso. Elimina a necessidade de etiquetagem prévia.

**EV-06 — Notificações Push / WhatsApp**
Avisar administrador quando R1 conclui, quando há divergência alta (> 10% dos itens), ou quando operador para de contar por > 30 minutos.

**EV-07 — Integração ERP**
Submeter ajustes de estoque diretamente ao SAP/TOTVS/Bling após aprovação, sem exportar planilha manualmente.

### Longo prazo (v3.0)

**EV-08 — App Mobile Nativo (React Native + Expo)**
Scanner 2× mais rápido, câmera nativa, notificações push nativas iOS/Android. Funciona sem browser.

**EV-09 — Computer Vision: Contagem por Foto**
Operador fotografa prateleira → IA estima quantidade visível sem escanear item por item.

**EV-10 — Análise de Causa-Raiz por IA**
Após múltiplos inventários, IA identifica padrões de divergência por setor, operador, categoria de produto e horário do dia. Dashboard de causa-raiz para o gestor.
