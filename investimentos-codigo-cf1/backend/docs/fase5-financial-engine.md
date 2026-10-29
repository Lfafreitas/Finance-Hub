# Fase 5 — Financial Engine, Position, Portfolio

## O que foi implementado

- **`app/domain/financial_engine/`** — módulo puro (sem banco, sem HTTP, sem I/O): `PositionCalculator` (posição/preço médio/ganho realizado/proventos), `XIRRCalculator`, `CAGRCalculator`. Opera sobre `TransactionFact`, um dataclass que **não tem campo `status`** — REVERSED não tem como chegar até aqui por construção, não por convenção lembrada.
- **`app/repositories/transactions.py`** — único ponto que consulta `Transaction` para fins de cálculo; filtra `status == ACTIVE` e converte para `TransactionFact`.
- **`Portfolio`** (`app/models/portfolio.py`) — entidade estrutural real (tabela `portfolios` + `accounts.portfolio_id` nullable), 1 Account → 0 ou 1 Portfolio. Não calcula nada, só delimita escopo.
- **`TransactionType.TRANSFER` → `TRANSFER_OUT`/`TRANSFER_IN`** + `linked_transaction_id` (auto-referência), com toda a regra de consistência do par implementada em banco (ver abaixo).
- **`fx_rate_to_brl`** (nullable) em `Transaction` — campo adicionado, semântica documentada no código, ainda sem nenhuma lógica de câmbio construída em cima (D3/D4).

## Decisões implementadas (D1–D7, todas conforme aprovado)

| # | Decisão | Implementação |
|---|---|---|
| D1 | Position calculada, não persistida | `PositionCalculator.calculate()` — sem tabela |
| D2 | TRANSFER_OUT/IN + `linked_transaction_id`, com vínculo bidirecional validado | Ver seção "Trigger de vínculo" |
| D3 | Financial Engine não busca cotação/câmbio | `XIRRCalculator`/`CAGRCalculator` recebem valores prontos; nenhuma chamada externa |
| D4 | `fx_rate_to_brl` adicionado, sem lógica de câmbio ainda | Campo + docstring com a semântica exata (BRL por 1 unidade da moeda do evento) |
| D5 | Custo médio ponderado uniforme BR/exterior | `PositionCalculator` — mesma fórmula para qualquer `Asset`, moeda de negociação nunca convertida internamente |
| D6 | Portfolio como entidade real | Tabela `portfolios` + `accounts.portfolio_id` |
| D7 | Sem `CashHolding` nesta fase | `DEPOSIT`/`WITHDRAWAL` tratados como eventos de fluxo, não saldo persistido |

## Trigger de vínculo de transferência

Duas camadas de validação, ambas **deferidas para o COMMIT** (a FK `fk_transactions_linked_transaction_id` e o trigger `enforce_transfer_link_consistency`) — necessário porque as duas pernas de uma transferência costumam ser gravadas em momentos distintos, e a segunda perna pode nem existir ainda quando a primeira é criada.

Regras implementadas e testadas (SQL manual + pytest via ORM):
- `linked_transaction_id` pode ficar `NULL` (perna solitária, aceita).
- Quando preenchido: a outra ponta deve existir, ser do tipo complementar (`OUT`↔`IN`, nunca `OUT`↔`OUT` nem `IN`↔`IN`), apontar de volta simetricamente, e não pode ser autovínculo.
- Uma vez estabelecido, o vínculo é imutável (reforçado no trigger de imutabilidade da Fase 4, estendido).

## Migration

Uma migration nesta fase (`acfec251182b`): `portfolios` + `accounts.portfolio_id`; recriação do tipo `transaction_type` (TRANSFER → TRANSFER_OUT/TRANSFER_IN — seguro porque a tabela está vazia em uso real); `linked_transaction_id` e `fx_rate_to_brl` em `transactions`; atualização do trigger de imutabilidade; novo trigger de consistência de vínculo. Ciclo `upgrade → downgrade → upgrade` das 4 migrations (Fase 4 + Fase 5) validado do zero.

**Bug real encontrado e corrigido durante a implementação**: a FK de `linked_transaction_id` precisou ser declarada `deferrable=True, initially="DEFERRED"` — sem isso, a primeira perna de uma transferência (apontando para uma segunda perna que ainda não existe, dentro da mesma transação de banco) era rejeitada antes mesmo do commit.

