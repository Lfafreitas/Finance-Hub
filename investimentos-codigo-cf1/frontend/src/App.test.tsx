import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as analyticsApi from "./api/analytics";
import * as cashApi from "./api/cashflow";
import * as insightsApi from "./api/insights";
import * as apiClient from "./api/client";
import * as overviewApi from "./api/overview";
import * as performanceApi from "./api/performance";
import * as reviewApi from "./api/review";
import App from "./App";
import { currentMonth, monthRange } from "./lib/cashflow";
import { balancesFixture, breakdownFixture, makeEntry, summaryFixture } from "./test/cashFixtures";
import { makeSummary } from "./test/dashboardFixtures";
import { insightsFixture, monthlyFixture } from "./test/visualFixtures";

vi.mock("./api/client");
vi.mock("./api/cashflow");
vi.mock("./api/overview");
vi.mock("./api/performance");
vi.mock("./api/analytics");
vi.mock("./api/insights");
vi.mock("./api/review");

const mainNav = () => screen.getByRole("navigation", { name: "Navegação principal" });
const buttonsOf = (nav: HTMLElement) => Array.from(nav.querySelectorAll("button")).map((button) => button.textContent);
// Barra lateral do computador: um grupo por livro, cada tela um botão.
const group = (name: string) => within(mainNav()).getByRole("group", { name });
const side = (groupName: string, label: string) => within(group(groupName)).getByRole("button", { name: label });
const inv = (label: string) => side("Investimentos", label);
const pagesOf = (groupName: string) => buttonsOf(group(groupName)).slice(1); // o 1º é o título do grupo

