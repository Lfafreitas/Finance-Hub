import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as analyticsApi from "../api/analytics";
import * as apiClient from "../api/client";
import * as insightsApi from "../api/insights";
import * as overviewApi from "../api/overview";
import * as performanceApi from "../api/performance";
import * as reviewApi from "../api/review";
import type { AllocationSlice, ContributionPoint } from "../api/types";
import {
  BRL_ONLY_TEXTS,
  brlBlock,
  brlPosition,
  inconsistentPosition,
  INCONSISTENCY_REASON,
  makeBlock,
  makeSummary,
  USD_ONLY_TEXTS,
  usdBlock,
  usdPosition,
} from "../test/dashboardFixtures";
import { makeAnalytics, refreshFixture } from "../test/analyticsFixtures";
import { overviewFixture } from "../test/visualFixtures";
import { Dashboard } from "./Dashboard";

vi.mock("../api/client");
vi.mock("../api/overview");
vi.mock("../api/insights");
vi.mock("../api/performance");
vi.mock("../api/review");
vi.mock("../api/analytics");

// Os gráficos reais (recharts) não desenham nada mensurável no jsdom.
// Aqui eles só ecoam os dados que RECEBERAM, para os testes poderem
// afirmar que cada gráfico recebe apenas os dados do próprio bloco.
vi.mock("../components/AllocationChart", () => ({
  AllocationChart: ({ allocation }: { allocation: AllocationSlice[] }) => (
    <div data-testid="allocation-chart">
      {allocation.map((slice) => `${slice.asset_ticker}=${slice.percentage}|${slice.cost_basis}`).join(";")}
    </div>
  ),
}));
vi.mock("../components/ContributionChart", () => ({
  ContributionChart: ({ points }: { points: ContributionPoint[] }) => (
    <div data-testid="contribution-chart">
      {points.map((point) => `${point.date}=${point.cumulative_net_contribution}`).join(";")}
    </div>
  ),
}));

const twoCurrencies = makeSummary({
  positions: [brlPosition, usdPosition],
  totals_by_currency: [brlBlock, usdBlock],
});

async function renderLoaded(summary = makeSummary()) {
  vi.mocked(apiClient.getDashboardSummary).mockResolvedValue(summary);
  render(<Dashboard />);
  await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
}

describe("Dashboard", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(overviewApi.getOverview).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getPerformanceHistory).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getKpis).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAgenda).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getBenchmarks).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAllocation).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getFinancialHealth).mockReturnValue(new Promise(() => {}));
    vi.mocked(overviewApi.getMonthlyFlows).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([]);
    vi.mocked(performanceApi.getDividendsSummary).mockReturnValue(new Promise(() => {}));
    vi.mocked(insightsApi.getInsights).mockReturnValue(new Promise(() => {}));
    vi.mocked(reviewApi.getPendingGroups).mockReturnValue(new Promise(() => {}));
    vi.mocked(analyticsApi.getPortfolioAnalytics).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([]);
    vi.mocked(apiClient.getAccounts).mockResolvedValue([]);
    vi.mocked(overviewApi.getOverview).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getPerformanceHistory).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getKpis).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAgenda).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getBenchmarks).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAllocation).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getFinancialHealth).mockReturnValue(new Promise(() => {}));
    vi.mocked(overviewApi.getMonthlyFlows).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([]);
    vi.mocked(performanceApi.getDividendsSummary).mockReturnValue(new Promise(() => {}));
    vi.mocked(insightsApi.getInsights).mockReturnValue(new Promise(() => {}));
    vi.mocked(reviewApi.getPendingGroups).mockReturnValue(new Promise(() => {}));
    vi.mocked(analyticsApi.getPortfolioAnalytics).mockReturnValue(new Promise(() => {}));
  });

  it("mostra o estado de carregamento antes da resposta chegar", () => {
    vi.mocked(apiClient.getPortfolios).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getDashboardSummary).mockReturnValue(new Promise(() => {}));
    render(<Dashboard />);
    expect(screen.getByRole("status")).toHaveTextContent("Carregando");
  });

  it("renderiza os indicadores reais e marca os dependentes de mercado como indisponíveis", async () => {
    await renderLoaded();

    expect(screen.getByText("Valor investido (custo)")).toBeInTheDocument();
    expect(screen.getAllByText("Resultado realizado").length).toBeGreaterThan(0);
    expect(screen.getByText("Proventos recebidos")).toBeInTheDocument();

    const unavailableCards = screen.getAllByTestId("indicator-unavailable");
    // Patrimônio a mercado, P&L não realizado, Rentabilidade atual = 3 cards indisponíveis
    expect(unavailableCards).toHaveLength(3);
  });

  it("renderiza a tabela de posições vinda do resumo", async () => {
    await renderLoaded();

    expect(screen.getByTestId("positions-table")).toBeInTheDocument();
    expect(screen.getByText("PETR4")).toBeInTheDocument();
  });

  it("mostra mensagem de erro quando a chamada falha", async () => {
    vi.mocked(apiClient.getDashboardSummary).mockRejectedValue(new Error("500 falha no servidor"));
    render(<Dashboard />);

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent("500 falha no servidor");
  });
});

