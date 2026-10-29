import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { MonthFlow } from "../../../api/overview";
import { formatMonth } from "../../../lib/analytics";
import { AXIS_TEXT_COLOR, EXPENSE_COLOR, GRID_COLOR, INCOME_COLOR } from "../../../lib/chartColors";
import { formatCompactCurrency, formatCurrency, formatSignedCurrency } from "../../../lib/formatCurrency";
import { PANEL_CLASS } from "../../../lib/ui";
import { NoTooltip, chartMotion, useScrub } from "../../charts/chartKit";

/**
 * Entradas (renda) × saídas (gastos) mês a mês, com a sobra de cada
 * mês. Barras lado a lado no mesmo eixo; a tabela abaixo traz os
 * números exatos. Passar o mouse num mês (no gráfico ou na tabela)
 * destaca o mês nos dois e mostra os números dele no topo.
 */
export function MonthlyFlowChart({ currency, months }: { currency: string; months: MonthFlow[] }) {
  const data = months.map((m) => ({
    month: m.month,
    label: formatMonth(m.month).replace(/\/\d{4}$/, ""),
    incomeValue: Number(m.income),
    expensesValue: Number(m.expenses),
    income: m.income,
    expenses: m.expenses,
    surplus: m.surplus,
  }));
  const hasData = months.some((m) => m.entry_count > 0);
  const scrub = useScrub(data.length);
  const motion = chartMotion();
  const focus = scrub.index === null ? null : months[scrub.index];
  const dim = (i: number) => (scrub.index === null || scrub.index === i ? 1 : 0.3);
  return (
    <div className={PANEL_CLASS} data-testid={`monthly-${currency}`}>
      <h3 className="text-sm font-medium text-neutral-300">Entradas × saídas · últimos {months.length} meses</h3>
      <p className="mb-3 text-xs text-neutral-500">
        Entradas = renda; saídas = gastos. Investir e transferir não contam como gasto.
      </p>
      {!hasData ? (
        <p className="text-sm text-neutral-500">Nenhum lançamento nestes meses.</p>
      ) : (
        <>
          <p
            className="mb-2 min-h-5 text-xs tabular-nums text-neutral-400"
            aria-live="polite"
            data-testid={`monthly-focus-${currency}`}
          >
            {focus ? (
              <>
                <span className="text-neutral-200">{formatMonth(focus.month)}</span> · entradas{" "}
                {formatCurrency(focus.income, currency)} · saídas {formatCurrency(focus.expenses, currency)} · sobra{" "}
                <span className={Number(focus.surplus) < 0 ? "text-red-300" : "text-neutral-100"}>
                  {formatSignedCurrency(focus.surplus, currency)}
                </span>
              </>
            ) : (
              "Passe o mouse num mês para ver os números dele."
            )}
          </p>
          <div
            role="group"
            aria-label="Meses: use as setas para percorrer"
            {...scrub.keyboardProps}
            className="rounded-lg"
          >
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={data}
                barGap={2}
                barCategoryGap="28%"
                margin={{ top: 4, right: 4, left: 4, bottom: 0 }}
                {...scrub.chartProps}
              >
                <CartesianGrid stroke={GRID_COLOR} vertical={false} />
                <XAxis
                  dataKey="label"
                  stroke={GRID_COLOR}
                  tick={{ fill: AXIS_TEXT_COLOR, fontSize: 12 }}
                  tickLine={false}
                />
                <YAxis
                  tickFormatter={(value: number) => formatCompactCurrency(value, currency)}
                  stroke={GRID_COLOR}
                  tick={{ fill: AXIS_TEXT_COLOR, fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                  width={72}
                />
                <Tooltip
                  cursor={{ fill: "#24313a", opacity: 0.35, radius: 6 }}
                  content={NoTooltip}
                  isAnimationActive={false}
                />
                <Legend
                  verticalAlign="top"
                  align="right"
                  height={24}
                  iconType="circle"
                  iconSize={8}
                  formatter={(value) => <span className="text-xs text-neutral-300">{value}</span>}
                />
                <Bar
                  dataKey="incomeValue"
                  name="Entradas"
                  fill={INCOME_COLOR}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={24}
                  {...motion}
                >
                  {data.map((row, i) => (
                    <Cell key={row.month} fillOpacity={dim(i)} style={{ transition: "fill-opacity 160ms" }} />
                  ))}
                </Bar>
                <Bar
                  dataKey="expensesValue"
                  name="Saídas"
                  fill={EXPENSE_COLOR}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={24}
                  {...motion}
                >
                  {data.map((row, i) => (
                    <Cell key={row.month} fillOpacity={dim(i)} style={{ transition: "fill-opacity 160ms" }} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="mt-3 w-full text-right text-xs" data-testid={`monthly-table-${currency}`}>
            <thead>
              <tr className="text-neutral-500">
                <th className="py-1 text-left font-normal">Mês</th>
                <th className="py-1 font-normal">Entradas</th>
                <th className="py-1 font-normal">Saídas</th>
                <th className="py-1 font-normal">Sobra</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {months.map((m, i) => (
                <tr
                  key={m.month}
                  className={`border-t border-neutral-800/60 transition-colors ${scrub.index === i ? "bg-neutral-800/60" : ""}`}
                  onMouseEnter={() => scrub.setIndex(i)}
                  onMouseLeave={() => scrub.setIndex(null)}
                >
                  <td className="py-1 text-left text-neutral-400">{formatMonth(m.month)}</td>
                  <td className="py-1">{formatCurrency(m.income, currency)}</td>
                  <td className="py-1">{formatCurrency(m.expenses, currency)}</td>
                  <td className={`py-1 ${Number(m.surplus) < 0 ? "text-red-300" : "text-neutral-100"}`}>
                    {formatSignedCurrency(m.surplus, currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
