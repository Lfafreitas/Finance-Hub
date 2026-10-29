import { render, screen, waitFor, within } from "@testing-library/react";
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
  updateInstitution: vi.fn(),
  updatePortfolio: vi.fn(),
  updateAccount: vi.fn(),
  updateAsset: vi.fn(),
  deleteInstitution: vi.fn(),
  deletePortfolio: vi.fn(),
  deleteAccount: vi.fn(),
  deleteAsset: vi.fn(),
}));

const institution = { id: "inst-1", name: "Corretora X", institution_type: "BANK" as const, country: "US" };
const portfolio = { id: "pf-1", name: "Longo prazo" };
const accountInPortfolio = { ...brlAccount, portfolio_id: "pf-1" };

describe("Registry — edição e exclusão", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(apiClient.getInstitutions).mockResolvedValue([institution]);
    vi.mocked(apiClient.getAccounts).mockResolvedValue([accountInPortfolio, checkingAccount]);
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([portfolio]);
    vi.mocked(apiClient.getAssets).mockResolvedValue([petr4]);
    vi.mocked(apiClient.getCurrencies).mockResolvedValue(currencies);
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([
      { code: "STOCK_BR", label: "Ação (Brasil)" },
      { code: "STOCK_US", label: "Ação (Exterior)" },
    ]);
  });

  it("Editar preenche o formulário com o item e Salvar envia a alteração para o id dele", async () => {
    vi.mocked(apiClient.updateInstitution).mockResolvedValue(institution);
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Editar Corretora X" }));

    expect(screen.getByLabelText("Nome da instituição")).toHaveValue("Corretora X");
    expect(screen.getByLabelText("Tipo")).toHaveValue("BANK");
    expect(screen.getByLabelText("País (2 letras)")).toHaveValue("US");
    expect(screen.getByTestId("editing-note")).toHaveTextContent("Editando: Corretora X");

    await user.clear(screen.getByLabelText("Nome da instituição"));
    await user.type(screen.getByLabelText("Nome da instituição"), "Corretora Y");
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(apiClient.updateInstitution).toHaveBeenCalledWith("inst-1", {
        name: "Corretora Y",
        institution_type: "BANK",
        country: "US",
      }),
    );
    expect(apiClient.createInstitution).not.toHaveBeenCalled();
    await waitFor(() => expect(apiClient.getInstitutions).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId("editing-note")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Nome da instituição")).toHaveValue("");
    expect(screen.getByLabelText("Tipo")).toHaveValue("BROKER");
  });

  it("Cancelar edição limpa o formulário e o próximo envio cria um item novo", async () => {
    vi.mocked(apiClient.createPortfolio).mockResolvedValue({ id: "pf-2", name: "Nova" });
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Editar Longo prazo" }));
    expect(screen.getByLabelText("Nome da carteira")).toHaveValue("Longo prazo");
    await user.click(screen.getByRole("button", { name: "Cancelar edição" }));

    expect(screen.getByLabelText("Nome da carteira")).toHaveValue("");
    await user.type(screen.getByLabelText("Nome da carteira"), "Nova");
    await user.click(screen.getByRole("form", { name: "Nova carteira" }).querySelector("button")!);

    await waitFor(() => expect(apiClient.createPortfolio).toHaveBeenCalledWith({ name: "Nova" }));
    expect(apiClient.updatePortfolio).not.toHaveBeenCalled();
  });

  it("edição de conta carrega instituição, moeda, tipo e carteira, e envia tudo de volta", async () => {
    vi.mocked(apiClient.updateAccount).mockResolvedValue(accountInPortfolio);
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Editar Conta Ações" }));

    expect(screen.getByLabelText("Nome da conta")).toHaveValue("Conta Ações");
    expect(screen.getByLabelText("Instituição")).toHaveValue("inst-1");
    expect(screen.getByLabelText("Moeda da conta")).toHaveValue("BRL");
    expect(screen.getByLabelText("Tipo da conta")).toHaveValue("BROKERAGE");
    expect(screen.getByLabelText("Carteira (opcional)")).toHaveValue("pf-1");

    await user.clear(screen.getByLabelText("Nome da conta"));
    await user.type(screen.getByLabelText("Nome da conta"), "Conta Renomeada");
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(apiClient.updateAccount).toHaveBeenCalledWith("acc-brl", {
        name: "Conta Renomeada",
        institution_id: "inst-1",
        currency_code: "BRL",
        account_type: "BROKERAGE",
        portfolio_id: "pf-1",
      }),
    );
    expect(apiClient.createAccount).not.toHaveBeenCalled();
  });

  it("edição de ativo envia ticker, nome, classe, país e moeda para o id dele", async () => {
    vi.mocked(apiClient.updateAsset).mockResolvedValue(petr4);
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Editar PETR4" }));
    expect(screen.getByLabelText("Classe")).toHaveValue("STOCK_BR");
    await user.clear(screen.getByLabelText("Ticker"));
    await user.type(screen.getByLabelText("Ticker"), "PETR3");
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(apiClient.updateAsset).toHaveBeenCalledWith("asset-petr4", {
        ticker: "PETR3",
        name: "Petrobras",
        asset_class_code: "STOCK_BR",
        country: "BR",
        currency_code: "BRL",
        maturity_date: null,
        annual_rate: null,
      }),
    );
  });

  it("renda fixa: vencimento e taxa em % vão como data e fração; taxa inválida não salva", async () => {
    const cd = {
      id: "asset-cd",
      ticker: "CD-EXEMPLO",
      name: "CD Exemplo",
      asset_class_code: "BOND",
      country: "US",
      currency_code: "USD",
      maturity_date: "2026-11-30",
      annual_rate: "0.038500",
    };
    vi.mocked(apiClient.getAssets).mockResolvedValue([petr4, cd]);
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([
      { code: "STOCK_BR", label: "Ação (Brasil)" },
      { code: "BOND", label: "Bond / Treasury" },
    ]);
    vi.mocked(apiClient.updateAsset).mockResolvedValue(cd);
    const user = userEvent.setup();
    render(<Registry />);

    expect(await screen.findByText(/CD-EXEMPLO — CD Exemplo .* vence em 30\/11\/2026/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Editar CD-EXEMPLO" }));
    expect(screen.getByLabelText("Vencimento (opcional)")).toHaveValue("2026-11-30");
    expect(screen.getByLabelText("Taxa ao ano, em % (opcional)")).toHaveValue("3,85");

    await user.clear(screen.getByLabelText("Taxa ao ano, em % (opcional)"));
    await user.type(screen.getByLabelText("Taxa ao ano, em % (opcional)"), "abc");
    expect(screen.getByRole("button", { name: "Salvar alterações" })).toBeDisabled();

    await user.clear(screen.getByLabelText("Taxa ao ano, em % (opcional)"));
    await user.type(screen.getByLabelText("Taxa ao ano, em % (opcional)"), "4,1");
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(apiClient.updateAsset).toHaveBeenCalledWith("asset-cd", {
        ticker: "CD-EXEMPLO",
        name: "CD Exemplo",
        asset_class_code: "BOND",
        country: "US",
        currency_code: "USD",
        maturity_date: "2026-11-30",
        annual_rate: "0.041",
      }),
    );
  });

  it("trocar a classe de renda fixa para ação apaga vencimento e taxa", async () => {
    const cd = {
      id: "asset-cd",
      ticker: "CD-EXEMPLO",
      name: "CD Exemplo",
      asset_class_code: "BOND",
      country: "US",
      currency_code: "USD",
      maturity_date: "2026-11-30",
      annual_rate: "0.038500",
    };
    vi.mocked(apiClient.getAssets).mockResolvedValue([cd]);
    vi.mocked(apiClient.getAssetClasses).mockResolvedValue([
      { code: "STOCK_BR", label: "Ação (Brasil)" },
      { code: "BOND", label: "Bond / Treasury" },
    ]);
    vi.mocked(apiClient.updateAsset).mockResolvedValue(cd);
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Editar CD-EXEMPLO" }));
    await user.selectOptions(screen.getByLabelText("Classe"), "STOCK_BR");
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(apiClient.updateAsset).toHaveBeenCalledWith(
        "asset-cd",
        expect.objectContaining({ asset_class_code: "STOCK_BR", maturity_date: null, annual_rate: null }),
      ),
    );
  });

  it("ação não mostra campos de vencimento", async () => {
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Editar PETR4" }));

    expect(screen.queryByLabelText("Vencimento (opcional)")).not.toBeInTheDocument();
  });

  it("começar a editar outro bloco limpa o anterior: nada do item antigo sobra como cadastro novo", async () => {
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Editar Corretora X" }));
    await user.click(screen.getByRole("button", { name: "Editar PETR4" }));

    expect(screen.getByLabelText("Nome da instituição")).toHaveValue("");
    expect(screen.getByLabelText("Ticker")).toHaveValue("PETR4");
    expect(screen.getAllByTestId("editing-note")).toHaveLength(1);
    expect(screen.getByTestId("editing-note")).toHaveTextContent("Editando: PETR4");
  });

  it("recusa do backend na edição aparece no bloco e a edição continua aberta", async () => {
    vi.mocked(apiClient.updateAccount).mockRejectedValue(
      new ApiError(409, "Conflict", JSON.stringify({ detail: "a conta já tem lançamentos: não é possível trocar a moeda" })),
    );
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Editar Conta Ações" }));
    await user.selectOptions(screen.getByLabelText("Moeda da conta"), "USD");
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("não é possível trocar a moeda");
    expect(screen.getByTestId("editing-note")).toHaveTextContent("Editando: Conta Ações");
    expect(apiClient.getAccounts).toHaveBeenCalledTimes(1);
  });

  it("Excluir só chama o backend depois da confirmação, e relê as listas", async () => {
    vi.mocked(apiClient.deleteAsset).mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Excluir PETR4" }));
    expect(apiClient.deleteAsset).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirmar exclusão de PETR4" }));

    await waitFor(() => expect(apiClient.deleteAsset).toHaveBeenCalledWith("asset-petr4"));
    await waitFor(() => expect(apiClient.getAssets).toHaveBeenCalledTimes(2));
  });

  it("Manter desiste da exclusão sem chamar o backend", async () => {
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Excluir Longo prazo" }));
    await user.click(screen.getByRole("button", { name: "Manter" }));

    expect(apiClient.deletePortfolio).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Excluir Longo prazo" })).toBeInTheDocument();
  });

  it("exclusão recusada mostra o motivo na linha do item e nada é relido", async () => {
    vi.mocked(apiClient.deleteAccount).mockRejectedValue(
      new ApiError(409, "Conflict", JSON.stringify({ detail: "a conta Conta Corrente já tem lançamentos e não pode ser excluída" })),
    );
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Excluir Conta Corrente" }));
    await user.click(screen.getByRole("button", { name: "Confirmar exclusão de Conta Corrente" }));

    const list = screen.getByTestId("account-list");
    expect(await within(list).findByRole("alert")).toHaveTextContent("não pode ser excluída");
    expect(apiClient.deleteAccount).toHaveBeenCalledWith("acc-checking");
    expect(apiClient.getAccounts).toHaveBeenCalledTimes(1);
    expect(within(list).getByText(/Conta Corrente — Banco Z/)).toBeInTheDocument();
  });

  it("cada tipo de cadastro exclui pelo próprio endpoint", async () => {
    vi.mocked(apiClient.deleteInstitution).mockResolvedValue(undefined);
    vi.mocked(apiClient.deletePortfolio).mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Excluir Corretora X" }));
    await user.click(screen.getByRole("button", { name: "Confirmar exclusão de Corretora X" }));
    await waitFor(() => expect(apiClient.deleteInstitution).toHaveBeenCalledWith("inst-1"));

    await user.click(await screen.findByRole("button", { name: "Excluir Longo prazo" }));
    await user.click(screen.getByRole("button", { name: "Confirmar exclusão de Longo prazo" }));
    await waitFor(() => expect(apiClient.deletePortfolio).toHaveBeenCalledWith("pf-1"));
  });

  it("carteira editada chama a atualização com o novo nome", async () => {
    vi.mocked(apiClient.updatePortfolio).mockResolvedValue(portfolio);
    const user = userEvent.setup();
    render(<Registry />);

    await user.click(await screen.findByRole("button", { name: "Editar Longo prazo" }));
    await user.type(screen.getByLabelText("Nome da carteira"), " 2");
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() => expect(apiClient.updatePortfolio).toHaveBeenCalledWith("pf-1", { name: "Longo prazo 2" }));
    expect(apiClient.createPortfolio).not.toHaveBeenCalled();
  });
});