describe("Dashboard — uma moeda", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(overviewApi.getOverview).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getPerformanceHistory).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getKpis).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAgenda).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getBenchmarks).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAllocation).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getFinancialHealth).mockReturnValue(new Promise(() => {}));
    vi.mocked(overviewApi.getMonthlyFlows).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([]);
    vi.mocked(performanceApi.getDividendsSummary).mockReturnValue(new Promise(() => {}));
    vi.mocked(insightsApi.getInsights).mockReturnValue(new Promise(() => {}));
    vi.mocked(reviewApi.getPendingGroups).mockReturnValue(new Promise(() => {}));
    vi.mocked(analyticsApi.getPortfolioAnalytics).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([]);
    vi.mocked(apiClient.getAccounts).mockResolvedValue([]);
  });

  it("não mostra abas: só o rótulo da moeda e o bloco único", async () => {
    await renderLoaded();

    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.getByTestId("single-currency-label")).toHaveTextContent("Valores em BRL");
    expect(screen.getByTestId("currency-block-BRL")).toBeInTheDocument();
  });

  it("formata os cards na moeda do bloco, mesmo quando a única moeda não é BRL", async () => {
    await renderLoaded(makeSummary({ positions: [usdPosition], totals_by_currency: [usdBlock] }));

    expect(screen.getByTestId("single-currency-label")).toHaveTextContent("Valores em USD");
    // No card de custo e na linha da posição.
    expect(screen.getAllByText(/US\$\s7\.777,00/).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/^R\$/)).not.toBeInTheDocument();
  });
});

