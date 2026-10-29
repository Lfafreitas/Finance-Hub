# Fase 7 — Dashboard v1 (reduzido e honesto)

## Backend — arquivos criados/alterados

```
app/repositories/accounts.py       (novo) list_accounts, list_portfolios, get_institutions_by_id
app/schemas/account.py             (novo) AccountRead, PortfolioRead
app/schemas/dashboard.py           (novo) PositionSummary, AllocationSlice, ContributionPoint, DashboardSummary
app/services/account_service.py    (novo) get_accounts, get_portfolios
app/services/dashboard_service.py  (novo) get_dashboard_summary — toda a agregação
app/services/exceptions.py         (alterado) + PortfolioNotFoundError
app/api/routers/accounts.py        (novo) GET /accounts, GET /portfolios
app/api/routers/dashboard.py       (novo) GET /dashboard/summary
app/main.py                        (alterado) registra os dois novos routers
```

## Endpoints novos

| Método | Rota | Descrição |
|---|---|---|
| GET | `/accounts` | Contas do usuário atual, com nome da instituição |
| GET | `/portfolios` | Carteiras do usuário atual |
| GET | `/dashboard/summary?portfolio_id=` | Resumo agregado — consolidado se `portfolio_id` omitido |

## Decisões implementadas

- **D-C1**: `DashboardSummary` só preenche com valor real o que é 100% derivável de `Transaction` hoje. `market_value`, `unrealized_pnl`, `current_return` são **sempre `None`**, com `market_data_unavailable_reason` explicando o motivo — em nenhum branch do código esses campos recebem um número.
- **D-C2**: `GET /accounts`/`GET /portfolios` implementados, isolados por usuário (nunca por `user_id` do cliente — mesma dependency da Fase 6).
- **D-C3**: gráfico e campo chamados explicitamente "capital aportado acumulado" (`contribution_evolution`), nunca "patrimônio".
- **D-C4**: `allocation` calculada por `total_cost_basis`, rótulo "CUSTO DE AQUISIÇÃO" explícito no componente do gráfico.
- **D-C5**: `portfolio_id` como filtro do resumo — **generalizei a regra de neutralidade de transferência da Fase 5** (antes só "conta individual" vs. "consolidado de todo o usuário") para qualquer escopo arbitrário de contas: uma `TRANSFER_IN`/`OUT` só conta como fluxo externo ao escopo se a outra perna estiver **fora** do conjunto de contas em análise — testado com portfolio parcial (seção de testes).
- **D-C6**: `recharts` instalado e usado nos dois gráficos.
- **D-C7**: Vitest + React Testing Library configurados, com a cobertura essencial pedida.

## Componentes criados (frontend)

```
src/api/types.ts, src/api/client.ts     tipos e cliente HTTP (Decimal chega como string, nunca recalculado)
src/components/IndicatorCard.tsx        card com estado "Indisponível" explícito quando value=null
src/components/PositionsTable.tsx       tabela de posições (custo, nunca mercado)
src/components/AllocationChart.tsx      pizza por custo de aquisição, rótulo explícito
src/components/ContributionChart.tsx    linha de capital aportado, rótulo explícito
src/components/PortfolioSelector.tsx    filtro de carteira
src/pages/Dashboard.tsx                 orquestra fetch + loading/erro, substitui o placeholder da Fase 3
src/App.tsx                             (alterado) renderiza <Dashboard />
```

## Dependências adicionadas

- **Produção**: `recharts`.
- **Dev**: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`.

## Regra de negócio: onde mora cada coisa

`dashboard_service.get_dashboard_summary` é o único lugar que agrega — reaproveita `get_active_transactions` (Fase 5/6, filtro `ACTIVE` centralizado) e `PositionCalculator` (Fase 5, intocado) por `(conta, ativo)`, soma no Python. O frontend **não soma nada, não calcula preço médio, não decide o que é aporte** — só recebe `DashboardSummary` pronto e formata para exibição (`Number(value).toLocaleString(...)` é formatação, não cálculo financeiro).

## Testes novos

**Backend (13)**: `tests/services/test_dashboard_service.py` — dado de mercado sempre `None` com motivo, soma de custo entre duas contas, percentual de distribuição por custo, filtro por portfolio (contas dentro vs. fora), portfolio de outro usuário rejeitado, transferência neutra no consolidado **e** contando como saída quando um lado sai do escopo do portfolio, exclusão de `REVERSED`. `tests/api/test_dashboard_api.py` — listagem de contas com nome de instituição, isolamento de usuário, listagem de portfolios, resumo com campos de mercado `null`, portfolio inexistente → 404.

**Frontend (16)**: `IndicatorCard.test.tsx` (valor formatado, estado indisponível, nunca renderiza número quando `null`), `PositionsTable.test.tsx` (linha por posição, "Indisponível" na coluna de mercado, estado vazio), `Charts.test.tsx` (rótulos explícitos de custo/aportado em ambos os gráficos, estado vazio), `Dashboard.test.tsx` (loading, indicadores renderizados com 3 cards indisponíveis confirmados, tabela de posições, estado de erro).

## Suíte completa

**98 testes de backend** + **16 testes de frontend** = **114 testes passando**. `ruff check .`/`black --check .` (backend) limpos. `npm run build` (frontend) e `npx vitest run` limpos.

## Problemas encontrados

- Dois ajustes de tipagem TypeScript (`Tooltip formatter` do recharts esperando `ValueType | undefined`, não `number`) — corrigidos.
- Um teste meu com `getByText` ambíguo (rótulo "Resultado realizado" aparece tanto no card quanto no cabeçalho da tabela) — corrigido para `getAllByText`.
- **Aviso de lint aceito conscientemente, não corrigido**: `oxlint` acusa `react(set-state-in-effect)` em `Dashboard.tsx` por chamar `setLoading(true)`/`setError(null)` de forma síncrona dentro do `useEffect` que dispara a busca. É o padrão usual de "iniciar carregamento" em efeitos de fetch — corrigir isso de verdade exigiria introduzir `useReducer` ou uma biblioteca de data-fetching, o que seria refatoração fora do escopo desta fase. Fica registrado como possível melhoria futura, não como pendência silenciada.

## Confirmação

**Nenhuma fase posterior foi iniciada.** Nenhuma autenticação real, cotação/FX, importação, Pluggy, reconciliação, metas ou tributação foi tocada. Nenhuma decisão das Fases 4–6 foi alterada — os únicos pontos novos (`get_dashboard_summary`, os dois routers, os componentes React) são estritamente aditivos.

## Atualização — correção de moedas (Moeda-1)

O contrato de `GET /dashboard/summary` mudou: valores de moedas diferentes nunca são somados.

- `DashboardSummary` tem só `portfolio_id`, `market_data_unavailable_reason`, `positions` e
  `totals_by_currency`. Os totais escalares que existiam no nível de cima foram removidos.
- `totals_by_currency` é a única fonte de totais: um `DashboardCurrencyTotals` por moeda, em ordem
  alfabética de código, com custo, resultado realizado, proventos, aportes, rentabilidade, alocação e
  evolução dos aportes daquela moeda. A alocação soma 100% dentro de cada bloco.
- A moeda de uma posição é a das suas Transactions ativas (não a do cadastro do ativo). Posição com
  Transactions ativas em mais de uma moeda vem com `currency_code = null`,
  `currency_inconsistency_reason` preenchido, só `quantity`/`is_closed` válidos, e fica fora de todos
  os blocos.
- Movimentos de caixa entram no bloco da moeda do próprio movimento.
- `fx_rate_to_brl` não é usado; não existe consolidado convertido.
