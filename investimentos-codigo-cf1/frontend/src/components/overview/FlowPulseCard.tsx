import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

import type { MonthFlow } from "../../api/overview";
import { getMonthlyFlows } from "../../api/overview";
import { currentMonth } from "../../lib/cashflow";
import { EXPENSE_COLOR, INCOME_COLOR } from "../../lib/chartColors";
import { shortMonth } from "../../lib/financialHealth";
import { formatCurrency, formatSignedCurrency } from "../../lib/formatCurrency";
import { PANEL_CLASS } from "../../lib/ui";
import { SegmentedControl } from "../ui/SegmentedControl";

type Range = "6" | "12";
const RANGES: { id: Range; label: string }[] = [
  { id: "6", label: "6M" },
  { id: "12", label: "12M" },
];
const CHART_HEIGHT = 168; // px: entradas em cima, saídas embaixo da linha

/**
 * O caixa mês a mês num cartão só: renda subindo da linha, gastos
 * descendo, a sobra do período em destaque. Tocar (ou passar o mouse
 * sobre) um mês contorna a coluna e mostra os números dele. Cada coluna
 * é um botão com o resumo do mês, para leitor de tela e teclado.
 */
export function FlowPulseCard({ currency = "BRL", reloadKey = 0 }: { currency?: string; reloadKey?: number }) {
  const [range, setRange] = useState<Range>("6");
  const [loaded, setLoaded] = useState<{ range: Range; months: MonthFlow[] } | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    getMonthlyFlows(currentMonth(), Number(range))
      .then((flows) => {
        if (!alive) return;
        const block = flows.totals_by_currency.find((b) => b.currency_code === currency);
        setLoaded({ range, months: block?.months ?? [] });
        setSelected(null);
      })
      .catch(() => alive && setLoaded({ range, months: [] }));
    return () => {
      alive = false;
    };
  }, [range, currency, reloadKey]);

  const months = loaded?.range === range ? loaded.months : null;
  // Sem renda nem gasto classificados no período, não há o que desenhar
  // (o aviso de "classificar" já aparece no topo do dashboard).
  if (months !== null && !months.some((m) => Number(m.income) > 0 || Number(m.expenses) > 0)) return null;

  const max = Math.max(1, ...(months ?? []).flatMap((m) => [Number(m.income), Number(m.expenses)]));
  const surplus = (months ?? []).reduce((sum, m) => sum + Number(m.surplus), 0);
  const active = months ? (selected ?? months.length - 1) : null;
  const focus = months && active !== null ? months[active] : null;

  return (
    <section className={`${PANEL_CLASS} overflow-hidden`} aria-labelledby="pulse-title" data-testid="flow-pulse">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id="pulse-title" className="text-[17px] font-semibold tracking-tight text-neutral-50">
            Caixa
          </h2>
          <p className="text-sm text-neutral-400">Renda e gastos, mês a mês</p>
        </div>
        <SegmentedControl label="Meses" options={RANGES} value={range} onChange={setRange} />
      </div>

      <p className="mt-4 flex items-baseline gap-2" data-testid="pulse-total">
        <span
          className={`figure-hero text-[2.25rem] ${surplus < 0 ? "text-red-300" : "text-neutral-50"}`}
          aria-live="polite"
        >
          {months === null ? "—" : formatSignedCurrency(String(surplus), currency)}
        </span>
        <span className="text-[15px] text-neutral-400">{surplus < 0 ? "faltaram" : "sobraram"}</span>
      </p>

      {months === null ? (
        <div className="mt-4 h-[200px] animate-pulse rounded-lg bg-neutral-800/40" aria-hidden="true" />
      ) : (
        <div className="relative mt-4" onPointerLeave={() => setSelected(null)}>
          {focus && (
            <div
              className="pointer-events-none absolute -top-1 z-10 w-44 rounded-xl border border-neutral-700/80 bg-neutral-900/95 px-3 py-2 text-[13px] shadow-[0_8px_24px_rgba(0,0,0,0.45)] backdrop-blur transition-[left] duration-200"
              style={{
                left: `clamp(0px, calc(${((active! + 0.5) / months.length) * 100}% - 88px), calc(100% - 176px))`,
              }}
              data-testid="pulse-tooltip"
            >
              <p className="mb-1 flex justify-between text-neutral-400">
                <span>{shortMonth(focus.month)}</span>
                <span className="tabular-nums text-neutral-100">{formatSignedCurrency(focus.surplus, currency)}</span>
              </p>
              <p className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5 text-neutral-300">
                  <span className="h-2.5 w-2.5 rounded-[3px]" style={{ backgroundColor: INCOME_COLOR }} />
                  Renda
                </span>
                <span className="tabular-nums text-neutral-100">{formatCurrency(focus.income, currency, 0)}</span>
              </p>
              <p className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5 text-neutral-300">
                  <span className="h-2.5 w-2.5 rounded-[3px]" style={{ backgroundColor: EXPENSE_COLOR }} />
                  Gastos
                </span>
                <span className="tabular-nums text-neutral-100">{formatCurrency(focus.expenses, currency, 0)}</span>
              </p>
            </div>
          )}

          <div className="flex items-stretch gap-1.5 pt-24" style={{ height: CHART_HEIGHT + 96 }}>
            {months.map((m, i) => {
              const income = (Number(m.income) / max) * (CHART_HEIGHT * 0.62);
              const expenses = (Number(m.expenses) / max) * (CHART_HEIGHT * 0.38);
              const isActive = i === active;
              return (
                <button
                  key={m.month}
                  type="button"
                  className={`group relative flex flex-1 flex-col items-center rounded-full outline-none transition-shadow ${
                    isActive ? "ring-[1.5px] ring-neutral-300/80 ring-offset-2 ring-offset-neutral-900" : ""
                  }`}
                  onPointerEnter={() => setSelected(i)}
                  onFocus={() => setSelected(i)}
                  onClick={() => setSelected(i)}
                  aria-pressed={isActive}
                  aria-label={`${shortMonth(m.month)}: renda ${formatCurrency(m.income, currency, 0)}, gastos ${formatCurrency(m.expenses, currency, 0)}, sobra ${formatSignedCurrency(m.surplus, currency)}`}
                  data-testid="pulse-month"
                >
                  {/* Renda: cresce para cima a partir da linha. */}
                  <span className="flex w-full flex-1 items-end justify-center">
                    <span
                      className="bar-grow block w-full max-w-[18px] rounded-full"
                      style={
                        {
                          height: Math.max(income, Number(m.income) > 0 ? 4 : 0),
                          backgroundColor: INCOME_COLOR,
                          opacity: isActive ? 1 : 0.42,
                          "--i": i,
                        } as CSSProperties
                      }
                    />
                  </span>
                  <span className="my-1 h-px w-full bg-neutral-700" aria-hidden="true" />
                  {/* Gastos: crescem para baixo. */}
                  <span className="flex w-full items-start justify-center" style={{ height: CHART_HEIGHT * 0.38 }}>
                    <span
                      className="bar-grow block w-full max-w-[18px] rounded-full"
                      style={
                        {
                          height: Math.max(expenses, Number(m.expenses) > 0 ? 4 : 0),
                          backgroundColor: EXPENSE_COLOR,
                          opacity: isActive ? 1 : 0.42,
                          "--i": i,
                          "--origin": "top",
                        } as CSSProperties
                      }
                    />
                  </span>
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex justify-between text-[13px] text-neutral-500">
            <span>{shortMonth(months[0].month)}</span>
            <span className="flex gap-3">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: INCOME_COLOR }} />
                renda
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: EXPENSE_COLOR }} />
                gastos
              </span>
            </span>
            <span>{shortMonth(months[months.length - 1].month)}</span>
          </div>
        </div>
      )}
    </section>
  );
}
