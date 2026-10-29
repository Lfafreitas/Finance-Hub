import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import { ApiError } from "../api/client";
import { aapl, brlAccount, currencies, makeHistoryTransaction, petr4 } from "../test/workFixtures";
import { Transactions } from "./Transactions";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getAccounts: vi.fn(),
  getAssets: vi.fn(),
  getCurrencies: vi.fn(),
  getAccountTransactions: vi.fn(),
  createTransaction: vi.fn(),
  createTransfer: vi.fn(),
  correctTransaction: vi.fn(),
  reverseTransaction: vi.fn(),
}));

/** Escolhe a conta, a não ser que a tela já tenha aberto nela (conta única). */
async function pickAccount(user: ReturnType<typeof userEvent.setup>, id: string) {
  const select = (await screen.findByLabelText("Conta")) as HTMLSelectElement;
  if (select.value !== id) await user.selectOptions(select, id);
}

const buy = makeHistoryTransaction({
  id: "tx-buy",
  transaction_type: "BUY",
  quantity: "100.00000000",
  unit_price: "30.00000000",
  fees: "1.5000",
  gross_amount: "3000.0000",
  transaction_date: "2026-01-05",
  notes: "nota 123",
});

async function openAccount(user: ReturnType<typeof userEvent.setup>) {
  render(<Transactions />);
  await pickAccount(user, brlAccount.id);
  return screen.findByTestId("transaction-history");
}

