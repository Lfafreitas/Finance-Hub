import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { BenchmarkComparison } from "../../api/performance";
import { setPrivate } from "../../lib/privacy";
import { BenchmarkPanel } from "./BenchmarkPanel";

const text = (el: HTMLElement) => el.textContent?.replace(/ /g, " ");

function usd(overrides: Partial<BenchmarkComparison> = {}): BenchmarkComparison {
  return {
    currency_code: "USD",
    benchmark: "SPY",
    benchmark_label: "SPY (S&P 500)",
    available: true,
    reason: null,
    net_invested: "791.32",
    portfolio_value: "797.05",
    benchmark_value: "812.40",
    difference: "-15.35",
    portfolio_return: "0.0072",
    benchmark_return: "0.0266",
    unpriced: ["VNQ"],
    points: [
      { date: "2026-08-25", portfolio: "200", benchmark: "200" },
      { date: "2026-10-16", portfolio: "797.05", benchmark: "812.40" },
    ],
    ...overrides,
  };
}

const wrap = (items: BenchmarkComparison[]) => ({ as_of: "2026-10-16", comparisons: items });

describe("BenchmarkPanel", () => {
  afterEach(() => setPrivate(false));

  it("diz quanto a referência valeria com os mesmos aportes e a diferença com sinal", () => {
    render(<BenchmarkPanel benchmarks={wrap([usd()])} />);

    const summary = text(screen.getByTestId("benchmark-summary-USD"));
    expect(summary).toContain("o SPY (S&P 500) valeria US$ 812,40");
    expect(summary).toContain("Sua carteira vale US$ 797,05");
    expect(summary).toContain("-US$ 15,35 atrás.");
    const block = text(screen.getByTestId("benchmark-USD"));
    expect(block).toContain("+0,72%");
    expect(block).toContain("+2,66%");
    expect(block).toContain("Sem cotação, entram pelo custo: VNQ.");
    expect(block).toContain("Só preço, sem dividendos");
  });

  it("à frente quando a carteira supera a referência", () => {
    render(<BenchmarkPanel benchmarks={wrap([usd({ difference: "4.10" })])} />);

    expect(text(screen.getByTestId("benchmark-summary-USD"))).toContain("+US$ 4,10 à frente.");
  });

  it("sem dado da referência mostra o motivo, sem números", () => {
    const brl = usd({
      currency_code: "BRL",
      benchmark: "CDI",
      benchmark_label: "CDI",
      available: false,
      reason: "CDI ainda não baixado desde o primeiro aporte.",
      points: [],
    });
    render(<BenchmarkPanel benchmarks={wrap([brl])} />);

    expect(screen.getByTestId("benchmark-reason-BRL")).toHaveTextContent("CDI ainda não baixado");
    expect(screen.queryByTestId("benchmark-summary-BRL")).toBeNull();
  });

  it("nada a comparar: não mostra a seção", () => {
    render(<BenchmarkPanel benchmarks={wrap([])} />);

    expect(screen.queryByTestId("benchmarks")).toBeNull();
  });

  it("modo privacidade esconde os valores e mantém os percentuais", () => {
    setPrivate(true);
    render(<BenchmarkPanel benchmarks={wrap([usd()])} />);

    const block = text(screen.getByTestId("benchmark-USD")) ?? "";
    expect(block).not.toMatch(/US\$ \d/);
    expect(block).toContain("+2,66%");
  });
});
