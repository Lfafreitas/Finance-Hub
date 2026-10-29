import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import {
  aapl,
  brlAccount,
  checkingAccount,
  currencies,
  makeHistoryTransaction,
  petr4,
  usdAccount,
} from "../test/workFixtures";
import { Transactions } from "./Transactions";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getAccounts: vi.fn(),
  getAssets: vi.fn(),
  getCurrencies: vi.fn(),
  getAccountTransactions: vi.fn(),
  createTransaction: vi.fn(),
  createTransfer: vi.fn(),
}));

/** Escolhe a conta, a não ser que a tela já tenha aberto nela (conta única). */
async function pickAccount(user: ReturnType<typeof userEvent.setup>, id: string) {
  const select = (await screen.findByLabelText("Conta")) as HTMLSelectElement;
  if (select.value !== id) await user.selectOptions(select, id);
}

describe("Transactions", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(apiClient.getAccounts).mockResolvedValue([brlAccount, usdAccount]);
    vi.mocked(apiClient.getAssets).mockResolvedValue([petr4, aapl]);
    vi.mocked(apiClient.getCurrencies).mockResolvedValue(currencies);
    vi.mocked(apiClient.getAccountTransactions).mockResolvedValue([]);
  });

  it("sem contas, orienta a cadastrar uma antes", async () => {
    vi.mocked(apiClient.getAccounts).mockResolvedValue([]);

    render(<Transactions />);

    expect(await screen.findByTestId("no-accounts")).toHaveTextContent("Cadastros");
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("contas do controle financeiro não são oferecidas para lançamento de investimento", async () => {
    vi.mocked(apiClient.getAccounts).mockResolvedValue([brlAccount, checkingAccount]);

    render(<Transactions />);

    const select = await screen.findByLabelText("Conta");
    const names = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(names.some((name) => name?.includes("Conta Ações"))).toBe(true);
    expect(names.some((name) => name?.includes("Conta Corrente"))).toBe(false);
  });

  it("só com contas do controle financeiro, orienta a cadastrar uma de investimentos", async () => {
    vi.mocked(apiClient.getAccounts).mockResolvedValue([checkingAccount]);

    render(<Transactions />);

    expect(await screen.findByTestId("no-accounts")).toBeInTheDocument();
  });

  it("falha ao carregar contas e ativos mostra erro", async () => {
    vi.mocked(apiClient.getAssets).mockRejectedValue(new Error("500 falha"));

    render(<Transactions />);

    expect(await screen.findByRole("alert")).toHaveTextContent("500 falha");
  });

  it("formulário e histórico só aparecem depois de escolher a conta", async () => {
    const user = userEvent.setup();
    render(<Transactions />);
    await screen.findByLabelText("Conta");

    expect(screen.queryByRole("form", { name: "Novo lançamento" })).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Conta"), brlAccount.id);

    expect(await screen.findByRole("form", { name: "Novo lançamento" })).toBeInTheDocument();
    expect(apiClient.getAccountTransactions).toHaveBeenCalledWith(brlAccount.id);
    expect(await screen.findByText("Nenhum lançamento nesta conta.")).toBeInTheDocument();
  });

  it("histórico mostra tipo, ativo, origem e marca as revertidas", async () => {
    vi.mocked(apiClient.getAccountTransactions).mockResolvedValue([
      makeHistoryTransaction({ id: "tx-1" }),
      makeHistoryTransaction({ id: "tx-2", status: "REVERSED", source: "IMPORT_CSV", transaction_type: "SELL" }),
    ]);
    const user = userEvent.setup();
    render(<Transactions />);

    await pickAccount(user, brlAccount.id);
    // Excluídos ficam escondidos até pedir.
    expect(within(await screen.findByTestId("transaction-history")).getAllByRole("row")).toHaveLength(2);
    await user.click(screen.getByLabelText("Mostrar excluídos"));

    const rows = within(await screen.findByTestId("transaction-history")).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveTextContent("Compra");
    expect(rows[1]).toHaveTextContent("PETR4");
    expect(rows[1]).toHaveTextContent("Lançamento manual");
    expect(rows[1]).toHaveTextContent("Ativa");
    expect(rows[2]).toHaveTextContent("Venda");
    expect(rows[2]).toHaveTextContent("Importação CSV");
    expect(rows[2]).toHaveTextContent("Revertida");
  });

  it("depois de lançar, o histórico é rebuscado no backend", async () => {
    vi.mocked(apiClient.getAccountTransactions)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([makeHistoryTransaction({ transaction_type: "DEPOSIT", asset_id: null })]);
    vi.mocked(apiClient.createTransaction).mockResolvedValue(makeHistoryTransaction());
    const user = userEvent.setup();
    render(<Transactions />);
    await pickAccount(user, brlAccount.id);
    await screen.findByText("Nenhum lançamento nesta conta.");

    await user.selectOptions(screen.getByLabelText("Tipo"), "DEPOSIT");
    await user.type(screen.getAllByLabelText("Data")[0], "2026-03-10");
    await user.type(screen.getByLabelText("Valor bruto"), "500");
    await user.click(screen.getByRole("button", { name: "Lançar" }));

    expect(await screen.findByTestId("transaction-history")).toHaveTextContent("Depósito");
    expect(apiClient.getAccountTransactions).toHaveBeenCalledTimes(2);
  });

  it("trocar de conta zera o formulário e busca o histórico da nova conta", async () => {
    const user = userEvent.setup();
    render(<Transactions />);
    await pickAccount(user, brlAccount.id);
    await user.type(await screen.findByLabelText("Quantidade"), "100");

    await user.selectOptions(screen.getByLabelText("Conta"), usdAccount.id);

    await waitFor(() => expect(apiClient.getAccountTransactions).toHaveBeenLastCalledWith(usdAccount.id));
    expect(screen.getByLabelText("Quantidade")).toHaveValue("");
  });
});

