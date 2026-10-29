import { Fragment, useState } from "react";

import type { HoldingReading } from "../../api/insights";
import type { AssetKpis, CurrencyKpis } from "../../api/performance";
import { classColor } from "../../lib/chartColors";
import { formatCurrency, formatIsoDate, formatSignedCurrency } from "../../lib/formatCurrency";
import { METRIC_LABELS, formatDecimal, formatMetric, pct, signedPct, sortMetrics, toneOf } from "../../lib/kpis";
import { PANEL_CLASS } from "../../lib/ui";
import { SafeLink } from "../insights/SafeLink";
import { ShareBar } from "../charts/ShareBar";

function Tile({ label, value, detail, testId }: { label: string; value: string; detail?: string; testId: string }) {
  return (
    <div className="border-l border-neutral-800 pl-4 first:border-l-0 first:pl-0" data-testid={testId}>
      <p className="text-xs text-neutral-500">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-neutral-100">{value}</p>
      {detail && <p className="mt-0.5 text-xs text-neutral-400">{detail}</p>}
    </div>
  );
}

/** Onde o preço está entre a mínima e a máxima de 52 semanas. */
function RangeBar({ asset, currency }: { asset: AssetKpis; currency: string }) {
  const { low_52w, high_52w, position_52w, from_high } = asset.stats;
  if (low_52w === null || high_52w === null || position_52w === null) {
    return <span className="text-neutral-500">—</span>;
  }
  const left = Math.min(Math.max(Number(position_52w) * 100, 0), 100);
  return (
    <div
      className="w-32"
      title={`Mínima ${formatCurrency(low_52w, currency)} · máxima ${formatCurrency(high_52w, currency)}`}
    >
      <div
        className="relative h-1.5 rounded-full bg-neutral-800"
        role="img"
        aria-label={`${pct(position_52w)} do caminho entre a mínima e a máxima de 52 semanas`}
      >
        <span
          className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-neutral-900 bg-neutral-100"
          style={{ left: `${left}%` }}
        />
      </div>
      <p className="mt-1 text-[11px] text-neutral-500">
        {from_high === null ? "" : `${signedPct(from_high)} da máxima`}
      </p>
    </div>
  );
}

const HEAD = "whitespace-nowrap px-3 py-2 text-right font-normal first:pl-0 first:text-left";
const CELL = "px-3 py-2.5 text-right tabular-nums first:pl-0 first:text-left";

