import type { FinancialHealth } from "../../api/performance";
import { coverageText, coverageTone, monthsText } from "../../lib/financialHealth";
import { formatCurrency, formatSignedPercent } from "../../lib/formatCurrency";
import { PANEL_CLASS, SECTION_TITLE_CLASS } from "../../lib/ui";

const SCALE = 12; // a régua vai até 12 meses de gasto
const TONE_TEXT = {
  low: "menos de 3 meses de gasto",
  ok: "entre 3 e 6 meses de gasto",
  good: "6 meses de gasto ou mais",
} as const;

function CoverageMeter({ health }: { health: FinancialHealth }) {
  const months = Number(health.coverage_months);
  const fill = Math.min(months, SCALE) / SCALE;
  return (
    <div className="mt-4" aria-hidden="true">
      <div className="relative h-2 rounded-full bg-neutral-800">
        <div className="h-full rounded-full bg-sky-400" style={{ width: `${fill * 100}%` }} />
        {[3, 6].map((mark) => (
          <span
            key={mark}
            className="absolute -top-1 h-4 w-0.5 rounded-full bg-neutral-500"
            style={{ left: `calc(${(mark / SCALE) * 100}% - 1px)` }}
          />
        ))}
      </div>
      <div className="relative mt-1.5 h-4 text-[11px] text-neutral-500">
        {[3, 6, 12].map((mark) => (
          <span
            key={mark}
            className="absolute -translate-x-1/2 tabular-nums last:translate-x-[-100%]"
            style={{ left: `${(mark / SCALE) * 100}%` }}
          >
            {mark === 12 ? "12+" : mark}
          </span>
        ))}
      </div>
    </div>
  );
}

function Figure({ label, value, note, testId }: { label: string; value: string; note?: string; testId: string }) {
  return (
    <div className="py-4 sm:px-5 sm:py-0 sm:first:pl-0" data-testid={testId}>
      <p className="text-sm text-neutral-400">{label}</p>
      <p className="mt-1 text-xl font-medium tabular-nums text-neutral-50">{value}</p>
      {note && <p className="mt-0.5 text-xs text-neutral-500">{note}</p>}
    </div>
  );
}

function CurrencyHealth({ health, onOpenReview }: { health: FinancialHealth; onOpenReview?: () => void }) {
  const c = health.currency_code;
  const coverage = coverageText(health);
  const tone = coverageTone(health);
  const period = monthsText(health.months);
  return (
    <div className={PANEL_CLASS} data-testid={`health-${c}`}>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-10">
        <div>
          <p className="text-sm text-neutral-400">A reserva cobre</p>
          <p className="figure-hero mt-1 text-[2.25rem] text-neutral-50" data-testid={`health-coverage-${c}`}>
            {coverage ?? "—"}
          </p>
          <p className="mt-1 text-sm text-neutral-400">
            {coverage === null
              ? health.complete
                ? "Sem gasto registrado nos meses fechados para comparar."
                : "Os gastos desses meses ainda estão sem classificação: classifique para ver a cobertura."
              : `de gasto médio, com ${formatCurrency(health.reserve, c)} guardados`}
          </p>
          {tone && (
            <>
              <CoverageMeter health={health} />
              <p className="text-xs text-neutral-500" data-testid={`health-band-${c}`}>
                Faixa: {TONE_TEXT[tone]}. As marcas são as referências usuais de reserva de emergência (3 e 6 meses).
              </p>
            </>
          )}
        </div>
        <div className="grid grid-cols-1 divide-y divide-neutral-800 self-start sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          <Figure
            testId={`health-savings-${c}`}
            label="Taxa de poupança"
            value={health.savings_rate === null ? "—" : formatSignedPercent(health.savings_rate)}
            note="da renda que sobrou depois dos gastos"
          />
          <Figure
            testId={`health-expenses-${c}`}
            label="Gasto médio"
            value={health.avg_expenses === null ? "—" : formatCurrency(health.avg_expenses, c, 0)}
            note="por mês"
          />
          <Figure
            testId={`health-invested-${c}`}
            label="Investido"
            value={health.avg_invested === null ? "—" : formatCurrency(health.avg_invested, c, 0)}
            note="por mês, líquido"
          />
        </div>
      </div>
      <p className="mt-5 border-t border-neutral-800 pt-3 text-xs text-neutral-500">
        {period
          ? `Média de ${period} (meses fechados; o mês atual fica de fora).`
          : "Ainda sem mês fechado com movimento."}
      </p>
      {!health.complete && (
        <p
          className="mt-2 flex flex-wrap items-baseline gap-x-2 text-xs text-amber-300"
          data-testid={`health-incomplete-${c}`}
        >
          <span>
            Há lançamentos sem classificação em {monthsText(health.incomplete_months)}: os gastos estão incompletos,
            então a cobertura é um teto e a taxa de poupança é provisória.
          </span>
          {onOpenReview && (
            <button type="button" className="text-sky-300 underline-offset-4 hover:underline" onClick={onOpenReview}>
              Classificar
            </button>
          )}
        </p>
      )}
    </div>
  );
}

/**
 * Saúde financeira: quantos meses de gasto a reserva cobre, quanto da
 * renda sobra e quanto vai para investimentos — com os meses fechados do
 * controle financeiro. Cada moeda à parte.
 */
export function FinancialHealthPanel({
  currencies,
  onOpenReview,
}: {
  currencies: FinancialHealth[];
  onOpenReview?: () => void;
}) {
  if (currencies.length === 0) return null;
  return (
    <section aria-labelledby="health-title" data-testid="financial-health">
      <h2 id="health-title" className={`mb-3 ${SECTION_TITLE_CLASS}`}>
        Reserva e poupança
      </h2>
      <div className="space-y-4">
        {currencies.map((h) => (
          <CurrencyHealth key={h.currency_code} health={h} onOpenReview={onOpenReview} />
        ))}
      </div>
    </section>
  );
}
