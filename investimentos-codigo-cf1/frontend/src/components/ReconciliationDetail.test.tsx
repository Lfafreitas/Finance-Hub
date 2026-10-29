import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import {
  accounts,
  divergentComparison,
  equivalentComparison,
  LOG_ID,
  makeLog,
  transactionA,
  transactionB,
  TX_A_ID,
  TX_B_ID,
} from "../test/reconciliationFixtures";
import { ReconciliationDetail } from "./ReconciliationDetail";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getTransaction: vi.fn(),
  getReconciliationComparison: vi.fn(),
  resolveReconciliation: vi.fn(),
}));

function mockLoaded(comparison = divergentComparison) {
  vi.mocked(apiClient.getTransaction).mockImplementation(async (id) =>
    id === TX_A_ID ? transactionA : transactionB,
  );
  vi.mocked(apiClient.getReconciliationComparison).mockResolvedValue(comparison);
}

function renderDetail() {
  render(<ReconciliationDetail log={makeLog()} accounts={accounts} onResolved={vi.fn()} />);
}

describe("ReconciliationDetail", () => {
  beforeEach(() => {
    vi.mocked(apiClient.getTransaction).mockReset();
    vi.mocked(apiClient.getReconciliationComparison).mockReset();
  });

  it("mostra carregamento enquanto as três chamadas não respondem", () => {
    vi.mocked(apiClient.getTransaction).mockReturnValue(new Promise(() => {}));
    vi.mocked(apiClient.getReconciliationComparison).mockReturnValue(new Promise(() => {}));

    renderDetail();

    expect(screen.getByRole("status")).toHaveTextContent("Carregando detalhe do par");
  });

  it("busca as duas transações do par e a comparação do log", async () => {
    mockLoaded();

    renderDetail();
    await screen.findByTestId("reconciliation-detail");

    expect(apiClient.getTransaction).toHaveBeenCalledWith(TX_A_ID);
    expect(apiClient.getTransaction).toHaveBeenCalledWith(TX_B_ID);
    expect(apiClient.getReconciliationComparison).toHaveBeenCalledWith(LOG_ID);
  });

  it("mostra a origem (source) e a conta de cada lado", async () => {
    mockLoaded();

    renderDetail();

    const cardA = await screen.findByTestId("transaction-card-A");
    const cardB = screen.getByTestId("transaction-card-B");
    expect(cardA).toHaveTextContent("Lançamento manual");
    expect(cardB).toHaveTextContent("Importação CSV");
    expect(cardA).toHaveTextContent("Conta Ações — Corretora X");
  });

  it("tabela campo a campo destaca só as linhas divergentes, com os valores do backend", async () => {
    mockLoaded();

    renderDetail();
    await screen.findByTestId("comparison-table");

    expect(screen.getByTestId("classification-badge")).toHaveTextContent("Divergente");

    const gross = screen.getByTestId("comparison-row-gross_amount");
    expect(gross).toHaveAttribute("data-equal", "false");
    expect(within(gross).getByText("Valor bruto")).toBeInTheDocument();
    expect(within(gross).getByText("3000.0000")).toBeInTheDocument();
    expect(within(gross).getByText("3300.0000")).toBeInTheDocument();
    expect(within(gross).getByText("300.0000")).toBeInTheDocument();
    expect(within(gross).getByText("9,09%")).toHaveAttribute("title", "0.09090909090909090909090909091");
    expect(within(gross).getByText("Diferente")).toBeInTheDocument();

    const date = screen.getByTestId("comparison-row-transaction_date");
    expect(date).toHaveAttribute("data-equal", "false");
    expect(within(date).getByText("1 dia")).toBeInTheDocument();

    const quantity = screen.getByTestId("comparison-row-quantity");
    expect(quantity).toHaveAttribute("data-equal", "true");
    expect(within(quantity).getByText("Igual")).toBeInTheDocument();
  });

  it("par equivalente é rotulado como tal e nenhuma linha é destacada", async () => {
    mockLoaded(equivalentComparison);

    renderDetail();
    await screen.findByTestId("comparison-table");

    expect(screen.getByTestId("classification-badge")).toHaveTextContent("Equivalente");
    expect(screen.queryByText("Diferente")).not.toBeInTheDocument();
  });

  it("mostra o motivo registrado e as ações", async () => {
    mockLoaded();

    renderDetail();
    await screen.findByTestId("reconciliation-detail");

    expect(screen.getByText(/Motivo registrado na detecção/)).toHaveTextContent("DIVERGENT: gross_amount");
    expect(screen.getByTestId("reconciliation-actions")).toBeInTheDocument();
  });

  it("falha em qualquer chamada mostra erro e não mostra ações", async () => {
    vi.mocked(apiClient.getTransaction).mockResolvedValue(transactionA);
    vi.mocked(apiClient.getReconciliationComparison).mockRejectedValue(new Error("404 Not Found: sumiu"));

    renderDetail();

    expect(await screen.findByRole("alert")).toHaveTextContent("404 Not Found: sumiu");
    expect(screen.queryByTestId("reconciliation-actions")).not.toBeInTheDocument();
  });
});
