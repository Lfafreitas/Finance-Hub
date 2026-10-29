// Jornal da carteira: datas da edição e como mostrar o tamanho da edição.
// Só apresentação; o conteúdo vem validado do backend.

function utcDate(iso: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return null;
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

/** "2026-10-27" → "terça-feira, 27 de outubro de 2026" */
export function longDate(iso: string): string {
  const date = utcDate(iso);
  if (date === null) return iso;
  return date.toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** Dias corridos entre a edição e hoje (data local). */
export function editionAgeDays(reportDate: string, today: Date = new Date()): number {
  const edition = utcDate(reportDate);
  if (edition === null) return 0;
  const local = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((local - edition.getTime()) / 86_400_000);
}

/**
 * Aviso de edição antiga. Fim de semana não conta: a de sexta ainda é a
 * mais nova no sábado, no domingo e na segunda antes das 7h51.
 */
export function staleNotice(reportDate: string, today: Date = new Date()): string | null {
  const days = editionAgeDays(reportDate, today);
  const weekday = today.getDay(); // 0 domingo … 6 sábado
  const allowed = weekday === 1 ? 3 : weekday === 0 ? 2 : 1;
  if (days <= allowed) return null;
  return `Edição de ${days} dias atrás: a análise diária não rodou desde então (o computador precisa estar ligado de manhã).`;
}

/** "07:51" a partir do horário em que a análise foi gerada. */
export function editionTime(generatedAt: string): string | null {
  const when = new Date(generatedAt);
  if (Number.isNaN(when.getTime())) return null;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(when.getHours())}h${pad(when.getMinutes())}`;
}

/** Quantos parágrafos do resumo ficam à mostra antes de "Continuar lendo". */
export const LEAD_PARAGRAPHS = 3;
