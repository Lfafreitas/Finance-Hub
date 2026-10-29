// Textos da saúde financeira (reserva em meses de gasto, taxa de poupança).
// Os números vêm prontos do backend; aqui só apresentação.

import type { FinancialHealth } from "../api/performance";

const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** "2026-08" → "ago/26" */
export function shortMonth(month: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) return month;
  return `${MONTHS[Number(match[2]) - 1]}/${match[1].slice(2)}`;
}

/** ["2026-08","2026-09","2026-10"] → "ago, set e out/26" (mesmo ano) */
export function monthsText(months: string[]): string {
  if (months.length === 0) return "";
  const labels = months.map(shortMonth);
  const sameYear = months.every((m) => m.slice(0, 4) === months[0].slice(0, 4));
  const names = sameYear ? labels.map((l, i) => (i === labels.length - 1 ? l : l.split("/")[0])) : labels;
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}`;
}

/** "6,2 meses" / "1 mês" / "até 6,2 meses" (gastos incompletos = teto). */
export function coverageText(health: FinancialHealth): string | null {
  if (health.coverage_months === null) return null;
  const value = Number(health.coverage_months);
  const rounded = Math.round(value * 10) / 10;
  const number = rounded.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const unit = rounded === 1 ? "mês" : "meses";
  return `${health.complete ? "" : "até "}${number} ${unit}`;
}

/** Faixas usuais para reserva de emergência (3 e 6 meses de gasto). */
export function coverageTone(health: FinancialHealth): "low" | "ok" | "good" | null {
  if (health.coverage_months === null) return null;
  const value = Number(health.coverage_months);
  if (value < 3) return "low";
  if (value < 6) return "ok";
  return "good";
}
