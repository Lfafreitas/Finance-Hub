import type { ConcentrationRead, WeightRead } from "../../api/analytics";
import { formatCurrency, formatPercent } from "../../lib/formatCurrency";
import { PANEL_CLASS } from "../../lib/ui";

function Weights({ title, items, currency, testId }: { title: string; items: WeightRead[]; currency: string; testId: string }) {
  return (
    <div>
      <p className="mb-2 text-sm text-neutral-400">{title}</p>
      <ul className="space-y-2" data-testid={testId}>
        {items.map((item) => (
          <li key={item.key}>
            <div className="flex justify-between gap-3 text-sm">
              <span>{item.label}</span>
              <span className="tabular-nums" title={formatCurrency(item.value, currency)}>
                {formatPercent(item.weight)}
              </span>
            </div>
            <div className="mt-1 h-1.5 rounded bg-neutral-800" aria-hidden="true">
              <div className="h-1.5 rounded bg-sky-500" style={{ width: `${(Number(item.weight) * 100).toFixed(1)}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Quanto cada ativo, classe e conta pesa, e os sinais de concentração. */
export function ConcentrationPanel({ currency, concentration }: { currency: string; concentration: ConcentrationRead | null }) {
  if (concentration === null) return null;
  return (
    <div className={PANEL_CLASS} data-testid={`concentration-${currency}`}>
      <h3 className="mb-1 text-sm font-medium text-neutral-300">Concentração</h3>
      <p className="mb-3 text-xs text-neutral-500" data-testid={`basis-${currency}`}>
        {concentration.basis === "MARKET"
          ? `Pesos pelo valor de mercado (${formatCurrency(concentration.total, currency)}).`
          : `Pesos pelo custo (${formatCurrency(concentration.total, currency)}): falta cotação de algum ativo.`}{" "}
        Os 3 maiores somam {formatPercent(concentration.top3_weight)}.
      </p>
      {concentration.flags.length > 0 && (
        <ul className="mb-3 space-y-1 text-sm text-amber-300" data-testid={`flags-${currency}`}>
          {concentration.flags.map((flag) => (
            <li key={flag}>{flag}</li>
          ))}
        </ul>
      )}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <Weights title="Por ativo" items={concentration.by_asset} currency={currency} testId={`by-asset-${currency}`} />
        <Weights title="Por classe" items={concentration.by_class} currency={currency} testId={`by-class-${currency}`} />
        <Weights title="Por conta" items={concentration.by_account} currency={currency} testId={`by-account-${currency}`} />
      </div>
    </div>
  );
}
