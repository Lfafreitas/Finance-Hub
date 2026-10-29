// Rótulos e formatação dos indicadores (KPIs-1 e relatório v2 do Claude).

import type { HoldingReading, InsightReportRead, KeyMetric, MetricCode } from "../api/insights";
import { formatPercent, formatSignedPercent } from "./formatCurrency";

export const METRIC_LABELS: Record<MetricCode, string> = {
  RETURN_1M: "Retorno em 1 mês",
  RETURN_YTD: "Retorno no ano",
  RETURN_1Y: "Retorno em 12 meses",
  RETURN_3Y_ANNUALIZED: "Retorno em 3 anos (ao ano)",
  DIVIDEND_YIELD: "Dividend yield",
  EXPENSE_RATIO: "Taxa de administração",
  OCCUPANCY: "Ocupação",
  EARNINGS_GROWTH: "Crescimento do lucro",
  YIELD_TO_MATURITY: "Taxa até o vencimento",
  PE_TTM: "P/L (12 meses)",
  PE_FORWARD: "P/L projetado",
  P_FFO: "P/FFO",
  PRICE_TO_BOOK: "P/VP",
  BETA: "Beta",
  DEBT_TO_EBITDA: "Dívida/EBITDA",
};

const FRACTIONS = new Set<MetricCode>([
  "RETURN_1M",
  "RETURN_YTD",
  "RETURN_1Y",
  "RETURN_3Y_ANNUALIZED",
  "DIVIDEND_YIELD",
  "EXPENSE_RATIO",
  "OCCUPANCY",
  "EARNINGS_GROWTH",
  "YIELD_TO_MATURITY",
]);

const SIGNED = new Set<MetricCode>(["RETURN_1M", "RETURN_YTD", "RETURN_1Y", "RETURN_3Y_ANNUALIZED", "EARNINGS_GROWTH"]);

/** "3,85%", "+12,40%", "17,2x", "1,05". */
export function formatMetric(metric: KeyMetric): string {
  if (FRACTIONS.has(metric.code)) {
    return SIGNED.has(metric.code) ? formatSignedPercent(String(metric.value)) : formatPercent(String(metric.value));
  }
  if (metric.code === "BETA") return metric.value.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  return `${metric.value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}x`;
}

/** Os indicadores mais úteis primeiro; o imobiliário mostra P/FFO e ocupação. */
const ORDER: MetricCode[] = [
  "DIVIDEND_YIELD",
  "P_FFO",
  "OCCUPANCY",
  "PE_FORWARD",
  "PE_TTM",
  "EXPENSE_RATIO",
  "YIELD_TO_MATURITY",
  "BETA",
  "PRICE_TO_BOOK",
  "DEBT_TO_EBITDA",
  "EARNINGS_GROWTH",
  "RETURN_YTD",
  "RETURN_1Y",
  "RETURN_1M",
  "RETURN_3Y_ANNUALIZED",
];

export function sortMetrics(metrics: KeyMetric[]): KeyMetric[] {
  return [...metrics].sort((a, b) => ORDER.indexOf(a.code) - ORDER.indexOf(b.code));
}

/** Leitura do Claude de cada ativo (do relatório mais recente), por código. */
export function readingsByTicker(report: InsightReportRead | null): Map<string, HoldingReading> {
  return new Map((report?.report.holdings ?? []).map((holding) => [holding.ticker, holding]));
}

/** Valor nulo vira "—"; fração vira percentual com sinal. */
export function signedPct(value: string | null): string {
  return value === null ? "—" : formatSignedPercent(value);
}

export function pct(value: string | null): string {
  return value === null ? "—" : formatPercent(value);
}

/** Cor de texto pelo sinal; o sinal também vai no texto. */
export function toneOf(value: string | null): string {
  if (value === null) return "text-neutral-500";
  const n = Number(value);
  if (n > 0) return "text-emerald-400";
  if (n < 0) return "text-red-400";
  return "text-neutral-300";
}

/** 0.7778 → "2,78" (número efetivo de ativos). */
export function formatDecimal(value: string | null, digits = 1): string {
  if (value === null) return "—";
  return Number(value).toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
