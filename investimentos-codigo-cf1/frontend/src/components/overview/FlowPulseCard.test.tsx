import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MonthFlow } from "../../api/overview";
import * as overviewApi from "../../api/overview";
import { FlowPulseCard } from "./FlowPulseCard";

vi.mock("../../api/overview");

const text = (el: HTMLElement) => el.textContent?.replace(/ /g, " ");

function month(m: string, income: string, expenses: string): MonthFlow {
  return {
    month: m,
    income,
    expenses,
    surplus: String(Number(income) - Number(expenses)),
    net_invested: "0",
    unclassified_net: "0",
    entry_count: 3,
  };
}

function flows(months: MonthFlow[], currency = "BRL") {
  return { end_month: "2026-10", months: months.length, totals_by_currency: [{ currency_code: currency, months }] };
}

describe("FlowPulseCard", () => {
  beforeEach(() => vi.resetAllMocks());

  it("sobra do período em destaque e o último mês aberto no balão", async () => {
    vi.mocked(overviewApi.getMonthlyFlows).mockResolvedValue(
      flows([month("2026-09", "7500", "3000"), month("2026-10", "7500", "8000")]),
    );
    render(<FlowPulseCard />);

    const total = text(await screen.findByTestId("pulse-total"));
    expect(total).toContain("+R$ 4.000,00");
    expect(total).toContain("sobraram");
    const tooltip = screen.getByTestId("pulse-tooltip");
    expect(text(tooltip)).toContain("out/26");
    expect(text(tooltip)).toContain("-R$ 500,00");
    expect(screen.getAllByTestId("pulse-month")[1]).toHaveAttribute("aria-pressed", "true");
  });

  it("tocar num mês mostra os números dele", async () => {
    const user = userEvent.setup();
    vi.mocked(overviewApi.getMonthlyFlows).mockResolvedValue(
      flows([month("2026-09", "7000", "2500"), month("2026-10", "7500", "3000")]),
    );
    render(<FlowPulseCard />);

    const [september] = await screen.findAllByTestId("pulse-month");
    expect(september.getAttribute("aria-label")?.replace(/\u00a0/g, " ")).toBe(
      "set/26: renda R$ 7.000, gastos R$ 2.500, sobra +R$ 4.500,00",
    );
    await user.click(september);
    expect(text(screen.getByTestId("pulse-tooltip"))).toContain("set/26");
    expect(september).toHaveAttribute("aria-pressed", "true");
  });

  it("gasto maior que a renda: total em vermelho, 'faltaram'", async () => {
    vi.mocked(overviewApi.getMonthlyFlows).mockResolvedValue(flows([month("2026-10", "1000", "1500")]));
    render(<FlowPulseCard />);
    expect(text(await screen.findByTestId("pulse-total"))).toContain("faltaram");
  });

  it("trocar para 12 meses busca de novo", async () => {
    const user = userEvent.setup();
    vi.mocked(overviewApi.getMonthlyFlows).mockResolvedValue(flows([month("2026-10", "7500", "3000")]));
    render(<FlowPulseCard />);
    await screen.findByTestId("pulse-total");

    await user.click(within(screen.getByRole("group", { name: "Meses" })).getByRole("button", { name: "12M" }));
    expect(vi.mocked(overviewApi.getMonthlyFlows).mock.calls.map((c) => c[1])).toEqual([6, 12]);
  });

  it("sem renda nem gasto classificados (ou só outra moeda), não aparece", async () => {
    vi.mocked(overviewApi.getMonthlyFlows).mockResolvedValue(flows([month("2026-10", "0", "0")]));
    const { container, rerender } = render(<FlowPulseCard />);
    await vi.waitFor(() => expect(overviewApi.getMonthlyFlows).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(container).toBeEmptyDOMElement();

    vi.mocked(overviewApi.getMonthlyFlows).mockResolvedValue(flows([month("2026-10", "100", "50")], "USD"));
    rerender(<FlowPulseCard reloadKey={1} />);
    await new Promise((r) => setTimeout(r, 0));
    expect(container).toBeEmptyDOMElement();
  });
});
