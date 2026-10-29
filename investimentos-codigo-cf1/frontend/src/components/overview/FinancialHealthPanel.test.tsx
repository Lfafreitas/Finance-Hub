import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FinancialHealth } from "../../api/performance";
import { setPrivate } from "../../lib/privacy";
import { FinancialHealthPanel } from "./FinancialHealthPanel";

const text = (id: string) => screen.getByTestId(id).textContent?.replace(/ /g, " ");

function health(overrides: Partial<FinancialHealth> = {}): FinancialHealth {
  return {
    currency_code: "BRL",
    months: ["2026-07", "2026-08", "2026-09"],
    avg_income: "5000",
    avg_expenses: "2133.33",
    avg_invested: "350",
    savings_rate: "0.5733",
    reserve: "12345.67",
    coverage_months: "6.2",
    complete: true,
    incomplete_months: [],
    ...overrides,
  };
}

describe("FinancialHealthPanel", () => {
  afterEach(() => setPrivate(false));

  it("mostra cobertura, faixa, poupança, gasto e investido com o período", () => {
    render(<FinancialHealthPanel currencies={[health()]} />);

    expect(text("health-coverage-BRL")).toBe("6,2 meses");
    expect(text("health-band-BRL")).toContain("6 meses de gasto ou mais");
    expect(text("health-savings-BRL")).toContain("+57,33%");
    expect(text("health-expenses-BRL")).toContain("R$ 2.133");
    expect(text("health-invested-BRL")).toContain("R$ 350");
    expect(text("financial-health")).toContain("Média de jul, ago e set/26");
    expect(screen.queryByTestId("health-incomplete-BRL")).toBeNull();
  });

  it("gastos incompletos: cobertura vira teto e há atalho para classificar", async () => {
    const onOpenReview = vi.fn();
    const user = userEvent.setup();
    render(
      <FinancialHealthPanel
        currencies={[health({ complete: false, incomplete_months: ["2026-09"], coverage_months: "2.4" })]}
        onOpenReview={onOpenReview}
      />,
    );

    expect(text("health-coverage-BRL")).toBe("até 2,4 meses");
    expect(text("health-band-BRL")).toContain("menos de 3 meses");
    expect(text("health-incomplete-BRL")).toContain("sem classificação em set/26");
    await user.click(screen.getByRole("button", { name: "Classificar" }));
    expect(onOpenReview).toHaveBeenCalledOnce();
  });

  it("sem gasto nos meses fechados não inventa cobertura", () => {
    render(
      <FinancialHealthPanel
        currencies={[health({ coverage_months: null, avg_expenses: null, savings_rate: null, months: [] })]}
      />,
    );
    expect(text("health-coverage-BRL")).toBe("—");
    expect(screen.queryByTestId("health-band-BRL")).toBeNull();
    expect(text("financial-health")).toContain("Ainda sem mês fechado");
    expect(text("financial-health")).toContain("Sem gasto registrado");
  });

  it("tudo sem classificação: pede para classificar em vez de inventar cobertura", () => {
    render(
      <FinancialHealthPanel
        currencies={[
          health({
            coverage_months: null,
            avg_expenses: "0",
            savings_rate: null,
            complete: false,
            incomplete_months: ["2026-09"],
          }),
        ]}
      />,
    );
    expect(text("health-coverage-BRL")).toBe("—");
    expect(text("financial-health")).toContain("classifique para ver a cobertura");
  });

  it("modo privacidade esconde os valores, não os meses", () => {
    setPrivate(true);
    render(<FinancialHealthPanel currencies={[health()]} />);
    expect(text("health-expenses-BRL")).not.toContain("2.133");
    expect(text("financial-health")).not.toContain("12.345");
    expect(text("health-coverage-BRL")).toBe("6,2 meses");
  });

  it("sem moeda, nada aparece", () => {
    const { container } = render(<FinancialHealthPanel currencies={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
