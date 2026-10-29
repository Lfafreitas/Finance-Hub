# Fase 8 — Rentabilidade Realizada (retorno absoluto + XIRR/CAGR de histórico fechado)

## Arquivos criados/alterados

```
app/domain/financial_engine/types.py       (alterado, D-E1) + realized_cost_basis em PositionResult
app/domain/financial_engine/position.py    (alterado, D-E1) acumula cost_removed em realized_cost_basis
app/services/profitability_service.py      (novo) toda a lógica de rentabilidade — puro, sem sessão de banco
app/schemas/dashboard.py                   (alterado) + campos de rentabilidade em PositionSummary/DashboardSummary
app/services/dashboard_service.py          (alterado) integra o profitability_service
tests/domain/test_position_calculator.py   (alterado) 2 asserções novas de realized_cost_basis
tests/services/test_profitability_service.py (novo) 8 testes puros
tests/services/test_dashboard_service.py   (alterado) +2 testes de integração
tests/api/test_dashboard_api.py            (alterado) +1 teste, +asserções no existente
```

Frontend: **nenhuma alteração**. A autorização desta etapa definiu onde os dados ficam embutidos no backend (D-D2), mas não pediu UI nova para exibi-los — deixo isso registrado como ponto em aberto (seção "Pendência", abaixo), não como esquecimento.

## Decisões implementadas

- **D-D1**: retorno absoluto realizado sempre disponível; XIRR/CAGR só de histórico fechado; TWR não implementado (fica para a Fase 12).
- **D-D2**: tudo embutido em `DashboardSummary`/`PositionSummary` — sem endpoint dedicado.
- **D-D3**: `is_closed` (por posição e agregado) = quantidade final zero — nunca afetado por XIRR ter ou não sido calculável.
- **CAGR corrigido**: só exposto quando os fluxos do escopo cabem em exatamente 2 datas distintas — testado com um caso de 3 datas confirmando que `cagr` vira `None` mas `xirr` continua calculado.
- **`realized_cost_basis` separado de `total_cost_basis` (remanescente)**: `PositionResult` agora expõe os dois separadamente; `total_cost_basis` manteve o nome e o comportamento de sempre (compatibilidade com Fases 6/7).
- **Especificação formal do XIRR**: implementada exatamente como a tabela da proposta — `BUY`/`SELL`/`DIVIDEND`/`JCP`/`INCOME`/`FEE` entram; eventos societários e `DEPOSIT`/`WITHDRAWAL`/`TRANSFER_*` ficam de fora (D-E2); `REVERSED` nunca chega (filtro centralizado herdado).
- **Regra nova 1 (moeda comum)**: `compute_scope_profitability` verifica `{i.currency_code for i in inputs}` — se houver mais de uma moeda, `xirr`/`cagr` do escopo viram `None` com motivo explícito, sem converter nem inventar taxa. Testado.
- **Regra nova 2 (fechado ≠ calculável)**: testado com um ativo cuja única entrada foi `BONUS_SHARES` (sem `BUY`) — continua `is_closed = True`, mas `xirr = None` com motivo "sem fluxo de entrada e saída conhecidos".
- **Financial Engine continua puro**: `profitability_service` não abre sessão de banco — recebe `TransactionFact`/`PositionResult` já prontos; quem busca no banco é o `dashboard_service`, como já era.

## Testes executados

**Backend**: `tests/services/test_profitability_service.py` (8, puros, sem Postgres) — posição aberta bloqueia XIRR mas permite retorno realizado; XIRR e CAGR batem no caso degenerado (2 datas); CAGR bloqueado com 3 datas mas XIRR calculado; ativo só-bonificação com XIRR indisponível e `is_closed` preservado; escopo combinado de 2 ativos mesma moeda; escopo com posição aberta bloqueia XIRR do escopo; escopo com moedas diferentes não combina; escopo vazio.

`tests/domain/test_position_calculator.py`: 2 asserções novas nos testes já existentes de venda parcial/total (`realized_cost_basis`), sem criar teste novo — os 13 originais continuam intactos.

`tests/services/test_dashboard_service.py`: +2 (posição fechada mostra XIRR no summary; posição aberta mantém XIRR `None` com motivo).

`tests/api/test_dashboard_api.py`: +1 teste novo (posição fechada via API real, HTTP completo) + asserções novas no teste já existente.

**Suíte completa de backend: 109 testes passando** (98 da Fase 7 + 11 novos).

**Frontend**: 16 testes e build inalterados, rodados de novo só para confirmar que nada quebrou (nenhum arquivo tocado).

## Lint/format

`ruff check .` e `black --check .` limpos.

## Inconsistências encontradas durante a implementação

Nenhuma nova além das já antecipadas e resolvidas na proposta revisada (zero-cost-basis, XIRR sem os dois sinais, moeda mista). A implementação seguiu a especificação sem exigir nenhuma outra decisão de correção.

## Pendência explícita (não é falha, é escopo)

O frontend não foi alterado — `xirr`, `cagr`, `realized_return_pct` e `is_closed` já chegam pela API, mas o Dashboard ainda não os exibe. Fica como ponto em aberto para uma futura pequena extensão de UI (reaproveitando o `IndicatorCard` já existente), a ser autorizada explicitamente quando fizer sentido — não assumi isso como parte implícita do escopo desta mensagem.

## Confirmação

**Nenhuma fase posterior foi iniciada.** `Transaction`, migrations e schema do banco não foram tocados — toda a Fase 8 é lógica de serviço sobre dado que já existia. Todas as decisões das Fases 4–7 permanecem como estavam.
