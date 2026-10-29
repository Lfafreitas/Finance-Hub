import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/cashflow";
import { ApiError } from "../../api/client";
import { todayIso } from "../../lib/cashflow";
import { allAccounts, makeEntry } from "../../test/cashFixtures";
import { CashEntryForm } from "./CashEntryForm";

vi.mock("../../api/cashflow");

function setup() {
  const onCreated = vi.fn();
  render(<CashEntryForm accounts={allAccounts} onCreated={onCreated} />);
  return { onCreated, user: userEvent.setup() };
}

const optionTexts = (label: string) =>
  Array.from(screen.getByLabelText(label).querySelectorAll("option")).map((o) => o.textContent);
const setDate = (value: string) => fireEvent.change(screen.getByLabelText("Data"), { target: { value } });

describe("CashEntryForm — lançamento", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.createCashEntry).mockResolvedValue(makeEntry());
    vi.mocked(api.createCashTransfer).mockResolvedValue({ transfer_group_id: "g", entries: [] });
  });

  it("só oferece contas de caixa e abre na data de hoje", () => {
    setup();

    expect(optionTexts("Conta")).toEqual([
      "Selecione…",
      "Conta Corrente — Conta corrente (BRL)",
      "Cartão — Cartão de crédito (BRL)",
      "Reserva — Reserva (BRL)",
    ]);
    expect(screen.getByLabelText("Data")).toHaveValue(todayIso());
    expect(screen.getByLabelText("Data")).toHaveAttribute("max", todayIso());
  });

  it("exige conta, valor e descrição", async () => {
    const { user } = setup();
    const button = screen.getByRole("button", { name: "Registrar lançamento" });

    expect(button).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Conta"), "acc-checking");
    await user.type(screen.getByLabelText("Valor"), "10");
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText("Descrição"), "   ");
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText("Descrição"), "Café");
    expect(button).toBeEnabled();
  });

  it("saída é enviada negativa; vírgula decimal vira ponto", async () => {
    const { user, onCreated } = setup();

    await user.selectOptions(screen.getByLabelText("Conta"), "acc-checking");
    setDate("2026-08-10");
    await user.type(screen.getByLabelText("Valor"), "1.234,56");
    await user.type(screen.getByLabelText("Descrição"), "  Aluguel ");
    await user.selectOptions(screen.getByLabelText("Natureza"), "EXPENSE");
    await user.type(screen.getByLabelText("Observação (opcional)"), " agosto ");
    await user.click(screen.getByRole("button", { name: "Registrar lançamento" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(api.createCashEntry).toHaveBeenCalledWith({
      account_id: "acc-checking",
      entry_date: "2026-08-10",
      amount: "-1234.56",
      description: "Aluguel",
      nature: "EXPENSE",
      notes: "agosto",
    });
    expect(screen.getByRole("status")).toHaveTextContent("Lançamento registrado.");
    expect(screen.getByLabelText("Valor")).toHaveValue("");
    expect(screen.getByLabelText("Descrição")).toHaveValue("");
  });

  it("entrada é enviada positiva, sem observação e não classificada por padrão", async () => {
    const { user, onCreated } = setup();

    await user.selectOptions(screen.getByLabelText("Conta"), "acc-checking");
    setDate("2026-08-10");
    await user.selectOptions(screen.getByLabelText("Sentido"), "in");
    await user.type(screen.getByLabelText("Valor"), "3000");
    await user.type(screen.getByLabelText("Descrição"), "Salário");
    await user.click(screen.getByRole("button", { name: "Registrar lançamento" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(api.createCashEntry).toHaveBeenCalledWith({
      account_id: "acc-checking",
      entry_date: "2026-08-10",
      amount: "3000",
      description: "Salário",
      nature: "UNCLASSIFIED",
      notes: null,
    });
  });

  it.each(["0", "-5", "abc", "1,23456"])("valor inválido %s bloqueia o envio e explica", async (bad) => {
    const { user } = setup();

    await user.selectOptions(screen.getByLabelText("Conta"), "acc-checking");
    await user.type(screen.getByLabelText("Descrição"), "x");
    await user.type(screen.getByLabelText("Valor"), bad);

    expect(screen.getByRole("button", { name: "Registrar lançamento" })).toBeDisabled();
    expect(screen.getByTestId("amount-hint")).toBeInTheDocument();
    expect(screen.getByLabelText("Valor")).toHaveAttribute("aria-invalid", "true");
  });

  it("recusa do backend mantém o que foi digitado", async () => {
    vi.mocked(api.createCashEntry).mockRejectedValue(
      new ApiError(400, "Bad Request", '{"detail":"a data do lançamento não pode estar no futuro"}'),
    );
    const { user, onCreated } = setup();

    await user.selectOptions(screen.getByLabelText("Conta"), "acc-checking");
    await user.type(screen.getByLabelText("Valor"), "10");
    await user.type(screen.getByLabelText("Descrição"), "Café");
    await user.click(screen.getByRole("button", { name: "Registrar lançamento" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("não pode estar no futuro");
    expect(onCreated).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Valor")).toHaveValue("10");
    expect(screen.getByLabelText("Descrição")).toHaveValue("Café");
  });
});

describe("CashEntryForm — transferência", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.createCashTransfer).mockResolvedValue({ transfer_group_id: "g", entries: [] });
  });

  it("oferece todas as contas, e o destino nunca repete a origem", async () => {
    const { user } = setup();

    await user.click(screen.getByRole("button", { name: "Transferência entre contas" }));
    expect(optionTexts("Sai de")).toHaveLength(6);
    expect(optionTexts("Sai de")).toContain("Corretora — Investimentos (BRL)");
    await user.selectOptions(screen.getByLabelText("Sai de"), "acc-checking");

    expect(optionTexts("Entra em")).not.toContain("Conta Corrente — Conta corrente (BRL)");
    expect(optionTexts("Entra em")).toHaveLength(5);
    expect(screen.queryByLabelText("Sentido")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Natureza")).not.toBeInTheDocument();
  });

  it("envia o valor sempre positivo, com origem e destino", async () => {
    const { user, onCreated } = setup();

    await user.click(screen.getByRole("button", { name: "Transferência entre contas" }));
    const button = screen.getByRole("button", { name: "Registrar transferência" });
    await user.selectOptions(screen.getByLabelText("Sai de"), "acc-checking");
    setDate("2026-08-10");
    await user.type(screen.getByLabelText("Valor"), "500,00");
    await user.type(screen.getByLabelText("Descrição"), "Para a reserva");
    expect(button).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Entra em"), "acc-savings");
    await user.click(button);

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(api.createCashTransfer).toHaveBeenCalledWith({
      from_account_id: "acc-checking",
      to_account_id: "acc-savings",
      entry_date: "2026-08-10",
      amount: "500.00",
      description: "Para a reserva",
      notes: null,
    });
    expect(api.createCashEntry).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Transferência registrada.");
  });

  it("trocar a origem para a conta que era o destino bloqueia o envio", async () => {
    const { user } = setup();

    await user.click(screen.getByRole("button", { name: "Transferência entre contas" }));
    await user.selectOptions(screen.getByLabelText("Sai de"), "acc-checking");
    await user.selectOptions(screen.getByLabelText("Entra em"), "acc-savings");
    await user.type(screen.getByLabelText("Valor"), "10");
    await user.type(screen.getByLabelText("Descrição"), "x");
    expect(screen.getByRole("button", { name: "Registrar transferência" })).toBeEnabled();

    await user.selectOptions(screen.getByLabelText("Sai de"), "acc-savings");

    expect(screen.getByRole("button", { name: "Registrar transferência" })).toBeDisabled();
  });
});