describe("Transactions — abrir direto e filtrar", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(apiClient.getAccounts).mockResolvedValue([brlAccount, usdAccount]);
    vi.mocked(apiClient.getAssets).mockResolvedValue([petr4, aapl]);
    vi.mocked(apiClient.getCurrencies).mockResolvedValue(currencies);
    vi.mocked(apiClient.getAccountTransactions).mockResolvedValue([
      makeHistoryTransaction({ id: "tx-petr", asset_id: petr4.id }),
      makeHistoryTransaction({ id: "tx-aapl", asset_id: aapl.id, transaction_date: "2026-02-01" }),
    ]);
  });

  it("vindo do Dashboard, abre na conta da posição", async () => {
    render(<Transactions initialAccountId={usdAccount.id} />);

    await screen.findByTestId("transaction-history");
    expect(screen.getByLabelText("Conta")).toHaveValue(usdAccount.id);
    expect(apiClient.getAccountTransactions).toHaveBeenCalledWith(usdAccount.id);
  });

  it("com várias contas e sem indicação, espera a escolha", async () => {
    render(<Transactions />);

    expect(await screen.findByLabelText("Conta")).toHaveValue("");
    expect(apiClient.getAccountTransactions).not.toHaveBeenCalled();
  });

  it("conta única abre sozinha", async () => {
    vi.mocked(apiClient.getAccounts).mockResolvedValue([brlAccount]);

    render(<Transactions />);

    await screen.findByTestId("transaction-history");
    expect(apiClient.getAccountTransactions).toHaveBeenCalledTimes(1);
  });

  it("filtro por ativo só mostra os lançamentos dele", async () => {
    const user = userEvent.setup();
    render(<Transactions initialAccountId={brlAccount.id} />);
    const table = await screen.findByTestId("transaction-history");
    expect(within(table).getAllByRole("row")).toHaveLength(3);

    await user.selectOptions(screen.getByLabelText("Filtrar por ativo"), aapl.id);

    const rows = within(screen.getByTestId("transaction-history")).getAllByRole("row");
    expect(rows).toHaveLength(2);
    expect(rows[1]).toHaveTextContent("AAPL");
  });
});
