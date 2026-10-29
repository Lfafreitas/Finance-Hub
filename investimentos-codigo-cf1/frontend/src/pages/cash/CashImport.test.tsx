import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/cashflow";
import type { CashflowImportBatchRead } from "../../api/cashflowTypes";
import * as client from "../../api/client";
import { ApiError } from "../../api/client";
import { allAccounts, brokerage, cashPreviewFixture, categories, commitResultFixture } from "../../test/cashFixtures";
import { CashImport } from "./CashImport";

vi.mock("../../api/cashflow");
vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getAccounts: vi.fn(),
}));

const file = new File(["OFXHEADER:100"], "extrato.ofx");
const OPENING = "Criar o saldo inicial desta conta";

const batch: CashflowImportBatchRead = {
  id: "batch-0",
  account_id: "acc-checking",
  profile: "NUBANK_ACCOUNT_OFX",
  file_name: "julho.ofx",
  file_sha256: "zzz",
  period_start: "2026-07-01",
  period_end: "2026-07-31",
  rows_total: 12,
  rows_imported: 10,
  statement_balance: null,
  statement_balance_date: null,
  created_at: "2026-08-02T10:00:00Z",
};

async function goToPreview(user: ReturnType<typeof userEvent.setup>) {
  render(<CashImport />);
  await user.selectOptions(await screen.findByLabelText("Conta"), "acc-checking");
  await user.upload(screen.getByLabelText("Arquivo"), file);
  await user.click(screen.getByRole("button", { name: "Pré-visualizar" }));
  return screen.findByTestId("cash-import-table");
}

const checkbox = (line: number) => screen.getByRole("checkbox", { name: `Incluir linha ${line}` });
const text = (testId: string) => screen.getByTestId(testId).textContent?.replace(/ /g, " ");

