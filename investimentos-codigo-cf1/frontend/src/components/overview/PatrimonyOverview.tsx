import type { CurrencyOverview, Overview } from "../../api/overview";
import { PART_COLORS } from "../../lib/chartColors";
import { formatCurrency, formatIsoDate, formatSignedCurrency, formatSignedPercent } from "../../lib/formatCurrency";
import { SECTION_TITLE_CLASS } from "../../lib/ui";
import { useCountUp } from "../../lib/useCountUp";
import { ShareBar } from "../charts/ShareBar";

const CURRENCY_TITLES: Record<string, string> = { BRL: "Em reais", USD: "Em dólar" };

function resultTone(value: string): string {
  const numeric = Number(value);
  if (numeric > 0) return "text-emerald-400";
  if (numeric < 0) return "text-red-400";
  return "text-neutral-300";
}

/** O total sobe até o valor na abertura; no fim, o texto exato do backend. */
function CountingTotal({ value, currency }: { value: string; currency: string }) {
  const target = Number(value);
  const shown = useCountUp(`total-${currency}`, target);
  return <>{formatCurrency(shown === target ? value : shown.toFixed(2), currency)}</>;
}

function CurrencyCard({ block }: { block: CurrencyOverview }) {
  const currency = block.currency_code;
  const hasInvestments = Number(block.investments_cost) > 0 || Number(block.investments_value) > 0;
  return (
    <section
      className="p-6 lg:p-7"
      aria-label={`Patrimônio ${CURRENCY_TITLES[currency] ?? `em ${currency}`}`}
      data-testid={`overview-${currency}`}
    >
      <p className="flex items-baseline gap-2 text-sm text-neutral-400">
        {CURRENCY_TITLES[currency] ?? `Em ${currency}`}
        <span className="rounded bg-neutral-800 px-1.5 py-px text-[11px] font-medium text-neutral-300">{currency}</span>
      </p>
      <p className="figure-hero mt-2 text-[2.75rem] text-neutral-50" data-testid={`overview-total-${currency}`}>
        <CountingTotal value={block.total} currency={currency} />
      </p>

      {hasInvestments && (
        <p className="mt-2 text-sm" data-testid={`overview-result-${currency}`}>
          <span className="text-neutral-400">Investimentos rendem </span>
          <span className={`font-medium tabular-nums ${resultTone(block.result)}`}>
            {formatSignedCurrency(block.result, currency)}
            {block.result_pct !== null && ` (${formatSignedPercent(block.result_pct)})`}
          </span>
          <span className="text-neutral-500"> sobre {formatCurrency(block.investments_cost, currency)} aplicados</span>
        </p>
      )}
      {block.investments_basis !== "MARKET" && (
        <p className="mt-1 text-xs text-amber-300" data-testid={`overview-basis-${currency}`}>
          Sem cotação para {block.unpriced.join(", ")}: {block.unpriced.length === 1 ? "entra" : "entram"} pelo valor
          aplicado, e o rendimento delas ainda não aparece.
        </p>
      )}

      <div className="mt-5">
        <ShareBar
          label={`Composição do patrimônio em ${currency}`}
          currency={currency}
          testId={`overview-parts-${currency}`}
          items={block.parts.map((part) => ({ ...part, color: PART_COLORS[part.key] ?? PART_COLORS.OTHER }))}
        />
      </div>

      {Number(block.card) < 0 && (
        <p
          className="mt-3 flex justify-between gap-4 border-t border-neutral-800 pt-3 text-sm"
          data-testid={`overview-card-${currency}`}
        >
          <span className="text-neutral-400">Fatura do cartão em aberto (já descontada do total)</span>
          <span className="whitespace-nowrap tabular-nums text-red-300">{formatCurrency(block.card, currency)}</span>
        </p>
      )}
    </section>
  );
}

/**
 * Patrimônio de todas as contas, uma coluna por moeda, lado a lado.
 * Moedas não se somam: cada coluna tem o seu total.
 */
export function PatrimonyOverview({ overview }: { overview: Overview }) {
  if (overview.totals_by_currency.length === 0) return null;
  return (
    <div className="space-y-3" data-testid="patrimony-overview">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className={SECTION_TITLE_CLASS}>Patrimônio de todas as contas</h2>
        <p className="text-xs text-neutral-500">Em {formatIsoDate(overview.as_of)}. Moedas não se somam.</p>
      </div>
      <div
        className={`grid grid-cols-1 divide-y divide-neutral-800 rounded-2xl border border-neutral-800 bg-neutral-900 ${
          overview.totals_by_currency.length > 1 ? "lg:grid-cols-2 lg:divide-x lg:divide-y-0" : ""
        }`}
      >
        {overview.totals_by_currency.map((block) => (
          <CurrencyCard key={block.currency_code} block={block} />
        ))}
      </div>
    </div>
  );
}
