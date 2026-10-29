# Moeda-3, telas de trabalho e Fase 12 (cotações)

Estado ao fim destas unidades. O código é a fonte da verdade.

## Moeda-3

`Transaction.currency_code == Asset.currency_code` para toda transação ligada a um ativo, em criação
manual, correção e importação (`_check_currency_matches_asset`, `CurrencyMismatchError`, HTTP 400; na
importação, 422 com o número da linha). Sem ativo (DEPOSIT, WITHDRAWAL, transferências) a moeda do
movimento é livre. CSV/XLSX sem coluna `moeda` continua sendo lido como BRL — e é rejeitado se o
ativo for de outra moeda. A preview já marca a linha com o erro.

## Cadastros e primeira execução

- `GET/POST /assets`, `GET/POST /institutions`, `POST /accounts`, `POST /portfolios`,
  `GET /currencies`, `GET /asset-classes`. Só criação e listagem; sem edição nem exclusão.
- O usuário único é criado na primeira requisição (não é mais preciso inserir um `User` à mão).

## Importação

- A preview marca como erro: ativo não cadastrado, moeda diferente da do ativo e ticker que existe
  em mais de um país (não é resolvido em silêncio).
- O commit é tudo-ou-nada por SAVEPOINT próprio, sem depender do chamador.

## Telas (frontend)

Navegação: Dashboard, Lançamentos, Importar, Cotações, Reconciliação, Cadastros.

- **Lançamentos**: formulário por tipo (campos exibidos espelham a validação do backend), transferência
  entre contas, histórico da conta. Valores vão como texto digitado; o frontend não calcula nada.
- **Importar**: arquivo → preview → escolha de linhas → commit. As linhas voltam ao servidor
  exatamente como vieram (são assinadas). Pré-seleção: só linhas sem erro, não duplicadas e sem
  suspeita de duplicata.
- **Cotações**: informar o preço de um ativo em uma data; lista da última cotação de cada ativo.
- **Cadastros**: instituições, carteiras, contas e ativos.

## Fase 12 — cotações e valoração

- `asset_prices` (migration `d2a6c1e85f34`): ativo, data, preço > 0, moeda (sempre a do ativo), fonte.
  Única fonte hoje: `MANUAL`. `PUT /assets/{id}/prices` substitui a cotação da mesma data;
  data futura é recusada. `GET /assets/{id}/prices`, `GET /prices/latest`.
- `ValuationCalculator` (Financial Engine, puro): valor de mercado = quantidade × preço; P&L não
  realizado = valor de mercado − custo remanescente; retorno = P&L / custo (None se custo zero).
- Dashboard: usa a cotação mais recente até a data de referência (hoje). Sem conversão de moeda:
  cotação em moeda diferente da posição não é aplicada. Posição zerada vale 0 sem cotação.
- Total a mercado do bloco só é publicado quando TODA posição aberta da moeda tem cotação;
  `market_data_as_of` é a cotação mais antiga usada.
- Posição aberta com cotação ganha XIRR/CAGR (valor de mercado como fluxo final na data da
  cotação), desde que a cotação não seja anterior à última movimentação.
- XIRR com todos os fluxos na mesma data passa a ser indisponível (antes saía infinito).

## Fora do escopo, de propósito

- Provedor externo de cotações (a fonte é um enum pronto para receber outros).
- Câmbio e consolidação entre moedas.
- TWR real (precisa de valoração em cada data de fluxo, ou seja, histórico de cotações).
- Saldo em dinheiro: "Patrimônio a mercado" soma só ativos.
- Edição/exclusão de cadastros e correção/estorno pela tela de Lançamentos (a API de correção existe).
