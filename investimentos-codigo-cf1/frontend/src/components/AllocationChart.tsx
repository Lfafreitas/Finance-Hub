import { useState } from "react";

import type { ConcentrationRead } from "../api/analytics";
import type { AllocationSlice } from "../api/types";
import { PART_COLORS } from "../lib/chartColors";
import { formatPercent } from "../lib/formatCurrency";
import { BarList } from "./charts/BarList";
import { ShareBar } from "./charts/ShareBar";

interface AllocationChartProps {
  currency: string;
  /** Pesos das análises (valor de mercado quando há cotação). */
  concentration: ConcentrationRead | null;
  /** Reserva: distribuição pelo custo, do resumo, se as análises faltarem. */
  allocation: AllocationSlice[];
}

type View = "assets" | "groups";

/**
 * Distribuição da carteira de UMA moeda: por ativo (barras, maior
 * primeiro) ou renda variável × renda fixa (barra única de 100%).
 */
export function AllocationChart({ currency, concentration, allocation }: AllocationChartProps) {
  const [view, setView] = useState<View>("assets");

  const assets = concentration
    ? concentration.by_asset.map((w) => ({ key: w.key, label: w.label, value: w.value, weight: w.weight }))
    : allocation.map((slice) => ({
        key: slice.asset_id,
        label: slice.asset_ticker,
        value: slice.cost_basis,
        weight: String(Number(slice.percentage) / 100),
      }));
  const marketBasis = concentration?.basis === "MARKET";

  if (assets.length === 0) {
    return <p className="text-neutral-500">Sem posições para distribuir.</p>;
  }

  return (
    <div data-testid="allocation-chart">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-neutral-500" data-testid="allocation-basis">
          {marketBasis ? "Pelo valor de mercado." : "Pelo valor aplicado (custo) — falta cotação de algum ativo."}
        </p>
        {concentration && (
          <div className="flex gap-1" role="group" aria-label="Ver distribuição">
            {(
              [
                ["assets", "Por ativo"],
                ["groups", "Renda fixa × variável"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                aria-pressed={view === id}
                onClick={() => setView(id)}
                className={`rounded-md px-2 py-1 text-xs ${
                  view === id ? "bg-neutral-800 text-neutral-100" : "text-neutral-400 hover:text-neutral-100"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {view === "assets" || !concentration ? (
        <BarList
          currency={currency}
          testId="allocation-assets"
          items={assets.map((item) => ({ ...item, note: formatPercent(item.weight) }))}
        />
      ) : (
        <ShareBar
          label={`Renda fixa e variável em ${currency}`}
          currency={currency}
          testId="allocation-groups"
          items={concentration.by_group.map((g) => ({ ...g, color: PART_COLORS[g.key] ?? PART_COLORS.OTHER }))}
        />
      )}
    </div>
  );
}