## Testes

**55 passando** no total (21 da Fase 4 + 34 novos):
- `tests/domain/test_position_calculator.py` (puro, sem banco): compra única, compras múltiplas, venda parcial, venda total, venda maior que a posição (rejeitada), bonificação, desdobramento, grupamento, dividendo/JCP (proventos sem afetar posição), taxa avulsa, pré-condições (lista vazia, asset_id ausente, contas misturadas).
- `tests/domain/test_performance_calculator.py` (puro): XIRR com 2 e com múltiplos fluxos irregulares, equivalência XIRR≈CAGR sem fluxo intermediário, validação de entrada (menos de 2 fluxos, todos mesmo sinal), CAGR com datas/valores inválidos.
- `tests/test_portfolio_persistence.py`: criação, nome único por usuário, mesmo nome em usuários diferentes permitido, FK obrigatória.
- `tests/test_transfer_linking.py`: par válido, perna solitária, autovínculo (rejeitado), OUT-OUT (rejeitado), assimetria (rejeitado), imutabilidade do vínculo estabelecido.
- `tests/test_financial_engine_integration.py`: prova de ponta a ponta que uma `Transaction REVERSED` não chega ao `PositionCalculator` via repositório real; prova aritmética de que uma transferência é neutra no agregado das duas contas e visível em cada conta individualmente.

## Lint/format

`ruff check .` → All checks passed. `black --check .` → All done, sem reformatação pendente.

## Reprodutibilidade

`pyxirr` adicionado ao `pyproject.toml`. `pip install -e ".[dev]"` validado do zero após a mudança.

## TWR — Convenção B (aprovada e implementada)

Semântica temporal, 4 instantes ao redor de cada fluxo:

```
(1) valor imediatamente ANTES do fluxo   = value_before_flow (= fim do sub-período anterior, ou capital inicial no primeiro)
(2) fluxo externo                         = external_flow (ocorre entre (1) e (3))
(3) valor imediatamente DEPOIS do fluxo   = value_before_flow + external_flow (derivado)
(4) evolução até o próximo fluxo/avaliação = value_at_period_end

r_i = value_at_period_end / (value_before_flow + external_flow) - 1
```

Convenção de sinal do TWR (diferente da usada no XIRR — documentado explicitamente no código para não confundir os dois): `external_flow` positivo = capital entrando na carteira (aporte, `TRANSFER_IN` daquela conta); negativo = capital saindo (retirada, `TRANSFER_OUT`).

Casos especiais documentados e testados: `DEPOSIT`/`WITHDRAWAL` (fluxo positivo/negativo direto); múltiplos fluxos na mesma data (quem monta a lista deve somá-los antes — sem granularidade intradiária no domínio); fluxo zero (válido, sub-período sem aporte/retirada); primeiro sub-período sem capital (`value_before_flow=0`); retirada que zera a carteira (tratada como neutra — fator 1 — não como erro); denominador zero em qualquer outro caso (erro explícito, nunca divisão silenciosa); `TRANSFER_IN`/`TRANSFER_OUT` no portfolio consolidado (excluídos da lista de fluxos — cancelam-se no agregado, não são aporte/retirada externa) vs. na conta individual (contam normalmente).

**Testes** (`tests/domain/test_twr_calculator.py`, 12 novos): exemplo numérico aprovado (R$1.000→1.100, aporte R$500, 1.600→1.700 = **16,875%**, exato); prova de que o tamanho do aporte não contamina a taxa do sub-período; aportes/retiradas em datas diferentes; múltiplos sub-períodos encadeados; fluxo zero; primeiro período sem capital; retirada total (neutro); dois casos de erro de inconsistência (base zero com valor final não-zero, base negativa); lista vazia; transferência interna excluída do consolidado vs. contando na conta individual.

## Suíte final da Fase 5

**67 testes passando** (21 Fase 4 + 34 Fase 5 inicial + 12 TWR), `ruff`/`black` limpos. Nenhuma migration nova foi necessária para o TWR (cálculo puro, sem schema). Nenhuma parte já implementada (Position, XIRR, CAGR, Portfolio, vínculo de transferência) foi alterada.

**Fase 5 encerrada.**
