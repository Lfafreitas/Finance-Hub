import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as cashApi from "../../api/cashflow";
import { ApiError } from "../../api/client";
import type { PendingGroup } from "../../api/review";
import * as api from "../../api/review";
import { categories } from "../../test/cashFixtures";
import { CashReview } from "./CashReview";

vi.mock("../../api/review");
vi.mock("../../api/cashflow");

const uber: PendingGroup = {
  match_text: "transferencia enviada pelo pix uber",
  currency_code: "BRL",
  sample_description: "Transferência enviada pelo Pix - Uber - 17.895.646/0001-87",
  count: 14,
  total: "-210.3000",
  inflows: 0,
  outflows: 14,
  first_date: "2025-01-20",
  last_date: "2026-09-03",
  entry_ids: ["u1", "u2"],
  preview: [{ id: "u1", account_id: "acc-checking", entry_date: "2026-09-03", amount: "-12.4500", description: "Pix Uber" }],
  suggestion: { nature: "EXPENSE", category_id: "cat-market", evidence: 3, share: "1.0000" },
};
const salary: PendingGroup = {
  ...uber,
  match_text: "transferencia recebida pelo pix empresa",
  sample_description: "Transferência recebida pelo Pix - EMPRESA",
  count: 1,
  total: "5000.0000",
  inflows: 1,
  outflows: 0,
  first_date: "2026-09-05",
  last_date: "2026-09-05",
  entry_ids: ["s1"],
  preview: [],
  suggestion: null,
};

const card = (group: PendingGroup) => screen.getByTestId(`group-${group.match_text}-BRL`);

