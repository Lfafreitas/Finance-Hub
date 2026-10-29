# Visual-1 — patrimônio por moeda, resumo do caixa e achados de gasto

Sem migração, sem pacote novo. Tudo continua por moeda: nada é somado
entre BRL e USD e nada é convertido.

## Endpoints novos

### `GET /overview`

Patrimônio de todas as contas, um bloco por moeda.

- `total` = valor dos investimentos + disponível + reserva + cartão
  (cartão negativo = fatura em aberto, já descontada).
- Valor dos investimentos: a última cotação de cada posição. Posição sem
  cotação entra pelo custo e é listada em `unpriced`.
  `investments_basis` é `MARKET` (tudo cotado), `MIXED` (parte pelo
  custo) ou `COST` (nada cotado).
- `result` = não realizado (só das posições cotadas) + realizado +
  proventos; `result_pct` = `result` / custo aplicado (nulo sem custo).
  `result_complete` é falso quando alguma posição está sem cotação.
- `parts`: fatias positivas do total (renda variável, renda fixa,
  fundos, reserva, disponível…), com o peso de cada uma.
  `investment_groups`: só os investimentos, pelos mesmos grupos.
- Moeda sem investimento e com saldos zerados não aparece.

Grupos (`investment_group`): ações, ETFs, REITs e FIIs → renda
variável; títulos, CDB e afins → renda fixa; fundos → fundos; o resto →
outros.

### `GET /cashflow/summary/monthly?end=AAAA-MM&months=N`

Últimos `N` meses (1 a 24, padrão 6) terminando em `end`, por moeda:
entradas (renda), saídas (gastos), sobra (entradas − saídas), investido
líquido, não classificado e quantidade de lançamentos. Mês sem
lançamento vem zerado, para o gráfico não ter buracos.

### `GET /cashflow/insights?month=AAAA-MM`

Achados determinísticos sobre os gastos do mês, comparados com o
próprio histórico. Nada sai do computador; nenhuma IA.

| Achado | Regra |
|---|---|
| Acima do normal | categoria-mãe com gasto ≥ 20% **e** ≥ 50 acima da média dos 3 meses anteriores; exige pelo menos 2 meses de histórico |
| Recorrente | mesma descrição normalizada em cada um dos 3 últimos meses |
| Pequenos que somam | compras abaixo de 30, quando são pelo menos 5 no mês |
| Onde está o gasto | as 3 maiores categorias e quanto do total elas somam |
| Não classificado | saídas sem classificação e a fatia delas nas saídas do mês |

Subcategoria conta na categoria-mãe. Só entram lançamentos de gasto e
não classificados.

`GET /analytics/portfolio` passou a trazer `by_group` na concentração
(renda variável × renda fixa por valor de mercado, ou custo se faltar
cotação).

## Telas

- **Dashboard**: cartões de patrimônio lado a lado (reais e dólar), com
  "quanto rendeu" em valor e percentual com sinal, aviso nomeando os
  ativos sem cotação, barra de composição e a fatura em aberto.
  Distribuição por ativo (barras, maior primeiro) ou renda fixa ×
  variável (barra de 100%).
- **Resumo do caixa**: destaques do mês (entradas, saídas, sobra,
  investido, reserva), entradas × saídas dos últimos 6 meses com tabela
  dos números exatos, para onde foi o dinheiro (categorias com fatia do
  total; investido à parte), "onde dá para melhorar" e saldos. A
  conferência completa do mês fica recolhida. Moeda sem nenhum
  lançamento mostra só os saldos.

Paleta categórica validada no fundo escuro: `#3987e5 #d95926 #199e70
#c98500 #d55181 #008300`. A cor acompanha a entidade (renda variável é
sempre a mesma cor). Fonte Inter pelo Google Fonts, com a fonte do
sistema como reserva quando não houver internet.

## Fora do escopo

- Rendimento do CDI da Caixinha não é calculado (entra pelo saldo).
- Nenhuma conversão de moeda; nenhum consolidado em BRL.
