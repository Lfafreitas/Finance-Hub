import type { ContributionPaceRead } from "../../api/analytics";
import { PACE_LABELS, formatMonth } from "../../lib/analytics";
import { formatCurrency } from "../../lib/formatCurrency";
import { PANEL_CLASS } from "../../lib/ui";

/** Aportes do ano, mês a mês, e onde eles chegam até dezembro em três ritmos. */
export function ContributionsPanel({ currency, pace }: { currency: string; pace: ContributionPaceRead | null }) {
  if (pace === null) {
    return (
      <div className={PANEL_CLASS} data-testid={`contributions-${currency}`}>
        <h3 className="mb-2 text-sm font-medium text-neutral-300">Ritmo de aporte</h3>
        <p className="text-sm text-neutral-500">
          Nenhum aporte registrado neste ano. Aporte é depósito na conta de investimentos (ou transferência de fora).
        </p>
      </div>
    );
  }
  const largest = Math.max(...pace.months.map((m) => Math.abs(Number(m.amount))), 0);
  return (
    <div className={PANEL_CLASS} data-testid={`contributions-${currency}`}>
      <h3 className="mb-1 text-sm font-medium text-neutral-300">Ritmo de aporte em {pace.year}</h3>
      <p className="mb-3 text-xs text-neutral-500">
        {formatCurrency(pace.total_year, currency)} aportados no ano · faltam {pace.remaining_months}{" "}
        {pace.remaining_months === 1 ? "mês" : "meses"}
      </p>
      <ul className="space-y-1.5">
        {pace.months.map((month) => (
          <li key={month.month} className="grid grid-cols-[4.5rem_1fr_7rem] items-center gap-2 text-sm">
            <span className="text-neutral-400">{formatMonth(month.month)}</span>
            <span className="h-1.5 rounded bg-neutral-800" aria-hidden="true">
              <span
                className={`block h-1.5 rounded ${Number(month.amount) < 0 ? "bg-red-500" : "bg-sky-500"}`}
                style={{ width: largest > 0 ? `${((Math.abs(Number(month.amount)) / largest) * 100).toFixed(1)}%` : "0%" }}
              />
            </span>
            <span className="text-right tabular-nums">{formatCurrency(month.amount, currency)}</span>
          </li>
        ))}
      </ul>
      <table className="mt-4 w-full text-left text-sm" data-testid={`projections-${currency}`}>
        <thead>
          <tr className="border-b border-neutral-800 text-neutral-400">
            <th className="py-2 pr-3">Se continuar no ritmo de</th>
            <th className="py-2 pr-3 text-right">Por mês</th>
            <th className="py-2 pr-3 text-right">Até dezembro</th>
            <th className="py-2 text-right">Total no ano</th>
          </tr>
        </thead>
        <tbody>
          {pace.projections.map((projection) => (
            <tr key={projection.pace} className="border-b border-neutral-900">
              <td className="py-2 pr-3">{PACE_LABELS[projection.pace]}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{formatCurrency(projection.monthly, currency)}</td>
              <td className="py-2 pr-3 text-right tabular-nums">+{formatCurrency(projection.remaining_total, currency)}</td>
              <td className="py-2 text-right tabular-nums">{formatCurrency(projection.year_end_total, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