describe("Transactions — corrigir e estornar", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(apiClient.getAccounts).mockResolvedValue([brlAccount]);
    vi.mocked(apiClient.getAssets).mockResolvedValue([petr4, aapl]);
    vi.mocked(apiClient.getCurrencies).mockResolvedValue(currencies);
    vi.mocked(apiClient.getAccountTransactions).mockResolvedValue([buy]);
  });

  it("Editar abre o formulário preenchido com o lançamento e trava o ativo", async () => {
    const user = userEvent.setup();
    await openAccount(user);

    await user.click(screen.getByRole("button", { name: "Editar Compra de 2026-01-05" }));

    const form = screen.getByRole("form", { name: "Editar lançamento" });
    expect(within(form).getByLabelText("Tipo")).toHaveValue("BUY");
    expect(within(form).getByLabelText("Data")).toHaveValue("2026-01-05");
    expect(within(form).getByLabelText("Ativo")).toHaveValue(petr4.id);
    expect(within(form).getByLabelText("Ativo")).toBeDisabled();
    expect(within(form).getByLabelText("Quantidade")).toHaveValue("100.00000000");
    expect(within(form).getByLabelText("Preço unitário")).toHaveValue("30.00000000");
    expect(within(form).getByLabelText("Valor bruto")).toHaveValue("3000.0000");
    expect(within(form).getByLabelText("Taxas (opcional)")).toHaveValue("1.5000");
    expect(within(form).getByLabelText("Observações (opcional)")).toHaveValue("nota 123");
    expect(screen.getByTestId("correction-note")).toHaveTextContent("revertido");
    expect(screen.queryByRole("form", { name: "Novo lançamento" })).not.toBeInTheDocument();
  });

  it("Salvar correção envia os valores para o id do original, relê o histórico e volta ao formulário vazio", async () => {
    vi.mocked(apiClient.correctTransaction).mockResolvedValue(makeHistoryTransaction({ id: "tx-new" }));
    const user = userEvent.setup();
    await openAccount(user);
    await user.click(screen.getByRole("button", { name: "Editar Compra de 2026-01-05" }));

    await user.clear(screen.getByLabelText("Quantidade"));
    await user.type(screen.getByLabelText("Quantidade"), "90");
    await user.clear(screen.getByLabelText("Valor bruto"));
    await user.type(screen.getByLabelText("Valor bruto"), "2700");
    await user.click(screen.getByRole("button", { name: "Salvar correção" }));

    await waitFor(() =>
      expect(apiClient.correctTransaction).toHaveBeenCalledWith("tx-buy", {
        account_id: brlAccount.id,
        asset_id: petr4.id,
        transaction_type: "BUY",
        quantity: "90",
        unit_price: "30.00000000",
        fees: "1.5000",
        gross_amount: "2700",
        currency_code: "BRL",
        transaction_date: "2026-01-05",
        notes: "nota 123",
      }),
    );
    expect(apiClient.createTransaction).not.toHaveBeenCalled();
    await waitFor(() => expect(apiClient.getAccountTransactions).toHaveBeenCalledTimes(2));
    const form = await screen.findByRole("form", { name: "Novo lançamento" });
    expect(within(form).getByLabelText("Quantidade")).toHaveValue("");
  });

  it("correção recusada mostra o motivo e mantém o formulário de correção com o que foi digitado", async () => {
    vi.mocked(apiClient.correctTransaction).mockRejectedValue(
      new ApiError(400, "Bad Request", JSON.stringify({ detail: "a correção deixaria uma venda sem posição" })),
    );
    const user = userEvent.setup();
    await openAccount(user);
    await user.click(screen.getByRole("button", { name: "Editar Compra de 2026-01-05" }));
    await user.clear(screen.getByLabelText("Quantidade"));
    await user.type(screen.getByLabelText("Quantidade"), "5");
    await user.click(screen.getByRole("button", { name: "Salvar correção" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("a correção deixaria uma venda sem posição");
    expect(screen.getByRole("form", { name: "Editar lançamento" })).toBeInTheDocument();
    expect(screen.getByLabelText("Quantidade")).toHaveValue("5");
    expect(apiClient.getAccountTransactions).toHaveBeenCalledTimes(1);
  });

  it("Cancelar correção volta ao formulário de novo lançamento, vazio", async () => {
    const user = userEvent.setup();
    await openAccount(user);
    await user.click(screen.getByRole("button", { name: "Editar Compra de 2026-01-05" }));

    await user.click(screen.getByRole("button", { name: "Cancelar correção" }));

    const form = screen.getByRole("form", { name: "Novo lançamento" });
    expect(within(form).getByLabelText("Quantidade")).toHaveValue("");
    expect(apiClient.correctTransaction).not.toHaveBeenCalled();
  });

  it("Excluir só chama o backend depois da confirmação e relê o histórico", async () => {
    vi.mocked(apiClient.reverseTransaction).mockResolvedValue({ ...buy, status: "REVERSED" });
    const user = userEvent.setup();
    await openAccount(user);

    await user.click(screen.getByRole("button", { name: "Excluir Compra de 2026-01-05" }));
    expect(apiClient.reverseTransaction).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirmar exclusão" }));

    await waitFor(() => expect(apiClient.reverseTransaction).toHaveBeenCalledWith("tx-buy"));
    await waitFor(() => expect(apiClient.getAccountTransactions).toHaveBeenCalledTimes(2));
  });

  it("Manter desiste do estorno", async () => {
    const user = userEvent.setup();
    await openAccount(user);

    await user.click(screen.getByRole("button", { name: "Excluir Compra de 2026-01-05" }));
    await user.click(screen.getByRole("button", { name: "Manter" }));

    expect(apiClient.reverseTransaction).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Excluir Compra de 2026-01-05" })).toBeInTheDocument();
  });

  it("estorno recusado mostra o motivo e não relê o histórico", async () => {
    vi.mocked(apiClient.reverseTransaction).mockRejectedValue(
      new ApiError(400, "Bad Request", JSON.stringify({ detail: "o estorno deixaria uma venda sem posição" })),
    );
    const user = userEvent.setup();
    await openAccount(user);

    await user.click(screen.getByRole("button", { name: "Excluir Compra de 2026-01-05" }));
    await user.click(screen.getByRole("button", { name: "Confirmar exclusão" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("o estorno deixaria uma venda sem posição");
    expect(apiClient.getAccountTransactions).toHaveBeenCalledTimes(1);
  });

  it("revertida não tem ação; perna de transferência não tem ação; câmbio só estorna", async () => {
    vi.mocked(apiClient.getAccountTransactions).mockResolvedValue([
      makeHistoryTransaction({ id: "tx-rev", status: "REVERSED", transaction_date: "2026-01-01" }),
      makeHistoryTransaction({ id: "tx-out", transaction_type: "TRANSFER_OUT", asset_id: null, transaction_date: "2026-01-02" }),
      makeHistoryTransaction({ id: "tx-fx", transaction_type: "FX_CONVERSION", asset_id: null, transaction_date: "2026-01-03" }),
    ]);
    const user = userEvent.setup();
    await openAccount(user);
    await user.click(screen.getByLabelText("Mostrar excluídos"));

    const rows = within(screen.getByTestId("transaction-history")).getAllByRole("row");
    expect(within(rows[1]).queryAllByRole("button")).toHaveLength(0);
    expect(within(rows[2]).queryAllByRole("button")).toHaveLength(0);
    expect(within(rows[3]).getAllByRole("button").map((b) => b.textContent)).toEqual(["Excluir"]);
  });

  it("trocar de conta fecha a correção em andamento", async () => {
    vi.mocked(apiClient.getAccounts).mockResolvedValue([brlAccount, { ...brlAccount, id: "acc-2", name: "Outra" }]);
    const user = userEvent.setup();
    await openAccount(user);
    await user.click(screen.getByRole("button", { name: "Editar Compra de 2026-01-05" }));

    await user.selectOptions(screen.getByLabelText("Conta"), "acc-2");

    expect(await screen.findByRole("form", { name: "Novo lançamento" })).toBeInTheDocument();
    expect(screen.queryByTestId("correction-note")).not.toBeInTheDocument();
  });
});
