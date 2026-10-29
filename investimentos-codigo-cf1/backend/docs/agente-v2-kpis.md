# Agente v2, alertas, indicadores e modo privacidade

## O que o Claude faz agora

| Tarefa agendada | Quando | O que grava | Como avisa |
|---|---|---|---|
| Análise diária da carteira | dias úteis, 7h51 | `claude-analises/relatorios/AAAA-MM-DD.json` (formato v2) | notificação no celular |
| Alertas de hora em hora | dias úteis, 8h a 20h | `claude-analises/alertas/AAAA-MM-DD.json` só quando há notícia séria | e-mail + faixa no dashboard + linha no widget |

Os textos completos das duas tarefas estão em `docs/agente-prompts/`.
Mudou o prompt? Atualize a tarefa agendada com o mesmo texto.

## Relatório v2

Igual ao v1, mais:

- `portfolio_review`: visão geral + listas "está bem", "pede atenção",
  "riscos" e "pode melhorar" (cada ponto com título, detalhe e tickers).
  Nunca recomenda compra ou venda.
- `holdings[].key_metrics`: indicadores de mercado com código fixo
  (dividend yield, P/L, P/FFO, ocupação, taxa do fundo, beta, YTM...),
  valor numérico, data e fonte. Frações em decimal (0.039 = 3,9%), e
  uma fração acima de 5 (500%) recusa o arquivo — pega o "39" no lugar
  de "0.39".

Relatórios v1 continuam valendo; arquivo fora do formato aparece como
"recusado" na tela, com o motivo.

## Alertas

- Só severidade `ALTA` ou `CRITICA`, cada um com 1 a 5 fontes http(s).
- O backend só lê os arquivos. "Lido" fica em `alertas/lidos.json`
  (gravação atômica; guarda no máximo 2000 ids).
- `GET /insights/alerts?days=7` (1 a 60), `POST /insights/alerts/{id}/read`,
  `POST /insights/alerts/read-all`.
- Arquivo com data futura ou fora da janela não aparece.

## Indicadores (`GET /performance/kpis`)

Calculados aqui, por moeda (moedas nunca se somam), com o histórico de
fechamentos que a busca de cotações já grava:

- Carteira: maior posição e as 3 maiores, diversificação (1/HHI —
  "quantos ativos de peso igual"), quantos no positivo, melhor e pior,
  proventos e rendimento sobre o custo, exposição por classe, e a
  composição atual simulada nos últimos 12 meses (só ativos de bolsa
  com o ano inteiro de histórico).
- Por ativo: peso, resultado, contribuição (pontos percentuais do
  resultado da carteira), pregão, 1 mês, 3 meses, no ano, 12 meses,
  volatilidade anualizada, pior queda e faixa de 52 semanas.
- Tudo é desempenho de PREÇO (sem proventos). Período que o histórico
  não cobre fica "—", nunca um período menor.
- Ativo sem cotação entra pelo custo e é nomeado.

O retrato `carteira.json` leva esses números para o Claude usar na
análise.

## Modo privacidade

Botão "Esconder valores" no topo. Esconde todo valor em dinheiro e as
quantidades ("R$ •••••"); percentuais continuam. A escolha fica no
navegador. No widget: botão direito → "Esconder valores".
