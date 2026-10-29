import type { Alert, InsightReportRead } from "../api/insights";
import type { AssetKpis, CurrencyKpis } from "../api/performance";

const stats = {
  last_price: "746.04",
  last_date: "2026-10-14",
  return_1m: "0.0210",
  return_3m: "0.0560",
  return_ytd: "0.1810",
  return_1y: "0.2250",
  volatility_1y: "0.1890",
  max_drawdown_1y: "-0.1230",
  low_52w: "600.00",
  high_52w: "760.00",
  position_52w: "0.9125",
  from_high: "-0.0184",
};

export function asset(overrides: Partial<AssetKpis> = {}): AssetKpis {
  return {
    ticker: "QQQ",
    name: "Invesco QQQ",
    asset_class: "ETF_US",
    asset_class_label: "ETF (Exterior)",
    quantity: "0.44793347",
    cost: "334.08",
    value: "334.17",
    weight: "0.4300",
    pnl: "0.09",
    return_pct: "0.0003",
    contribution: "0.0001",
    dividends: "0",
    yield_on_cost: "0.0000",
    day_change_pct: "-0.0074",
    stats,
    ...overrides,
  };
}

export function kpiBlock(overrides: Partial<CurrencyKpis> = {}): CurrencyKpis {
  return {
    currency_code: "USD",
    value: "787.76",
    cost: "791.32",
    pnl: "-3.56",
    return_pct: "-0.0045",
    complete: true,
    unpriced: [],
    top_ticker: "QQQ",
    top_weight: "0.4300",
    top3_weight: "0.7900",
    effective_assets: "3.4120",
    positive: 3,
    negative: 3,
    best: "QQQ",
    worst: "VNQ",
    dividends: "1.20",
    yield_on_cost: "0.0015",
    groups: [
      { asset_class: "ETF_US", label: "ETF (Exterior)", value: "560.00", weight: "0.7100" },
      { asset_class: "BOND", label: "Renda fixa", value: "150.89", weight: "0.1900" },
      { asset_class: "REIT", label: "REIT", value: "76.05", weight: "0.1000" },
    ],
    basket: {
      tickers: ["AAXJ", "QQQ", "SPY", "VNQ"],
      share_of_portfolio: "0.8100",
      return_1y: "0.1520",
      volatility_1y: "0.1640",
      max_drawdown_1y: "-0.1110",
    },
    assets: [
      asset(),
      asset({
        ticker: "VNQ",
        name: "Vanguard Real Estate",
        asset_class: "REIT",
        asset_class_label: "REIT",
        weight: "0.1000",
        value: "76.05",
        pnl: "-4.30",
        return_pct: "-0.0535",
        contribution: "-0.0054",
        stats: { ...stats, low_52w: null, high_52w: null, position_52w: null, from_high: null, return_1y: null },
      }),
    ],
    ...overrides,
  };
}

export function reportWithReview(): InsightReportRead {
  return {
    report_date: "2026-10-15",
    report: {
      schema_version: 2,
      generated_at: "2026-10-15T08:00:00-03:00",
      headline: "Manchete",
      summary: ["Resumo."],
      holdings: [
        {
          ticker: "VNQ",
          signal: "ATENCAO",
          reading: "Juros longos pesam sobre REITs.",
          metrics: [],
          key_metrics: [
            { code: "P_FFO", value: 17.2, as_of: "2026-10-14", source: "Nareit", url: "https://www.reit.com/x" },
            { code: "DIVIDEND_YIELD", value: 0.0385, as_of: "2026-10-14", source: "Vanguard" },
          ],
          sources: [],
        },
      ],
      news: [],
      research: [],
      watch: [],
      portfolio_review: {
        overall: "Carteira concentrada em tecnologia americana.",
        good: [{ title: "Custos baixos", detail: "Taxas abaixo de 0,25%.", tickers: ["SPY", "QQQ"] }],
        attention: [{ title: "Concentração", detail: "QQQ é 43%.", tickers: ["QQQ"] }],
        risks: [],
        improve: [{ title: "Pouca renda", detail: "0,15% sobre o custo.", tickers: [] }],
      },
      disclaimer: "Não é recomendação.",
    },
  };
}

export function alert(overrides: Partial<Alert> = {}): Alert {
  return {
    id: "a1",
    detected_at: "2026-10-15T10:05:00-03:00",
    severity: "ALTA",
    tickers: ["AAXJ"],
    title: "Bolsa da Coreia cai 7%",
    summary: "Venda forte de chips.",
    why_it_matters: "AAXJ tem peso alto em Coreia.",
    sources: [{ title: "AP", url: "https://apnews.com/x" }],
    ...overrides,
  };
}
