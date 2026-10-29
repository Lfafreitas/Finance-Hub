import type { DashboardCurrencyTotals, DashboardSummary, PositionSummary } from "../api/types";

export const MARKET_REASON = "sem cotação utilizável para: PETR4";

export function makePosition(overrides: Partial<PositionSummary> = {}): PositionSummary {
  return {
    account_id: "acc-1",
    asset_id: "asset-1",
    asset_ticker: "PETR4",
    asset_name: "Petrobras",
    currency_code: "BRL",
    currency_inconsistency_reason: null,
    quantity: "10.00000000",
    average_cost: "100.00000000",
    total_cost_basis: "1000.0000000000",
    realized_gain: "50.0000",
    dividends_received: "20.0000",
    realized_cost_basis: "0",
    realized_return_pct: null,
    is_closed: false,
    xirr: null,
    cagr: null,
    profitability_unavailable_reason: null,
    market_price: null,
    market_price_date: null,
    market_value: null,
    unrealized_pnl: null,
    unrealized_return_pct: null,
    unavailable_reason: "sem cotação cadastrada para PETR4",
    ...overrides,
  };
}

export function makeBlock(overrides: Partial<DashboardCurrencyTotals> = {}): DashboardCurrencyTotals {
  return {
    currency_code: "BRL",
    total_cost_basis: "1000.0000000000",
    total_realized_gain: "50.0000",
    total_dividends_received: "20.0000",
    net_contributions: "1000.00",
    total_realized_cost_basis: "0",
    realized_return_pct: null,
    is_closed: false,
    xirr: null,
    cagr: null,
    profitability_unavailable_reason: null,
    market_value: null,
    unrealized_pnl: null,
    current_return: null,
    market_data_as_of: null,
    market_data_unavailable_reason: MARKET_REASON,
    allocation: [
      { asset_id: "asset-1", asset_ticker: "PETR4", asset_name: "Petrobras", cost_basis: "1000.00", percentage: "100.00" },
    ],
    contribution_evolution: [{ date: "2026-01-01", cumulative_net_contribution: "1000.00" }],
    ...overrides,
  };
}

export function makeSummary(overrides: Partial<DashboardSummary> = {}): DashboardSummary {
  return {
    portfolio_id: null,
    positions: [makePosition()],
    totals_by_currency: [makeBlock()],
    ...overrides,
  };
}

// --- Cenário BRL + USD com valores propositalmente inconfundíveis ---------
// Cada número só existe em UMA moeda, para um teste poder afirmar que
// nada de uma aparece na aba da outra.

export const brlBlock = makeBlock({
  currency_code: "BRL",
  total_cost_basis: "1111.00",
  total_realized_gain: "222.00",
  total_dividends_received: "33.00",
  net_contributions: "4444.00",
  allocation: [
    { asset_id: "asset-br", asset_ticker: "PETR4", asset_name: "Petrobras", cost_basis: "1111.00", percentage: "100.00" },
  ],
  contribution_evolution: [{ date: "2026-01-01", cumulative_net_contribution: "4444.00" }],
});

export const usdBlock = makeBlock({
  currency_code: "USD",
  total_cost_basis: "7777.00",
  total_realized_gain: "-888.00",
  total_dividends_received: "99.00",
  net_contributions: "6666.00",
  allocation: [
    { asset_id: "asset-us", asset_ticker: "AAPL", asset_name: "Apple", cost_basis: "7777.00", percentage: "100.00" },
  ],
  contribution_evolution: [{ date: "2026-02-02", cumulative_net_contribution: "6666.00" }],
  market_data_unavailable_reason: "sem cotação utilizável para: AAPL",
});

export const brlPosition = makePosition({
  asset_id: "asset-br",
  asset_ticker: "PETR4",
  currency_code: "BRL",
  total_cost_basis: "1111.0000",
  average_cost: "11.11000000",
});

export const usdPosition = makePosition({
  asset_id: "asset-us",
  asset_ticker: "AAPL",
  asset_name: "Apple",
  currency_code: "USD",
  total_cost_basis: "7777.0000",
  average_cost: "77.77000000",
  unavailable_reason: "sem cotação cadastrada para AAPL",
});

export const INCONSISTENCY_REASON =
  "transações ativas em mais de uma moeda (BRL, USD) — valores não calculados e posição fora dos totais até a correção dos dados";

export const inconsistentPosition = makePosition({
  account_id: "acc-mix",
  asset_id: "asset-mix",
  asset_ticker: "MIXD3",
  asset_name: "Misturada",
  currency_code: null,
  currency_inconsistency_reason: INCONSISTENCY_REASON,
  quantity: "15.00000000",
  average_cost: null,
  total_cost_basis: null,
  realized_gain: null,
  dividends_received: null,
  realized_cost_basis: null,
  profitability_unavailable_reason: INCONSISTENCY_REASON,
});

export const BRL_ONLY_TEXTS = ["PETR4", "1.111,00", "222,00", "33,00", "4.444,00", "11,11"];
export const USD_ONLY_TEXTS = ["AAPL", "7.777,00", "888,00", "99,00", "6.666,00", "77,77"];

// --- Bloco e posição VALORADOS (Fase 12) -----------------------------------

export const valuedPosition = makePosition({
  market_price: "33.00000000",
  market_price_date: "2026-06-29",
  market_value: "3300.0000",
  unrealized_pnl: "300.0000",
  unrealized_return_pct: "0.1",
  unavailable_reason: null,
});

export const valuedBlock = makeBlock({
  market_value: "3300.00",
  unrealized_pnl: "300.00",
  current_return: "0.1",
  market_data_as_of: "2026-06-29",
  market_data_unavailable_reason: null,
});