describe("App — navegação", () => {
  beforeEach(() => {
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([]);
    vi.mocked(apiClient.getAccounts).mockResolvedValue([]);
    vi.mocked(apiClient.getDashboardSummary).mockReturnValue(new Promise(() => {}));
    vi.mocked(overviewApi.getOverview).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getHealth).mockResolvedValue({ status: "ok" });
    vi.mocked(performanceApi.getPerformanceHistory).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getKpis).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAgenda).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getBenchmarks).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAllocation).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getFinancialHealth).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getDividendsSummary).mockReturnValue(new Promise(() => {}));
    vi.mocked(insightsApi.getAlerts).mockResolvedValue({ alerts: [], unread_count: 0, invalid_files: [] });
    vi.mocked(insightsApi.getInsights).mockReturnValue(new Promise(() => {}));
    vi.mocked(reviewApi.getPendingGroups).mockResolvedValue({ pending_entries: 0, pending_groups: 0, groups: [] });
    vi.mocked(overviewApi.getMonthlyFlows).mockReturnValue(new Promise(() => {}));
    vi.mocked(overviewApi.getSpendingInsights).mockReturnValue(new Promise(() => {}));
    vi.mocked(analyticsApi.getPortfolioAnalytics).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getPendingReconciliations).mockResolvedValue([]);
    vi.mocked(apiClient.getAssets).mockResolvedValue([]);
    vi.mocked(apiClient.getCurrencies).mockResolvedValue([]);
    vi.mocked(apiClient.getInstitutions).mockResolvedValue([]);
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([]);
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
  });

  it("abre no Dashboard", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Visão geral" })).toBeInTheDocument();
    expect(inv("Visão geral")).toHaveAttribute("aria-current", "page");
    expect(inv("Reconciliação")).not.toHaveAttribute("aria-current");
  });

  it("atalhos do Dashboard levam aos lançamentos da conta e a Classificar", async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.getDashboardSummary).mockResolvedValue(makeSummary());
    vi.mocked(reviewApi.getPendingGroups).mockResolvedValue({ pending_entries: 3, pending_groups: 1, groups: [] });
    vi.mocked(cashApi.getCategories).mockResolvedValue([]);
    vi.mocked(apiClient.getAccountTransactions).mockResolvedValue([]);
    const accountId = makeSummary().positions[0].account_id;
    vi.mocked(apiClient.getAccounts).mockResolvedValue([
      {
        id: "outra",
        name: "Outra",
        institution_id: "i",
        institution_name: "Banco",
        currency_code: "BRL",
        portfolio_id: null,
        account_type: "BROKERAGE",
      },
      {
        id: accountId,
        name: "XP",
        institution_id: "i",
        institution_name: "XP",
        currency_code: "BRL",
        portfolio_id: null,
        account_type: "BROKERAGE",
      },
    ]);
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Lançamentos de PETR4" }));
    expect(screen.getByRole("heading", { name: "Lançamentos" })).toBeInTheDocument();
    await waitFor(() => expect(apiClient.getAccountTransactions).toHaveBeenCalledWith(accountId));
    expect(screen.getByLabelText("Conta")).toHaveValue(accountId);

    await user.click(inv("Visão geral"));
    await user.click(
      await within(await screen.findByTestId("attention-list")).findByRole("button", { name: "Classificar" }),
    );
    expect(screen.getByRole("heading", { name: "Classificar o que falta" })).toBeInTheDocument();
  });

  it("navega para Reconciliação e volta para o Dashboard", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(inv("Reconciliação"));

    expect(screen.getByRole("heading", { name: "Reconciliação" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Visão geral" })).not.toBeInTheDocument();
    expect(inv("Reconciliação")).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("Nenhuma pendência de reconciliação.")).toBeInTheDocument();

    await user.click(inv("Visão geral"));

    expect(screen.getByRole("heading", { name: "Visão geral" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Reconciliação" })).not.toBeInTheDocument();
  });

  it("a tela de Reconciliação só busca dados quando é aberta", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(apiClient.getPendingReconciliations).not.toHaveBeenCalled();

    await user.click(inv("Reconciliação"));

    expect(apiClient.getPendingReconciliations).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["Lançamentos", "Nenhuma conta cadastrada. Crie uma conta em Cadastros antes de lançar operações."],
    ["Importar", "Nenhuma conta cadastrada. Crie uma conta em Cadastros antes de importar."],
    ["Cotações", "Nenhum ativo cadastrado. Cadastre um ativo em Cadastros antes de informar cotações."],
  ])("abre a tela %s", async (label, expectedText) => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(inv(label));

    expect(screen.getByRole("heading", { name: label })).toBeInTheDocument();
    expect(inv(label)).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText(expectedText)).toBeInTheDocument();
  });

  it("a barra lateral mostra todas as telas, agrupadas por livro", () => {
    render(<App />);

    expect(
      buttonsOf(mainNav()).filter((t) => ["Investimentos", "Controle financeiro", "Geral"].includes(t ?? "")),
    ).toEqual(["Investimentos", "Controle financeiro", "Geral"]);
    expect(pagesOf("Investimentos")).toEqual([
      "Visão geral",
      "Análises",
      "Jornal",
      "Lançamentos",
      "Importar",
      "Cotações",
      "Reconciliação",
    ]);
    expect(pagesOf("Controle financeiro")).toEqual([
      "Resumo",
      "Classificar",
      "Lançamentos",
      "Importar extrato",
      "Categorias",
      "Regras",
    ]);
    expect(pagesOf("Geral")).toEqual(["Anotações", "Cadastros", "Segurança"]);
  });

  it("um grupo recolhe e lembra que ficou recolhido", async () => {
    const user = userEvent.setup();
    localStorage.removeItem("sidebar-collapsed-v1");
    const { unmount } = render(<App />);

    const header = within(mainNav()).getByRole("button", { name: "Controle financeiro" });
    expect(header).toHaveAttribute("aria-expanded", "true");
    await user.click(header);
    expect(header).toHaveAttribute("aria-expanded", "false");
    unmount();

    render(<App />);
    expect(within(mainNav()).getByRole("button", { name: "Controle financeiro" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    localStorage.removeItem("sidebar-collapsed-v1");
  });

  it("Jornal mostra na barra lateral quantos alertas não foram lidos", async () => {
    vi.mocked(insightsApi.getAlerts).mockResolvedValue({ alerts: [], unread_count: 2, invalid_files: [] });
    render(<App />);
    expect(await within(group("Investimentos")).findByLabelText("2 não lido(s)")).toBeInTheDocument();
  });

  describe("celular: abas embaixo, no jeito do iPhone", () => {
    const tabBar = () => screen.getByRole("navigation", { name: "Abas" });

    it("cinco abas, Início ativa ao abrir", () => {
      render(<App />);
      expect(buttonsOf(tabBar())).toEqual(["Início", "Análises", "Jornal", "Caixa", "Mais"]);
      expect(within(tabBar()).getByRole("button", { name: "Início" })).toHaveAttribute("aria-current", "page");
    });

    it("Mais abre a lista agrupada e volta pelo ‹ Mais", async () => {
      const user = userEvent.setup();
      render(<App />);

      await user.click(within(tabBar()).getByRole("button", { name: "Mais" }));
      const menu = screen.getByTestId("more-menu");
      expect(within(menu).getByRole("button", { name: /Cotações/ })).toBeInTheDocument();
      await user.click(within(menu).getByRole("button", { name: /Cadastros/ }));

      expect(screen.queryByTestId("more-menu")).not.toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Cadastros" })).toBeInTheDocument();
      expect(within(tabBar()).getByRole("button", { name: "Mais" })).toHaveAttribute("aria-current", "page");
      await user.click(within(screen.getByTestId("compact-bar")).getByRole("button", { name: "Mais" }));
      expect(screen.getByTestId("more-menu")).toBeInTheDocument();
    });

    it("Jornal mostra quantos alertas não foram lidos", async () => {
      vi.mocked(insightsApi.getAlerts).mockResolvedValue({ alerts: [], unread_count: 3, invalid_files: [] });
      render(<App />);
      expect(await within(tabBar()).findByLabelText("3 não lido(s)")).toBeInTheDocument();
    });

    it("Caixa traz as telas do controle financeiro em pílulas", async () => {
      const user = userEvent.setup();
      vi.mocked(cashApi.getCashSummary).mockReturnValue(new Promise(() => {}));
      vi.mocked(cashApi.getCashBalances).mockReturnValue(new Promise(() => {}));
      vi.mocked(cashApi.getCategoryBreakdown).mockReturnValue(new Promise(() => {}));
      render(<App />);

      await user.click(within(tabBar()).getByRole("button", { name: "Caixa" }));
      const pills = screen.getByRole("navigation", { name: "Telas do caixa" });
      expect(within(pills).getByRole("button", { name: "Resumo" })).toHaveAttribute("aria-current", "page");
      await user.click(within(pills).getByRole("button", { name: "Classificar" }));
      expect(within(pills).getByRole("button", { name: "Classificar" })).toHaveAttribute("aria-current", "page");
    });
  });

  it("Cadastros é uma área sem telas internas", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(side("Geral", "Cadastros"));

    expect(screen.getByRole("heading", { name: "Cadastros" })).toBeInTheDocument();
    expect(await screen.findByText("Nenhuma instituição cadastrada.")).toBeInTheDocument();

    // Sem telas internas: nada de pílulas de telas (só as do caixa no celular).
    expect(screen.queryByRole("navigation", { name: /Telas/ })).not.toBeInTheDocument();
    expect(side("Geral", "Cadastros")).toHaveAttribute("aria-current", "page");
    expect(inv("Visão geral")).not.toHaveAttribute("aria-current");
  });
});

describe("App — controle financeiro", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([]);
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([]);
    vi.mocked(apiClient.getAccounts).mockResolvedValue([]);
    vi.mocked(apiClient.getDashboardSummary).mockReturnValue(new Promise(() => {}));
    vi.mocked(overviewApi.getOverview).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getHealth).mockResolvedValue({ status: "ok" });
    vi.mocked(performanceApi.getPerformanceHistory).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getKpis).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAgenda).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getBenchmarks).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getAllocation).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getFinancialHealth).mockReturnValue(new Promise(() => {}));
    vi.mocked(performanceApi.getDividendsSummary).mockReturnValue(new Promise(() => {}));
    vi.mocked(insightsApi.getAlerts).mockResolvedValue({ alerts: [], unread_count: 0, invalid_files: [] });
    vi.mocked(insightsApi.getInsights).mockReturnValue(new Promise(() => {}));
    vi.mocked(reviewApi.getPendingGroups).mockResolvedValue({ pending_entries: 0, pending_groups: 0, groups: [] });
    vi.mocked(overviewApi.getMonthlyFlows).mockImplementation((end) => Promise.resolve(monthlyFixture(end)));
    vi.mocked(overviewApi.getSpendingInsights).mockImplementation((m) => Promise.resolve(insightsFixture(m)));
    vi.mocked(analyticsApi.getPortfolioAnalytics).mockReturnValue(new Promise(() => {}));
    vi.mocked(cashApi.getCashBalances).mockResolvedValue(balancesFixture);
    vi.mocked(cashApi.getCashSummary).mockResolvedValue(summaryFixture);
    vi.mocked(cashApi.getCategoryBreakdown).mockResolvedValue(breakdownFixture);
    vi.mocked(cashApi.countCashEntries).mockResolvedValue({ total: 4 });
    vi.mocked(cashApi.getCashEntries).mockResolvedValue([makeEntry()]);
    vi.mocked(cashApi.getCategories).mockResolvedValue([]);
    vi.mocked(cashApi.getTags).mockResolvedValue([]);
    vi.mocked(cashApi.getRules).mockResolvedValue([]);
    vi.mocked(cashApi.getCashImportBatches).mockResolvedValue([]);
    vi.mocked(apiClient.getAssets).mockResolvedValue([]);
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
  });

  const openCash = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(side("Controle financeiro", "Resumo"));
    return group("Controle financeiro");
  };

  it("nada do livro de caixa é buscado antes de a área ser aberta", () => {
    render(<App />);

    expect(cashApi.getCashBalances).not.toHaveBeenCalled();
    expect(cashApi.getCashEntries).not.toHaveBeenCalled();
  });

  it("abre no Resumo", async () => {
    const user = userEvent.setup();
    render(<App />);

    const nav = await openCash(user);

    expect(within(nav).getByRole("button", { name: "Resumo" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "Resumo do controle financeiro" })).toBeInTheDocument();
    expect(await screen.findByTestId("period-BRL")).toBeInTheDocument();
    expect(inv("Visão geral")).not.toHaveAttribute("aria-current");
  });

  it.each([
    ["Classificar", "Classificar o que falta"],
    ["Lançamentos", "Lançamentos de caixa"],
    ["Importar extrato", "Importar extrato ou fatura"],
    ["Categorias", "Categorias e tags"],
    ["Regras", "Regras de classificação"],
  ])("abre a tela %s do controle financeiro", async (label, heading) => {
    const user = userEvent.setup();
    render(<App />);
    const nav = await openCash(user);

    await user.click(within(nav).getByRole("button", { name: label }));

    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: label })).toHaveAttribute("aria-current", "page");
  });

  it("a barra lateral vai direto a qualquer tela, de um livro para o outro", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(inv("Cotações"));
    await user.click(side("Controle financeiro", "Regras"));
    expect(screen.getByRole("heading", { name: "Regras de classificação" })).toBeInTheDocument();
    expect(inv("Cotações")).not.toHaveAttribute("aria-current");

    await user.click(inv("Cotações"));
    expect(screen.getByRole("heading", { name: "Cotações" })).toBeInTheDocument();
  });

  it("o aviso do Resumo leva à tela Classificar", async () => {
    const user = userEvent.setup();
    render(<App />);
    const nav = await openCash(user);

    await user.click(await screen.findByRole("button", { name: "Classificar em grupos" }));

    expect(screen.getByRole("heading", { name: "Classificar o que falta" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Classificar" })).toHaveAttribute("aria-current", "page");
  });

  it("o aviso do Resumo abre os lançamentos não classificados daquele mês", async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.getAccounts).mockResolvedValue([
      {
        id: "acc-checking",
        name: "Conta Corrente",
        institution_id: "i",
        institution_name: "Banco",
        currency_code: "BRL",
        portfolio_id: null,
        account_type: "CHECKING",
      },
    ]);
    render(<App />);
    await openCash(user);

    await user.click(await screen.findByRole("button", { name: "Ver esses lançamentos" }));

    const range = monthRange(currentMonth());
    expect(screen.getByRole("heading", { name: "Lançamentos de caixa" })).toBeInTheDocument();
    await screen.findByTestId("entries-table");
    expect(cashApi.getCashEntries).toHaveBeenCalledWith(
      { start: range?.start, end: range?.end, nature: "UNCLASSIFIED" },
      50,
      0,
    );
    expect(screen.getByLabelText("Natureza")).toHaveValue("UNCLASSIFIED");
  });
});