describe("Dashboard — duas ou mais moedas", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(overviewApi.getOverview).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getPerformanceHistory).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getKpis).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAgenda).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getBenchmarks).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAllocation).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getFinancialHealth).mockReturnValue(new Promise(() => {}));
    vi.mocked(overviewApi.getMonthlyFlows).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([]);
    vi.mocked(performanceApi.getDividendsSummary).mockReturnValue(new Promise(() => {}));
    vi.mocked(insightsApi.getInsights).mockReturnValue(new Promise(() => {}));
    vi.mocked(reviewApi.getPendingGroups).mockReturnValue(new Promise(() => {}));
    vi.mocked(analyticsApi.getPortfolioAnalytics).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([]);
    vi.mocked(apiClient.getAccounts).mockResolvedValue([]);
  });

  it("mostra uma aba por moeda, na ordem exata do backend, com a primeira ativa", async () => {
    await renderLoaded(makeSummary({ positions: [], totals_by_currency: [usdBlock, brlBlock] }));

    const tabs = within(screen.getByRole("tablist")).getAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual(["USD", "BRL"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[1]).toHaveAttribute("aria-selected", "false");
    expect(screen.getByTestId("currency-block-USD")).toBeInTheDocument();
    expect(screen.queryByTestId("single-currency-label")).not.toBeInTheDocument();
  });

  it("só um bloco fica na tela por vez, e trocar de aba troca o bloco", async () => {
    await renderLoaded(twoCurrencies);
    const user = userEvent.setup();

    expect(screen.getByTestId("currency-block-BRL")).toBeInTheDocument();
    expect(screen.queryByTestId("currency-block-USD")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "USD" }));

    expect(screen.getByTestId("currency-block-USD")).toBeInTheDocument();
    expect(screen.queryByTestId("currency-block-BRL")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "USD" })).toHaveAttribute("aria-selected", "true");
  });

  it("com BRL + USD, nenhum valor de uma moeda é renderizado na aba da outra", async () => {
    await renderLoaded(twoCurrencies);
    const user = userEvent.setup();

    // Aba BRL: cards, posições e gráficos só de BRL. Os gráficos são
    // conferidos por igualdade EXATA: nenhum ponto/fatia de outra moeda.
    const brl = screen.getByTestId("currency-block-BRL");
    for (const text of BRL_ONLY_TEXTS) expect(brl).toHaveTextContent(text);
    for (const text of USD_ONLY_TEXTS) expect(document.body).not.toHaveTextContent(text);
    expect(brl).toHaveTextContent(/R\$\s1\.111,00/);
    expect(document.body).not.toHaveTextContent("US$");
    expect(within(brl).getByTestId("allocation-chart").textContent).toBe("PETR4=100.00|1111.00");
    expect(within(brl).getByTestId("contribution-chart").textContent).toBe("2026-01-01=4444.00");

    await user.click(screen.getByRole("tab", { name: "USD" }));

    // Aba USD: o inverso.
    const usd = screen.getByTestId("currency-block-USD");
    for (const text of USD_ONLY_TEXTS) expect(usd).toHaveTextContent(text);
    for (const text of BRL_ONLY_TEXTS) expect(document.body).not.toHaveTextContent(text);
    expect(usd).toHaveTextContent(/US\$\s7\.777,00/);
    expect(document.body).not.toHaveTextContent("R$");
    expect(within(usd).getByTestId("allocation-chart").textContent).toBe("AAPL=100.00|7777.00");
    expect(within(usd).getByTestId("contribution-chart").textContent).toBe("2026-02-02=6666.00");
  });

  it("nenhum total somado ou convertido aparece em lugar nenhum", async () => {
    await renderLoaded(twoCurrencies);
    const user = userEvent.setup();

    // 1111 + 7777 = 8888; 4444 + 6666 = 11110.
    for (const tab of ["BRL", "USD"]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      expect(document.body).not.toHaveTextContent("8.888");
      expect(document.body).not.toHaveTextContent("8888");
      expect(document.body).not.toHaveTextContent("11.110,00");
      expect(document.body).not.toHaveTextContent("11110.00");
    }
  });

  it("trocar de carteira com a aba USD ativa cai no primeiro bloco se o novo resumo não tem USD", async () => {
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([{ id: "pf-1", name: "Só Brasil" }]);
    vi.mocked(apiClient.getDashboardSummary).mockImplementation(async (portfolioId) =>
      portfolioId === "pf-1"
        ? makeSummary({ portfolio_id: "pf-1", positions: [brlPosition], totals_by_currency: [brlBlock] })
        : twoCurrencies,
    );
    const user = userEvent.setup();
    render(<Dashboard />);
    await user.click(await screen.findByRole("tab", { name: "USD" }));
    expect(screen.getByTestId("currency-block-USD")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Selecionar carteira"), "pf-1");

    expect(await screen.findByTestId("currency-block-BRL")).toBeInTheDocument();
    expect(screen.queryByTestId("currency-block-USD")).not.toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    for (const text of USD_ONLY_TEXTS) expect(document.body).not.toHaveTextContent(text);
    // A distribuição acompanha a carteira escolhida.
    expect(analyticsApi.getPortfolioAnalytics).toHaveBeenLastCalledWith("pf-1", null);
  });
});

