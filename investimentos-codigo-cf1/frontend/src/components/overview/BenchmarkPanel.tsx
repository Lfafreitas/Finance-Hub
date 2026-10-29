import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { BenchmarkComparison, Benchmarks } from "../../api/performance";
import { AXIS_TEXT_COLOR, GRID_COLOR, SERIES } from "../../lib/chartColors";
import { formatCompactCurrency, formatCurrency, formatIsoDate, formatSignedCurrency } from "../../lib/formatCurrency";
import { signedPct, toneOf } from "../../lib/kpis";
import { PANEL_CLASS, SECTION_TITLE_CLASS } from "../../lib/ui";
import { CROSSHAIR, NoTooltip, activeDot, chartMotion, useScrub } from "../charts/chartKit";

const MINE = SERIES[0];
const REFERENCE = SERIES[2];
const CURRENCY_TITLES: Record<string, string> = { BRL: "Em reais", USD: "Em dólar" };

/**
 * As duas linhas com a leitura do dia em foco no topo: passar o mouse (ou
 * as setas) mostra quanto cada lado valia naquele dia e a diferença.
 */
function ComparisonChart({ item }: { item: BenchmarkComparison }) {
  const currency = item.currency_code;
  const data = item.points.map((p) => ({ ...p, mine: Number(p.portfolio), ref: Number(p.benchmark) }));
  const scrub = useScrub(data.length);
  const motion = chartMotion();
  const focus = data[Math.min(scrub.focus ?? data.length - 1, data.length - 1)];
  const gap = focus.mine - focus.ref;
  return (
    <div className="mt-4">
      <p
        className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm"
        aria-live="polite"
        data-testid={`benchmark-focus-${currency}`}
      >
        <span className="text-neutral-500">{scrub.index === null ? "Hoje" : formatIsoDate(focus.date)}</span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3" style={{ backgroundColor: MINE }} aria-hidden="true" />
          <span className="tabular-nums text-neutral-100">{formatCurrency(focus.portfolio, currency)}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3" style={{ backgroundColor: REFERENCE }} aria-hidden="true" />
          <span className="tabular-nums text-neutral-100">{formatCurrency(focus.benchmark, currency)}</span>
        </span>
        <span className={`tabular-nums ${toneOf(String(gap))}`}>{formatSignedCurrency(gap.toFixed(2), currency)}</span>
      </p>
      <div
        className="-mx-1 mt-2 h-44 cursor-crosshair rounded-lg"
        role="group"
        aria-label={`Sua carteira e o ${item.benchmark_label} com os mesmos aportes: use as setas para percorrer os dias`}
        {...scrub.keyboardProps}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 0 }} {...scrub.chartProps}>
            <CartesianGrid stroke={GRID_COLOR} vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={(value: string) => `${value.slice(8, 10)}/${value.slice(5, 7)}`}
              stroke={GRID_COLOR}
              tick={{ fill: AXIS_TEXT_COLOR, fontSize: 12 }}
              tickLine={false}
              minTickGap={48}
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
            <Line
              type="monotone"
              dataKey="ref"
              stroke={REFERENCE}
              strokeWidth={2}
              dot={false}
              activeDot={false}
              {...motion}
            />
            <Line
              type="monotone"
              dataKey="mine"
              stroke={MINE}
              strokeWidth={2}
              dot={false}
              activeDot={false}
              {...motion}
            />
            {scrub.index !== null && <ReferenceLine x={focus.date} {...CROSSHAIR} />}
            {scrub.index !== null && <ReferenceDot x={focus.date} y={focus.ref} {...activeDot(REFERENCE)} />}
            {scrub.index !== null && <ReferenceDot x={focus.date} y={focus.mine} {...activeDot(MINE)} />}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Comparison({ item }: { item: BenchmarkComparison }) {
  const currency = item.currency_code;
  const title = CURRENCY_TITLES[currency] ?? `Em ${currency}`;
  if (!item.available) {
    return (
      <div className={PANEL_CLASS} data-testid={`benchmark-${currency}`}>
        <p className="text-sm text-neutral-400">
          {title}, comparado ao {item.benchmark_label}
        </p>
        <p className="mt-2 text-sm text-neutral-300" data-testid={`benchmark-reason-${currency}`}>
          {item.reason}
        </p>
      </div>
    );
  }
  const ahead = Number(item.difference) >= 0;
  const data = item.points;
  return (
    <div className={PANEL_CLASS} data-testid={`benchmark-${currency}`}>
      <p className="text-sm text-neutral-400">
        {title}, comparado ao {item.benchmark_label}
      </p>
      <p
        className="mt-2 max-w-2xl text-[15px] leading-relaxed text-neutral-200"
        data-testid={`benchmark-summary-${currency}`}
      >
        Com os mesmos aportes, nas mesmas datas, o {item.benchmark_label} valeria{" "}
        <span className="tabular-nums text-neutral-50">{formatCurrency(item.benchmark_value ?? "0", currency)}</span>.
        Sua carteira vale{" "}
        <span className="tabular-nums text-neutral-50">{formatCurrency(item.portfolio_value ?? "0", currency)}</span>
        {" — "}
        <span className={`font-medium tabular-nums ${toneOf(item.difference)}`}>
          {formatSignedCurrency(item.difference ?? "0", currency)}
        </span>{" "}
        {ahead ? "à frente." : "atrás."}
      </p>
      <dl className="mt-4 grid grid-cols-3 gap-4 text-sm">
        <div>
          <dt className="text-xs text-neutral-500">Aportado (líquido)</dt>
          <dd className="mt-0.5 tabular-nums text-neutral-100">{formatCurrency(item.net_invested ?? "0", currency)}</dd>
        </div>
        <div>
          <dt className="text-xs text-neutral-500">Sua carteira</dt>
          <dd className={`mt-0.5 tabular-nums ${toneOf(item.portfolio_return)}`}>{signedPct(item.portfolio_return)}</dd>
        </div>
        <div>
          <dt className="text-xs text-neutral-500">{item.benchmark_label}</dt>
          <dd className={`mt-0.5 tabular-nums ${toneOf(item.benchmark_return)}`}>{signedPct(item.benchmark_return)}</dd>
        </div>
      </dl>
      {data.length >= 2 && <ComparisonChart item={item} />}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-400">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3" style={{ backgroundColor: MINE }} /> Sua carteira
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3" style={{ backgroundColor: REFERENCE }} /> {item.benchmark_label} com os mesmos
          aportes
        </span>
      </div>
      <p className="mt-3 text-xs text-neutral-500">
        {item.benchmark === "CDI"
          ? "CDI acumulado do Banco Central, antes de impostos."
          : "Só preço, sem dividendos, dos dois lados."}{" "}
        Proventos recebidos não entram.
        {item.unpriced.length > 0 && ` Sem cotação, entram pelo custo: ${item.unpriced.join(", ")}.`}
      </p>
    </div>
  );
}

/** Sua carteira contra a referência da moeda, com os mesmos aportes nas mesmas datas. */
export function BenchmarkPanel({ benchmarks }: { benchmarks: Benchmarks }) {
  if (benchmarks.comparisons.length === 0) return null;
  return (
    <section aria-labelledby="benchmark-title" data-testid="benchmarks">
      <h2 id="benchmark-title" className={`mb-3 ${SECTION_TITLE_CLASS}`}>
        Comparação com a referência
      </h2>
      <div className={`grid grid-cols-1 gap-4 ${benchmarks.comparisons.length > 1 ? "lg:grid-cols-2" : ""}`}>
        {benchmarks.comparisons.map((item) => (
          <Comparison key={item.currency_code} item={item} />
        ))}
      </div>
    </section>
  );
}
