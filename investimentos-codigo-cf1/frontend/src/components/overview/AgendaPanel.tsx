import type { Agenda, DividendsSummary, Maturity } from "../../api/performance";
import { daysLeftText, lastMonths, monthLabel, monthShort } from "../../lib/agenda";
import { MAGNITUDE_COLOR } from "../../lib/chartColors";
import { formatCurrency, formatIsoDate, formatPercent } from "../../lib/formatCurrency";
import { PANEL_CLASS, SECTION_TITLE_CLASS } from "../../lib/ui";

const MONTHS_LONG = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

function MaturityRow({ item }: { item: Maturity }) {
  const [year, month, day] = item.maturity_date.split("-");
  const overdue = item.days_left < 0;
  const soon = item.days_left >= 0 && item.days_left <= 30;
  return (
    <li className="flex items-start gap-4 py-3" data-testid={`maturity-${item.ticker}`}>
      <div
        className="w-12 shrink-0 rounded-lg bg-neutral-800/70 py-1.5 text-center"
        aria-label={formatIsoDate(item.maturity_date)}
      >
        <p className="text-lg font-semibold leading-none tabular-nums text-neutral-50">{day}</p>
        <p className="mt-1 text-[11px] text-neutral-400">
          {MONTHS_LONG[Number(month) - 1]}/{year.slice(2)}
        </p>
      </div>
      {/* No celular, valor embaixo do nome; a partir de sm, lado a lado. */}
      <div className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:justify-between sm:gap-4">
        <div className="min-w-0">
          <p className="text-sm font-medium text-neutral-100">
            {item.ticker}
            {item.annual_rate !== null && (
              <span className="ml-2 font-normal text-neutral-400">{formatPercent(item.annual_rate)} a.a.</span>
            )}
          </p>
          <p className={`text-xs ${overdue ? "text-amber-300" : soon ? "text-sky-300" : "text-neutral-400"}`}>
            {daysLeftText(item.days_left)}
            {overdue && " — confira se o valor já voltou para a conta"}
          </p>
        </div>
        <div className="text-sm tabular-nums sm:text-right">
          <p className="whitespace-nowrap text-neutral-100">
            {formatCurrency(item.value ?? item.cost, item.currency_code)}
          </p>
          {item.estimated_at_maturity !== null && (
            <p
              className="text-xs text-neutral-400"
              title="Estimativa: juros compostos da taxa desde a compra, sem impostos"
            >
              ≈ {formatCurrency(item.estimated_at_maturity, item.currency_code)} no vencimento
            </p>
          )}
        </div>
      </div>
    </li>
  );
}

function DividendBars({ summary, currency, asOf }: { summary: DividendsSummary; currency: string; asOf: string }) {
  const months = lastMonths(asOf);
  const amounts = new Map(
    summary.by_month.filter((m) => m.currency_code === currency).map((m) => [m.month, Number(m.amount)]),
  );
  const values = months.map((m) => amounts.get(m) ?? 0);
  const max = Math.max(...values, 0);
  const totals = summary.totals_by_currency.find((t) => t.currency_code === currency);
  return (
    <div data-testid={`dividends-${currency}`}>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm text-neutral-400">Em {currency}</p>
        {totals && (
          <p className="text-sm">
            <span className="tabular-nums text-neutral-100">
              {formatCurrency(totals.total_last_12_months, currency)}
            </span>
            <span className="text-neutral-400"> em 12 meses</span>
          </p>
        )}
      </div>
      <div className="mt-3 flex h-24 items-end gap-1" role="img" aria-label={`Proventos por mês em ${currency}`}>
        {months.map((month, i) => {
          const value = values[i];
          const height = max > 0 ? Math.max((value / max) * 100, value > 0 ? 4 : 0) : 0;
          return (
            <div
              key={month}
              className="group relative flex h-full flex-1 items-end"
              title={`${monthLabel(month)}: ${formatCurrency(String(value), currency)}`}
            >
              {value > 0 ? (
                <div
                  className="w-full rounded-t-[4px]"
                  style={{ height: `${height}%`, backgroundColor: MAGNITUDE_COLOR }}
                />
              ) : (
                <div className="h-px w-full bg-neutral-700" />
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 flex gap-1 text-center text-[10px] text-neutral-500" aria-hidden="true">
        {months.map((month) => (
          <span key={month} className="flex-1">
            {monthShort(month).slice(0, 1)}
          </span>
        ))}
      </div>
      {totals && (
        <p className="mt-2 text-xs text-neutral-500">
          Média de {formatCurrency(totals.average_monthly_last_12_months, currency)} por mês.
        </p>
      )}
    </div>
  );
}

/**
 * Agenda: o que vence na renda fixa (com a estimativa no vencimento) e
 * os proventos recebidos mês a mês nos últimos 12 meses.
 */
export function AgendaPanel({
  agenda,
  dividends,
  onOpenRegistry,
}: {
  agenda: Agenda;
  dividends: DividendsSummary | null;
  onOpenRegistry?: () => void;
}) {
  const currencies = (dividends?.totals_by_currency ?? []).map((t) => t.currency_code);
  return (
    <section aria-labelledby="agenda-title" data-testid="agenda">
      <h2 id="agenda-title" className={`mb-3 ${SECTION_TITLE_CLASS}`}>
        Agenda
      </h2>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className={PANEL_CLASS}>
          <h3 className="text-sm font-medium text-neutral-300">Vencimentos da renda fixa</h3>
          {agenda.maturities.length === 0 ? (
            <p className="mt-3 text-sm text-neutral-400" data-testid="maturities-empty">
              Nenhum vencimento informado.
            </p>
          ) : (
            <ul className="mt-1 divide-y divide-neutral-800">
              {agenda.maturities.map((item) => (
                <MaturityRow key={`${item.currency_code}-${item.ticker}`} item={item} />
              ))}
            </ul>
          )}
          {agenda.missing_maturity.length > 0 && (
            <p className="mt-3 text-xs text-neutral-400" data-testid="maturities-missing">
              Sem vencimento no cadastro: {agenda.missing_maturity.join(", ")}.{" "}
              {onOpenRegistry ? (
                <button
                  type="button"
                  className="text-sky-300 underline-offset-4 hover:underline"
                  onClick={onOpenRegistry}
                >
                  Informar em Cadastros
                </button>
              ) : (
                "Informe em Cadastros → Ativos."
              )}
            </p>
          )}
          {agenda.maturities.some((m) => m.estimated_at_maturity !== null) && (
            <p className="mt-3 text-xs text-neutral-500">
              “≈ no vencimento” é uma estimativa com juros compostos da taxa desde a compra, sem impostos.
            </p>
          )}
        </div>
        <div className={PANEL_CLASS}>
          <h3 className="text-sm font-medium text-neutral-300">Proventos recebidos</h3>
          {currencies.length === 0 ? (
            <p className="mt-3 text-sm text-neutral-400" data-testid="dividends-empty">
              Nenhum provento registrado ainda. Dividendos e juros entram como lançamentos de provento.
            </p>
          ) : (
            <div className="mt-3 space-y-6">
              {currencies.map((currency) => (
                <DividendBars
                  key={currency}
                  summary={dividends as DividendsSummary}
                  currency={currency}
                  asOf={agenda.as_of}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
