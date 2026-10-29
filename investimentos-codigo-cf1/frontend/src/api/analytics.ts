// Análises da carteira e atualização automática de cotações
// (Análises-1). Valores chegam calculados; a tela só formata.

import { request } from "./client";

export interface WeightRead {
  key: string;
  label: string;
  value: string;
  /** Fração: 0.25 = 25%. */
  weight: string;
}

export interface ConcentrationRead {
  /** MARKET: pesos pelo valor de mercado; COST: pelo custo (falta cotação). */
  basis: "MARKET" | "COST";
  total: string;
  by_asset: WeightRead[];
  by_class: WeightRead[];
  by_account: WeightRead[];
  /** Renda variável, renda fixa, fundos (chaves VARIABLE, FIXED, FUND, OTHER). */
  by_group: WeightRead[];
  top3_weight: string;
  flags: string[];
}

export interface HoldingAssumptionRead {
  key: string;
  weight: string;
  volatility: string;
  volatility_from_history: boolean;
  history_returns: number;
  expected_return: string;
}

export interface ScenariosRead {
  until: string;
  horizon_days: number;
  value_today: string;
  expected_return: string;
  volatility: string;
  pessimistic_return: string;
  realistic_return: string;
  optimistic_return: string;
  pessimistic_value: string;
  realistic_value: string;
  optimistic_value: string;
  probability_below_today: string;
  assumptions: HoldingAssumptionRead[];
  excluded: { key: string; reason: string }[];
}

export type PaceName = "AVERAGE" | "LAST_3" | "LAST_MONTH";

export interface ContributionPaceRead {
  year: number;
  total_year: string;
  months: { month: string; amount: string }[];
  remaining_months: number;
  projections: { pace: PaceName; monthly: string; remaining_total: string; year_end_total: string }[];
}

export interface CurrencyAnalytics {
  currency_code: string;
  market_value: string | null;
  market_data_as_of: string | null;
  concentration: ConcentrationRead | null;
  scenarios: ScenariosRead | null;
  scenarios_unavailable_reason: string | null;
  contributions: ContributionPaceRead | null;
  alerts: string[];
}

export interface PortfolioAnalytics {
  reference_date: string;
  /** Última gravação de cotação automática dos ativos do escopo. */
  quotes_refreshed_at: string | null;
  blocks: CurrencyAnalytics[];
}

export interface QuoteRefreshItem {
  asset_id: string;
  ticker: string;
  status: "OK" | "ERROR" | "UNSUPPORTED";
  message: string | null;
  price: string | null;
  price_date: string | null;
  points: number;
}

export interface QuoteRefreshResult {
  refreshed_at: string;
  items: QuoteRefreshItem[];
}

export function getPortfolioAnalytics(portfolioId: string | null, until: string | null): Promise<PortfolioAnalytics> {
  const params = new URLSearchParams();
  if (portfolioId) params.set("portfolio_id", portfolioId);
  if (until) params.set("until", until);
  const query = params.toString();
  return request<PortfolioAnalytics>(`/analytics/portfolio${query ? `?${query}` : ""}`);
}

/** Busca as cotações dos ativos da carteira na fonte automática. */
export function refreshQuotes(): Promise<QuoteRefreshResult> {
  return request<QuoteRefreshResult>("/prices/refresh", { method: "POST" });
}
