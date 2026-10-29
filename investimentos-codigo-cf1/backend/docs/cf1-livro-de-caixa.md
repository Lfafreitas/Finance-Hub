# CF-1 — Livro de caixa

Primeira unidade do Controle Financeiro. Cria o livro de caixa ao lado
do livro de investimentos, sem tocar em nenhuma regra dele.

## Dois livros, uma tabela de contas

`accounts.account_type` decide o livro:

| Tipo | Livro | Papel |
|---|---|---|
| `BROKERAGE` | investimentos (`transactions`) | corretora |
| `CHECKING`, `CASH` | caixa (`cashflow_entries`) | caixa disponível |
| `SAVINGS` | caixa | reserva sem ativo nem cotação (caixinha, poupança) |
| `CREDIT_CARD` | caixa | passivo: compra é gasto, saldo fica negativo |

Toda conta que existia antes da migration vira `BROKERAGE`. Um banco
que também é corretora são duas contas.

Os livros não se misturam, e isso é garantido no banco (triggers), não
só no service:

- conta `BROKERAGE` não recebe `cashflow_entries`;
- conta de caixa não recebe `transactions`;
- conta que já tem lançamento não troca de livro (trocar entre tipos de
  caixa é permitido).

Nas telas de investimentos (lançamentos, importação, scan de
reconciliação) só aparecem contas `BROKERAGE`.

## `cashflow_entries`

**Fato (imutável por trigger):** conta, `entry_date`, `amount`, moeda,
descrição, origem. Erro de fato se corrige com estorno
(`ACTIVE -> REVERSED`, único caminho) e um lançamento novo. `DELETE` é
recusado.

**Classificação (mutável):** `nature`, contraparte, grupo de
transferência, `notes`.

- `amount` é assinado na moeda da conta: positivo entra, negativo sai.
  A moeda nunca vem do cliente.
- `entry_date` é a data de competência (data da compra, não a do
  pagamento da fatura). Data futura é recusada.
- O sinal é independente da natureza: `EXPENSE` positivo é estorno e
  reduz o gasto; `INCOME` negativo é devolução de renda.

### Naturezas

| Natureza | Uso |
|---|---|
| `INCOME` | renda |
| `EXPENSE` | gasto |
| `THIRD_PARTY` | dinheiro de/para terceiros que não é renda nem gasto (reembolso, divisão de conta, acerto com família) — linha própria, fora do denominador de qualquer taxa |
| `TRANSFER` | movimento entre contas próprias |
| `ADJUSTMENT` | saldo inicial e acertos |
| `UNCLASSIFIED` | padrão de um lançamento novo |

`THIRD_PARTY` nasceu do CF-0: 16,8% das entradas do histórico real não
eram renda nem transferência própria.

### Transferências

- caixa → caixa: duas pernas, mesmo `transfer_group_id`, mesma data,
  valores opostos. Pagamento de fatura é isto (corrente → cartão).
- caixa → `BROKERAGE` (aporte) ou `BROKERAGE` → caixa (resgate): uma
  perna só, no lado do caixa. A outra ponta é do livro de investimentos
  — a ponte entre os dois é o CF-6.
- moedas diferentes: recusado (decisão 7, CF-6).
- estornar uma perna estorna o grupo inteiro.
- transferência não é reclassificada, e um lançamento comum não vira
  transferência por reclassificação: estorna e registra de novo.
  Vincular lançamentos importados como transferência é do CF-3.

## Motor (`app/domain/cashflow_engine`)

Puro: sem banco, sem relógio. Só recebe lançamentos `ACTIVE`. Nunca
soma moedas e nunca converte.

Resumo de um período, por moeda:

```
income + third_party_net + adjustments_net + unclassified_net
    + internal_transfers_net
= expenses + net_invested + liquid_variation + reserve_variation
    + card_balance_variation
```

- `expenses` e `net_invested` são "quanto saiu" (positivos).
- `liquid_variation` = CHECKING + CASH; `reserve_variation` = SAVINGS;
  `card_balance_variation` é negativa quando a dívida cresce.
- `internal_transfers_net` é zero quando as duas pernas estão no
  período; diferente de zero denuncia perna órfã.

A igualdade é conferida a cada cálculo; se não fechar, o motor levanta
`CashflowIdentityError` e não devolve número nenhum.

Saldo de conta = soma dos lançamentos até a data. Não existe saldo
inicial fora do livro.

## API

| Rota | O que faz |
|---|---|
| `POST /cashflow/entries` | lançamento manual (não aceita `TRANSFER`) |
| `GET /cashflow/entries` | lista; filtros `account_id`, `start`, `end`, `include_reversed`, `limit` (≤ 500), `offset` |
| `GET /cashflow/entries/{id}` | um lançamento |
| `PUT /cashflow/entries/{id}/nature` | reclassifica |
| `POST /cashflow/entries/{id}/reverse` | estorna (devolve todos os lançamentos estornados) |
| `POST /cashflow/transfers` | transferência inteira ou nada |
| `GET /cashflow/summary?start&end` | resumo por moeda |
| `GET /cashflow/balances?as_of` | saldo por conta e totais por moeda e papel |

`POST /accounts` aceita `account_type` (padrão `BROKERAGE`);
`GET /accounts` devolve o tipo. Carteira só vincula conta `BROKERAGE`.

## Fora desta unidade

Categorias, tags e regras (CF-2); importação e dedup (CF-3); KPIs
(CF-4); telas do controle financeiro (CF-5); ponte com investimentos e
câmbio (CF-6); recorrência e insights (CF-7); fatura e parcelas (CF-8).
