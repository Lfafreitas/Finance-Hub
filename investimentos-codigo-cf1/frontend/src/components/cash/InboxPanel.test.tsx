import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/cashflow";
import type { InboxFileResult } from "../../api/cashflowTypes";
import { ApiError } from "../../api/client";
import { describeInboxFile } from "../../lib/inbox";
import { InboxPanel } from "./InboxPanel";

vi.mock("../../api/cashflow");

const base: InboxFileResult = {
  file_name: "fatura.pdf",
  status: "IMPORTED",
  profile: "NUBANK_CARD_PDF",
  account_id: "acc-card",
  account_name: "Cartão Nubank",
  imported_count: 7,
  duplicate_count: 2,
  error_rows: 1,
  matched_transfers: 1,
  balance_difference: null,
  message: "Compras, estornos e créditos: confere",
  moved_to: "importados/2026-10-13/fatura.pdf",
};

describe("InboxPanel", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.getInbox).mockResolvedValue({
      inbox_dir: "C:\\Dashboard Financeiro\\Entrada",
      exists: true,
      files: ["extrato.ofx", "fatura.pdf"],
    });
  });

  it("mostra a pasta e o que está esperando", async () => {
    render(<InboxPanel onLoaded={() => {}} />);

    expect(await screen.findByTestId("inbox-count")).toHaveTextContent("2 arquivos esperando");
    expect(screen.getByText("C:\\Dashboard Financeiro\\Entrada")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-files")).toHaveTextContent("extrato.ofxfatura.pdf");
  });

  it("sem arquivo o botão fica desligado", async () => {
    vi.mocked(api.getInbox).mockResolvedValue({ inbox_dir: "/x", exists: true, files: [] });
    render(<InboxPanel onLoaded={() => {}} />);

    expect(await screen.findByText("nenhum arquivo esperando")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Carregar a pasta Entrada" })).toBeDisabled();
  });

  it("pasta que não existe é dita", async () => {
    vi.mocked(api.getInbox).mockResolvedValue({ inbox_dir: "/x", exists: false, files: [] });
    render(<InboxPanel onLoaded={() => {}} />);

    expect(await screen.findByText("a pasta ainda não existe")).toBeInTheDocument();
  });

  it("carrega, mostra cada arquivo e avisa a página", async () => {
    const onLoaded = vi.fn();
    vi.mocked(api.processInbox).mockResolvedValue({
      inbox_dir: "/x",
      files: [
        base,
        { ...base, file_name: "velho.ofx", status: "NOTHING_NEW", imported_count: 0, account_name: "Conta" },
        {
          ...base,
          file_name: "ruim.pdf",
          status: "REFUSED",
          account_name: null,
          message: "a fatura de 02/2026 não confere",
          moved_to: null,
        },
        { ...base, file_name: "sem.csv", status: "NO_ACCOUNT", message: "nenhuma conta", moved_to: null },
      ],
    });
    const user = userEvent.setup();
    render(<InboxPanel onLoaded={onLoaded} />);

    await user.click(await screen.findByRole("button", { name: "Carregar a pasta Entrada" }));

    expect(await screen.findByTestId("inbox-result-fatura.pdf")).toHaveTextContent(
      "✓ fatura.pdf — importadoCartão Nubank · 7 lançamentos novos · 2 já existiam · 1 linha com erro · 1 pagamento de fatura ligado",
    );
    expect(screen.getByTestId("inbox-result-velho.ofx")).toHaveTextContent("= velho.ofx — nada novoConta · tudo já estava no app");
    expect(screen.getByTestId("inbox-result-ruim.pdf")).toHaveTextContent(
      "✗ ruim.pdf — recusado — ficou na pastaa fatura de 02/2026 não confere",
    );
    expect(screen.getByTestId("inbox-result-sem.csv")).toHaveTextContent("! sem.csv — sem conta — ficou na pastanenhuma conta");
    expect(onLoaded).toHaveBeenCalledTimes(1);
    expect(api.getInbox).toHaveBeenCalledTimes(2);
  });

  it("erro do backend aparece e a página não é avisada", async () => {
    const onLoaded = vi.fn();
    vi.mocked(api.processInbox).mockRejectedValue(new ApiError(500, "Internal", "falhou"));
    const user = userEvent.setup();
    render(<InboxPanel onLoaded={onLoaded} />);

    await user.click(await screen.findByRole("button", { name: "Carregar a pasta Entrada" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(onLoaded).not.toHaveBeenCalled();
  });

  it("descrição curta de cada situação", () => {
    expect(describeInboxFile({ ...base, duplicate_count: 0, error_rows: 0, matched_transfers: 0, imported_count: 1 })).toBe(
      "Cartão Nubank · 1 lançamento novo",
    );
    expect(describeInboxFile({ ...base, status: "REFUSED", message: null })).toBe("");
  });
});
