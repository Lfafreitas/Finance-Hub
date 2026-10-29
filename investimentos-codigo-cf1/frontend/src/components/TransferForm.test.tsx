import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import { ApiError } from "../api/client";
import { makeTransaction } from "../test/reconciliationFixtures";
import { brlAccount, usdAccount } from "../test/workFixtures";
import { TransferForm } from "./TransferForm";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  createTransfer: vi.fn(),
}));

const other = { ...brlAccount, id: "acc-brl-2", name: "Conta Reserva" };

function setup() {
  const onCreated = vi.fn();
  render(<TransferForm accounts={[brlAccount, other, usdAccount]} onCreated={onCreated} />);
  return { onCreated, user: userEvent.setup() };
}

describe("TransferForm", () => {
  beforeEach(() => {
    vi.mocked(apiClient.createTransfer).mockReset();
  });

  it("envia origem, destino, valor e data como digitados", async () => {
    vi.mocked(apiClient.createTransfer).mockResolvedValue({
      transfer_out: makeTransaction(),
      transfer_in: makeTransaction(),
    });
    const { user, onCreated } = setup();

    await user.selectOptions(screen.getByLabelText("Conta de origem"), brlAccount.id);
    await user.selectOptions(screen.getByLabelText("Conta de destino"), other.id);
    await user.type(screen.getByLabelText("Valor"), "300.00");
    await user.type(screen.getByLabelText("Data"), "2026-03-10");
    await user.click(screen.getByRole("button", { name: "Transferir" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(apiClient.createTransfer).toHaveBeenCalledWith({
      from_account_id: brlAccount.id,
      to_account_id: other.id,
      gross_amount: "300.00",
      transaction_date: "2026-03-10",
    });
  });

  it("origem igual ao destino bloqueia o envio e avisa", async () => {
    const { user } = setup();

    await user.selectOptions(screen.getByLabelText("Conta de origem"), brlAccount.id);
    await user.selectOptions(screen.getByLabelText("Conta de destino"), brlAccount.id);
    await user.type(screen.getByLabelText("Valor"), "300");
    await user.type(screen.getByLabelText("Data"), "2026-03-10");

    expect(screen.getByRole("button", { name: "Transferir" })).toBeDisabled();
    expect(screen.getByText("Origem e destino precisam ser contas diferentes.")).toBeInTheDocument();
  });

  it("recusa do backend (moedas diferentes) é mostrada e onCreated não é chamado", async () => {
    vi.mocked(apiClient.createTransfer).mockRejectedValue(
      new ApiError(
        400,
        "Bad Request",
        JSON.stringify({ detail: "transferência entre contas de moedas diferentes está fora do escopo desta fase" }),
      ),
    );
    const { user, onCreated } = setup();

    await user.selectOptions(screen.getByLabelText("Conta de origem"), brlAccount.id);
    await user.selectOptions(screen.getByLabelText("Conta de destino"), usdAccount.id);
    await user.type(screen.getByLabelText("Valor"), "300");
    await user.type(screen.getByLabelText("Data"), "2026-03-10");
    await user.click(screen.getByRole("button", { name: "Transferir" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("moedas diferentes");
    expect(onCreated).not.toHaveBeenCalled();
  });
});