describe("Dashboard — posição inconsistente", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(overviewApi.getOverview).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getPerformanceHistory).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getKpis).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAgenda).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getBenchmarks).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAllocation).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getFinancialHealth).mockReturnValue(new Promise(() => {}));
    vi.mocked(overviewApi.getMonthlyFlows).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([]);
    vi.mocked(performanceApi.getDividendsSummary).mockReturnValue(new Promise(() => {}));
    vi.mocked(insightsApi.getInsights).mockReturnValue(new Promise(() => {}));
    vi.mocked(reviewApi.getPendingGroups).mockReturnValue(new Promise(() => {}));
    vi.mocked(analyticsApi.getPortfolioAnalytics).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([]);
    vi.mocked(apiClient.getAccounts).mockResolvedValue([
      {
        id: "acc-mix",
        name: "Conta Internacional",
        institution_id: "inst-1",
        institution_name: "Corretora Y",
        currency_code: "USD",
        portfolio_id: null,
        account_type: "BROKERAGE",
      },
    ]);
  });

  it("aparece no painel de aviso com conta, quantidade e motivo", async () => {
    await renderLoaded(makeSummary({ positions: [brlPosition, inconsistentPosition] }));

    const panel = screen.getByTestId("inconsistent-positions");
    expect(panel).toHaveTextContent("Posições com moedas misturadas (1)");
    expect(panel).toHaveTextContent("MIXD3");
    expect(panel).toHaveTextContent("Conta Internacional — Corretora Y");
    expect(panel).toHaveTextContent("15.00000000");
    expect(panel).toHaveTextContent(INCONSISTENCY_REASON);
  });

  it("uma posição inconsistente nunca aparece dentro de nenhum CurrencyBlock", async () => {
    await renderLoaded(
      makeSummary({
        positions: [brlPosition, usdPosition, inconsistentPosition],
        totals_by_currency: [brlBlock, usdBlock],
      }),
    );
    const user = userEvent.setup();

    for (const tab of ["BRL", "USD"]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      const block = screen.getByTestId(`currency-block-${tab}`);
      expect(block).not.toHaveTextContent("MIXD3");
      expect(block).not.toHaveTextContent("15.00000000");
      expect(within(block).getAllByRole("row")).toHaveLength(2); // cabeçalho + 1 posição
      // ...e o aviso continua visível, fora do bloco, em qualquer aba.
      expect(screen.getByTestId("inconsistent-positions")).toHaveTextContent("MIXD3");
      expect(block).not.toContainElement(screen.getByTestId("inconsistent-positions"));
    }
  });

  it("só inconsistentes e nenhum bloco: aviso + estado vazio, sem cards", async () => {
    await renderLoaded(makeSummary({ positions: [inconsistentPosition], totals_by_currency: [] }));

    expect(screen.getByTestId("inconsistent-positions")).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-empty")).toBeInTheDocument();
    expect(screen.queryByText("Valor investido (custo)")).not.toBeInTheDocument();
  });

  it("sem inconsistentes o painel não existe", async () => {
    await renderLoaded();

    expect(screen.queryByTestId("inconsistent-positions")).not.toBeInTheDocument();
  });

  it("falha ao carregar contas não impede o dashboard: mostra o id da conta", async () => {
    vi.mocked(apiClient.getAccounts).mockRejectedValue(new Error("x"));

    await renderLoaded(makeSummary({ positions: [inconsistentPosition] }));

    expect(screen.getByTestId("inconsistent-positions")).toHaveTextContent("acc-mix");
    expect(screen.getByTestId("currency-block-BRL")).toBeInTheDocument();
  });
});

