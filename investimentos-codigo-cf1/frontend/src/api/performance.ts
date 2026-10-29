// Evolução do patrimônio (Painel-1). Uma série por moeda; moedas não se somam.

import { request } from "./client";

export interface HistoryPoint {
  date: string;
  investments_value: string;
  investments_cost: string;
  cash: string;
  total: string;
  unpriced: string[];
}

export interface PerformanceHistory {
  start: string | null;
  end: string;
  totals_by_currency: { currency_code: string; points: HistoryPoint[] }[];
}

/** Sem `days`, desde o primeiro movimento. */
export function getPerformanceHistory(days: number | null): Promise<PerformanceHistory> {
  return request<PerformanceHistory>(days === null ? "/performance/history" : `/performance/history?days=${days}`);
}

// --- KPIs-1 ----------------------------------------------------------------------

/** Desempenho de PREÇO (sem proventos). Nulo = histórico não cobre o período. */
export interface PriceStats {
  last_price: string | null;
  last_date: string | null;
  return_1m: string | null;
  return_3m: string | null;
  return_ytd: string | null;
  return_1y: string | null;
  volatility_1y: string | null;
  max_drawdown_1y: string | null;
  low_52w: string | null;
  high_52w: string | null;
  position_52w: string | null;
  from_high: string | null;
}

export interface AssetKpis {
  ticker: string;
  name: string;
  asset_class: string;
  asset_class_label: string;
  quantity: string;
  cost: string;
  value: string | null;
  weight: string | null;
  pnl: string | null;
  return_pct: string | null;
  contribution: string | null;
  dividends: string;
  yield_on_cost: string | null;
  day_change_pct: string | null;
  stats: PriceStats;
  /** (resultado + proventos recebidos) / custo. Nulo sem cotação. */
  total_return_pct?: string | null;
}

export interface CurrencyKpis {
  currency_code: string;
  value: string;
  cost: string;
  pnl: string;
  return_pct: string | null;
  complete: boolean;
  unpriced: string[];
  top_ticker: string | null;
  top_weight: string | null;
  top3_weight: string | null;
  effective_assets: string | null;
  positive: number;
  negative: number;
  best: string | null;
  worst: string | null;
  dividends: string;
  yield_on_cost: string | null;
  total_return_pct?: string | null;
  groups: { asset_class: string; label: string; value: string; weight: string }[];
  basket: {
    tickers: string[];
    share_of_portfolio: string;
    return_1y: string;
    volatility_1y: string;
    max_drawdown_1y: string;
  } | null;
  assets: AssetKpis[];
}

export interface PortfolioKpis {
  as_of: string;
  totals_by_currency: CurrencyKpis[];
}

export function getKpis(): Promise<PortfolioKpis> {
  return request<PortfolioKpis>("/performance/kpis");
}

// --- Agenda ----------------------------------------------------------------------

export interface Maturity {
  ticker: string;
  name: string;
  currency_code: string;
  maturity_date: string;
  /** Negativo = já venceu e ainda aparece na carteira. */
  days_left: number;
  annual_rate: string | null;
  cost: string;
  value: string | null;
  /** Juros compostos da taxa desde a 1ª compra, sobre o custo. Só referência. */
  estimated_at_maturity: string | null;
}

export interface Agenda {
  as_of: string;
  maturities: Maturity[];
  missing_maturity: string[];
}

export function getAgenda(): Promise<Agenda> {
  return request<Agenda>("/performance/agenda");
}

// --- Proventos (resumo já existente no backend) ----------------------------------

export interface DividendsSummary {
  totals_by_currency: {
    currency_code: string;
    total_received: string;
    total_last_12_months: string;
    average_monthly_last_12_months: string;
  }[];
  by_month: { month: string; currency_code: string; amount: string }[];
  by_asset: { asset_ticker: string; currency_code: string; amount: string }[];
}

export function getDividendsSummary(): Promise<DividendsSummary> {
  return request<DividendsSummary>("/dividends/summary");
}

// --- Comparação com referência ---------------------------------------------------

export interface BenchmarkComparison {
  currency_code: string;
  benchmark: string;
  benchmark_label: string;
  available: boolean;
  reason: string | null;
  net_invested: string | null;
  portfolio_value: string | null;
  benchmark_value: string | null;
  difference: string | null;
  portfolio_return: string | null;
  benchmark_return: string | null;
  unpriced: string[];
  points: { date: string; portfolio: string; benchmark: string }[];
}

export interface Benchmarks {
  as_of: string;
  comparisons: BenchmarkComparison[];
}

export function getBenchmarks(): Promise<Benchmarks> {
  return request<Benchmarks>("/performance/benchmarks");
}

// --- Alocação-alvo ---------------------------------------------------------------

export interface AllocationRow {
  asset_class: string;
  label: string;
  value: string;
  current_weight: string;
  target_weight: string | null;
  /** atual − alvo (fração; positivo = acima do alvo) */
  gap: string | null;
  /** alvo × total − valor atual (positivo = falta para o alvo) */
  value_gap: string | null;
}

export interface CurrencyAllocation {
  currency_code: string;
  total: string;
  has_targets: boolean;
  rows: AllocationRow[];
}

export interface Allocation {
  currencies: CurrencyAllocation[];
}

export function getAllocation(): Promise<Allocation> {
  return request<Allocation>("/performance/allocation");
}

export function setAllocationTargets(
  currency: string,
  targets: { asset_class_code: string; target_weight: string }[],
): Promise<Allocation> {
  return request<Allocation>(`/performance/allocation/${encodeURIComponent(currency)}`, {
    method: "PUT",
    body: { targets },
  });
}

// --- Saúde financeira ------------------------------------------------------------

/**
 * Uma moeda: médias dos últimos meses fechados (`months`). `complete`
 * falso: há lançamento sem classificação nesses meses — a cobertura vira
 * um teto e a taxa de poupança, provisória.
 */
export interface FinancialHealth {
  currency_code: string;
  months: string[];
  avg_income: string | null;
  avg_expenses: string | null;
  avg_invested: string | null;
  savings_rate: string | null;
  reserve: string;
  coverage_months: string | null;
  complete: boolean;
  incomplete_months: string[];
}

export function getFinancialHealth(): Promise<{ as_of: string; currencies: FinancialHealth[] }> {
  return request<{ as_of: string; currencies: FinancialHealth[] }>("/performance/financial-health");
}
