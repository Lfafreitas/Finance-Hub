// Apoio da agenda: meses da janela de proventos e texto do prazo.

const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** Os `n` meses ("AAAA-MM") que terminam no mês de `asOf`, do mais antigo ao atual. */
export function lastMonths(asOf: string, n = 12): string[] {
  const [y, m] = asOf.split("-").map(Number);
  const out: string[] = [];
  for (let i = n - 1; i >= 0; i--) {
    const total = y * 12 + (m - 1) - i;
    out.push(`${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`);
  }
  return out;
}

/** "2026-10" → "out". */
export function monthShort(month: string): string {
  return MONTHS[Number(month.slice(5, 7)) - 1] ?? month;
}

/** "2026-10" → "out/26". */
export function monthLabel(month: string): string {
  return `${monthShort(month)}/${month.slice(2, 4)}`;
}

/** "faltam 38 dias", "vence hoje", "venceu há 3 dias". */
export function daysLeftText(days: number): string {
  if (days === 0) return "vence hoje";
  if (days === 1) return "vence amanhã";
  if (days > 1) return `faltam ${days} dias`;
  return days === -1 ? "venceu ontem" : `venceu há ${-days} dias`;
}
