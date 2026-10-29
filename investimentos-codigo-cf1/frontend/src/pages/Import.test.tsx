import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import { ApiError } from "../api/client";
import { brlAccount, checkingAccount, previewFixture, usdAccount } from "../test/workFixtures";
import { Import } from "./Import";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getAccounts: vi.fn(),
  previewImport: vi.fn(),
  commitImport: vi.fn(),
}));

const file = new File(["data,tipo,valor\n"], "extrato.csv", { type: "text/csv" });

async function goToPreview(user: ReturnType<typeof userEvent.setup>) {
  render(<Import />);
  await user.selectOptions(await screen.findByLabelText("Conta"), brlAccount.id);
  await user.upload(screen.getByLabelText("Arquivo"), file);
  await user.click(screen.getByRole("button", { name: "Pré-visualizar" }));
  return screen.findByTestId("import-preview-table");
}

const checkbox = (line: number) => screen.getByRole("checkbox", { name: `Incluir linha ${line}` });

describe("Import", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(apiClient.getAccounts).mockResolvedValue([brlAccount, usdAccount]);
    vi.mocked(apiClient.previewImport).mockResolvedValue(previewFixture);
  });

  it("sem contas, orienta a cadastrar uma antes", async () => {
    vi.mocked(apiClient.getAccounts).mockResolvedValue([]);

    render(<Import />);

    expect(await screen.findByTestId("no-accounts")).toHaveTextContent("Cadastros");
  });

  it("contas do controle financeiro não são oferecidas para importação de investimentos", async () => {
    vi.mocked(apiClient.getAccounts).mockResolvedValue([brlAccount, checkingAccount]);

    render(<Import />);

    const select = await screen.findByLabelText("Conta");
    const names = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(names.some((name) => name?.includes("Conta Ações"))).toBe(true);
    expect(names.some((name) => name?.includes("Conta Corrente"))).toBe(false);
  });

  it("Pré-visualizar exige conta e arquivo, e envia conta, formato e o arquivo", async () => {
    const user = userEvent.setup();
    render(<Import />);
    const button = await screen.findByRole("button", { name: "Pré-visualizar" });

    expect(button).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Conta"), brlAccount.id);
    expect(button).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Formato"), "XLSX");
    await user.upload(screen.getByLabelText("Arquivo"), file);
    await user.click(button);

    await screen.findByTestId("import-preview-table");
    expect(apiClient.previewImport).toHaveBeenCalledWith(brlAccount.id, "XLSX", file);
    expect(apiClient.commitImport).not.toHaveBeenCalled();
  });

  it("pré-seleção conservadora: só linhas sem erro, não duplicadas e sem suspeita", async () => {
    await goToPreview(userEvent.setup());

    expect(checkbox(1)).toBeChecked();
    expect(checkbox(2)).not.toBeChecked(); // erro
    expect(checkbox(2)).toBeDisabled();
    expect(checkbox(3)).not.toBeChecked(); // duplicata exata
    expect(checkbox(3)).toBeDisabled();
    expect(checkbox(4)).not.toBeChecked(); // possível duplicata: o usuário decide
    expect(checkbox(4)).toBeEnabled();
    expect(checkbox(5)).toBeChecked();
    expect(screen.getByTestId("import-summary")).toHaveTextContent(
      "5 linhas no arquivo · 2 selecionadas · 1 com erro · 1 já importadas",
    );
  });

  it("mostra a situação de cada linha com o texto do servidor", async () => {
    await goToPreview(userEvent.setup());

    expect(screen.getByTestId("import-row-0")).toHaveTextContent("Pronta para importar");
    expect(screen.getByTestId("import-row-1")).toHaveTextContent("ativo 'XPTO3' não cadastrado");
    expect(screen.getByTestId("import-row-2")).toHaveTextContent("Já importada antes");
    expect(screen.getByTestId("import-row-3")).toHaveTextContent("encontrada 1 transação ativa existente");
    const deposit = screen.getByTestId("import-row-4");
    expect(within(deposit).getByText("Depósito")).toBeInTheDocument();
    expect(within(deposit).getByText("500")).toBeInTheDocument();
  });

  it("commit devolve a preview intacta e só os índices marcados, incluindo uma suspeita aceita", async () => {
    vi.mocked(apiClient.commitImport).mockResolvedValue({
      imported_count: 2,
      excluded_count: 3,
      transaction_ids: ["a", "b"],
    });
    const user = userEvent.setup();
    await goToPreview(user);

    await user.click(checkbox(5)); // desmarca o depósito
    await user.click(checkbox(4)); // aceita a possível duplicata
    await user.click(screen.getByRole("button", { name: "Importar 2 selecionadas" }));

    await waitFor(() => expect(apiClient.commitImport).toHaveBeenCalledWith(previewFixture, [0, 3]));
    // O MESMO objeto recebido do servidor — nenhuma linha recriada ou editada.
    expect(vi.mocked(apiClient.commitImport).mock.calls[0][0]).toBe(previewFixture);
    expect(await screen.findByTestId("import-result")).toHaveTextContent(
      "2 transações importadas; 3 linhas não incluídas",
    );
    expect(screen.queryByTestId("import-preview-table")).not.toBeInTheDocument();
  });

  it("sem nenhuma linha marcada, Importar fica desabilitado", async () => {
    const user = userEvent.setup();
    await goToPreview(user);

    await user.click(checkbox(1));
    await user.click(checkbox(5));

    expect(screen.getByRole("button", { name: "Importar 0 selecionadas" })).toBeDisabled();
  });

  it("lote recusado mostra o motivo do servidor e mantém a preview para correção", async () => {
    vi.mocked(apiClient.commitImport).mockRejectedValue(
      new ApiError(422, "Unprocessable", JSON.stringify({ detail: "linha 0: SELL de 100 excede a posição atual (0)" })),
    );
    const user = userEvent.setup();
    await goToPreview(user);

    await user.click(screen.getByRole("button", { name: "Importar 2 selecionadas" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("linha 0: SELL de 100 excede a posição atual (0)");
    expect(screen.getByTestId("import-preview-table")).toBeInTheDocument();
    expect(screen.queryByTestId("import-result")).not.toBeInTheDocument();
  });

  it("arquivo recusado na preview mostra o erro e nenhuma tabela", async () => {
    vi.mocked(apiClient.previewImport).mockRejectedValue(
      new ApiError(400, "Bad Request", JSON.stringify({ detail: "CSV sem as colunas obrigatórias: tipo" })),
    );
    const user = userEvent.setup();
    render(<Import />);
    await user.selectOptions(await screen.findByLabelText("Conta"), brlAccount.id);
    await user.upload(screen.getByLabelText("Arquivo"), file);
    await user.click(screen.getByRole("button", { name: "Pré-visualizar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("CSV sem as colunas obrigatórias: tipo");
    expect(screen.queryByTestId("import-preview-table")).not.toBeInTheDocument();
  });

  it("trocar de conta descarta a preview: ela foi assinada para a conta anterior", async () => {
    const user = userEvent.setup();
    await goToPreview(user);

    await user.selectOptions(screen.getByLabelText("Conta"), usdAccount.id);

    expect(screen.queryByTestId("import-preview-table")).not.toBeInTheDocument();
  });

  it("depois de importar, o campo de arquivo volta vazio (o mesmo arquivo pode ser escolhido de novo)", async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.commitImport).mockResolvedValue({ imported_count: 2, excluded_count: 3 } as never);
    await goToPreview(user);
    expect((screen.getByLabelText("Arquivo") as HTMLInputElement).files).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Importar 2 selecionadas" }));

    await screen.findByTestId("import-result");
    expect((screen.getByLabelText("Arquivo") as HTMLInputElement).files).toHaveLength(0);
  });
});
