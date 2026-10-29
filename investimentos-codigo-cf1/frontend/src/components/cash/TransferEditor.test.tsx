import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/cashflow";
import type { CashflowEntryRead } from "../../api/cashflowTypes";
import { ApiError } from "../../api/client";
import { allAccounts, checking, makeEntry } from "../../test/cashFixtures";
import { TransferEditor } from "./TransferEditor";

vi.mock("../../api/cashflow");

const sent = makeEntry({ id: "e-sent", description: "Pagamento de fatura", amount: "-500.0000", entry_date: "2026-08-05" });
const received = makeEntry({
  id: "e-received",
  account_id: "acc-card",
  description: "Pagamento recebido",
  amount: "500.0000",
  entry_date: "2026-08-06",
});
const otherValue = makeEntry({ id: "e-other", account_id: "acc-card", description: "Outra coisa", amount: "499.0000" });
const sameAccount = makeEntry({ id: "e-same", description: "Estorno na mesma conta", amount: "500.0000" });

function setup(entry: CashflowEntryRead = sent, accounts = allAccounts) {
  const onLinked = vi.fn();
  const onCancel = vi.fn();
  render(<TransferEditor entry={entry} accounts={accounts} onLinked={onLinked} onCancel={onCancel} />);
  return { onLinked, onCancel, user: userEvent.setup() };
}

describe("TransferEditor", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.getCashEntries).mockResolvedValue([sent, received, otherValue, sameAccount]);
    vi.mocked(api.linkCashTransfer).mockResolvedValue({ entries: [] });
    vi.mocked(api.markInvestmentTransfer).mockResolvedValue({ entries: [] });
  });

  it("procura a outra ponta em 10 dias para cada lado, em todas as contas", async () => {
    setup();

    await screen.findByLabelText("Lançamento da outra ponta");
    expect(api.getCashEntries).toHaveBeenCalledWith({ start: "2026-07-26", end: "2026-08-15" }, 500);
  });

  it("só oferece lançamento de outra conta com o valor exatamente oposto", async () => {
    setup();

    const select = await screen.findByLabelText("Lançamento da outra ponta");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent)).toEqual([
      "Selecione…",
      "06/08/2026 · Cartão · Pagamento recebido",
    ]);
  });

  it("liga os dois lançamentos escolhidos", async () => {
    const { user, onLinked } = setup();
    const button = screen.getByRole("button", { name: "Marcar como transferência" });
    expect(button).toBeDisabled();

    await user.selectOptions(await screen.findByLabelText("Lançamento da outra ponta"), "e-received");
    await user.click(button);

    await waitFor(() => expect(onLinked).toHaveBeenCalled());
    expect(api.linkCashTransfer).toHaveBeenCalledWith("e-sent", "e-received");
    expect(api.markInvestmentTransfer).not.toHaveBeenCalled();
  });

  it("sem candidata, explica o que falta e não deixa ligar", async () => {
    vi.mocked(api.getCashEntries).mockResolvedValue([sent, otherValue]);
    setup();

    expect(await screen.findByTestId("no-candidates")).toHaveTextContent("Importe o extrato da outra conta primeiro");
    expect(screen.getByRole("button", { name: "Marcar como transferência" })).toBeDisabled();
  });

  it("saída vira aporte; só contas de investimentos da mesma moeda são oferecidas", async () => {
    const { user, onLinked } = setup();

    await user.click(screen.getByLabelText("um aporte em conta de investimentos"));
    const select = screen.getByLabelText("Conta de investimentos");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent)).toEqual([
      "Selecione…",
      "Corretora — Banco Exemplo",
    ]);
    await user.selectOptions(select, "acc-broker");
    await user.click(screen.getByRole("button", { name: "Marcar como transferência" }));

    await waitFor(() => expect(onLinked).toHaveBeenCalled());
    expect(api.markInvestmentTransfer).toHaveBeenCalledWith("e-sent", "acc-broker");
    expect(api.linkCashTransfer).not.toHaveBeenCalled();
  });

  it("entrada é chamada de resgate", () => {
    setup(makeEntry({ amount: "800.0000" }));

    expect(screen.getByLabelText("um resgate de conta de investimentos")).toBeInTheDocument();
    expect(screen.queryByLabelText("um aporte em conta de investimentos")).not.toBeInTheDocument();
  });

  it("sem conta de investimentos na moeda, avisa", async () => {
    const { user } = setup(sent, [checking]);

    await user.click(screen.getByLabelText("um aporte em conta de investimentos"));

    expect(screen.getByTestId("no-investment-accounts")).toHaveTextContent("Nenhuma conta de investimentos em BRL");
    expect(screen.getByRole("button", { name: "Marcar como transferência" })).toBeDisabled();
  });

  it("a escolha de um modo não vale para o outro", async () => {
    const { user } = setup();

    await user.selectOptions(await screen.findByLabelText("Lançamento da outra ponta"), "e-received");
    await user.click(screen.getByLabelText("um aporte em conta de investimentos"));

    expect(screen.getByRole("button", { name: "Marcar como transferência" })).toBeDisabled();
    expect(api.linkCashTransfer).not.toHaveBeenCalled();
  });

  it("recusa do backend aparece e o editor continua aberto", async () => {
    vi.mocked(api.linkCashTransfer).mockRejectedValue(
      new ApiError(400, "Bad Request", '{"detail":"as datas estão a mais de 10 dias uma da outra"}'),
    );
    const { user, onLinked } = setup();

    await user.selectOptions(await screen.findByLabelText("Lançamento da outra ponta"), "e-received");
    await user.click(screen.getByRole("button", { name: "Marcar como transferência" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("as datas estão a mais de 10 dias");
    expect(onLinked).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Marcar como transferência" })).toBeEnabled();
  });

  it("falha ao procurar candidatas aparece como erro", async () => {
    vi.mocked(api.getCashEntries).mockRejectedValue(new Error("rede"));
    setup();

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível falar com o servidor");
  });
});
