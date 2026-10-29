import type { CashflowCurrencySummary, CurrencyCategoryBreakdown } from "../../../api/cashflowTypes";
import { SERIES } from "../../../lib/chartColors";
import { formatPercent } from "../../../lib/formatCurrency";
import { PANEL_CLASS } from "../../../lib/ui";
import { BarList, type BarItem } from "../../charts/BarList";

/**
 * Para onde foi o dinheiro do mês: gastos por categoria (mãe e filhas,
 * maior primeiro) e o que foi investido. Os valores vêm do backend; a
 * porcentagem ao lado é só a fatia de cada um no total, para leitura.
 */
export function WhereMoneyWent({
  currency,
  breakdown,
  period,
}: {
  currency: string;
  breakdown: CurrencyCategoryBreakdown | undefined;
  period: CashflowCurrencySummary | undefined;
}) {
  const spent = (value: string) => Number(value) !== 0;
  const total = Number(breakdown?.expenses ?? 0);
  const share = (value: string) => (total > 0 ? formatPercent(String(Number(value) / total)) : undefined);
  const items: BarItem[] = [];
  const roots = (breakdown?.categories ?? [])
    .filter((row) => row.parent_id === null && spent(row.total_expenses))
    .sort((a, b) => Number(b.total_expenses) - Number(a.total_expenses));
  for (const root of roots) {
    const key = root.category_id ?? "none";
    items.push({
      key,
      label: root.category_name ?? "Sem categoria",
      value: root.total_expenses,
      note: share(root.total_expenses),
    });
    for (const child of (breakdown?.categories ?? [])
      .filter((row) => root.category_id !== null && row.parent_id === root.category_id && spent(row.total_expenses))
      .sort((a, b) => Number(b.total_expenses) - Number(a.total_expenses))) {
      items.push({
        key: child.category_id ?? `child-${key}`,
        label: child.category_name ?? "",
        value: child.total_expenses,
        note: share(child.total_expenses),
        indent: true,
      });
    }
  }
  const invested = period && Number(period.net_invested) > 0 ? period.net_invested : null;

  return (
    <div className={PANEL_CLASS} data-testid={`categories-${currency}`}>
      <h3 className="text-sm font-medium text-neutral-300">Para onde foi o dinheiro</h3>
      <p className="mb-3 text-xs text-neutral-500">Gastos do mês por categoria; investimento à parte.</p>
      {items.length === 0 ? (
        <p className="text-sm text-neutral-500">Nenhum gasto classificado no período.</p>
      ) : (
        <BarList currency={currency} testId="category" items={items} />
      )}
      {invested && (
        <div className="mt-4 border-t border-neutral-800 pt-3">
          <BarList
            currency={currency}
            testId="invested-bar"
            items={[{ key: currency, label: "Investido (líquido)", value: invested, color: SERIES[2] }]}
          />
        </div>
      )}
    </div>
  );
}