describe("CashImport", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(client.getAccounts).mockResolvedValue(allAccounts);
    vi.mocked(api.getCategories).mockResolvedValue(categories);
    vi.mocked(api.getCashImportBatches).mockResolvedValue([]);
    vi.mocked(api.previewCashImport).mockResolvedValue(cashPreviewFixture);
    vi.mocked(api.countCashEntries).mockResolvedValue({ total: 0 });
    vi.mocked(api.commitCashImport).mockResolvedValue(commitResultFixture);
    vi.mocked(api.getInbox).mockResolvedValue({ inbox_dir: "C:\\Entrada", exists: true, files: [] });
  });

  it("sem conta de caixa, orienta a cadastrar", async () => {
    vi.mocked(client.getAccounts).mockResolvedValue([brokerage]);

    render(<CashImport />);

    expect(await screen.findByTestId("no-cash-accounts")).toHaveTextContent("Cadastros");
  });

  it("contas de investimentos não são oferecidas", async () => {
    render(<CashImport />);

    const select = await screen.findByLabelText("Conta");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent)).toEqual([
      "Selecione…",
      "Conta Corrente — Conta corrente (BRL)",
      "Cartão — Cartão de crédito (BRL)",
      "Reserva — Reserva (BRL)",
    ]);
  });

  it("a prévia exige conta e arquivo; sem formato escolhido, o backend detecta", async () => {
    const user = userEvent.setup();
    render(<CashImport />);
    const button = await screen.findByRole("button", { name: "Pré-visualizar" });

    expect(button).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Conta"), "acc-checking");
    expect(button).toBeDisabled();
    await user.upload(screen.getByLabelText("Arquivo"), file);
    await user.click(button);

    await screen.findByTestId("cash-import-table");
    expect(api.previewCashImport).toHaveBeenCalledWith("acc-checking", file, null);
    expect(api.commitCashImport).not.toHaveBeenCalled();
  });

  it("formato escolhido à mão é enviado", async () => {
    const user = userEvent.setup();
    render(<CashImport />);

    await user.selectOptions(await screen.findByLabelText("Conta"), "acc-card");
    await user.selectOptions(screen.getByLabelText("Formato"), "NUBANK_CARD_CSV");
    await user.upload(screen.getByLabelText("Arquivo"), file);
    await user.click(screen.getByRole("button", { name: "Pré-visualizar" }));

    await screen.findByTestId("cash-import-table");
    expect(api.previewCashImport).toHaveBeenCalledWith("acc-card", file, "NUBANK_CARD_CSV");
  });

  it("fatura em PDF: mostra vencimento, total e as conferências com o resumo", async () => {
    vi.mocked(api.previewCashImport).mockResolvedValue({
      ...cashPreviewFixture,
      profile: "NUBANK_CARD_PDF",
      statement_balance: null,
      statement_balance_date: null,
      statement_due_date: "2026-02-06",
      statement_previous: "300.00",
      statement_total: "305.48",
      checks: [
        { label: "Compras, estornos e créditos", expected: "305.48", found: "305.48", ok: true },
        { label: "Pagamentos recebidos", expected: "-300.00", found: "-300.00", ok: true },
      ],
    });

    await goToPreview(userEvent.setup());

    expect(text("cash-import-invoice")).toBe("Fatura com vencimento em 06/02/2026 · total a pagar R$ 305,48");
    const checks = within(screen.getByTestId("cash-import-checks")).getAllByRole("listitem");
    expect(checks.map((item) => item.textContent?.replace(/\u00a0/g, " "))).toEqual([
      "✓ Compras, estornos e créditos: R$ 305,48 lidos = R$ 305,48 no resumo da fatura",
      "✓ Pagamentos recebidos: -R$ 300,00 lidos = -R$ 300,00 no resumo da fatura",
    ]);
    expect(screen.getByTestId("cash-import-summary")).toHaveTextContent("Nubank — fatura do cartão (PDF)");
  });

  it("extrato sem conferências não mostra a lista nem a linha da fatura", async () => {
    await goToPreview(userEvent.setup());

    expect(screen.queryByTestId("cash-import-checks")).toBeNull();
    expect(screen.queryByTestId("cash-import-invoice")).toBeNull();
  });

  it("o campo de arquivo aceita PDF", async () => {
    render(<CashImport />);

    expect(await screen.findByLabelText("Arquivo")).toHaveAttribute("accept", ".csv,.ofx,.pdf");
  });

  it("pré-seleciona só o que pode entrar: erro e duplicata ficam travados", async () => {
    await goToPreview(userEvent.setup());

    expect(checkbox(1)).toBeChecked();
    expect(checkbox(2)).not.toBeChecked();
    expect(checkbox(2)).toBeDisabled();
    expect(checkbox(3)).not.toBeChecked();
    expect(checkbox(3)).toBeDisabled();
    expect(checkbox(4)).toBeChecked();
    expect(screen.getByTestId("cash-import-summary")).toHaveTextContent(
      "Nubank — extrato da conta (OFX) · 4 linhas · 2 selecionadas · 1 com erro · 1 já importadas",
    );
  });

  it("mostra a situação, a regra que classificaria e o saldo informado pelo banco", async () => {
    await goToPreview(userEvent.setup());

    expect(screen.getByTestId("cash-import-row-0")).toHaveTextContent("Pronta para importar");
    expect(screen.getByTestId("cash-import-row-0")).toHaveTextContent("Gasto · Alimentação › Mercado");
    expect(screen.getByTestId("cash-import-row-0")).toHaveTextContent("Mercado do bairro");
    expect(text("cash-import-row-0")).toContain("-R$ 100,00");
    expect(screen.getByTestId("cash-import-row-1")).toHaveTextContent("data inválida");
    expect(screen.getByTestId("cash-import-row-2")).toHaveTextContent("Já importada nesta conta");
    expect(screen.getByTestId("cash-import-row-3")).toHaveTextContent("nenhuma");
    expect(screen.getByText(/saldo informado pelo banco em 31\/08\/2026/)).toBeInTheDocument();
  });

  it("primeira importação com saldo no arquivo: propõe o saldo inicial e o envia", async () => {
    const user = userEvent.setup();
    await goToPreview(user);

    expect(api.countCashEntries).toHaveBeenCalledWith({ account_id: "acc-checking", include_reversed: true });
    expect(screen.getByLabelText(OPENING)).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Importar 2 selecionadas" }));

    await screen.findByTestId("cash-import-result");
    expect(api.commitCashImport).toHaveBeenCalledWith(cashPreviewFixture, [0, 3], true);
  });

  it("o saldo inicial pode ser recusado pelo usuário", async () => {
    const user = userEvent.setup();
    await goToPreview(user);

    await user.click(screen.getByLabelText(OPENING));
    await user.click(screen.getByRole("button", { name: "Importar 2 selecionadas" }));

    await screen.findByTestId("cash-import-result");
    expect(api.commitCashImport).toHaveBeenCalledWith(cashPreviewFixture, [0, 3], false);
  });

  it("tirar uma linha válida desliga o saldo inicial e explica por quê", async () => {
    const user = userEvent.setup();
    await goToPreview(user);

    await user.click(checkbox(4));

    expect(screen.getByLabelText(OPENING)).not.toBeChecked();
    expect(screen.getByLabelText(OPENING)).toBeDisabled();
    expect(screen.getByTestId("opening-hint")).toHaveTextContent("todas as linhas válidas do arquivo precisam estar selecionadas");
    await user.click(screen.getByRole("button", { name: "Importar 1 selecionada" }));
    await screen.findByTestId("cash-import-result");
    expect(api.commitCashImport).toHaveBeenCalledWith(cashPreviewFixture, [0], false);
  });

  it("conta que já tem lançamentos não recebe oferta de saldo inicial", async () => {
    vi.mocked(api.countCashEntries).mockResolvedValue({ total: 3 });
    const user = userEvent.setup();
    await goToPreview(user);

    expect(screen.queryByLabelText(OPENING)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Importar 2 selecionadas" }));

    await screen.findByTestId("cash-import-result");
    expect(api.commitCashImport).toHaveBeenCalledWith(cashPreviewFixture, [0, 3], false);
  });

  it("arquivo sem saldo (CSV, fatura) não recebe oferta de saldo inicial", async () => {
    vi.mocked(api.previewCashImport).mockResolvedValue({
      ...cashPreviewFixture,
      statement_balance: null,
      statement_balance_date: null,
    });
    await goToPreview(userEvent.setup());

    expect(screen.queryByLabelText(OPENING)).not.toBeInTheDocument();
    expect(screen.queryByText(/saldo informado pelo banco/)).not.toBeInTheDocument();
  });

  it("resultado: contagens, saldo inicial, regras, fatura casada e saldo conferido", async () => {
    const user = userEvent.setup();
    await goToPreview(user);
    await user.click(screen.getByRole("button", { name: "Importar 2 selecionadas" }));

    const result = await screen.findByTestId("cash-import-result");
    expect(result).toHaveTextContent("2 lançamentos importados · 2 linhas não incluídas.");
    expect(text("result-opening")).toBe("Saldo inicial criado: R$ 1.254,30.");
    expect(screen.getByTestId("result-rules")).toHaveTextContent(
      "1 lançamento classificado por regra · 1 pagamento de fatura casado.",
    );
    expect(text("result-balance")).toBe("Saldo conferido: R$ 89,20 no sistema e no banco.");
    expect(screen.queryByTestId("cash-import-table")).not.toBeInTheDocument();
  });

  it("saldo que não bate é dito com os dois valores e a diferença", async () => {
    vi.mocked(api.commitCashImport).mockResolvedValue({
      ...commitResultFixture,
      opening_adjustment: null,
      system_balance: "100.0000",
      balance_difference: "10.8000",
    });
    const user = userEvent.setup();
    await goToPreview(user);
    await user.click(screen.getByRole("button", { name: "Importar 2 selecionadas" }));

    await screen.findByTestId("cash-import-result");
    expect(text("result-balance")).toBe(
      "Saldo não bate: R$ 100,00 no sistema, R$ 89,20 no banco (diferença de R$ 10,80).",
    );
    expect(screen.queryByTestId("result-opening")).not.toBeInTheDocument();
  });

  it("arquivo sem saldo não gera linha de conferência no resultado", async () => {
    vi.mocked(api.commitCashImport).mockResolvedValue({
      ...commitResultFixture,
      statement_balance: null,
      system_balance: null,
      balance_difference: null,
    });
    const user = userEvent.setup();
    await goToPreview(user);
    await user.click(screen.getByRole("button", { name: "Importar 2 selecionadas" }));

    await screen.findByTestId("cash-import-result");
    expect(screen.queryByTestId("result-balance")).not.toBeInTheDocument();
  });

  it("depois de importar, o campo de arquivo volta vazio e o histórico é recarregado", async () => {
    const user = userEvent.setup();
    await goToPreview(user);
    expect((screen.getByLabelText("Arquivo") as HTMLInputElement).files).toHaveLength(1);
    vi.mocked(api.getCashImportBatches).mockResolvedValue([batch]);

    await user.click(screen.getByRole("button", { name: "Importar 2 selecionadas" }));

    await screen.findByTestId("cash-import-batches");
    expect((screen.getByLabelText("Arquivo") as HTMLInputElement).files).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Pré-visualizar" })).toBeDisabled();
    expect(api.getCashImportBatches).toHaveBeenCalledTimes(2);
  });

  it("avisa quando o mesmo arquivo já foi importado, e sem nada selecionado não importa", async () => {
    vi.mocked(api.previewCashImport).mockResolvedValue({
      ...cashPreviewFixture,
      file_already_imported: true,
      rows: cashPreviewFixture.rows.map((row) => ({ ...row, error: null, is_duplicate: true })),
    });
    await goToPreview(userEvent.setup());

    expect(screen.getByTestId("file-already-imported")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Importar 0 selecionadas" })).toBeDisabled();
  });

  it("trocar a conta descarta a prévia", async () => {
    const user = userEvent.setup();
    await goToPreview(user);

    await user.selectOptions(screen.getByLabelText("Conta"), "acc-card");

    expect(screen.queryByTestId("cash-import-table")).not.toBeInTheDocument();
  });

  it("erro na prévia aparece com o motivo e nada é mostrado", async () => {
    vi.mocked(api.previewCashImport).mockRejectedValue(
      new ApiError(400, "Bad Request", '{"detail":"arquivo de cartão em conta que não é cartão"}'),
    );
    const user = userEvent.setup();
    render(<CashImport />);
    await user.selectOptions(await screen.findByLabelText("Conta"), "acc-checking");
    await user.upload(screen.getByLabelText("Arquivo"), file);
    await user.click(screen.getByRole("button", { name: "Pré-visualizar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("arquivo de cartão em conta que não é cartão");
    expect(screen.queryByTestId("cash-import-table")).not.toBeInTheDocument();
  });

  it("erro no commit mantém a prévia e a seleção", async () => {
    vi.mocked(api.commitCashImport).mockRejectedValue(
      new ApiError(409, "Conflict", '{"detail":"assinatura da prévia inválida"}'),
    );
    const user = userEvent.setup();
    await goToPreview(user);

    await user.click(screen.getByRole("button", { name: "Importar 2 selecionadas" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("assinatura da prévia inválida");
    expect(screen.getByTestId("cash-import-table")).toBeInTheDocument();
    expect(checkbox(1)).toBeChecked();
    expect(screen.queryByTestId("cash-import-result")).not.toBeInTheDocument();
  });

  it("histórico mostra conta, arquivo, período e linhas", async () => {
    vi.mocked(api.getCashImportBatches).mockResolvedValue([batch]);

    render(<CashImport />);

    const table = await screen.findByTestId("cash-import-batches");
    const row = within(table).getByText("julho.ofx").closest("tr");
    expect(row).toHaveTextContent("02/08/2026");
    expect(row).toHaveTextContent("Conta Corrente");
    expect(row).toHaveTextContent("01/07/2026 a 31/07/2026");
    expect(row).toHaveTextContent("10 de 12");
    await waitFor(() => expect(screen.queryByText("Nenhuma importação ainda.")).not.toBeInTheDocument());
  });
});
