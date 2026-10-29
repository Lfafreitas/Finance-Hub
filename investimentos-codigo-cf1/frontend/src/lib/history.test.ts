import { describe, expect, it } from "vitest";

import type { HistoryPoint } from "../api/performance";
import { monthEnds, periodChange, trimLeadingEmpty } from "./history";

const p = (date: string, total: string, cost = "0"): HistoryPoint => ({
  date,
  total,
  investments_value: "0",
  investments_cost: cost,
  cash: total,
  unpriced: [],
});

describe("evolução", () => {
  it("tira só os dias vazios do começo", () => {
    const points = [p("2026-01-01", "0"), p("2026-01-02", "0", "50"), p("2026-01-03", "0"), p("2026-01-04", "10")];

    expect(trimLeadingEmpty(points).map((x) => x.date)).toEqual(["2026-01-02", "2026-01-03", "2026-01-04"]);
    expect(trimLeadingEmpty([p("2026-01-01", "0")])).toEqual([]);
  });

  it("variação do período sobre o início", () => {
    expect(periodChange([p("2026-01-01", "200"), p("2026-01-02", "150")])).toMatchObject({ change: -50, pct: -0.25 });
    expect(periodChange([p("2026-01-01", "0"), p("2026-01-02", "150")])?.pct).toBeNull();
    expect(periodChange([p("2026-01-01", "1")])).toBeNull();
  });

  it("último ponto de cada mês", () => {
    const points = [p("2026-01-30", "1"), p("2026-01-31", "2"), p("2026-02-01", "3")];

    expect(monthEnds(points).map((x) => x.total)).toEqual(["2", "3"]);
  });
});
