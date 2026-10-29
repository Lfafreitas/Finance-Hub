import { formatCurrency, formatPercent } from "../lib/formatCurrency";

interface IndicatorCardProps {
  label: string;
  value: string | null;
  /** Moeda em que `value` JÁ ESTÁ. Obrigatória: não existe moeda padrão. */
  currencyCode: string;
  /** "percent": `value` é uma fração (0.10 = 10%), não um valor em dinheiro. */
  format?: "currency" | "percent";
  unavailableReason?: string | null;
  tone?: "neutral" | "positive" | "negative";
}

export function IndicatorCard({
  label,
  value,
  currencyCode,
  format = "currency",
  unavailableReason,
  tone = "neutral",
}: IndicatorCardProps) {
  const isUnavailable = value === null;
  const toneClass =
    tone === "positive" ? "text-emerald-400" : tone === "negative" ? "text-red-400" : "text-neutral-100";

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
      <p className="text-sm text-neutral-400">{label}</p>
      {isUnavailable ? (
        <div>
          <p className="mt-1 text-lg font-medium text-neutral-500" data-testid="indicator-unavailable">
            Indisponível
          </p>
          {unavailableReason && <p className="mt-1 text-xs text-neutral-500">{unavailableReason}</p>}
        </div>
      ) : (
        <p className={`mt-1 text-2xl font-semibold ${toneClass}`}>
          {format === "percent" ? formatPercent(value) : formatCurrency(value, currencyCode)}
        </p>
      )}
    </div>
  );
}
