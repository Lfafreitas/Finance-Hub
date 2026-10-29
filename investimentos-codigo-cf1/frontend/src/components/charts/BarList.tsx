import { useState } from "react";
import type { CSSProperties } from "react";

import { MAGNITUDE_COLOR } from "../../lib/chartColors";
import { formatCurrency } from "../../lib/formatCurrency";

export interface BarItem {
  key: string;
  label: string;
  value: string;
  /** Texto à direita do valor (ex.: "47,40%"), já formatado. */
  note?: string;
  /** Rótulo secundário sob o nome. */
  hint?: string;
  /** Recuo para subitens (subcategoria). */
  indent?: boolean;
  color?: string;
}

/**
 * Barras horizontais ordenadas, uma por item, com o valor na ponta. A
 * largura é só proporção visual em relação ao maior item da lista. Passar
 * o mouse (ou focar) num item acende ele e apaga um pouco os outros.
 */
export function BarList({ items, currency, testId }: { items: BarItem[]; currency: string; testId?: string }) {
  const largest = Math.max(...items.map((item) => Math.abs(Number(item.value))), 0);
  const [hovered, setHovered] = useState<string | null>(null);
  return (
    <ul className="space-y-1" data-testid={testId} onMouseLeave={() => setHovered(null)}>
      {items.map((item, i) => {
        const width = largest > 0 ? (Math.abs(Number(item.value)) / largest) * 100 : 0;
        const dimmed = hovered !== null && hovered !== item.key;
        return (
          <li
            key={item.key}
            className={`-mx-2 rounded-lg px-2 py-1 transition-[opacity,background-color] duration-150 ${item.indent ? "pl-7" : ""} ${
              dimmed ? "opacity-45" : ""
            } ${hovered === item.key ? "bg-neutral-800/50" : ""}`}
            onMouseEnter={() => setHovered(item.key)}
            data-testid={testId ? `${testId}-${item.key}` : undefined}
          >
            <div className="flex items-baseline gap-3 text-sm">
              <span className={item.indent ? "text-neutral-400" : "text-neutral-200"}>
                {item.label}
                {item.hint && <span className="ml-2 text-xs text-neutral-500">{item.hint}</span>}
              </span>
              <span className="ml-auto tabular-nums text-neutral-100">{formatCurrency(item.value, currency)}</span>
              {item.note !== undefined && (
                <span className="w-16 text-right tabular-nums text-neutral-400">{item.note}</span>
              )}
            </div>
            <div className="mt-1.5 h-2 rounded-full bg-neutral-800" aria-hidden="true">
              <div
                className="reveal-x h-2 rounded-full"
                style={
                  {
                    width: `${width.toFixed(1)}%`,
                    backgroundColor: item.color ?? MAGNITUDE_COLOR,
                    opacity: item.indent ? 0.7 : 1,
                    "--i": i,
                  } as CSSProperties
                }
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
