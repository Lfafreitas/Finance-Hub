import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import { ApiError } from "../api/client";
import { aapl, brlAccount, currencies, makeHistoryTransaction, petr4 } from "../test/workFixtures";
import { TransactionForm } from "./TransactionForm";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  createTransaction: vi.fn(),
}));

function setup() {
  const onCreated = vi.fn();
  render(
    <TransactionForm account={brlAccount} assets={[petr4, aapl]} currencies={currencies} onCreated={onCreated} />,
  );
  return { onCreated, user: userEvent.setup() };
}

async function fillBuy(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Data"), "2026-03-10");
  await user.selectOptions(screen.getByLabelText("Ativo"), petr4.id);
  await user.type(screen.getByLabelText("Quantidade"), "100");
  await user.type(screen.getByLabelText("Preço unitário"), "30.55");
  await user.type(screen.getByLabelText("Valor bruto"), "3055.00");
}

describe("TransactionForm", () => {
  beforeEach(() => {
    vi.mocked(apiClient.createTransaction).mockReset();
  });

  it("Lançar fica desabilitado até os campos obrigatórios do tipo estarem preenchidos", async () => {
    const { user } = setup();
    const submit = screen.getByRole("button", { name: "Lançar" });

    expect(submit).toBeDisabled();
    await fillBuy(user);

    expect(submit).toBeEnabled();
  });

  it("compra envia os valores como texto, exatamente como digitados, sem calcular nada", async () => {
    vi.mocked(apiClient.createTransaction).mockResolvedValue(makeHistoryTransaction());
    const { user, onCreated } = setup();

    await fillBuy(user);
    await user.type(screen.getByLabelText("Taxas (opcional)"), "1.50");
    await user.click(screen.getByRole("button", { name: "Lançar" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(apiClient.createTransaction).toHaveBeenCalledWith({
      account_id: brlAccount.id,
      asset_id: petr4.id,
      transaction_type: "BUY",
      quantity: "100",
      unit_price: "30.55",
      fees: "1.50",
      gross_amount: "3055.00",
      currency_code: "BRL",
      transaction_date: "2026-03-10",
    });
    expect(screen.getByRole("status")).toHaveTextContent("Lançamento criado");
    expect(screen.getByLabelText("Quantidade")).toHaveValue("");
  });

  it("com ativo, a moeda é a do ativo e não pode ser escolhida", async () => {
    vi.mocked(apiClient.createTransaction).mockResolvedValue(makeHistoryTransaction());
    const { user } = setup();

    await user.type(screen.getByLabelText("Data"), "2026-03-10");
    await user.selectOptions(screen.getByLabelText("Ativo"), aapl.id);
    await user.type(screen.getByLabelText("Quantidade"), "5");
    await user.type(screen.getByLabelText("Preço unitário"), "200");
    await user.type(screen.getByLabelText("Valor bruto"), "1000");

    expect(screen.getByTestId("tx-currency-fixed")).toHaveTextContent("USD (moeda do ativo)");
    expect(screen.queryByRole("combobox", { name: "Moeda" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Lançar" }));

    await waitFor(() => expect(apiClient.createTransaction).toHaveBeenCalled());
    expect(vi.mocked(apiClient.createTransaction).mock.calls[0][0].currency_code).toBe("USD");
  });

  it("depósito não tem ativo, quantidade nem preço; a moeda começa na da conta e pode ser trocada", async () => {
    vi.mocked(apiClient.createTransaction).mockResolvedValue(makeHistoryTransaction());
    const { user } = setup();

    await user.selectOptions(screen.getByLabelText("Tipo"), "DEPOSIT");

    expect(screen.queryByLabelText("Ativo")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Quantidade")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Preço unitário")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Moeda")).toHaveValue("BRL");

    await user.selectOptions(screen.getByLabelText("Moeda"), "USD");
    await user.type(screen.getByLabelText("Data"), "2026-03-10");
    await user.type(screen.getByLabelText("Valor bruto"), "500");
    await user.click(screen.getByRole("button", { name: "Lançar" }));

    await waitFor(() =>
      expect(apiClient.createTransaction).toHaveBeenCalledWith({
        account_id: brlAccount.id,
        transaction_type: "DEPOSIT",
        gross_amount: "500",
        currency_code: "USD",
        transaction_date: "2026-03-10",
      }),
    );
  });

  it("um ativo escolhido antes não vaza para um tipo que não tem ativo", async () => {
    vi.mocked(apiClient.createTransaction).mockResolvedValue(makeHistoryTransaction());
    const { user } = setup();

    await user.selectOptions(screen.getByLabelText("Ativo"), aapl.id);
    await user.selectOptions(screen.getByLabelText("Tipo"), "WITHDRAWAL");
    await user.type(screen.getByLabelText("Data"), "2026-03-10");
    await user.type(screen.getByLabelText("Valor bruto"), "50");
    await user.click(screen.getByRole("button", { name: "Lançar" }));

    await waitFor(() => expect(apiClient.createTransaction).toHaveBeenCalled());
    const payload = vi.mocked(apiClient.createTransaction).mock.calls[0][0];
    expect(payload.asset_id).toBeUndefined();
    expect(payload.currency_code).toBe("BRL");
  });

  it("dividendo exige ativo e valor, sem quantidade nem preço", async () => {
    vi.mocked(apiClient.createTransaction).mockResolvedValue(makeHistoryTransaction());
    const { user } = setup();

    await user.selectOptions(screen.getByLabelText("Tipo"), "DIVIDEND");
    await user.type(screen.getByLabelText("Data"), "2026-03-10");
    await user.type(screen.getByLabelText("Valor bruto"), "42.10");

    expect(screen.getByRole("button", { name: "Lançar" })).toBeDisabled();
    expect(screen.queryByLabelText("Quantidade")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Ativo"), petr4.id);
    await user.click(screen.getByRole("button", { name: "Lançar" }));

    await waitFor(() =>
      expect(apiClient.createTransaction).toHaveBeenCalledWith({
        account_id: brlAccount.id,
        asset_id: petr4.id,
        transaction_type: "DIVIDEND",
        gross_amount: "42.10",
        currency_code: "BRL",
        transaction_date: "2026-03-10",
      }),
    );
  });

  it("grupamento envia a variação negativa como digitada e valor bruto zero, sem taxas", async () => {
    vi.mocked(apiClient.createTransaction).mockResolvedValue(makeHistoryTransaction());
    const { user } = setup();

    await user.selectOptions(screen.getByLabelText("Tipo"), "REVERSE_SPLIT");

    expect(screen.queryByLabelText("Valor bruto")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Taxas (opcional)")).not.toBeInTheDocument();
    expect(screen.getByText(/NEGATIVA/)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Data"), "2026-03-10");
    await user.selectOptions(screen.getByLabelText("Ativo"), petr4.id);
    await user.type(screen.getByLabelText("Quantidade"), "-50");
    await user.click(screen.getByRole("button", { name: "Lançar" }));

    await waitFor(() =>
      expect(apiClient.createTransaction).toHaveBeenCalledWith({
        account_id: brlAccount.id,
        asset_id: petr4.id,
        transaction_type: "REVERSE_SPLIT",
        quantity: "-50",
        gross_amount: "0",
        currency_code: "BRL",
        transaction_date: "2026-03-10",
      }),
    );
  });

  it("erro do backend é mostrado como veio, nada é limpo e onCreated não é chamado", async () => {
    vi.mocked(apiClient.createTransaction).mockRejectedValue(
      new ApiError(400, "Bad Request", JSON.stringify({ detail: "SELL de 100 excede a posição atual (0)" })),
    );
    const { user, onCreated } = setup();

    await fillBuy(user);
    await user.click(screen.getByRole("button", { name: "Lançar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("SELL de 100 excede a posição atual (0)");
    expect(onCreated).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Quantidade")).toHaveValue("100");
    expect(screen.getByRole("button", { name: "Lançar" })).toBeEnabled();
  });
});
