import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ContributionPoint } from "../api/types";
import { AXIS_TEXT_COLOR, GRID_COLOR, MAGNITUDE_COLOR } from "../lib/chartColors";
import { formatCompactCurrency, formatCurrency, formatIsoDate } from "../lib/formatCurrency";
import { CROSSHAIR, NoTooltip, activeDot, chartMotion, useScrub } from "./charts/chartKit";

interface ContributionChartProps {
  points: ContributionPoint[];
  currency: string;
}

function shortDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return match ? `${match[3]}/${match[2]}` : iso;
}

/** Quanto dinheiro você já colocou (acumulado), ao longo do tempo. */
export function ContributionChart({ points, currency }: ContributionChartProps) {
  const scrub = useScrub(points.length);
  if (points.length === 0) {
    return <p className="text-neutral-500">Sem movimentações de aporte/retirada ainda.</p>;
  }

  const data = points.map((point) => ({
    date: point.date,
    value: Number(point.cumulative_net_contribution),
    raw: point.cumulative_net_contribution,
  }));
  const last = points[points.length - 1];
  const focus = points[Math.min(scrub.focus ?? points.length - 1, points.length - 1)];
  const scrubbing = scrub.index !== null;

  return (
    <div data-testid="contribution-chart">
      <p className="mb-2 text-xs text-neutral-500">
        Dinheiro que você já colocou, acumulado — não é patrimônio nem desempenho de mercado.{" "}
        <span aria-live="polite">
          {scrubbing ? `Até ${formatIsoDate(focus.date)}: ` : "Hoje: "}
          <span className="tabular-nums text-neutral-300" data-testid="contribution-last">
            {formatCurrency((scrubbing ? focus : last).cumulative_net_contribution, currency)}
          </span>
        </span>
      </p>
      <div
        role="group"
        aria-label="Aportes: use as setas para percorrer"
        className="cursor-crosshair rounded-lg"
        {...scrub.keyboardProps}
      >
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 0 }} {...scrub.chartProps}>
            <CartesianGrid stroke={GRID_COLOR} vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={shortDate}
              stroke={GRID_COLOR}
              tick={{ fill: AXIS_TEXT_COLOR, fontSize: 12 }}
              tickLine={false}
              minTickGap={24}
            />
            <YAxis
              tickFormatter={(value: number) => formatCompactCurrency(value, currency)}
              stroke={GRID_COLOR}
              tick={{ fill: AXIS_TEXT_COLOR, fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={72}
            />
            <Tooltip content={NoTooltip} cursor={false} isAnimationActive={false} />
            <Area
              type="stepAfter"
              dataKey="value"
              stroke={MAGNITUDE_COLOR}
              strokeWidth={2}
              fill={MAGNITUDE_COLOR}
              fillOpacity={0.1}
              dot={{ r: 4, fill: MAGNITUDE_COLOR, stroke: "#141b1f", strokeWidth: 2 }}
              activeDot={false}
              {...chartMotion()}
            />
            {scrubbing && <ReferenceLine x={focus.date} {...CROSSHAIR} />}
            {scrubbing && (
              <ReferenceDot
                x={focus.date}
                y={Number(focus.cumulative_net_contribution)}
                {...activeDot(MAGNITUDE_COLOR)}
                r={6}
              />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