describe("CashReview", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.getPendingGroups).mockResolvedValue({ pending_entries: 15, pending_groups: 2, groups: [uber, salary] });
    vi.mocked(cashApi.getCategories).mockResolvedValue(categories);
    vi.mocked(api.classifyBatch).mockResolvedValue({ classified: 14 });
    vi.mocked(cashApi.createRule).mockResolvedValue({} as never);
  });

  it("mostra quanto falta e cada grupo com quantidade, período e total", async () => {
    render(<CashReview />);

    expect(await screen.findByTestId("review-header")).toHaveTextContent("Faltam 15 lançamentos em 2 grupos.");
    expect(card(uber)).toHaveTextContent("14 lançamentos · jan/2025 – set/2026");
    expect(screen.getByTestId(`group-${uber.match_text}-BRL-total`).textContent?.replace(/ /g, " ")).toBe("-R$ 210,30");
    expect(screen.getByTestId(`group-${salary.match_text}-BRL-total`)).toHaveClass("text-emerald-400");
    expect(card(salary)).toHaveTextContent("1 lançamento · set/2026");
  });

  it("a sugestão diz de onde vem e um clique classifica o grupo e cria a regra", async () => {
    const user = userEvent.setup();
    render(<CashReview />);
    await screen.findByTestId("review-header");

    const suggestion = screen.getByTestId(`group-${uber.match_text}-BRL-suggestion`);
    expect(suggestion).toHaveTextContent("Você já classificou assim 3 vezes:");
    expect(suggestion).toHaveTextContent("Gasto · Alimentação › Mercado");
    vi.mocked(api.getPendingGroups).mockClear();
    await user.click(within(suggestion).getByRole("button", { name: "Usar a sugestão" }));

    expect(api.classifyBatch).toHaveBeenCalledWith({
      entry_ids: ["u1", "u2"],
      nature: "EXPENSE",
      category_id: "cat-market",
      tag_ids: [],
    });
    expect(cashApi.createRule).toHaveBeenCalledWith(
      expect.objectContaining({
        pattern: "transferencia enviada pelo pix uber",
        direction: "OUT",
        set_nature: "EXPENSE",
        set_category_id: "cat-market",
      }),
    );
    expect(await screen.findByTestId("review-notice")).toHaveTextContent(
      "14 lançamentos classificados e regra criada para os próximos.",
    );
    expect(api.getPendingGroups).toHaveBeenCalledTimes(1);
  });

  it("sem sugestão: escolhe natureza e categoria; sem regra se desmarcar", async () => {
    const user = userEvent.setup();
    render(<CashReview />);
    await screen.findByTestId("review-header");
    const box = card(salary);
    expect(within(box).queryByRole("button", { name: "Usar a sugestão" })).not.toBeInTheDocument();
    // Entradas puxam "Renda" como ponto de partida.
    expect(within(box).getByLabelText(/^Natureza/)).toHaveValue("INCOME");

    await user.selectOptions(within(box).getByLabelText(/^Natureza/), "THIRD_PARTY");
    await user.click(within(box).getByLabelText("Criar regra para os próximos"));
    await user.click(within(box).getByRole("button", { name: "Classificar" }));

    expect(api.classifyBatch).toHaveBeenCalledWith({ entry_ids: ["s1"], nature: "THIRD_PARTY", category_id: null, tag_ids: [] });
    expect(cashApi.createRule).not.toHaveBeenCalled();
    expect(await screen.findByTestId("review-notice")).toHaveTextContent("1 lançamento classificado.");
  });

  it("recusa no lote aparece no grupo e nada mais acontece", async () => {
    const user = userEvent.setup();
    vi.mocked(api.classifyBatch).mockRejectedValue(new ApiError(400, "Bad", '{"detail":"lançamento x está estornado"}'));
    render(<CashReview />);
    await screen.findByTestId("review-header");

    await user.click(within(card(uber)).getByRole("button", { name: "Classificar os 14" }));

    expect(await within(card(uber)).findByRole("alert")).toHaveTextContent("está estornado");
    expect(cashApi.createRule).not.toHaveBeenCalled();
    expect(screen.queryByTestId("review-notice")).not.toBeInTheDocument();
  });

  it("se a regra falhar, os lançamentos ficam classificados e o aviso explica", async () => {
    const user = userEvent.setup();
    vi.mocked(cashApi.createRule).mockRejectedValue(new ApiError(409, "Conflict", '{"detail":"regra repetida"}'));
    render(<CashReview />);
    await screen.findByTestId("review-header");

    await user.click(within(card(uber)).getByRole("button", { name: "Classificar os 14" }));

    expect(await screen.findByTestId("review-notice")).toHaveTextContent(
      "14 lançamentos classificados, mas a regra não foi criada: regra repetida",
    );
  });

  it("pagamento de fatura avisa que não é gasto", async () => {
    const invoice = { ...uber, match_text: "pagamento de fatura", sample_description: "Pagamento de fatura" };
    vi.mocked(api.getPendingGroups).mockResolvedValue({ pending_entries: 14, pending_groups: 1, groups: [invoice] });

    render(<CashReview />);

    expect(await screen.findByTestId("group-pagamento de fatura-BRL-invoice")).toHaveTextContent("não é gasto");
    expect(screen.queryByTestId(`group-${uber.match_text}-BRL-invoice`)).not.toBeInTheDocument();
  });

  it("ver lançamentos mostra os mais recentes e quantos faltam", async () => {
    const user = userEvent.setup();
    render(<CashReview />);
    await screen.findByTestId("review-header");

    await user.click(within(card(uber)).getByRole("button", { name: "Ver lançamentos" }));

    const preview = screen.getByTestId(`group-${uber.match_text}-BRL-preview`);
    expect(preview).toHaveTextContent("03/09/2026");
    expect(preview).toHaveTextContent("e mais 13…");
  });

  it("tudo classificado diz isso; sem categorias oferece as padrão", async () => {
    vi.mocked(api.getPendingGroups).mockResolvedValue({ pending_entries: 0, pending_groups: 0, groups: [] });
    const { unmount } = render(<CashReview />);
    expect(await screen.findByTestId("review-header")).toHaveTextContent("Tudo classificado.");
    unmount();

    const user = userEvent.setup();
    vi.mocked(api.getPendingGroups).mockResolvedValue({ pending_entries: 15, pending_groups: 2, groups: [uber, salary] });
    vi.mocked(cashApi.getCategories).mockResolvedValue([]);
    vi.mocked(cashApi.createDefaultCategories).mockResolvedValue(categories);
    render(<CashReview />);
    await user.click(await screen.findByRole("button", { name: "Criar as categorias padrão" }));

    expect(cashApi.createDefaultCategories).toHaveBeenCalled();
    expect((await screen.findAllByRole("option", { name: "Alimentação › Mercado" })).length).toBe(2);
  });

  it("erro ao carregar aparece com o motivo", async () => {
    vi.mocked(api.getPendingGroups).mockRejectedValue(new ApiError(500, "Erro", '{"detail":"banco fora"}'));

    render(<CashReview />);

    expect(await screen.findByRole("alert")).toHaveTextContent("banco fora");
  });
});
