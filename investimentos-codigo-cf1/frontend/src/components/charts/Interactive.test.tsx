import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MonthFlow } from "../../api/overview";
import type { BenchmarkComparison, HistoryPoint } from "../../api/performance";
import * as api from "../../api/performance";
import { MonthlyFlowChart } from "../cash/summary/MonthlyFlowChart";
import { BenchmarkPanel } from "../overview/BenchmarkPanel";
import { PatrimonyHistory } from "../overview/PatrimonyHistory";
import { BarList } from "./BarList";
import { scrubIndex, stepIndex } from "./chartKit";
import { ShareBar } from "./ShareBar";

vi.mock("../../api/performance");

const text = (el: HTMLElement) => el.textContent?.replace(/\u00a0/g, " ");

describe("scrub dos gráficos: regras puras", () => {
  it("scrubIndex só aceita um índice inteiro dentro dos dados e com o mouse sobre o gráfico", () => {
    expect(scrubIndex({ activeTooltipIndex: "2", isTooltipActive: true }, 4)).toBe(2);
    expect(scrubIndex({ activeTooltipIndex: 0, isTooltipActive: true }, 4)).toBe(0);
    expect(scrubIndex({ activeTooltipIndex: 2, isTooltipActive: false }, 4)).toBeNull();
    expect(scrubIndex({ activeTooltipIndex: 4, isTooltipActive: true }, 4)).toBeNull();
    expect(scrubIndex({ activeTooltipIndex: -1, isTooltipActive: true }, 4)).toBeNull();
    expect(scrubIndex({ activeTooltipIndex: undefined, isTooltipActive: true }, 4)).toBeNull();
    expect(scrubIndex(null, 4)).toBeNull();
  });

  it("stepIndex: setas andam um ponto a partir do último (o que está à mostra), sem passar das pontas; Home/End; Esc sai; outras teclas não mexem", () => {
    expect(stepIndex(null, "ArrowLeft", 5)).toBe(3);
    expect(stepIndex(null, "ArrowRight", 5)).toBe(4);
    expect(stepIndex(3, "ArrowLeft", 5)).toBe(2);
    expect(stepIndex(0, "ArrowLeft", 5)).toBe(0);
    expect(stepIndex(4, "ArrowRight", 5)).toBe(4);
    expect(stepIndex(2, "Home", 5)).toBe(0);
    expect(stepIndex(2, "End", 5)).toBe(4);
    expect(stepIndex(2, "Escape", 5)).toBeNull();
    expect(stepIndex(2, "a", 5)).toBeUndefined();
    expect(stepIndex(null, "ArrowLeft", 0)).toBeUndefined();
  });
});

function point(date: string, total: string, extra: Partial<HistoryPoint> = {}): HistoryPoint {
  return { date, total, investments_value: "0", investments_cost: "0", cash: total, unpriced: [], ...extra };
}

describe("Evolução do patrimônio: o número do topo segue o dia em foco", () => {
  beforeEach(() => {
    vi.mocked(api.getPerformanceHistory).mockResolvedValue({
      start: "2026-08-31",
      end: "2026-10-08",
      totals_by_currency: [
        {
          currency_code: "BRL",
          points: [point("2026-08-31", "1000"), point("2026-09-30", "1100"), point("2026-10-08", "1250")],
        },
      ],
    });
  });

  it("abre no último dia e as setas percorrem os dias, com a variação até o dia em foco", async () => {
    const user = userEvent.setup();
    render(<PatrimonyHistory />);
    await screen.findByTestId("history-BRL");

    expect(text(screen.getByTestId("history-value-BRL"))).toBe("R$ 1.250,00");
    expect(screen.getByTestId("history-BRL")).toHaveTextContent("hoje");

    screen.getByRole("group", { name: /Evolução em reais/ }).focus();
    await user.keyboard("{ArrowLeft}");
    expect(text(screen.getByTestId("history-value-BRL"))).toBe("R$ 1.100,00");
    expect(text(screen.getByTestId("history-change-BRL"))).toBe(
      "+R$ 100,00 de 31/08/2026 a 30/09/2026, com aportes e resgates",
    );

    await user.keyboard("{Home}");
    expect(text(screen.getByTestId("history-value-BRL"))).toBe("R$ 1.000,00");

    await user.keyboard("{Escape}");
    expect(text(screen.getByTestId("history-value-BRL"))).toBe("R$ 1.250,00");
    expect(text(screen.getByTestId("history-change-BRL"))).toBe("+R$ 250,00 desde 31/08/2026, com aportes e resgates");
  });

  it("trocar de período com um dia em foco volta a mostrar hoje", async () => {
    const user = userEvent.setup();
    render(<PatrimonyHistory />);
    await screen.findByTestId("history-BRL");
    screen.getByRole("group", { name: /Evolução em reais/ }).focus();
    await user.keyboard("{Home}");
    expect(text(screen.getByTestId("history-value-BRL"))).toBe("R$ 1.000,00");

    vi.mocked(api.getPerformanceHistory).mockResolvedValue({
      start: "2026-09-30",
      end: "2026-10-08",
      totals_by_currency: [
        { currency_code: "BRL", points: [point("2026-09-30", "1100"), point("2026-10-08", "1250")] },
      ],
    });
    await user.click(screen.getByRole("button", { name: "1M" }));
    await waitFor(() => expect(api.getPerformanceHistory).toHaveBeenLastCalledWith(30));
    expect(text(await screen.findByTestId("history-value-BRL"))).toBe("R$ 1.250,00");
    expect(screen.getByTestId("history-BRL")).toHaveTextContent("hoje");
  });
});