function AssetRow({
  asset,
  currency,
  reading,
}: {
  asset: AssetKpis;
  currency: string;
  reading: HoldingReading | undefined;
}) {
  const [open, setOpen] = useState(false);
  const metrics = sortMetrics(reading?.key_metrics ?? []);
  const s = asset.stats;
  return (
    <Fragment>
      <tr className="border-t border-neutral-800/70 align-top" data-testid={`kpi-row-${asset.ticker}`}>
        <td className={CELL}>
          <button
            type="button"
            className="flex items-start gap-2 text-left"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <span
              className="mt-1.5 h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: classColor(asset.asset_class) }}
              aria-hidden="true"
            />
            <span>
              <span className="whitespace-nowrap font-semibold text-neutral-100">{asset.ticker}</span>
              <span className="block whitespace-nowrap text-xs text-neutral-500">{asset.asset_class_label}</span>
            </span>
          </button>
        </td>
        <td className={CELL}>{pct(asset.weight)}</td>
        <td className={`${CELL} ${asset.value === null ? "text-neutral-500" : ""}`}>
          {asset.value === null ? "—" : formatCurrency(asset.value, currency)}
        </td>
        <td className={`${CELL} ${toneOf(asset.pnl)}`}>
          {asset.pnl === null ? "—" : formatSignedCurrency(asset.pnl, currency)}
          <span className="block text-xs">{signedPct(asset.return_pct)}</span>
        </td>
        <td className={`${CELL} ${toneOf(asset.total_return_pct ?? null)}`}>
          {signedPct(asset.total_return_pct ?? null)}
        </td>
        <td className={`${CELL} ${toneOf(asset.contribution)}`}>{signedPct(asset.contribution)}</td>
        <td className={`${CELL} ${toneOf(asset.day_change_pct)}`}>{signedPct(asset.day_change_pct)}</td>
        <td className={`${CELL} ${toneOf(s.return_1m)}`}>{signedPct(s.return_1m)}</td>
        <td className={`${CELL} ${toneOf(s.return_ytd)}`}>{signedPct(s.return_ytd)}</td>
        <td className={`${CELL} ${toneOf(s.return_1y)}`}>{signedPct(s.return_1y)}</td>
        <td className={`${CELL} ${s.volatility_1y === null ? "text-neutral-500" : ""}`}>{pct(s.volatility_1y)}</td>
        <td className={`${CELL} ${toneOf(s.max_drawdown_1y)}`}>{signedPct(s.max_drawdown_1y)}</td>
        <td className={`${CELL} text-left`}>
          <RangeBar asset={asset} currency={currency} />
        </td>
      </tr>
      {open && (
        <tr data-testid={`kpi-detail-${asset.ticker}`}>
          <td colSpan={13} className="pb-4 pl-4 pr-3">
            <div className="grid gap-4 rounded-md bg-neutral-950/60 p-4 md:grid-cols-[1fr_1.4fr]">
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <dt className="text-neutral-500">Custo</dt>
                <dd className="text-right tabular-nums">{formatCurrency(asset.cost, currency)}</dd>
                <dt className="text-neutral-500">Proventos recebidos</dt>
                <dd className="text-right tabular-nums">{formatCurrency(asset.dividends, currency)}</dd>
                <dt className="text-neutral-500">Rendimento sobre o custo</dt>
                <dd className="text-right tabular-nums">{pct(asset.yield_on_cost)}</dd>
                <dt className="text-neutral-500">Retorno em 3 meses</dt>
                <dd className={`text-right tabular-nums ${toneOf(s.return_3m)}`}>{signedPct(s.return_3m)}</dd>
                <dt className="text-neutral-500">Faixa de 52 semanas</dt>
                <dd className="text-right tabular-nums">
                  {s.low_52w && s.high_52w
                    ? `${formatCurrency(s.low_52w, currency)} – ${formatCurrency(s.high_52w, currency)}`
                    : "—"}
                </dd>
              </dl>
              <div>
                <p className="mb-2 text-xs text-neutral-500">Indicadores de mercado (análise do Claude)</p>
                {metrics.length === 0 ? (
                  <p className="text-sm text-neutral-500">A análise diária ainda não trouxe indicadores deste ativo.</p>
                ) : (
                  <dl className="grid grid-cols-1 gap-y-1.5 text-sm sm:grid-cols-2 sm:gap-x-6">
                    {metrics.map((metric) => (
                      <div key={metric.code} className="flex items-baseline justify-between gap-3">
                        <dt className="text-neutral-400">{METRIC_LABELS[metric.code]}</dt>
                        <dd className="text-right tabular-nums">
                          {formatMetric(metric)}
                          <span className="block text-[11px] text-neutral-500">
                            {metric.url ? <SafeLink url={metric.url}>{metric.source}</SafeLink> : metric.source},{" "}
                            {formatIsoDate(metric.as_of)}
                          </span>
                        </dd>
                      </div>
                    ))}
                  </dl>
                )}
                {reading && <p className="mt-3 text-sm leading-relaxed text-neutral-400">{reading.reading}</p>}
              </div>
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  );
}

/**
 * Indicadores de uma moeda: concentração, diversificação, renda,
 * desempenho da composição atual e a tabela de cada ativo (clique no
 * ativo para ver custo, proventos e os indicadores de mercado).
 */
export function PortfolioKpis({ block, readings }: { block: CurrencyKpis; readings: Map<string, HoldingReading> }) {
  const currency = block.currency_code;
  const priced = block.positive + block.negative;
  return (
    <section className="space-y-4" aria-labelledby={`kpis-${currency}`} data-testid={`kpis-${currency}`}>
      <h2 id={`kpis-${currency}`} className="text-[15px] font-semibold tracking-tight text-neutral-100">
        Indicadores da carteira em {currency === "USD" ? "dólar" : currency === "BRL" ? "reais" : currency}
      </h2>

      <div className={`${PANEL_CLASS} grid grid-cols-2 gap-y-5 md:grid-cols-5`}>
        <Tile
          testId="kpi-top"
          label="Maior posição"
          value={block.top_ticker ? `${block.top_ticker} ${pct(block.top_weight)}` : "—"}
          detail={block.top3_weight ? `as 3 maiores somam ${pct(block.top3_weight)}` : undefined}
        />
        <Tile
          testId="kpi-effective"
          label="Diversificação"
          value={block.effective_assets ? `${formatDecimal(block.effective_assets)} ativos` : "—"}
          detail="equivalentes de mesmo peso"
        />
        <Tile
          testId="kpi-positive"
          label="No positivo"
          value={priced > 0 ? `${block.positive} de ${priced}` : "—"}
          detail={block.best && block.worst ? `melhor ${block.best}, pior ${block.worst}` : undefined}
        />
        <Tile
          testId="kpi-income"
          label="Proventos recebidos"
          value={formatCurrency(block.dividends, currency)}
          detail={
            block.yield_on_cost
              ? `${pct(block.yield_on_cost)} sobre o custo${
                  block.total_return_pct ? `; resultado com proventos ${signedPct(block.total_return_pct)}` : ""
                }`
              : undefined
          }
        />
        <Tile
          testId="kpi-basket"
          label="Composição atual em 12 meses"
          value={block.basket ? signedPct(block.basket.return_1y) : "—"}
          detail={
            block.basket
              ? `volatilidade ${pct(block.basket.volatility_1y)}, pior queda ${signedPct(block.basket.max_drawdown_1y)}`
              : "precisa de um ano de cotações"
          }
        />
      </div>

      {block.groups.length > 0 && (
        <div className={PANEL_CLASS}>
          <p className="mb-3 text-xs text-neutral-500">Exposição por classe de ativo</p>
          <ShareBar
            testId={`exposure-${currency}`}
            label="Exposição por classe de ativo"
            currency={currency}
            items={block.groups.map((g) => ({
              key: g.asset_class,
              label: g.label,
              value: g.value,
              weight: g.weight,
              color: classColor(g.asset_class),
            }))}
          />
        </div>
      )}

      <div className={`${PANEL_CLASS} overflow-x-auto`}>
        <table className="w-full min-w-[1160px] text-sm" data-testid={`kpi-table-${currency}`}>
          <thead className="text-xs text-neutral-500">
            <tr>
              <th className={HEAD}>Ativo</th>
              <th className={HEAD}>Peso</th>
              <th className={HEAD}>Valor</th>
              <th className={HEAD}>Resultado</th>
              <th className={HEAD} title="Resultado mais os proventos recebidos, sobre o custo">
                Com proventos
              </th>
              <th className={HEAD} title="Pontos percentuais do resultado da carteira que vieram deste ativo">
                Contribuição
              </th>
              <th className={HEAD}>Pregão</th>
              <th className={HEAD}>1 mês</th>
              <th className={HEAD}>No ano</th>
              <th className={HEAD}>12 meses</th>
              <th className={HEAD}>Volatilidade</th>
              <th className={HEAD}>Pior queda</th>
              <th className={`${HEAD} text-left`}>Faixa de 52 semanas</th>
            </tr>
          </thead>
          <tbody>
            {block.assets.map((asset) => (
              <AssetRow key={asset.ticker} asset={asset} currency={currency} reading={readings.get(asset.ticker)} />
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs text-neutral-500">
          Retornos, volatilidade e queda medem só o preço (sem proventos), pelo fechamento diário. “—” quando o
          histórico ainda não cobre o período.
          {block.unpriced.length > 0 && ` Sem cotação, entram pelo custo: ${block.unpriced.join(", ")}.`} Clique no
          ativo para ver os indicadores de mercado.
        </p>
      </div>
    </section>
  );
}
