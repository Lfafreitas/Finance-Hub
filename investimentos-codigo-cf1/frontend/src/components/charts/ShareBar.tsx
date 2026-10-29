import { useState } from "react";

import { formatCurrency, formatPercent } from "../../lib/formatCurrency";

export interface ShareItem {
  key: string;
  label: string;
  /** Valor já calculado pelo backend. */
  value: string;
  /** Fração 0..1 já calculada pelo backend. */
  weight: string;
  color: string;
}

interface ShareBarProps {
  items: ShareItem[];
  currency: string;
  /** Rótulo acessível da barra inteira. */
  label: string;
  testId?: string;
}

/**
 * Parte do todo numa barra única de 100%: fatias separadas por 2px de
 * fundo, pontas arredondadas, e a legenda logo abaixo com valor e
 * porcentagem — a cor nunca é a única pista. Passar o mouse numa fatia
 * (ou na linha da legenda) acende as duas e apaga um pouco as outras.
 */
export function ShareBar({ items, currency, label, testId }: ShareBarProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  if (items.length === 0) return null;
  const dim = (key: string) => (hovered !== null && hovered !== key ? "opacity-35" : "");
  return (
    <div data-testid={testId} onMouseLeave={() => setHovered(null)}>
      <div className="reveal-x flex h-3 w-full gap-[2px] overflow-hidden rounded-full" role="img" aria-label={label}>
        {items.map((item) => (
          <div
            key={item.key}
            className={`h-full transition-opacity duration-150 first:rounded-l-full last:rounded-r-full ${dim(item.key)}`}
            style={{ width: `${Math.max(Number(item.weight) * 100, 0.5)}%`, backgroundColor: item.color }}
            title={`${item.label}: ${formatCurrency(item.value, currency)} (${formatPercent(item.weight)})`}
            onMouseEnter={() => setHovered(item.key)}
          />
        ))}
      </div>
      <ul className="mt-3 space-y-0.5 text-sm">
        {items.map((item) => (
          <li
            key={item.key}
            className={`-mx-2 flex items-center gap-2 rounded-md px-2 py-0.5 transition-[opacity,background-color] duration-150 ${dim(
              item.key,
            )} ${hovered === item.key ? "bg-neutral-800/50" : ""}`}
            onMouseEnter={() => setHovered(item.key)}
            data-testid={testId ? `${testId}-${item.key}` : undefined}
          >
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: item.color }}
              aria-hidden="true"
            />
            <span className="text-neutral-300">{item.label}</span>
            <span className="ml-auto tabular-nums text-neutral-100">{formatCurrency(item.value, currency)}</span>
            <span className="w-16 text-right tabular-nums text-neutral-400">{formatPercent(item.weight)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