describe("Comparação com a referência: leitura do dia em foco", () => {
  const usd: BenchmarkComparison = {
    currency_code: "USD",
    benchmark: "SPY",
    benchmark_label: "SPY (S&P 500)",
    available: true,
    reason: null,
    net_invested: "700",
    portfolio_value: "797.05",
    benchmark_value: "812.40",
    difference: "-15.35",
    portfolio_return: "0.0072",
    benchmark_return: "0.0266",
    unpriced: [],
    points: [
      { date: "2026-08-25", portfolio: "210", benchmark: "200" },
      { date: "2026-10-16", portfolio: "797.05", benchmark: "812.40" },
    ],
  };

  it("mostra hoje e, com as setas, o dia anterior com a diferença de cada dia", async () => {
    const user = userEvent.setup();
    render(<BenchmarkPanel benchmarks={{ as_of: "2026-10-16", comparisons: [usd] }} />);

    expect(text(screen.getByTestId("benchmark-focus-USD"))).toBe("HojeUS$ 797,05US$ 812,40-US$ 15,35");
    screen.getByRole("group", { name: /SPY \(S&P 500\) com os mesmos aportes/ }).focus();
    await user.keyboard("{ArrowLeft}");
    expect(text(screen.getByTestId("benchmark-focus-USD"))).toBe("25/08/2026US$ 210,00US$ 200,00+US$ 10,00");
  });
});

describe("Entradas × saídas: o mês em foco no gráfico e na tabela", () => {
  const month = (m: string, income: string, expenses: string, surplus: string): MonthFlow => ({
    month: m,
    income,
    expenses,
    surplus,
    net_invested: "0",
    unclassified_net: "0",
    entry_count: 3,
  });

  it("passar o mouse numa linha da tabela destaca o mês e mostra os números dele no topo", () => {
    render(
      <MonthlyFlowChart
        currency="BRL"
        months={[month("2026-09", "5000", "3000", "2000"), month("2026-10", "5000", "5600", "-600")]}
      />,
    );
    const focus = screen.getByTestId("monthly-focus-BRL");
    expect(focus).toHaveTextContent("Passe o mouse num mês");

    const rows = within(screen.getByTestId("monthly-table-BRL")).getAllByRole("row");
    fireEvent.mouseEnter(rows[2]);
    expect(text(focus)).toBe("out/2026 · entradas R$ 5.000,00 · saídas R$ 5.600,00 · sobra -R$ 600,00");
    expect(rows[2]).toHaveClass("bg-neutral-800/60");
    expect(rows[1]).not.toHaveClass("bg-neutral-800/60");

    fireEvent.mouseLeave(rows[2]);
    expect(focus).toHaveTextContent("Passe o mouse num mês");
  });
});

describe("Barras horizontais: passar o mouse acende um e apaga os outros", () => {
  it("BarList", () => {
    render(
      <BarList
        currency="BRL"
        testId="bars"
        items={[
          { key: "a", label: "Moradia", value: "2400" },
          { key: "b", label: "Mercado", value: "640" },
        ]}
      />,
    );
    fireEvent.mouseEnter(screen.getByTestId("bars-a"));
    expect(screen.getByTestId("bars-b")).toHaveClass("opacity-45");
    expect(screen.getByTestId("bars-a")).not.toHaveClass("opacity-45");
    fireEvent.mouseLeave(screen.getByTestId("bars"));
    expect(screen.getByTestId("bars-b")).not.toHaveClass("opacity-45");
  });

  it("ShareBar: a fatia e a linha da legenda acendem juntas", () => {
    render(
      <ShareBar
        currency="BRL"
        label="Partes"
        testId="share"
        items={[
          { key: "x", label: "Renda variável", value: "60", weight: "0.6", color: "#3987e5" },
          { key: "y", label: "Renda fixa", value: "40", weight: "0.4", color: "#d95926" },
        ]}
      />,
    );
    const segments = screen.getByRole("img", { name: "Partes" }).querySelectorAll("div");
    fireEvent.mouseEnter(segments[1]);
    expect(screen.getByTestId("share-x")).toHaveClass("opacity-35");
    expect(segments[0]).toHaveClass("opacity-35");
    expect(screen.getByTestId("share-y")).not.toHaveClass("opacity-35");
  });
});
