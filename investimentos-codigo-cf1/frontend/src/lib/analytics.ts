import type { PaceName } from "../api/analytics";

/** De quanto em quanto tempo a tela busca cotações sozinha. */
export const AUTO_REFRESH_MS = 15 * 60 * 1000;

/** Cotação automática nunca buscada, ou buscada há mais de 15 minutos. */
export function quotesAreStale(refreshedAt: string | null, now: number): boolean {
  if (refreshedAt === null) return true;
  const when = Date.parse(refreshedAt);
  return Number.isNaN(when) || now - when > AUTO_REFRESH_MS;
}

export const PACE_LABELS: Record<PaceName, string> = {
  AVERAGE: "Média do ano",
  LAST_3: "Últimos 3 meses",
  LAST_MONTH: "Este mês",
};

/** "2026-10" → "out/2026". */
export function formatMonth(month: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) return month;
  const names = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  return `${names[Number(match[2]) - 1]}/${match[1]}`;
}

/** Data e hora LOCAIS de um instante ISO: "08/10 às 14:05". */
export function formatRefreshTime(iso: string): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(when.getDate())}/${pad(when.getMonth() + 1)} às ${pad(when.getHours())}:${pad(when.getMinutes())}`;
}
