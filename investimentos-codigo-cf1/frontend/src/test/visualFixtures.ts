import type { CurrencySpendingInsights, MonthlyFlows, Overview, SpendingInsights } from "../api/overview";

// Cada número aparece uma única vez, para o teste saber de onde veio.
export const overviewFixture: Overview = {
  as_of: "2026-10-08",
  totals_by_currency: [
    {
      currency_code: "BRL",
      total: "13275.6000",
      investments_value: "0.0000",
      investments_cost: "0.0000",
      investments_basis: "MARKET",
      unpriced: [],
      result: "0.0000",
      result_pct: null,
      result_complete: true,
      net_contributions: "0.0000",
      liquid: "89.2000",
      reserve: "13200.0000",
      card: "-13.6000",
      parts: [
        { key: "RESERVE", label: "Reserva", value: "13200.0000", weight: "0.9933" },
        { key: "LIQUID", label: "Disponível", value: "89.2000", weight: "0.0067" },
      ],
      investment_groups: [],
    },
    {
      currency_code: "USD",
      total: "506.8600",
      investments_value: "506.8600",
      investments_cost: "501.2400",
      investments_basis: "MIXED",
      unpriced: ["AAXJ", "VNQ"],
      result: "5.6200",
      result_pct: "0.0112",
      result_complete: false,
      net_contributions: "501.2400",
      liquid: "0.0000",
      reserve: "0.0000",
      card: "0.0000",
      parts: [
        { key: "VARIABLE", label: "Renda variável", value: "356.0300", weight: "0.7024" },
        { key: "FIXED", label: "Renda fixa", value: "150.8300", weight: "0.2976" },
      ],
      investment_groups: [
        { key: "VARIABLE", label: "Renda variável", value: "356.0300", weight: "0.7024" },
        { key: "FIXED", label: "Renda fixa", value: "150.8300", weight: "0.2976" },
      ],
    },
  ],
};

function month(monthKey: string, income: string, expenses: string, surplus: string, entryCount: number) {
  return { month: monthKey, income, expenses, surplus, net_invested: "0.0000", unclassified_net: "0.0000", entry_count: entryCount };
}

/** O último mês é o escolhido na tela: a "Sobra" vem dele. */
export function monthlyFixture(endMonth: string): MonthlyFlows {
  return {
    end_month: endMonth,
    months: 2,
    totals_by_currency: [
      {
        currency_code: "BRL",
        months: [
          month("2026-07", "4100.0000", "3900.0000", "200.0000", 12),
          month(endMonth, "5001.0000", "1234.5600", "3766.4400", 30),
        ],
      },
    ],
  };
}

export function makeInsights(overrides: Partial<CurrencySpendingInsights> = {}): CurrencySpendingInsights {
  return {
    currency_code: "BRL",
    month: "2026-08",
    expenses: "1234.5600",
    history_months: 3,
    above_normal: [],
    recurring: [],
    recurring_total: "0.0000",
    small_count: 0,
    small_total: "0.0000",
    small_limit: "30.0000",
    top_categories: [],
    top_share: null,
    unclassified_outflow: "0.0000",
    unclassified_share: null,
    ...overrides,
  };
}

export function insightsFixture(monthKey: string, block: Partial<CurrencySpendingInsights> = {}): SpendingInsights {
  return { month: monthKey, totals_by_currency: [makeInsights({ month: monthKey, ...block })] };
}
