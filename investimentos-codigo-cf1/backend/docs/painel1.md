# Painel-1 — widget, evolução do patrimônio, classificar em grupos e navegação

Sem migração e sem pacote novo.

## Endpoints

### `GET /performance/history?days=N`

Patrimônio dia a dia, uma série por moeda (moedas não se somam). Cada
ponto: valor dos investimentos, custo aplicado, caixa (conta + reserva +
cartão) e total. Sem `days`, desde o primeiro movimento (máx. 1100 dias).

- Quantidade e custo de cada dia saem do `PositionCalculator` aplicado às
  transações até aquele dia.
- Valor = quantidade × último preço até aquele dia, na moeda da posição.
  Sem cotação (ou cotação em outra moeda), entra pelo custo e o ticker vai
  em `unpriced`.
- Na mesma data, a cotação digitada à mão vence a automática.
- Ajustes (saldo inicial, rendimento acumulado da Caixinha) aparecem como
  degrau no dia em que foram lançados.

### `GET /performance/widget`

Resumo para o widget: por moeda, o patrimônio e o "quanto rendeu" do
`/overview`, a variação do último pregão e os últimos 30 dias do valor dos
investimentos.

Variação do último pregão: último preço contra o preço da data anterior,
só para ativos negociados em bolsa com duas cotações. Renda fixa fica de
fora (a diferença entre duas cotações digitadas pode ser de semanas). O
mesmo ativo em duas contas vira uma linha; o percentual da moeda é a soma
das variações sobre o valor anterior de todos.

### `GET /cashflow/pending/groups?limit=50`

O que falta classificar, junto pelo `match_text` (o mesmo texto que as
regras comparam) e pela moeda, maiores primeiro. A sugestão é a
classificação mais frequente que você já deu a esse mesmo texto (empate:
a mais recente); transferência nunca é sugerida.

### `POST /cashflow/entries/classify-batch`

Mesma classificação manual para até 500 lançamentos. Tudo ou nada: se um
for recusado (de outro usuário, excluído, transferência), nenhum muda.

## Telas

- **Visão geral (antigo Dashboard):** horário das cotações com
  "Atualizar agora"; cotação com mais de 15 minutos é buscada sozinha (no
  máximo a cada 15 minutos) e a tela relê tudo depois. Lista "pede sua
  atenção": lançamentos sem classificação, ativos sem cotação, falha ao
  buscar cotação — cada um com o botão que leva para onde se resolve.
  Gráfico "Evolução do patrimônio" (1M, 3M, 6M, 1A, Tudo) com a tabela
  mês a mês. Cada posição tem atalho "Lançamentos".
- **Lançamentos (investimentos):** abre direto na conta vinda do atalho
  ou na única conta; filtro por ativo; excluídos escondidos até marcar
  "Mostrar excluídos".
- **Controle financeiro → Classificar:** grupos com sugestão ("Usar a
  sugestão"), natureza, categoria e "Criar regra para os próximos"
  (marcado por padrão). Pagamento de fatura avisa que não é gasto.
- **Faixa vermelha no topo** quando o backend não responde (`/health` a
  cada 30 s).

## Widget da área de trabalho (`widget/`)

Mini app em Python (só biblioteca padrão + tkinter), para Windows e Linux:
sempre por cima, sem borda, arrastável, menu no botão direito, lembra a
posição. Lê `/performance/widget` a cada minuto e pede `/prices/refresh`
quando a cotação tem mais de 15 minutos. Com `--ligar-backend`, liga o
uvicorn do `backend/.venv` se o backend estiver desligado. Ver
`widget/LEIAME.md`.
