import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import {
  accounts,
  divergentComparison,
  makeLog,
  transactionA,
  transactionB,
  TX_A_ID,
} from "../test/reconciliationFixtures";
import { Reconciliation } from "./Reconciliation";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getAccounts: vi.fn(),
  getPortfolios: vi.fn(),
  getPendingReconciliations: vi.fn(),
  getTransaction: vi.fn(),
  getReconciliationComparison: vi.fn(),
  resolveReconciliation: vi.fn(),
  scanReconciliation: vi.fn(),
}));

const log = makeLog();
const secondLog = makeLog({ id: "88888888-ffff-4fff-8fff-ffffffffffff", match_reason: "EQUIVALENT: todos os campos" });

describe("Reconciliation", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(apiClient.getAccounts).mockResolvedValue(accounts);
    vi.mocked(apiClient.getPortfolios).mockResolvedValue([]);
    vi.mocked(apiClient.getTransaction).mockImplementation(async (id) =>
      id === TX_A_ID ? transactionA : transactionB,
    );
    vi.mocked(apiClient.getReconciliationComparison).mockResolvedValue(divergentComparison);
  });

  it("mostra carregamento antes da lista chegar", () => {
    vi.mocked(apiClient.getPendingReconciliations).mockReturnValue(new Promise(() => {}));

    render(<Reconciliation />);

    expect(screen.getByRole("status")).toHaveTextContent("Carregando pendências");
  });

  it("mostra erro quando a lista falha", async () => {
    vi.mocked(apiClient.getPendingReconciliations).mockRejectedValue(new Error("500 falha"));

    render(<Reconciliation />);

    expect(await screen.findByRole("alert")).toHaveTextContent("500 falha");
  });

  it("mostra estado vazio quando não há pendências", async () => {
    vi.mocked(apiClient.getPendingReconciliations).mockResolvedValue([]);

    render(<Reconciliation />);

    expect(await screen.findByText("Nenhuma pendência de reconciliação.")).toBeInTheDocument();
  });

  it("lista as pendências com o motivo registrado", async () => {
    vi.mocked(apiClient.getPendingReconciliations).mockResolvedValue([log, secondLog]);

    render(<Reconciliation />);

    const table = await screen.findByTestId("reconciliation-list");
    expect(within(table).getAllByRole("button", { name: /Ver detalhes/ })).toHaveLength(2);
    expect(within(table).getByText(/DIVERGENT: gross_amount/)).toBeInTheDocument();
    expect(within(table).getByText("EQUIVALENT: todos os campos")).toBeInTheDocument();
  });

  it("selecionar uma pendência abre o detalhe, e Fechar o esconde", async () => {
    vi.mocked(apiClient.getPendingReconciliations).mockResolvedValue([log]);
    const user = userEvent.setup();

    render(<Reconciliation />);
    await user.click(await screen.findByRole("button", { name: /Ver detalhes/ }));

    expect(await screen.findByTestId("reconciliation-detail")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Fechar" }));

    expect(screen.queryByTestId("reconciliation-detail")).not.toBeInTheDocument();
  });

  it("depois de resolver, rebusca a lista no backend (não é otimista) e fecha o detalhe", async () => {
    vi.mocked(apiClient.getPendingReconciliations).mockResolvedValueOnce([log]).mockResolvedValueOnce([]);
    vi.mocked(apiClient.resolveReconciliation).mockResolvedValue(makeLog({ status: "IGNORED" }));
    const user = userEvent.setup();

    render(<Reconciliation />);
    await user.click(await screen.findByRole("button", { name: /Ver detalhes/ }));
    await screen.findByTestId("reconciliation-detail");
    await user.click(screen.getByRole("button", { name: "Ignorar" }));
    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(await screen.findByText("Nenhuma pendência de reconciliação.")).toBeInTheDocument();
    expect(apiClient.getPendingReconciliations).toHaveBeenCalledTimes(2);
    expect(screen.queryByTestId("reconciliation-detail")).not.toBeInTheDocument();
    expect(screen.getByTestId("resolve-notice")).toHaveTextContent("Pendência ignorada");
  });

  it("se a resolução falha, a lista NÃO é rebuscada e o par continua aberto", async () => {
    vi.mocked(apiClient.getPendingReconciliations).mockResolvedValue([log]);
    vi.mocked(apiClient.resolveReconciliation).mockRejectedValue(new Error("rede caiu"));
    const user = userEvent.setup();

    render(<Reconciliation />);
    await user.click(await screen.findByRole("button", { name: /Ver detalhes/ }));
    await screen.findByTestId("reconciliation-detail");
    await user.click(screen.getByRole("button", { name: "Ignorar" }));
    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível falar com o servidor");
    expect(apiClient.getPendingReconciliations).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("reconciliation-detail")).toBeInTheDocument();
  });

  it("scan bem-sucedido rebusca a lista e mostra os pares novos", async () => {
    vi.mocked(apiClient.getPendingReconciliations).mockResolvedValueOnce([]).mockResolvedValueOnce([log]);
    vi.mocked(apiClient.scanReconciliation).mockResolvedValue({ created_count: 1, created: [log] });
    const user = userEvent.setup();

    render(<Reconciliation />);
    await screen.findByText("Nenhuma pendência de reconciliação.");
    await user.click(screen.getByRole("button", { name: "Procurar divergências" }));

    expect(await screen.findByTestId("reconciliation-list")).toBeInTheDocument();
    expect(screen.getByTestId("scan-result")).toHaveTextContent("1 par novo encontrado");
    expect(apiClient.getPendingReconciliations).toHaveBeenCalledTimes(2);
  });

  it("o scan por conta só oferece contas de investimentos", async () => {
    vi.mocked(apiClient.getAccounts).mockResolvedValue([
      ...accounts,
      { ...accounts[0], id: "acc-checking", name: "Conta Corrente", account_type: "CHECKING" },
    ]);
    vi.mocked(apiClient.getPendingReconciliations).mockResolvedValue([]);
    const user = userEvent.setup();

    render(<Reconciliation />);
    await screen.findByText("Nenhuma pendência de reconciliação.");
    await user.selectOptions(screen.getByLabelText("Escopo da busca"), "account");

    const names = Array.from(screen.getByLabelText("Conta").querySelectorAll("option")).map((o) => o.textContent);
    expect(names).toEqual(["Selecione…", "Conta Ações"]);
  });

  it("Atualizar rebusca a lista", async () => {
    vi.mocked(apiClient.getPendingReconciliations).mockResolvedValue([log]);
    const user = userEvent.setup();

    render(<Reconciliation />);
    await screen.findByTestId("reconciliation-list");
    await user.click(screen.getByRole("button", { name: "Atualizar" }));

    await waitFor(() => expect(apiClient.getPendingReconciliations).toHaveBeenCalledTimes(2));
  });

  it("falha ao listar contas/carteiras não impede a tela", async () => {
    vi.mocked(apiClient.getAccounts).mockRejectedValue(new Error("x"));
    vi.mocked(apiClient.getPortfolios).mockRejectedValue(new Error("x"));
    vi.mocked(apiClient.getPendingReconciliations).mockResolvedValue([log]);

    render(<Reconciliation />);

    expect(await screen.findByTestId("reconciliation-list")).toBeInTheDocument();
  });
});
