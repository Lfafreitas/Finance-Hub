# Celular, Jornal da carteira e indicadores novos

## Acesso pelo celular (Tailscale)

O dashboard continua só no computador do usuário. O Tailscale cria uma rede
privada entre os aparelhos dele (gratuito para uso pessoal); o comando
`celular` do iniciador publica o frontend SÓ dentro dessa rede:

    tailscale serve --bg http://localhost:5173

- Endereço: `https://<computador>.<rede>.ts.net` (HTTPS com certificado do
  próprio Tailscale). Ninguém fora da rede dele alcança.
- O backend nunca é publicado: o frontend chama `/api/...` na própria
  origem e o Vite repassa para `127.0.0.1:8000` (proxy em `vite.config.ts`).
  O backend continua aceitando só Host `localhost`/`127.0.0.1`.
- O Vite aceita Host `localhost` e `*.ts.net` (`server.allowedHosts`);
  qualquer outro nome é recusado (DNS rebinding).
- iPhone: app Tailscale ligado, Safari no endereço, Compartilhar ›
  Adicionar à Tela de Início (manifest + ícone; abre em tela cheia).
- Precisa do computador ligado com o dashboard no ar.
- Desfazer: `tailscale serve reset`.

O cartão final do "Iniciar Dashboard" mostra a linha "Celular" quando o
Tailscale está instalado (endereço, ou o atalho para ativar).

## Jornal da carteira (relatório v3)

A tela Notícias e análises virou a edição do dia: data por extenso,
faixa de números do mercado, manchete com lide, "O que acompanhar" ao
lado, "Para estudar", avaliação da carteira, manchetes, grandes casas,
empresas por trás dos ETFs, seus ativos e a conversa com o Claude.

Campos novos do relatório (todos opcionais; v1/v2 continuam válidos):

- `market`: até 10 números (texto já formatado, direção UP/DOWN/FLAT).
- `opportunities`: até 6 ideias para ESTUDAR, cada uma com tese, por que
  agora, relação com a carteira, 1–5 riscos, como acompanhar e ao menos
  uma fonte. A tela sempre diz que não são recomendação.
- `etf_holdings`: maiores posições de cada ETF (fração do fundo, soma ≤ 1,
  sem empresa repetida, um registro por ETF).

O prompt da tarefa diária (`agente-prompts/analise-diaria.md`) pede v3; um
teste garante que o prompt pede a versão mais nova e mostra todos os campos.

## Indicadores novos

- **Empresas por trás dos ETFs** (`GET /insights/lookthrough`): peso do
  fundo na carteira × peso da empresa no fundo, somado entre fundos (ação
  comprada direto conta como a própria empresa). É um piso: só entram as
  maiores posições publicadas. Fundo sem composição aparece em `missing`.
- **Reserva e poupança** (`GET /performance/financial-health`): com os
  últimos 3 meses fechados que têm renda, gasto ou lançamento a
  classificar — reserva ÷ gasto médio (meses de cobertura), (renda −
  gastos) ÷ renda (taxa de poupança) e aporte líquido médio. Com
  lançamentos sem classificação, a cobertura é um teto e a tela avisa.

Os dois entram no retrato da carteira (`financial_health`) e no resumo que
vai para a conversa com o Claude (só totais; nenhuma descrição de extrato).
