import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import { ApiError } from "../api/client";
import { makeLog, TX_A_ID, TX_B_ID } from "../test/reconciliationFixtures";
import { ReconciliationActions } from "./ReconciliationActions";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  resolveReconciliation: vi.fn(),
}));

const log = makeLog();

function setup() {
  const onResolved = vi.fn();
  render(<ReconciliationActions log={log} onResolved={onResolved} />);
  return { onResolved, user: userEvent.setup() };
}

describe("ReconciliationActions", () => {
  beforeEach(() => {
    vi.mocked(apiClient.resolveReconciliation).mockReset();
  });

  it("Mesclar começa desabilitado e só habilita depois de escolher a sobrevivente", async () => {
    const { user } = setup();
    const merge = screen.getByRole("button", { name: "Mesclar" });

    expect(merge).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ignorar" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Manter as duas" })).toBeEnabled();

    await user.click(screen.getByLabelText("Manter a transação B"));

    expect(merge).toBeEnabled();
  });

  it("nenhuma decisão é enviada sem confirmação, e Cancelar não envia nada", async () => {
    const { user, onResolved } = setup();

    await user.click(screen.getByRole("button", { name: "Ignorar" }));

    expect(screen.getByRole("alertdialog")).toHaveTextContent("Não pode ser desfeito");
    expect(apiClient.resolveReconciliation).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(apiClient.resolveReconciliation).not.toHaveBeenCalled();
    expect(onResolved).not.toHaveBeenCalled();
  });

  it("IGNORE confirmado envia só a decisão, sem sobrevivente", async () => {
    const resolved = makeLog({ status: "IGNORED" });
    vi.mocked(apiClient.resolveReconciliation).mockResolvedValue(resolved);
    const { user, onResolved } = setup();

    await user.click(screen.getByRole("button", { name: "Ignorar" }));
    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(onResolved).toHaveBeenCalledWith(resolved));
    expect(apiClient.resolveReconciliation).toHaveBeenCalledWith(log.id, { decision: "IGNORE" });
  });

  it("KEEP_BOTH não envia sobrevivente mesmo que uma tenha sido marcada", async () => {
    vi.mocked(apiClient.resolveReconciliation).mockResolvedValue(makeLog({ status: "KEPT_BOTH" }));
    const { user } = setup();

    await user.click(screen.getByLabelText("Manter a transação A"));
    await user.click(screen.getByRole("button", { name: "Manter as duas" }));
    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() =>
      expect(apiClient.resolveReconciliation).toHaveBeenCalledWith(log.id, { decision: "KEEP_BOTH" }),
    );
  });

  it.each([
    ["A", TX_A_ID, "22222222…"],
    ["B", TX_B_ID, "11111111…"],
  ])("MERGE mantendo %s envia o id certo e avisa qual será revertida", async (side, survivorId, reversedShort) => {
    vi.mocked(apiClient.resolveReconciliation).mockResolvedValue(makeLog({ status: "MERGED" }));
    const { user } = setup();

    await user.click(screen.getByLabelText(`Manter a transação ${side}`));
    await user.click(screen.getByRole("button", { name: "Mesclar" }));

    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("REVERTIDA");
    expect(dialog).toHaveTextContent(reversedShort);

    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() =>
      expect(apiClient.resolveReconciliation).toHaveBeenCalledWith(log.id, {
        decision: "MERGE",
        surviving_transaction_id: survivorId,
      }),
    );
  });

  it.each([
    [400, "inconsistentes"],
    [404, "não existe mais"],
    [409, "já foi resolvida"],
    [422, "inválida"],
  ])("erro %i mostra mensagem compreensível e não chama onResolved", async (status, fragment) => {
    vi.mocked(apiClient.resolveReconciliation).mockRejectedValue(
      new ApiError(status, "Erro", JSON.stringify({ detail: "motivo do backend" })),
    );
    const { user, onResolved } = setup();

    await user.click(screen.getByRole("button", { name: "Ignorar" }));
    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(fragment);
    expect(alert).toHaveTextContent("motivo do backend");
    expect(onResolved).not.toHaveBeenCalled();
    // A confirmação fecha e os botões voltam a ficar utilizáveis.
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ignorar" })).toBeEnabled();
  });
});
