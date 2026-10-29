import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/cashflow";
import { ApiError } from "../../api/client";
import * as overviewApi from "../../api/overview";
import type { CurrencySpendingInsights } from "../../api/overview";
import { currentMonth, monthRange } from "../../lib/cashflow";
import { balancesFixture, breakdownFixture, summaryFixture } from "../../test/cashFixtures";
import { insightsFixture, monthlyFixture } from "../../test/visualFixtures";
import { CashSummary } from "./CashSummary";

vi.mock("../../api/cashflow");
vi.mock("../../api/overview");

function mockAll(unclassified = 0, insights: Partial<CurrencySpendingInsights> = {}) {
  vi.mocked(api.getCashBalances).mockResolvedValue(balancesFixture);
  vi.mocked(api.getCashSummary).mockResolvedValue(summaryFixture);
  vi.mocked(api.getCategoryBreakdown).mockResolvedValue(breakdownFixture);
  vi.mocked(api.countCashEntries).mockResolvedValue({ total: unclassified });
  vi.mocked(overviewApi.getMonthlyFlows).mockImplementation((end) => Promise.resolve(monthlyFixture(end)));
  vi.mocked(overviewApi.getSpendingInsights).mockImplementation((m) => Promise.resolve(insightsFixture(m, insights)));
}

const text = (testId: string) => screen.getByTestId(testId).textContent?.replace(/\u00a0/g, " ");

const pickMonth = (month: string) => fireEvent.change(screen.getByLabelText("Mês"), { target: { value: month } });

