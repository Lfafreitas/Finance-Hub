import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import { ApiError } from "../api/client";
import { brlAccount, checkingAccount, currencies, petr4 } from "../test/workFixtures";
import { Registry } from "./Registry";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getInstitutions: vi.fn(),
  getAccounts: vi.fn(),
  getPortfolios: vi.fn(),
  getAssets: vi.fn(),
  getCurrencies: vi.fn(),
  getAssetClasses: vi.fn(),
  createInstitution: vi.fn(),
  createAccount: vi.fn(),
  createAsset: vi.fn(),
  createPortfolio: vi.fn(),
}));

const institution = { id: "inst-1", name: "Corretora X", institution_type: "BROKER" as const, country: "BR" };

describe("Registry", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(apiClient.getInstitutions).mockResolvedValue([institution]);
    vi.mocked(apiClient.getAccounts).mockResolvedValue([]);
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([{ id: "pf-1", name: "Longo prazo" }]);
    vi.mocked(apiClient.getAssets).mockResolvedValue([]);
    vi.mocked(apiClient.getCurrencies).mockResolvedValue(currencies);
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([{ code: "STOCK_US", label: "Ação (Exterior)" }]);
  });

  it("mostra as listas existentes e os estados vazios", async () => {
    render(<Registry />);

    expect(await screen.findByTestId("institution-list")).toHaveTextContent("Corretora X (BR)");
    expect(screen.getByTestId("portfolio-list")).toHaveTextContent("Longo prazo");
    expect(screen.getByText("Nenhuma conta cadastrada.")).toBeInTheDocument();
    expect(screen.getByText("Nenhum ativo cadastrado.")).toBeInTheDocument();
  });

  it("cria conta com instituição, moeda e carteira escolhidas e relê as listas", async () => {
    vi.mocked(apiClient.createAccount).mockResolvedValue(brlAccount);
    vi.mocked(apiClient.getAccounts).mockResolvedValueOnce([]).mockResolvedValueOnce([brlAccount]);
    const user = userEvent.setup();
    render(<Registry />);

    await user.type(await screen.findByLabelText("Nome da conta"), "Conta Ações");
    await user.selectOptions(screen.getByLabelText("Instituição"), "inst-1");
    await user.selectOptions(screen.getByLabelText("Moeda da conta"), "USD");
    await user.selectOptions(screen.getByLabelText("Carteira (opcional)"), "pf-1");
    await user.click(screen.getByRole("form", { name: "Nova conta" }).querySelector("button")!);

    await waitFor(() =>
      expect(apiClient.createAccount).toHaveBeenCalledWith({
        name: "Conta Ações",
        institution_id: "inst-1",
        currency_code: "USD",
        account_type: "BROKERAGE",
        portfolio_id: "pf-1",
      }),
    );
    expect(await screen.findByTestId("account-list")).toHaveTextContent(
      "Conta Ações — Corretora X (BRL) · Investimentos",
    );
    expect(apiClient.getAccounts).toHaveBeenCalledTimes(2);
  });

  it("conta de caixa envia o tipo, nunca a carteira, e aparece com o rótulo do tipo", async () => {
    vi.mocked(apiClient.createAccount).mockResolvedValue(checkingAccount);
    vi.mocked(apiClient.getAccounts).mockResolvedValueOnce([]).mockResolvedValueOnce([checkingAccount]);
    const user = userEvent.setup();
    render(<Registry />);

    await user.type(await screen.findByLabelText("Nome da conta"), "Conta Corrente");
    await user.selectOptions(screen.getByLabelText("Instituição"), "inst-1");
    await user.selectOptions(screen.getByLabelText("Carteira (opcional)"), "pf-1");
    await user.selectOptions(screen.getByLabelText("Tipo da conta"), "CHECKING");

    expect(screen.getByLabelText("Carteira (opcional)")).toBeDisabled();
    expect(screen.getByLabelText("Carteira (opcional)")).toHaveValue("");
    await user.click(screen.getByRole("form", { name: "Nova conta" }).querySelector("button")!);

    await waitFor(() =>
      expect(apiClient.createAccount).toHaveBeenCalledWith({
        name: "Conta Corrente",
        institution_id: "inst-1",
        currency_code: "BRL",
        account_type: "CHECKING",
      }),
    );
    expect(await screen.findByTestId("account-list")).toHaveTextContent(
      "Conta Corrente — Banco Z (BRL) · Conta corrente",
    );
  });

  it("oferece os cinco tipos de conta, com Investimentos como padrão", async () => {
    render(<Registry />);

    const select = await screen.findByLabelText("Tipo da conta");

    expect(select).toHaveValue("BROKERAGE");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent)).toEqual([
      "Investimentos",
      "Conta corrente",
      "Reserva",
      "Cartão de crédito",
      "Dinheiro",
    ]);
  });

  it("conta sem carteira não envia portfolio_id", async () => {
    vi.mocked(apiClient.createAccount).mockResolvedValue(brlAccount);
    const user = userEvent.setup();
    render(<Registry />);

    await user.type(await screen.findByLabelText("Nome da conta"), "Conta Simples");
    await user.selectOptions(screen.getByLabelText("Instituição"), "inst-1");
    await user.click(screen.getByRole("form", { name: "Nova conta" }).querySelector("button")!);

    await waitFor(() =>
      expect(apiClient.createAccount).toHaveBeenCalledWith({
        name: "Conta Simples",
        institution_id: "inst-1",
        currency_code: "BRL",
        account_type: "BROKERAGE",
      }),
    );
  });

  it("cria ativo com ticker, classe, país e moeda", async () => {
    vi.mocked(apiClient.createAsset).mockResolvedValue(petr4);
    vi.mocked(apiClient.getAssets).mockResolvedValueOnce([]).mockResolvedValueOnce([petr4]);
    const user = userEvent.setup();
    render(<Registry />);

    await user.type(await screen.findByLabelText("Ticker"), "aapl");
    await user.type(screen.getByLabelText("Nome do ativo"), "Apple");
    await user.selectOptions(screen.getByLabelText("Classe"), "STOCK_US");
    await user.clear(screen.getByLabelText("País do ativo (2 letras)"));
    await user.type(screen.getByLabelText("País do ativo (2 letras)"), "US");
    await user.selectOptions(screen.getByLabelText("Moeda do ativo"), "USD");
    await user.click(screen.getByRole("form", { name: "Novo ativo" }).querySelector("button")!);

    await waitFor(() =>
      expect(apiClient.createAsset).toHaveBeenCalledWith({
        ticker: "aapl",
        name: "Apple",
        asset_class_code: "STOCK_US",
        country: "US",
        currency_code: "USD",
        maturity_date: null,
        annual_rate: null,
      }),
    );
    // A lista vem da releitura do backend, não do que foi digitado.
    expect(await screen.findByTestId("asset-list")).toHaveTextContent("PETR4 — Petrobras (BR, BRL)");
    expect(screen.getByLabelText("Ticker")).toHaveValue("");
  });

  it("cria instituição e carteira", async () => {
    vi.mocked(apiClient.createInstitution).mockResolvedValue(institution);
    vi.mocked(apiClient.createPortfolio).mockResolvedValue({ id: "pf-2", name: "Reserva" });
    const user = userEvent.setup();
    render(<Registry />);

    await user.type(await screen.findByLabelText("Nome da instituição"), "Banco Z");
    await user.selectOptions(screen.getByLabelText("Tipo"), "BANK");
    await user.click(screen.getByRole("form", { name: "Nova instituição" }).querySelector("button")!);
    await user.type(screen.getByLabelText("Nome da carteira"), "Reserva");
    await user.click(screen.getByRole("form", { name: "Nova carteira" }).querySelector("button")!);

    await waitFor(() => expect(apiClient.createPortfolio).toHaveBeenCalledWith({ name: "Reserva" }));
    expect(apiClient.createInstitution).toHaveBeenCalledWith({
      name: "Banco Z",
      institution_type: "BANK",
      country: "BR",
    });
  });

  it("duplicata recusada pelo backend aparece no bloco certo e nada é relido", async () => {
    vi.mocked(apiClient.createAsset).mockRejectedValue(
      new ApiError(409, "Conflict", JSON.stringify({ detail: "já existe um ativo AAPL no país US" })),
    );
    const user = userEvent.setup();
    render(<Registry />);

    await user.type(await screen.findByLabelText("Ticker"), "AAPL");
    await user.type(screen.getByLabelText("Nome do ativo"), "Apple");
    await user.selectOptions(screen.getByLabelText("Classe"), "STOCK_US");
    await user.click(screen.getByRole("form", { name: "Novo ativo" }).querySelector("button")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("já existe um ativo AAPL no país US");
    expect(apiClient.getAssets).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Ticker")).toHaveValue("AAPL");
  });

  it("falha ao carregar mostra erro", async () => {
    vi.mocked(apiClient.getAssets).mockRejectedValue(new Error("500 falha"));

    render(<Registry />);

    expect(await screen.findByRole("alert")).toHaveTextContent("500 falha");
  });
});
