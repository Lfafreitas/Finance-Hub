// Patrimônio por moeda e visão do caixa mês a mês (Visual-1).

import { request } from "./client";

export interface OverviewPart {
  key: "VARIABLE" | "FIXED" | "RESERVE" | "LIQUID" | "FUND" | "OTHER";
  label: string;
  value: string;
  weight: string;
}

export interface CurrencyOverview {
  currency_code: string;
  total: string;
  investments_value: string;
  investments_cost: string;
  /** MARKET: tudo com cotação; MIXED: parte pelo custo; COST: nenhuma cotação. */
  investments_basis: "MARKET" | "MIXED" | "COST";
  unpriced: string[];
  result: string;
  result_pct: string | null;
  result_complete: boolean;
  net_contributions: string;
  liquid: string;
  reserve: string;
  card: string;
  parts: OverviewPart[];
  investment_groups: OverviewPart[];
}

export interface Overview {
  as_of: string;
  totals_by_currency: CurrencyOverview[];
}

export interface MonthFlow {
  month: string;
  income: string;
  expenses: string;
  surplus: string;
  net_invested: string;
  unclassified_net: string;
  entry_count: number;
}

export interface MonthlyFlows {
  end_month: string;
  months: number;
  totals_by_currency: { currency_code: string; months: MonthFlow[] }[];
}

export interface CurrencySpendingInsights {
  currency_code: string;
  month: string;
  expenses: string;
  history_months: number;
  above_normal: { key: string; label: string; current: string; average: string; difference: string }[];
  recurring: { label: string; monthly_average: string }[];
  recurring_total: string;
  small_count: number;
  small_total: string;
  small_limit: string;
  top_categories: { key: string | null; label: string | null; amount: string; share: string }[];
  top_share: string | null;
  unclassified_outflow: string;
  unclassified_share: string | null;
}

export interface SpendingInsights {
  month: string;
  totals_by_currency: CurrencySpendingInsights[];
}

export function getOverview(): Promise<Overview> {
  return request<Overview>("/overview");
}

export function getMonthlyFlows(endMonth: string, months = 6): Promise<MonthlyFlows> {
  return request<MonthlyFlows>(`/cashflow/summary/monthly?end=${endMonth}&months=${months}`);
}

export function getSpendingInsights(month: string): Promise<SpendingInsights> {
  return request<SpendingInsights>(`/cashflow/insights?month=${month}`);
}

