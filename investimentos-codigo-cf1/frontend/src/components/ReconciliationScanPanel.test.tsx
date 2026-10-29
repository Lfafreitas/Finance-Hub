import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import { ApiError } from "../api/client";
import { ACCOUNT_ID, accounts, makeLog } from "../test/reconciliationFixtures";
import { ReconciliationScanPanel } from "./ReconciliationScanPanel";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  scanReconciliation: vi.fn(),
}));

const portfolios = [{ id: "pf-1", name: "Longo prazo" }];

function setup() {
  const onScanned = vi.fn();
  render(<ReconciliationScanPanel accounts={accounts} portfolios={portfolios} onScanned={onScanned} />);
  return { onScanned, user: userEvent.setup() };
}

describe("ReconciliationScanPanel", () => {
  beforeEach(() => {
    vi.mocked(apiClient.scanReconciliation).mockReset();
  });

  it("escopo padrão escaneia todas as contas e mostra quantos pares novos surgiram", async () => {
    const result = { created_count: 2, created: [makeLog(), makeLog({ id: "outro" })] };
    vi.mocked(apiClient.scanReconciliation).mockResolvedValue(result);
    const { user, onScanned } = setup();

    await user.click(screen.getByRole("button", { name: "Procurar divergências" }));

    await waitFor(() => expect(onScanned).toHaveBeenCalledWith(result));
    expect(apiClient.scanReconciliation).toHaveBeenCalledWith({});
    expect(screen.getByTestId("scan-result")).toHaveTextContent("2 pares novos encontrados");
  });

  it("escopo por conta exige escolher a conta e envia account_id", async () => {
    vi.mocked(apiClient.scanReconciliation).mockResolvedValue({ created_count: 1, created: [makeLog()] });
    const { user } = setup();
    const button = screen.getByRole("button", { name: "Procurar divergências" });

    await user.selectOptions(screen.getByLabelText("Escopo da busca"), "account");
    expect(button).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("Conta"), ACCOUNT_ID);
    await user.click(button);

    await waitFor(() => expect(apiClient.scanReconciliation).toHaveBeenCalledWith({ account_id: ACCOUNT_ID }));
    expect(await screen.findByTestId("scan-result")).toHaveTextContent("1 par novo encontrado");
  });

  it("escopo por carteira envia portfolio_id", async () => {
    vi.mocked(apiClient.scanReconciliation).mockResolvedValue({ created_count: 0, created: [] });
    const { user } = setup();

    await user.selectOptions(screen.getByLabelText("Escopo da busca"), "portfolio");
    await user.selectOptions(screen.getByLabelText("Carteira"), "pf-1");
    await user.click(screen.getByRole("button", { name: "Procurar divergências" }));

    await waitFor(() => expect(apiClient.scanReconciliation).toHaveBeenCalledWith({ portfolio_id: "pf-1" }));
    expect(await screen.findByTestId("scan-result")).toHaveTextContent("Nenhum par novo encontrado");
  });

  it("trocar de escopo limpa a seleção anterior", async () => {
    const { user } = setup();

    await user.selectOptions(screen.getByLabelText("Escopo da busca"), "account");
    await user.selectOptions(screen.getByLabelText("Conta"), ACCOUNT_ID);
    await user.selectOptions(screen.getByLabelText("Escopo da busca"), "portfolio");

    expect(screen.getByLabelText("Carteira")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Procurar divergências" })).toBeDisabled();
  });

  it("erro do servidor mostra mensagem e não dispara atualização da lista", async () => {
    vi.mocked(apiClient.scanReconciliation).mockRejectedValue(
      new ApiError(404, "Not Found", JSON.stringify({ detail: "conta não encontrada" })),
    );
    const { user, onScanned } = setup();

    await user.click(screen.getByRole("button", { name: "Procurar divergências" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("não foi encontrada");
    expect(alert).toHaveTextContent("conta não encontrada");
    expect(onScanned).not.toHaveBeenCalled();
    expect(screen.queryByTestId("scan-result")).not.toBeInTheDocument();
  });
});