describe("CashSummary", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockAll();
  });

  it("abre no mês corrente e pede o período inteiro dele", async () => {
    render(<CashSummary />);

    await screen.findByTestId("period-BRL");
    const range = monthRange(currentMonth());
    expect(api.getCashSummary).toHaveBeenCalledWith(range?.start, range?.end);
    expect(api.getCategoryBreakdown).toHaveBeenCalledWith(range?.start, range?.end);
    expect(api.countCashEntries).toHaveBeenCalledWith({ start: range?.start, end: range?.end, nature: "UNCLASSIFIED" });
    expect(overviewApi.getMonthlyFlows).toHaveBeenCalledWith(currentMonth(), 6);
    expect(overviewApi.getSpendingInsights).toHaveBeenCalledWith(currentMonth());
  });

  it("os destaques do mês: entradas, saídas, sobra, investido e reserva, como o backend calculou", async () => {
    render(<CashSummary />);
    await screen.findByTestId("period-BRL");

    expect(text("kpi-income-BRL-value")).toBe("R$ 5.001,00");
    expect(text("kpi-expenses-BRL-value")).toBe("R$ 1.234,56");
    expect(text("kpi-surplus-BRL-value")).toBe("+R$ 3.766,44");
    expect(screen.getByTestId("kpi-surplus-BRL-value")).toHaveClass("text-emerald-400");
    expect(text("kpi-invested-BRL-value")).toBe("R$ 1.050,00");
    expect(text("kpi-reserve-BRL-value")).toBe("R$ 2.222,00");
    expect(screen.getByTestId("kpi-reserve-BRL")).toHaveTextContent("saldo em 31/08/2026");
  });

  it("sobra negativa fica em vermelho e com sinal de menos", async () => {
    vi.mocked(overviewApi.getMonthlyFlows).mockImplementation((end) => {
      const flows = monthlyFixture(end);
      flows.totals_by_currency[0].months[1] = { ...flows.totals_by_currency[0].months[1], surplus: "-120.5000" };
      return Promise.resolve(flows);
    });
    render(<CashSummary />);
    await screen.findByTestId("period-BRL");

    expect(text("kpi-surplus-BRL-value")).toBe("-R$ 120,50");
    expect(screen.getByTestId("kpi-surplus-BRL-value")).toHaveClass("text-red-400");
  });

  it("entradas × saídas: um gráfico e a tabela com os números exatos de cada mês", async () => {
    render(<CashSummary />);
    await screen.findByTestId("period-BRL");

    const rows = Array.from(screen.getByTestId("monthly-table-BRL").querySelectorAll("tbody tr")).map((row) =>
      Array.from(row.querySelectorAll("td")).map((cell) => cell.textContent?.replace(/\u00a0/g, " ")),
    );
    expect(rows[0]).toEqual(["jul/2026", "R$ 4.100,00", "R$ 3.900,00", "+R$ 200,00"]);
    expect(rows[1][3]).toBe("+R$ 3.766,44");
    expect(screen.getByTestId("monthly-BRL")).toHaveTextContent("últimos 2 meses");
  });

  it("a conferência do mês fica recolhida, mas com todos os números", async () => {
    render(<CashSummary />);
    const period = await screen.findByTestId("period-BRL");

    const details = period.closest("details");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
  });

  it("mostra cada número do período exatamente como o backend calculou", async () => {
    render(<CashSummary />);

    await screen.findByTestId("period-BRL");
    const expected: Record<string, string> = {
      "income-BRL": "R$ 5.001,00",
      "third-BRL": "-R$ 12,00",
      "adjust-BRL": "R$ 1.254,30",
      "unclassified-BRL": "-R$ 629,80",
      "transit-BRL": "R$ 7,77",
      "expenses-BRL": "R$ 1.234,56",
      "invested-BRL": "R$ 1.050,00",
      "liquid-var-BRL": "R$ 89,20",
      "reserve-var-BRL": "R$ 300,00",
      "card-var-BRL": "R$ 535,30",
    };
    for (const [testId, text] of Object.entries(expected)) {
      expect(screen.getByTestId(testId).textContent?.replace(/ /g, " "), testId).toBe(text);
    }
    expect(screen.getByTestId("period-BRL")).toHaveTextContent("30 lançamentos");
  });

  it("mostra o saldo de cada conta e os totais por papel, sem um total geral", async () => {
    render(<CashSummary />);

    const panel = await screen.findByTestId("balances-BRL");
    expect(panel).toHaveTextContent("Saldos em 31/08/2026");
    expect(screen.getByTestId("balance-acc-checking").textContent?.replace(/ /g, " ")).toBe("R$ 1.789,20");
    expect(screen.getByTestId("balance-acc-card").textContent?.replace(/ /g, " ")).toBe("-R$ 313,60");
    expect(screen.getByTestId("liquid-BRL").textContent?.replace(/ /g, " ")).toBe("R$ 1.789,20");
    expect(screen.getByTestId("reserve-BRL").textContent?.replace(/ /g, " ")).toBe("R$ 2.222,00");
    expect(screen.getByTestId("card-BRL").textContent?.replace(/ /g, " ")).toBe("-R$ 313,60");
    expect(within(panel).queryByText(/total geral/i)).not.toBeInTheDocument();
    expect(within(panel).queryByText("Conta Dólar")).not.toBeInTheDocument();
  });

  it("cada moeda tem a sua seção; moeda sem movimento no mês diz isso", async () => {
    render(<CashSummary />);

    await screen.findByTestId("period-BRL");
    const usd = screen.getByRole("region", { name: "Resumo em USD" });
    expect(within(usd).getByText("Conta Dólar")).toBeInTheDocument();
    expect(within(usd).getByTestId("liquid-USD").textContent).toContain("55,50");
    expect(within(usd).getByTestId("no-movement-USD")).toBeInTheDocument();
    expect(screen.queryByTestId("period-USD")).not.toBeInTheDocument();
    expect(within(usd).queryByTestId("kpi-income-USD")).not.toBeInTheDocument();
    expect(within(usd).queryByTestId("categories-USD")).not.toBeInTheDocument();
  });

  it("para onde foi: maiores primeiro, filhas sob a mãe, fatia do gasto total, sem as que não têm gasto", async () => {
    render(<CashSummary />);

    const panel = await screen.findByTestId("categories-BRL");
    const rows = Array.from(panel.querySelectorAll("[data-testid^='category-']")).map((row) =>
      row.textContent?.replace(/\u00a0/g, " "),
    );
    expect(rows).toEqual([
      "MoradiaR$ 650,0065,00%",
      "AlimentaçãoR$ 250,0025,00%",
      "MercadoR$ 200,0020,00%",
      "Sem categoriaR$ 100,0010,00%",
    ]);
    expect(screen.getByTestId("category-cat-market")).toHaveClass("pl-7");
    expect(within(panel).queryByText("Salário")).not.toBeInTheDocument();
  });

  it("a barra é proporcional à maior categoria; o investido aparece à parte", async () => {
    render(<CashSummary />);

    await screen.findByTestId("categories-BRL");
    const bar = (id: string) => (screen.getByTestId(id).querySelector("div[style]") as HTMLElement).style.width;
    expect(bar("category-cat-home")).toBe("100%");
    expect(bar("category-cat-food")).toBe("38.5%");
    expect(bar("category-none")).toBe("15.4%");
    expect(text("invested-bar-BRL")).toBe("Investido (líquido)R$ 1.050,00");
  });

  it("resgate maior que aporte não vira barra de investido", async () => {
    vi.mocked(api.getCashSummary).mockResolvedValue({
      ...summaryFixture,
      totals_by_currency: [{ ...summaryFixture.totals_by_currency[0], net_invested: "-50.0000" }],
    });
    render(<CashSummary />);

    await screen.findByTestId("categories-BRL");
    expect(screen.queryByTestId("invested-bar-BRL")).not.toBeInTheDocument();
  });

  it("sem gasto no período, diz isso em vez de uma lista vazia", async () => {
    vi.mocked(api.getCategoryBreakdown).mockResolvedValue({
      ...breakdownFixture,
      totals_by_currency: [{ currency_code: "BRL", expenses: "0.0000", income: "0.0000", categories: [] }],
    });

    render(<CashSummary />);

    expect(await screen.findByText("Nenhum gasto classificado no período.")).toBeInTheDocument();
  });

  it("onde dá para melhorar: cada achado do backend vira um cartão com os números dele", async () => {
    mockAll(0, {
      unclassified_outflow: "629.8000",
      unclassified_share: "0.3378",
      above_normal: [{ key: "cat-home", label: "Moradia", current: "650.0000", average: "400.0000", difference: "250.0000" }],
      recurring: [{ label: "STREAMING", monthly_average: "39.9000" }],
      recurring_total: "39.9000",
      small_count: 6,
      small_total: "88.0000",
      top_categories: [
        { key: "cat-home", label: "Moradia", amount: "650.0000", share: "0.6500" },
        { key: null, label: null, amount: "100.0000", share: "0.1000" },
      ],
      top_share: "0.7500",
    });
    render(<CashSummary />);
    await screen.findByTestId("improvements-BRL");

    expect(text("insight-unclassified")).toContain("R$ 629,80 em saídas ainda sem classificação (33,78% das saídas do mês)");
    expect(text("insight-above")).toContain("Moradia: R$ 650,00 este mês, contra uma média de R$ 400,00 nos 3 meses anteriores (+R$ 250,00)");
    expect(text("insight-recurring")).toContain("Se repetem todo mês · R$ 39,90/mês");
    expect(text("insight-recurring")).toContain("STREAMINGR$ 39,90/mês");
    expect(text("insight-small")).toContain("6 compras abaixo de R$ 30,00 somaram R$ 88,00 no mês");
    expect(text("insight-top")).toContain("As 2 maiores categorias somam 75,00% dos gastos: Moradia (65,00%), Sem categoria (10,00%)");
    expect(screen.queryByTestId("insight-history")).not.toBeInTheDocument();
  });

  it("sem histórico, explica o que falta; pouco não classificado e nada fora do padrão, diz isso", async () => {
    mockAll(0, { history_months: 1, unclassified_outflow: "10.0000", unclassified_share: "0.1999" });
    const { unmount } = render(<CashSummary />);
    await screen.findByTestId("improvements-BRL");
    expect(screen.getByTestId("insight-history")).toHaveTextContent("pelo menos 2 meses anteriores");
    expect(screen.queryByTestId("insight-unclassified")).not.toBeInTheDocument();
    unmount();

    mockAll(0, { history_months: 2 });
    render(<CashSummary />);
    const panel = await screen.findByTestId("improvements-BRL");
    expect(panel).toHaveTextContent("Nada fora do seu padrão neste mês.");
  });

  it("20% das saídas sem classificação já pede para classificar", async () => {
    mockAll(0, { unclassified_outflow: "246.9100", unclassified_share: "0.2000" });
    render(<CashSummary />);
    await screen.findByTestId("improvements-BRL");

    expect(screen.getByTestId("insight-unclassified")).toHaveTextContent("20,00% das saídas do mês");
  });

  it("uma só categoria no topo não vira cartão de concentração", async () => {
    mockAll(0, {
      top_categories: [{ key: "cat-home", label: "Moradia", amount: "650.0000", share: "1.0000" }],
      top_share: "1.0000",
    });
    render(<CashSummary />);
    await screen.findByTestId("improvements-BRL");

    expect(screen.queryByTestId("insight-top")).not.toBeInTheDocument();
  });

  it("avisa quantos lançamentos do mês faltam classificar e leva até eles", async () => {
    mockAll(27);
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<CashSummary onOpenUnclassified={onOpen} />);
    await screen.findByTestId("period-BRL");
    pickMonth("2026-08");

    const warning = await screen.findByTestId("unclassified-warning");
    expect(warning).toHaveTextContent("27 lançamentos do mês ainda não foram classificados");
    await user.click(within(warning).getByRole("button", { name: "Ver esses lançamentos" }));

    expect(onOpen).toHaveBeenCalledWith("2026-08");
  });

  it("um só lançamento pendente fica no singular; nenhum, sem aviso", async () => {
    mockAll(1);
    const { unmount } = render(<CashSummary />);
    expect(await screen.findByTestId("unclassified-warning")).toHaveTextContent(
      "1 lançamento do mês ainda não foi classificado",
    );
    unmount();

    mockAll(0);
    render(<CashSummary />);
    await screen.findByTestId("period-BRL");
    expect(screen.queryByTestId("unclassified-warning")).not.toBeInTheDocument();
  });

  it("trocar o mês busca o novo período", async () => {
    render(<CashSummary />);
    await screen.findByTestId("period-BRL");

    pickMonth("2026-02");

    await waitFor(() => expect(api.getCashSummary).toHaveBeenLastCalledWith("2026-02-01", "2026-02-28"));
    expect(api.getCategoryBreakdown).toHaveBeenLastCalledWith("2026-02-01", "2026-02-28");
    expect(overviewApi.getMonthlyFlows).toHaveBeenLastCalledWith("2026-02", 6);
    expect(overviewApi.getSpendingInsights).toHaveBeenLastCalledWith("2026-02");
  });

  it("ao trocar de mês, os números do mês anterior somem enquanto o novo carrega", async () => {
    render(<CashSummary />);
    await screen.findByTestId("period-BRL");
    vi.mocked(api.getCashSummary).mockReturnValue(new Promise(() => {}));

    pickMonth("2026-03");

    expect(screen.queryByTestId("period-BRL")).not.toBeInTheDocument();
    expect(screen.queryByTestId("balances-BRL")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Carregando");
  });

  it("resposta atrasada de um mês anterior não aparece no mês escolhido", async () => {
    let resolveOld: (value: typeof summaryFixture) => void = () => {};
    vi.mocked(api.getCashSummary).mockImplementation((start) =>
      start === "2026-01-01"
        ? new Promise((resolve) => {
            resolveOld = resolve;
          })
        : Promise.resolve({ ...summaryFixture, totals_by_currency: [] }),
    );
    render(<CashSummary />);
    pickMonth("2026-01");
    pickMonth("2026-03");
    await screen.findByTestId("no-movement-BRL");

    resolveOld(summaryFixture);
    await Promise.resolve();

    expect(screen.queryByTestId("period-BRL")).not.toBeInTheDocument();
    expect(screen.getByTestId("no-movement-BRL")).toBeInTheDocument();
  });

  it("mês apagado não dispara busca e pede para escolher", async () => {
    render(<CashSummary />);
    await screen.findByTestId("period-BRL");
    vi.mocked(api.getCashSummary).mockClear();

    pickMonth("");

    expect(screen.getByText("Escolha um mês.")).toBeInTheDocument();
    expect(api.getCashSummary).not.toHaveBeenCalled();
  });

  it("sem conta de caixa, orienta a cadastrar", async () => {
    vi.mocked(api.getCashBalances).mockResolvedValue({ as_of: "2026-08-31", accounts: [], totals_by_currency: [] });

    render(<CashSummary />);

    expect(await screen.findByTestId("no-cash-accounts")).toHaveTextContent("Cadastros");
  });

  it("erro do servidor aparece com o motivo, sem números", async () => {
    vi.mocked(api.getCashSummary).mockRejectedValue(new ApiError(400, "Bad Request", '{"detail":"início do período depois do fim"}'));

    render(<CashSummary />);

    expect(await screen.findByRole("alert")).toHaveTextContent("início do período depois do fim");
    expect(screen.queryByTestId("period-BRL")).not.toBeInTheDocument();
  });
});
