import type { HistoryPoint } from "../api/performance";

/** Os primeiros dias sem nada (antes do primeiro movimento da moeda) saem do gráfico. */
export function trimLeadingEmpty(points: HistoryPoint[]): HistoryPoint[] {
  const first = points.findIndex((p) => Number(p.total) !== 0 || Number(p.investments_cost) !== 0);
  return first === -1 ? [] : points.slice(first);
}

export interface PeriodChange {
  start: HistoryPoint;
  end: HistoryPoint;
  /** Diferença do patrimônio total no período (já vem calculado em cada ponto). */
  change: number;
  /** Fração sobre o início; nula quando o início é zero. */
  pct: number | null;
}

/**
 * Variação do patrimônio entre o primeiro dia mostrado e o último (ou o
 * dia em foco no gráfico, `endIndex`). Só
 * apresentação: os totais de cada dia vêm do backend.
 */
export function periodChange(points: HistoryPoint[], endIndex?: number): PeriodChange | null {
  if (points.length < 2) return null;
  const start = points[0];
  const last = endIndex === undefined ? points.length - 1 : Math.min(Math.max(endIndex, 0), points.length - 1);
  const end = points[last];
  const change = Number(end.total) - Number(start.total);
  const base = Number(start.total);
  return { start, end, change, pct: base > 0 ? change / base : null };
}

/** Último ponto de cada mês, para a tabela. */
export function monthEnds(points: HistoryPoint[]): HistoryPoint[] {
  const byMonth = new Map<string, HistoryPoint>();
  for (const point of points) byMonth.set(point.date.slice(0, 7), point);
  return [...byMonth.values()];
}

export const RANGES: { id: string; label: string; days: number | null }[] = [
  { id: "1m", label: "1M", days: 30 },
  { id: "3m", label: "3M", days: 90 },
  { id: "6m", label: "6M", days: 180 },
  { id: "1a", label: "1A", days: 365 },
  { id: "all", label: "Tudo", days: null },
];
