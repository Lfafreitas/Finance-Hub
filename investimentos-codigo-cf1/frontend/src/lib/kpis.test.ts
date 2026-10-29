import { describe, expect, it } from "vitest";

import { formatDecimal, formatMetric, sortMetrics, toneOf } from "./kpis";

const m = (code: Parameters<typeof formatMetric>[0]["code"], value: number) => ({ code, value, as_of: "2026-10-14", source: "x" });
const plain = (s: string) => s.replace(/ /g, " ");

describe("indicadores", () => {
  it("fração vira percentual, retorno com sinal, múltiplo com x", () => {
    expect(plain(formatMetric(m("DIVIDEND_YIELD", 0.0385)))).toBe("3,85%");
    expect(plain(formatMetric(m("RETURN_YTD", -0.124)))).toBe("-12,40%");
    expect(plain(formatMetric(m("RETURN_1Y", 0.2)))).toBe("+20,00%");
    expect(formatMetric(m("P_FFO", 17.24))).toBe("17,2x");
    expect(formatMetric(m("BETA", 1.054))).toBe("1,05");
  });

  it("ordem: rendimento e P/FFO primeiro", () => {
    expect(sortMetrics([m("BETA", 1), m("P_FFO", 17), m("DIVIDEND_YIELD", 0.03)]).map((x) => x.code)).toEqual([
      "DIVIDEND_YIELD",
      "P_FFO",
      "BETA",
    ]);
  });

  it("tom pelo sinal e número efetivo", () => {
    expect(toneOf("0.1")).toContain("emerald");
    expect(toneOf("-0.1")).toContain("red");
    expect(toneOf(null)).toContain("neutral-500");
    expect(formatDecimal("3.4120")).toBe("3,4");
    expect(formatDecimal(null)).toBe("—");
  });
});
