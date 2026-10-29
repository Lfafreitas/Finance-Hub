import type { CurrencyAnalytics, PortfolioAnalytics, QuoteRefreshResult } from "../api/analytics";

export function makeAnalyticsBlock(overrides: Partial<CurrencyAnalytics> = {}): CurrencyAnalytics {
  return {
    currency_code: "USD",
    market_value: "356.0100",
    market_data_as_of: "2026-10-08",
    concentration: {
      basis: "MARKET",
      total: "356.01",
      by_asset: [
        { key: "a-qqq", label: "QQQ", value: "168.75", weight: "0.4740" },
        { key: "a-spy", label: "SPY", value: "126.32", weight: "0.3548" },
        { key: "a-aaxj", label: "AAXJ", value: "50.59", weight: "0.1421" },
        { key: "a-vnq", label: "VNQ", value: "10.35", weight: "0.0291" },
      ],
      by_class: [
        { key: "ETF_US", label: "ETF (Exterior)", value: "345.66", weight: "0.9709" },
        { key: "REIT", label: "REIT", value: "10.35", weight: "0.0291" },
      ],
      by_account: [{ key: "acc-inter", label: "Inter US", value: "356.01", weight: "1.0000" }],
      by_group: [{ key: "VARIABLE", label: "Renda variável", value: "356.01", weight: "1.0000" }],
      top3_weight: "0.9709",
      flags: ["QQQ sozinho é mais de 40% da carteira", "os 3 maiores ativos somam mais de 75% da carteira"],
    },
    scenarios: {
      until: "2026-12-31",
      horizon_days: 84,
      value_today: "356.01",
      expected_return: "0.0700",
      volatility: "0.1834",
      pessimistic_return: "-0.0940",
      realistic_return: "0.0120",
      optimistic_return: "0.1330",
      pessimistic_value: "322.55",
      realistic_value: "360.28",
      optimistic_value: "403.36",
      probability_below_today: "0.4500",
      assumptions: [
        { key: "QQQ", weight: "0.4740", volatility: "0.2210", volatility_from_history: true, history_returns: 250, expected_return: "0.0700" },
        { key: "VNQ", weight: "0.0291", volatility: "0.2000", volatility_from_history: false, history_returns: 12, expected_return: "0.0600" },
      ],
      excluded: [{ key: "CDUS", reason: "renda fixa ou classe sem risco de mercado modelado: fica fora dos cenários" }],
    },
    scenarios_unavailable_reason: null,
    contributions: {
      year: 2026,
      total_year: "351.24",
      months: [
        { month: "2026-08", amount: "100.00" },
        { month: "2026-09", amount: "50.65" },
        { month: "2026-10", amount: "200.59" },
      ],
      remaining_months: 2,
      projections: [
        { pace: "AVERAGE", monthly: "117.08", remaining_total: "234.16", year_end_total: "585.40" },
        { pace: "LAST_3", monthly: "117.08", remaining_total: "234.16", year_end_total: "585.40" },
        { pace: "LAST_MONTH", monthly: "200.59", remaining_total: "401.18", year_end_total: "752.42" },
      ],
    },
    alerts: [],
    ...overrides,
  };
}

export function makeAnalytics(overrides: Partial<PortfolioAnalytics> = {}): PortfolioAnalytics {
  return {
    reference_date: "2026-10-08",
    quotes_refreshed_at: new Date().toISOString(),
    blocks: [makeAnalyticsBlock()],
    ...overrides,
  };
}

export const refreshFixture: QuoteRefreshResult = {
  refreshed_at: "2026-10-08T14:05:00Z",
  items: [
    { asset_id: "a-spy", ticker: "SPY", status: "OK", message: null, price: "777.14", price_date: "2026-10-08", points: 251 },
    { asset_id: "a-cd", ticker: "CDUS", status: "UNSUPPORTED", message: "sem fonte automática para esta classe ou país — informe a cotação à mão", price: null, price_date: null, points: 0 },
  ],
};