describe("Dashboard — blocos especiais", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(overviewApi.getOverview).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getPerformanceHistory).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getKpis).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAgenda).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getBenchmarks).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAllocation).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getFinancialHealth).mockReturnValue(new Promise(() => {}));
    vi.mocked(overviewApi.getMonthlyFlows).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([]);
    vi.mocked(performanceApi.getDividendsSummary).mockReturnValue(new Promise(() => {}));
    vi.mocked(insightsApi.getInsights).mockReturnValue(new Promise(() => {}));
    vi.mocked(reviewApi.getPendingGroups).mockReturnValue(new Promise(() => {}));
    vi.mocked(analyticsApi.getPortfolioAnalytics).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([]);
    vi.mocked(apiClient.getAccounts).mockResolvedValue([]);
  });

  it("moeda só com caixa: nota explicativa, aportes formatados e estados vazios", async () => {
    const cashOnly = makeBlock({
      currency_code: "USD",
      total_cost_basis: "0",
      total_realized_gain: "0",
      total_dividends_received: "0",
      net_contributions: "500.00",
      is_closed: true,
      profitability_unavailable_reason: "sem posições no escopo",
      allocation: [],
      contribution_evolution: [{ date: "2026-03-03", cumulative_net_contribution: "500.00" }],
    });

    await renderLoaded(makeSummary({ positions: [], totals_by_currency: [cashOnly] }));

    expect(screen.getByTestId("cash-only-note")).toHaveTextContent("apenas movimentações de caixa");
    expect(screen.getByText(/US\$\s500,00/)).toBeInTheDocument();
    expect(screen.getByText("Nenhuma posição encontrada.")).toBeInTheDocument();
    expect(screen.getByTestId("contribution-chart")).toHaveTextContent("2026-03-03=500.00");
    // `is_closed`/motivo de rentabilidade do bloco não viram "carteira encerrada".
    expect(document.body).not.toHaveTextContent("sem posições no escopo");
  });

  it("bloco com posições não mostra a nota de caixa", async () => {
    await renderLoaded();

    expect(screen.queryByTestId("cash-only-note")).not.toBeInTheDocument();
  });

  it("escopo sem nenhum bloco mostra estado vazio — sem cards e sem moeda inventada", async () => {
    await renderLoaded(makeSummary({ positions: [], totals_by_currency: [] }));

    expect(screen.getByTestId("dashboard-empty")).toHaveTextContent("Nenhuma movimentação neste escopo.");
    expect(screen.queryByText("Valor investido (custo)")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("R$");
    expect(screen.queryByTestId("single-currency-label")).not.toBeInTheDocument();
  });
});

