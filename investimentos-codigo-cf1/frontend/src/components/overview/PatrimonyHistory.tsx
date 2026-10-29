import { useEffect, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { HistoryPoint, PerformanceHistory } from "../../api/performance";
import { getPerformanceHistory } from "../../api/performance";
import { formatMonth } from "../../lib/analytics";
import { AXIS_TEXT_COLOR, GRID_COLOR, SERIES } from "../../lib/chartColors";
import { formatCompactCurrency, formatCurrency, formatIsoDate, formatSignedCurrency } from "../../lib/formatCurrency";
import { RANGES, monthEnds, periodChange, trimLeadingEmpty } from "../../lib/history";
import { CROSSHAIR, NoTooltip, activeDot, chartMotion, useScrub } from "../charts/chartKit";
import { SegmentedControl } from "../ui/SegmentedControl";

const TOTAL_COLOR = SERIES[0];
const COST_COLOR = "#9eadb6";
const CURRENCY_TITLES: Record<string, string> = { BRL: "Em reais", USD: "Em dólar" };

type Loaded = { status: "loading" } | { status: "error" } | { status: "ready"; data: PerformanceHistory };

function CurrencyHistory({ currency, points }: { currency: string; points: HistoryPoint[] }) {
  const shown = trimLeadingEmpty(points);
  const scrub = useScrub(shown.length);
  const motion = chartMotion();
  if (shown.length < 2) return null;
  const focusIndex = Math.min(scrub.focus ?? shown.length - 1, shown.length - 1);
  const focus = shown[focusIndex];
  const scrubbing = scrub.index !== null;
  const change = periodChange(shown, focusIndex);
  const showCost = shown.some((p) => Number(p.investments_cost) !== 0);
  const last = shown[shown.length - 1];
  const data = shown.map((p) => ({ ...p, totalValue: Number(p.total), costValue: Number(p.investments_cost) }));
  const tone =
    change && change.change > 0
      ? "text-emerald-400"
      : change && change.change < 0
        ? "text-red-400"
        : "text-neutral-300";
  const title = CURRENCY_TITLES[currency] ?? `Em ${currency}`;

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-900 p-5" data-testid={`history-${currency}`}>
      <p className="text-sm text-neutral-400">
        {title} · {currency}
      </p>
      <div aria-live="polite">
        <p className="mt-1 flex flex-wrap items-baseline gap-x-3">
          <span className="figure-hero text-[1.9rem] text-neutral-50" data-testid={`history-value-${currency}`}>
            {formatCurrency(focus.total, currency)}
          </span>
          <span className="text-sm text-neutral-500">{scrubbing ? formatIsoDate(focus.date) : "hoje"}</span>
        </p>
        {change && (
          <p className="mt-1 text-sm" data-testid={`history-change-${currency}`}>
            <span className={`font-medium tabular-nums ${tone}`}>
              {formatSignedCurrency(String(change.change), currency)}
            </span>
            <span className="text-neutral-500">
              {scrubbing
                ? ` de ${formatIsoDate(change.start.date)} a ${formatIsoDate(focus.date)}, com aportes e resgates`
                : ` desde ${formatIsoDate(change.start.date)}, com aportes e resgates`}
            </span>
          </p>
        )}
        {showCost && (
          <p className="mt-0.5 text-xs tabular-nums text-neutral-500" data-testid={`history-detail-${currency}`}>
            Investimentos {formatCurrency(focus.investments_value, currency)} · aplicado{" "}
            {formatCurrency(focus.investments_cost, currency)}
            {Number(focus.cash) !== 0 && <> · caixa {formatCurrency(focus.cash, currency)}</>}
          </p>
        )}
      </div>
      <div
        className="-mx-1 mt-3 cursor-crosshair rounded-lg"
        role="group"
        aria-label={`Evolução ${title.toLowerCase()}: use as setas para percorrer os dias`}
        {...scrub.keyboardProps}
      >
        <ResponsiveContainer width="100%" height={210}>
          <ComposedChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 0 }} {...scrub.chartProps}>
            <defs>
              <linearGradient id={`fill-${currency}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={TOTAL_COLOR} stopOpacity={0.28} />
                <stop offset="100%" stopColor={TOTAL_COLOR} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={GRID_COLOR} vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={(value: string) => formatMonth(value.slice(0, 7)).replace(/\/\d{2}(\d{2})$/, "/$1")}
              stroke={GRID_COLOR}
              tick={{ fill: AXIS_TEXT_COLOR, fontSize: 12 }}
              tickLine={false}
              minTickGap={40}
            />
            <YAxis
              tickFormatter={(value: number) => formatCompactCurrency(value, currency)}
              stroke={GRID_COLOR}
              tick={{ fill: AXIS_TEXT_COLOR, fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={76}
              domain={["auto", "auto"]}
            />
            <Tooltip content={NoTooltip} cursor={false} isAnimationActive={false} />
            <Area
              type="monotone"
              dataKey="totalValue"
              stroke={TOTAL_COLOR}
              strokeWidth={2}
              fill={`url(#fill-${currency})`}
              activeDot={false}
              {...motion}
            />
            {showCost && (
              <Line
                type="stepAfter"
                dataKey="costValue"
                stroke={COST_COLOR}
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
                activeDot={false}
                {...motion}
              />
            )}
            {scrubbing && <ReferenceLine x={focus.date} {...CROSSHAIR} />}
            {scrubbing && showCost && (
              <ReferenceDot x={focus.date} y={Number(focus.investments_cost)} {...activeDot(COST_COLOR)} r={3.5} />
            )}
            {scrubbing && <ReferenceDot x={focus.date} y={Number(focus.total)} {...activeDot(TOTAL_COLOR)} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-400">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: TOTAL_COLOR }} /> Patrimônio (investimentos +
          caixa)
        </span>
        {showCost && (
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-3" style={{ backgroundColor: COST_COLOR }} /> Aplicado nos investimentos
          </span>
        )}
      </div>
      {last.unpriced.length > 0 && (
        <p className="mt-2 text-xs text-amber-300">
          Sem cotação para {last.unpriced.join(", ")}: entram pelo valor aplicado.
        </p>
      )}
      <details className="mt-3">
        <summary className="cursor-pointer text-xs text-neutral-400 hover:text-neutral-200">
          Ver os números mês a mês
        </summary>
        <table className="mt-2 w-full text-right text-xs" data-testid={`history-table-${currency}`}>
          <thead>
            <tr className="text-neutral-500">
              <th className="py-1 text-left font-normal">Fim de</th>
              <th className="py-1 font-normal">Patrimônio</th>
              {showCost && <th className="py-1 font-normal">Investimentos</th>}
              {showCost && <th className="py-1 font-normal">Aplicado</th>}
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {monthEnds(shown).map((p) => (
              <tr key={p.date} className="border-t border-neutral-800/60">
                <td className="py-1 text-left text-neutral-400">{formatMonth(p.date.slice(0, 7))}</td>
                <td className="py-1">{formatCurrency(p.total, currency)}</td>
                {showCost && <td className="py-1">{formatCurrency(p.investments_value, currency)}</td>}
                {showCost && <td className="py-1">{formatCurrency(p.investments_cost, currency)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}

/**
 * Evolução do patrimônio, uma moeda por bloco. Ajustes (saldo inicial,
 * rendimento lançado de uma vez) aparecem como degrau no dia do ajuste.
 */
export function PatrimonyHistory() {
  const [range, setRange] = useState("6m");
  const [loaded, setLoaded] = useState<{ range: string; state: Loaded } | null>(null);
  const days = RANGES.find((r) => r.id === range)?.days ?? null;

  useEffect(() => {
    let cancelled = false;
    getPerformanceHistory(days)
      .then((data) => {
        if (!cancelled) setLoaded({ range, state: { status: "ready", data } });
      })
      .catch(() => {
        if (!cancelled) setLoaded({ range, state: { status: "error" } });
      });
    return () => {
      cancelled = true;
    };
  }, [range, days]);

  const state: Loaded = loaded && loaded.range === range ? loaded.state : { status: "loading" };
  const blocks = state.status === "ready" ? state.data.totals_by_currency : [];

  return (
    <div className="space-y-2" data-testid="patrimony-history">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold tracking-tight text-neutral-100">Evolução do patrimônio</h2>
        <SegmentedControl label="Período" options={RANGES} value={range} onChange={setRange} />
      </div>
      {state.status === "loading" && <p className="text-sm text-neutral-500">Carregando…</p>}
      {state.status === "error" && (
        <p className="text-sm text-neutral-500">Não foi possível carregar a evolução agora.</p>
      )}
      {state.status === "ready" && blocks.length === 0 && (
        <p className="text-sm text-neutral-500">Ainda não há movimentos para mostrar.</p>
      )}
      <div className={`grid grid-cols-1 gap-4 ${blocks.length > 1 ? "lg:grid-cols-2" : ""}`}>
        {blocks.map((block) => (
          <CurrencyHistory key={block.currency_code} currency={block.currency_code} points={block.points} />
        ))}
      </div>
    </div>
  );
}
