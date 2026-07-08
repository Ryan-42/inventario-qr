# Prompt para IA de apresentação — INVIQ

> Copie tudo abaixo da linha horizontal e cole na IA que vai gerar os slides (Gamma, Canva, Tome, etc.).

---

Você vai criar uma apresentação de slides sobre o **INVIQ**, um sistema web de inventário físico por QR Code. Use exclusivamente as informações deste documento — **não invente preços, clientes, cases ou métricas que não estejam aqui**.

## 1. O problema (contexto)

Inventário físico em empresas ainda é feito com prancheta, papel e digitação manual em planilha. Isso gera:

- Erros de transcrição e contagem "viciada" (o contador vê a quantidade esperada no papel e tende a confirmá-la em vez de contar de verdade);
- Retrabalho: divergências só aparecem dias depois, quando o estoque já mudou;
- Custo alto de coletores de dados dedicados (hardware proprietário caro, um por operador);
- Zero visibilidade em tempo real para o gestor durante a contagem;
- Nenhuma trilha de auditoria: não se sabe quem contou o quê, quando, nem quantas vezes.

## 2. O que é o INVIQ

Sistema web completo de inventário físico. O celular do próprio operador vira o coletor de dados — sem instalar aplicativo (é um PWA que abre no navegador) e **sem o operador precisar de login ou cadastro**: ele escaneia um QR Code e já está contando.

### Fluxo do produto em 7 passos

1. **O admin cria uma sessão de inventário** no painel web e sobe a planilha do estoque (Excel ou CSV) com códigos, descrições e quantidades esperadas.
2. **O sistema gera um QR Code de acesso** com um token embutido. O admin projeta na parede ou compartilha o link. O operador escaneia com o celular e entra direto no scanner — sem login, sem app, sem cadastro.
3. **Contagem cega**: o operador escaneia o código de barras/QR do item e digita quantas unidades contou. Ele **nunca vê a quantidade esperada** — isso é garantido no servidor (a API não envia o dado), não apenas escondido na tela. Elimina a contagem viciada.
4. **Tempo real**: cada contagem aparece instantaneamente no painel do admin via WebSocket — barra de progresso, itens contados, divergências. Funciona offline: se o Wi-Fi do galpão cair, as contagens ficam no celular e sincronizam quando a conexão volta.
5. **Rodadas de recontagem automáticas**: itens divergentes entram automaticamente em 2ª e 3ª rodada de contagem (com novo token, para separar as rodadas). Se a mesma divergência se repete, o item vai para a fila **"Para Ajuste"** em vez de gerar recontagem infinita.
6. **Aprovação em 4 olhos**: o inventário concluído pode exigir uma segunda aprovação, por outra pessoa, com token próprio. Depois de aprovada, a sessão fica imutável — trilha de auditoria completa.
7. **Resultado e integração**: relatórios finais em Excel e PDF (completo, só divergências, etiquetas de prateleira), análise financeira (valor de estoque, maiores perdas e ganhos em R$) e exportação no layout do ERP TOTVS.

### Papéis de usuário

- **Admin/gestor** — painel web com login (JWT): cria sessões, sobe planilhas, acompanha em tempo real, aprova, exporta.
- **Operador** — só o celular, sem login: escaneia QR da sessão, conta itens.
- **Grupos de operadores** — o admin divide a contagem por corredor/setor: cada grupo tem seu QR e só enxerga os itens do seu filtro (por prefixo de código ou lista).
- **Supervisor** — token próprio, acompanha o progresso da equipe em página dedicada, sem poder de admin.
- **Segundo aprovador** — token próprio para a aprovação em 4 olhos.

## 3. Camadas técnicas (para 1–2 slides de "como funciona por dentro")

- **Frontend**: HTML + JavaScript puro, sem build — PWA instalável, scanner de QR/código de barras pela câmera, funciona offline (service worker).
- **Backend**: FastAPI (Python) + WebSocket para tempo real + agendador interno de inventários recorrentes (ex.: contagem cíclica toda semana).
- **Banco**: PostgreSQL em produção (Neon), SQLite em desenvolvimento; migrações versionadas com Alembic.
- **11 agentes de IA** (validação de planilha, detecção de anomalias/antifraude, alertas, análise pós-inventário, plano de ação, previsão, relatórios, coach de procedimento, ajuste, sincronização ERP) — **desligados por padrão** (LGPD-first: nenhum dado sai do servidor sem opt-in explícito). Funcionam com Anthropic Claude ou Groq.
- **Segurança**: contagem cega garantida na API; tokens de acesso comparados com proteção contra timing attack; proteção contra força bruta e rate-limiting; JWT com blacklist de logout; QR codes e tokens só acessíveis ao admin autenticado.
- **Qualidade**: 429 testes automatizados rodando em CI (GitHub Actions) a cada alteração — o deploy só sai se a suíte passar; Docker + deploy contínuo no Render.
- **Multi-filial**: suporte a múltiplas filiais/locais de estoque e inventários agendados por filial.

## 4. Diferenciais (slide de "por que INVIQ")

1. **Custo zero de hardware** — o celular do operador substitui o coletor dedicado.
2. **Zero fricção para o operador** — sem app para instalar, sem login, sem treinamento: escaneou, contou.
3. **Contagem cega de verdade** — imposta pelo servidor, não pela interface; auditável.
4. **Governança embutida** — rodadas automáticas de recontagem, fila "Para Ajuste", aprovação em 4 olhos, trilha imutável.
5. **Tempo real + offline** — o gestor vê o inventário andando ao vivo; o galpão sem sinal não para a contagem.
6. **IA opcional e privada por padrão** — insights de anomalia e plano de ação sem enviar dados para fora sem consentimento (LGPD).

## 5. Instruções para a apresentação

- **Idioma**: português do Brasil.
- **Público**: gestores de operações/estoque e diretores — **não técnico**. Traduza termos técnicos em benefício de negócio (ex.: "WebSocket" → "painel ao vivo"; "PWA" → "abre no navegador do celular, sem instalar nada").
- **Tamanho**: 12 a 15 slides.
- **Estrutura sugerida**:
  1. Capa — INVIQ: inventário físico por QR Code;
  2. O problema do inventário manual (dores do item 1);
  3. A solução em uma frase + imagem-conceito;
  4–7. O fluxo em passos (criar sessão → operador escaneia e conta → tempo real → recontagens e aprovação);
  8. Contagem cega — por que isso muda o resultado;
  9. Papéis e grupos de operadores;
  10. Relatórios, análise financeira e integração TOTVS;
  11. Como funciona por dentro (camadas, 1 slide simples);
  12. Segurança e qualidade (429 testes, CI, LGPD);
  13. Diferenciais (item 4);
  14. Encerramento / próximos passos.
- Use os números concretos deste documento (7 passos, 3 rodadas, 4 olhos, 11 agentes, 429 testes) — eles dão credibilidade.
- **Não invente**: preços, nomes de clientes, depoimentos, market share ou métricas de resultado que não estão neste documento.
