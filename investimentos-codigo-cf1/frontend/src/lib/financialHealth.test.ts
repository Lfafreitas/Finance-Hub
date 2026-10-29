import { describe, expect, it } from "vitest";

import type { FinancialHealth } from "../api/performance";
import { coverageText, coverageTone, monthsText, shortMonth } from "./financialHealth";

function health(overrides: Partial<FinancialHealth> = {}): FinancialHealth {
  return {
    currency_code: "BRL",
    months: ["2026-07", "2026-08", "2026-09"],
    avg_income: "5000",
    avg_expenses: "2000",
    avg_invested: "300",
    savings_rate: "0.6",
    reserve: "12400",
    coverage_months: "6.2",
    complete: true,
    incomplete_months: [],
    ...overrides,
  };
}

describe("saúde financeira", () => {
  it("mês curto", () => {
    expect(shortMonth("2026-10")).toBe("out/26");
    expect(shortMonth("xx")).toBe("xx");
  });

  it("meses por extenso, sem repetir o ano", () => {
    expect(monthsText(["2026-07", "2026-08", "2026-09"])).toBe("jul, ago e set/26");
    expect(monthsText(["2025-12", "2026-01"])).toBe("dez/25 e jan/26");
    expect(monthsText(["2026-09"])).toBe("set/26");
    expect(monthsText([])).toBe("");
  });

  it("cobertura com uma casa e 'até' quando os gastos estão incompletos", () => {
    expect(coverageText(health())).toBe("6,2 meses");
    expect(coverageText(health({ coverage_months: "0.97" }))).toBe("1,0 mês");
    expect(coverageText(health({ complete: false }))).toBe("até 6,2 meses");
    expect(coverageText(health({ coverage_months: null }))).toBeNull();
  });

  it("faixas de 3 e 6 meses", () => {
    expect(coverageTone(health({ coverage_months: "2.99" }))).toBe("low");
    expect(coverageTone(health({ coverage_months: "3" }))).toBe("ok");
    expect(coverageTone(health({ coverage_months: "6" }))).toBe("good");
    expect(coverageTone(health({ coverage_months: null }))).toBeNull();
  });
});
