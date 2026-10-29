import type { MarketPulse } from "../../api/insights";
import { formatIsoDate } from "../../lib/formatCurrency";

// Seta + cor: a direção nunca fica só na cor.
const DIRECTION = {
  UP: { arrow: "▲", tone: "text-emerald-300", label: "subiu" },
  DOWN: { arrow: "▼", tone: "text-red-300", label: "caiu" },
  FLAT: { arrow: "■", tone: "text-neutral-400", label: "estável" },
} as const;

/**
 * Faixa de números do mercado no topo do jornal (S&P 500, juros, dólar,
 * Selic…), escrita pelo Claude com data e fonte. Rola de lado no celular.
 */
export function MarketStrip({ items }: { items: MarketPulse[] }) {
  if (items.length === 0) return null;
  return (
    <div className="-mx-1 overflow-x-auto" data-testid="market-strip">
      <ul className="flex min-w-max divide-x divide-neutral-800 text-sm">
        {items.map((item) => {
          const dir = item.direction ? DIRECTION[item.direction] : null;
          return (
            <li
              key={item.label}
              className="px-4 py-2 first:pl-1"
              title={`${item.source}, ${formatIsoDate(item.as_of)}`}
              data-testid="market-item"
            >
              <span className="block text-xs text-neutral-400">{item.label}</span>
              <span className="tabular-nums text-neutral-100">{item.value}</span>
              {item.change && (
                <span className={`ml-2 text-xs tabular-nums ${dir ? dir.tone : "text-neutral-400"}`}>
                  {dir && (
                    <span aria-label={dir.label} className="mr-0.5">
                      {dir.arrow}
                    </span>
                  )}
                  {item.change}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