describe("Dashboard · patrimônio de todas as contas", () => {
  const text = (testId: string) => screen.getByTestId(testId).textContent?.replace(/ /g, " ");

  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([]);
    vi.mocked(apiClient.getAccounts).mockResolvedValue([]);
    vi.mocked(analyticsApi.getPortfolioAnalytics).mockReturnValue(new Promise(() => {}));
    vi.mocked(overviewApi.getOverview).mockResolvedValue(overviewFixture);
    vi.mocked(performanceApi.getPerformanceHistory).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getKpis).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAgenda).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getBenchmarks).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAllocation).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getFinancialHealth).mockReturnValue(new Promise(() => {}));
    vi.mocked(overviewApi.getMonthlyFlows).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([]);
    vi.mocked(performanceApi.getDividendsSummary).mockReturnValue(new Promise(() => {}));
    vi.mocked(insightsApi.getInsights).mockReturnValue(new Promise(() => {}));
    vi.mocked(reviewApi.getPendingGroups).mockReturnValue(new Promise(() => {}));
  });

  it("uma coluna por moeda, cada uma com o próprio total; nada somado entre elas", async () => {
    await renderLoaded();
    await screen.findByTestId("patrimony-overview");

    expect(text("overview-total-BRL")).toBe("R$ 13.275,60");
    expect(text("overview-total-USD")).toBe("US$ 506,86");
    expect(screen.getByTestId("patrimony-overview")).toHaveTextContent("Em 08/10/2026. Moedas não se somam.");
    expect(screen.getByRole("region", { name: "Patrimônio Em reais" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Patrimônio Em dólar" })).toBeInTheDocument();
    // 13275,60 + 506,86 = 13782,46 — nunca aparece.
    expect(document.body).not.toHaveTextContent("13.782");
  });

  it("quanto rendeu: valor e percentual com sinal, sobre o que foi aplicado", async () => {
    await renderLoaded();
    await screen.findByTestId("patrimony-overview");

    expect(text("overview-result-USD")).toBe("Investimentos rendem +US$ 5,62 (+1,12%) sobre US$ 501,24 aplicados");
    expect(within(screen.getByTestId("overview-result-USD")).getByText(/\+US\$ 5,62/)).toHaveClass("text-emerald-400");
    // Moeda sem investimento não mostra "rendeu".
    expect(screen.queryByTestId("overview-result-BRL")).not.toBeInTheDocument();
  });

  it("perda aparece em vermelho e com sinal de menos", async () => {
    const usd = { ...overviewFixture.totals_by_currency[1], result: "-12.3000", result_pct: "-0.0245" };
    vi.mocked(overviewApi.getOverview).mockResolvedValue({ ...overviewFixture, totals_by_currency: [usd] });
    await renderLoaded();
    await screen.findByTestId("patrimony-overview");

    expect(text("overview-result-USD")).toContain("-US$ 12,30 (-2,45%)");
    expect(within(screen.getByTestId("overview-result-USD")).getByText(/-US\$ 12,30/)).toHaveClass("text-red-400");
  });

  it("ativos sem cotação são nomeados e entram pelo valor aplicado", async () => {
    await renderLoaded();
    await screen.findByTestId("patrimony-overview");

    expect(text("overview-basis-USD")).toBe(
      "Sem cotação para AAXJ, VNQ: entram pelo valor aplicado, e o rendimento delas ainda não aparece.",
    );
    expect(screen.queryByTestId("overview-basis-BRL")).not.toBeInTheDocument();
  });

  it("composição: renda variável × renda fixa, reserva e disponível, com valor e fatia", async () => {
    await renderLoaded();
    await screen.findByTestId("patrimony-overview");

    expect(text("overview-parts-USD-VARIABLE")).toBe("Renda variávelUS$ 356,0370,24%");
    expect(text("overview-parts-USD-FIXED")).toBe("Renda fixaUS$ 150,8329,76%");
    expect(text("overview-parts-BRL-RESERVE")).toBe("ReservaR$ 13.200,0099,33%");
    expect(text("overview-parts-BRL-LIQUID")).toBe("DisponívelR$ 89,200,67%");
  });

  it("fatura em aberto aparece descontada; sem fatura, a linha não existe", async () => {
    await renderLoaded();
    await screen.findByTestId("patrimony-overview");

    expect(text("overview-card-BRL")).toBe("Fatura do cartão em aberto (já descontada do total)-R$ 13,60");
    expect(screen.queryByTestId("overview-card-USD")).not.toBeInTheDocument();
  });

  it("falha no patrimônio não derruba o resto do dashboard", async () => {
    vi.mocked(overviewApi.getOverview).mockRejectedValue(new Error("fora do ar"));
    await renderLoaded();

    expect(screen.queryByTestId("patrimony-overview")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Investimentos · todas as contas")).toBeInTheDocument();
  });

  it("sem nenhuma moeda, o painel de patrimônio não aparece", async () => {
    vi.mocked(overviewApi.getOverview).mockResolvedValue({ as_of: "2026-10-08", totals_by_currency: [] });
    await renderLoaded();
    await waitFor(() => expect(overviewApi.getOverview).toHaveBeenCalled());

    expect(screen.queryByTestId("patrimony-overview")).not.toBeInTheDocument();
  });

  it("a distribuição pede as análises da carteira escolhida", async () => {
    await renderLoaded();

    expect(analyticsApi.getPortfolioAnalytics).toHaveBeenCalledWith(null, null);
  });
});

describe("Dashboard · atenção, cotações e atalhos", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([]);
    vi.mocked(apiClient.getAccounts).mockResolvedValue([]);
    vi.mocked(apiClient.getDashboardSummary).mockResolvedValue(makeSummary());
    vi.mocked(overviewApi.getOverview).mockResolvedValue(overviewFixture);
    vi.mocked(performanceApi.getPerformanceHistory).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getKpis).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAgenda).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getBenchmarks).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAllocation).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getFinancialHealth).mockReturnValue(new Promise(() => {}));
    vi.mocked(overviewApi.getMonthlyFlows).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([]);
    vi.mocked(performanceApi.getDividendsSummary).mockReturnValue(new Promise(() => {}));
    vi.mocked(insightsApi.getInsights).mockReturnValue(new Promise(() => {}));
    vi.mocked(reviewApi.getPendingGroups).mockResolvedValue({ pending_entries: 612, pending_groups: 194, groups: [] });
    vi.mocked(analyticsApi.getPortfolioAnalytics).mockResolvedValue(makeAnalytics());
    vi.mocked(analyticsApi.refreshQuotes).mockResolvedValue(refreshFixture);
  });

  it("lista o que pede atenção e leva para onde se resolve", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<Dashboard onOpen={onOpen} />);

    const classify = await screen.findByTestId("attention-classify");
    expect(classify).toHaveTextContent("612 lançamentos do controle financeiro sem classificação");
    const unpriced = screen.getByTestId("attention-unpriced");
    expect(unpriced).toHaveTextContent("Sem cotação: AAXJ, VNQ.");

    await user.click(within(classify).getByRole("button", { name: "Classificar" }));
    await user.click(within(unpriced).getByRole("button", { name: "Informar cotação" }));
    expect(onOpen.mock.calls).toEqual([[{ page: "review" }], [{ page: "prices" }]]);
  });

  it("sem pendência e com tudo cotado, não há lista de atenção", async () => {
    vi.mocked(reviewApi.getPendingGroups).mockResolvedValue({ pending_entries: 0, pending_groups: 0, groups: [] });
    vi.mocked(overviewApi.getOverview).mockResolvedValue({
      ...overviewFixture,
      totals_by_currency: overviewFixture.totals_by_currency.map((b) => ({ ...b, unpriced: [] })),
    });

    render(<Dashboard />);

    await screen.findByTestId("patrimony-overview");
    expect(screen.queryByTestId("attention-list")).not.toBeInTheDocument();
  });

  it("cotação recente não é buscada de novo; o horário aparece no topo", async () => {
    render(<Dashboard />);

    await waitFor(() => expect(screen.getByTestId("quotes-status")).toHaveTextContent("Cotações de"));
    expect(analyticsApi.refreshQuotes).not.toHaveBeenCalled();
  });

  it("cotação velha é buscada sozinha e tudo é relido depois", async () => {
    // Um objeto novo a cada leitura, como no backend de verdade.
    vi.mocked(analyticsApi.getPortfolioAnalytics).mockImplementation(() =>
      Promise.resolve(makeAnalytics({ quotes_refreshed_at: "2026-01-01T10:00:00Z" })),
    );

    render(<Dashboard />);

    await waitFor(() => expect(analyticsApi.refreshQuotes).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(overviewApi.getOverview).toHaveBeenCalledTimes(2));
    expect(apiClient.getDashboardSummary).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(analyticsApi.getPortfolioAnalytics).toHaveBeenCalledTimes(2));
    await new Promise((resolve) => setTimeout(resolve, 50));
    // Mesmo continuando velha, não busca em seguida de novo (no máximo a cada 15 min).
    expect(analyticsApi.refreshQuotes).toHaveBeenCalledTimes(1);
  });

  it("falha ao buscar cotações vira um aviso com tentar de novo", async () => {
    vi.mocked(analyticsApi.getPortfolioAnalytics).mockResolvedValue(makeAnalytics({ quotes_refreshed_at: null }));
    vi.mocked(analyticsApi.refreshQuotes).mockRejectedValue(new TypeError("Failed to fetch"));
    const user = userEvent.setup();

    render(<Dashboard />);

    const warning = await screen.findByTestId("attention-quotes");
    expect(warning).toHaveTextContent("Não consegui buscar as cotações agora: Não foi possível falar com o servidor.");
    vi.mocked(analyticsApi.refreshQuotes).mockResolvedValue(refreshFixture);
    await user.click(within(warning).getByRole("button", { name: "Tentar de novo" }));
    await waitFor(() => expect(analyticsApi.refreshQuotes).toHaveBeenCalledTimes(2));
  });

  it("cada posição tem atalho para os lançamentos da conta dela", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<Dashboard onOpen={onOpen} />);

    await user.click(await screen.findByRole("button", { name: "Lançamentos de PETR4" }));

    expect(onOpen).toHaveBeenCalledWith({ page: "transactions", accountId: brlPosition.account_id });
  });
});
