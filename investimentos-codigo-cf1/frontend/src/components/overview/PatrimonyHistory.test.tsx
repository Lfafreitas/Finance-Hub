import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { HistoryPoint, PerformanceHistory } from "../../api/performance";
import * as api from "../../api/performance";
import { PatrimonyHistory } from "./PatrimonyHistory";

vi.mock("../../api/performance");

function point(date: string, total: string, extra: Partial<HistoryPoint> = {}): HistoryPoint {
  return { date, total, investments_value: "0", investments_cost: "0", cash: total, unpriced: [], ...extra };
}

const history: PerformanceHistory = {
  start: "2026-08-30",
  end: "2026-10-08",
  totals_by_currency: [
    {
      currency_code: "BRL",
      points: [
        point("2026-08-30", "0"),
        point("2026-08-31", "1000"),
        point("2026-09-30", "1100"),
        point("2026-10-08", "1250"),
      ],
    },
    {
      currency_code: "USD",
      points: [
        point("2026-09-01", "400", { investments_value: "400", investments_cost: "400", cash: "0" }),
        point("2026-10-08", "380", { investments_value: "380", investments_cost: "400", cash: "0", unpriced: ["VNQ"] }),
      ],
    },
  ],
};

const text = (id: string) => screen.getByTestId(id).textContent?.replace(/ /g, " ");

describe("PatrimonyHistory", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.getPerformanceHistory).mockResolvedValue(history);
  });

  it("abre em 6 meses e mostra a variação do período por moeda, sem somar moedas", async () => {
    render(<PatrimonyHistory />);

    await screen.findByTestId("history-BRL");
    expect(api.getPerformanceHistory).toHaveBeenCalledWith(180);
    // Começa no primeiro dia com algum valor (31/08), não no zero.
    expect(text("history-change-BRL")).toBe("+R$ 250,00 desde 31/08/2026, com aportes e resgates");
    expect(text("history-change-USD")).toBe("-US$ 20,00 desde 01/09/2026, com aportes e resgates");
    expect(screen.getByTestId("history-change-USD").querySelector("span")).toHaveClass("text-red-400");
    expect(screen.getByRole("button", { name: "6M" })).toHaveAttribute("aria-pressed", "true");
  });

  it("a linha do aplicado e o aviso de cotação só aparecem onde há investimento", async () => {
    render(<PatrimonyHistory />);

    await screen.findByTestId("history-USD");
    expect(screen.getByTestId("history-USD")).toHaveTextContent("Aplicado nos investimentos");
    expect(screen.getByTestId("history-USD")).toHaveTextContent("Sem cotação para VNQ: entram pelo valor aplicado.");
    expect(screen.getByTestId("history-BRL")).not.toHaveTextContent("Aplicado nos investimentos");
  });

  it("a tabela traz o último dia de cada mês", async () => {
    render(<PatrimonyHistory />);

    const table = await screen.findByTestId("history-table-BRL");
    const rows = Array.from(table.querySelectorAll("tbody tr")).map((row) =>
      Array.from(row.querySelectorAll("td")).map((cell) => cell.textContent?.replace(/ /g, " ")),
    );
    expect(rows).toEqual([
      ["ago/2026", "R$ 1.000,00"],
      ["set/2026", "R$ 1.100,00"],
      ["out/2026", "R$ 1.250,00"],
    ]);
  });

  it("trocar o período busca de novo; Tudo pede sem limite", async () => {
    const user = userEvent.setup();
    render(<PatrimonyHistory />);
    await screen.findByTestId("history-BRL");

    await user.click(screen.getByRole("button", { name: "1M" }));
    await waitFor(() => expect(api.getPerformanceHistory).toHaveBeenLastCalledWith(30));
    await user.click(screen.getByRole("button", { name: "Tudo" }));
    await waitFor(() => expect(api.getPerformanceHistory).toHaveBeenLastCalledWith(null));
    expect(screen.getByRole("button", { name: "Tudo" })).toHaveAttribute("aria-pressed", "true");
  });

  it("sem movimento diz isso; erro não derruba a tela", async () => {
    vi.mocked(api.getPerformanceHistory).mockResolvedValue({ start: null, end: "2026-10-08", totals_by_currency: [] });
    const { unmount } = render(<PatrimonyHistory />);
    expect(await screen.findByText("Ainda não há movimentos para mostrar.")).toBeInTheDocument();
    unmount();

    vi.mocked(api.getPerformanceHistory).mockRejectedValue(new Error("fora"));
    render(<PatrimonyHistory />);
    expect(await screen.findByText("Não foi possível carregar a evolução agora.")).toBeInTheDocument();
  });

  it("moeda com um ponto só não vira gráfico", async () => {
    vi.mocked(api.getPerformanceHistory).mockResolvedValue({
      start: "2026-10-08",
      end: "2026-10-08",
      totals_by_currency: [{ currency_code: "BRL", points: [point("2026-10-08", "10")] }],
    });

    render(<PatrimonyHistory />);

    await waitFor(() => expect(api.getPerformanceHistory).toHaveBeenCalled());
    await screen.findByTestId("patrimony-history");
    expect(screen.queryByTestId("history-BRL")).not.toBeInTheDocument();
  });
});
