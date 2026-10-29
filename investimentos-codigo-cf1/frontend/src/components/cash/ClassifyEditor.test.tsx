import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/cashflow";
import type { CashflowEntryRead } from "../../api/cashflowTypes";
import { ApiError } from "../../api/client";
import { categories, makeEntry, makeRule, tags } from "../../test/cashFixtures";
import { ClassifyEditor } from "./ClassifyEditor";

vi.mock("../../api/cashflow");

const RULE_BOX = "Criar regra para os próximos lançamentos com este texto";

function setup(entry: CashflowEntryRead = makeEntry()) {
  const onSaved = vi.fn();
  const onCancel = vi.fn();
  render(<ClassifyEditor entry={entry} categories={categories} tags={tags} onSaved={onSaved} onCancel={onCancel} />);
  return { onSaved, onCancel, user: userEvent.setup() };
}

describe("ClassifyEditor", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.classifyCashEntry).mockResolvedValue(makeEntry({ nature: "EXPENSE" }));
    vi.mocked(api.createRule).mockResolvedValue(makeRule());
  });

  it("não oferece Transferência como natureza", () => {
    setup();

    const options = Array.from(screen.getByLabelText("Natureza").querySelectorAll("option")).map((o) => o.textContent);
    expect(options).toEqual(["Gasto", "Renda", "Terceiros", "Ajuste", "Não classificado"]);
  });

  it("lançamento não classificado abre sugerindo Gasto; classificado abre com o que já tem", () => {
    const { unmount } = render(
      <ClassifyEditor entry={makeEntry()} categories={categories} tags={tags} onSaved={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByLabelText("Natureza")).toHaveValue("EXPENSE");
    expect(screen.getByLabelText("Categoria")).toHaveValue("");
    unmount();

    setup(makeEntry({ nature: "INCOME", category_id: "cat-home", tag_ids: ["tag-work"] }));
    expect(screen.getByLabelText("Natureza")).toHaveValue("INCOME");
    expect(screen.getByLabelText("Categoria")).toHaveValue("cat-home");
    expect(screen.getByLabelText("reembolsável")).toBeChecked();
    expect(screen.getByLabelText("viagem: praia")).not.toBeChecked();
  });

  it("grava natureza, categoria e tags de uma vez, sem criar regra", async () => {
    const { user, onSaved } = setup();

    await user.selectOptions(screen.getByLabelText("Natureza"), "THIRD_PARTY");
    await user.selectOptions(screen.getByLabelText("Categoria"), "cat-market");
    await user.click(screen.getByLabelText("viagem: praia"));
    await user.click(screen.getByRole("button", { name: "Salvar classificação" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(false));
    expect(api.classifyCashEntry).toHaveBeenCalledWith("e-1", {
      nature: "THIRD_PARTY",
      category_id: "cat-market",
      tag_ids: ["tag-trip"],
    });
    expect(api.createRule).not.toHaveBeenCalled();
  });

  it("sem categoria manda null, e desmarcar uma tag a tira", async () => {
    const { user, onSaved } = setup(makeEntry({ nature: "EXPENSE", category_id: "cat-home", tag_ids: ["tag-work"] }));

    await user.selectOptions(screen.getByLabelText("Categoria"), "");
    await user.click(screen.getByLabelText("reembolsável"));
    await user.click(screen.getByRole("button", { name: "Salvar classificação" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(api.classifyCashEntry).toHaveBeenCalledWith("e-1", { nature: "EXPENSE", category_id: null, tag_ids: [] });
  });

  it("com regra: usa o texto normalizado, o sentido do lançamento e o mesmo destino", async () => {
    const { user, onSaved } = setup(makeEntry({ amount: "-100.0000", match_text: "mercado exemplo" }));

    await user.selectOptions(screen.getByLabelText("Categoria"), "cat-market");
    await user.click(screen.getByLabelText("reembolsável"));
    await user.click(screen.getByLabelText(RULE_BOX));
    expect(screen.getByLabelText(/Texto que a regra procura \(só em saídas\)/)).toHaveValue("mercado exemplo");
    await user.click(screen.getByRole("button", { name: "Salvar classificação" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(true));
    expect(api.createRule).toHaveBeenCalledWith({
      name: "mercado exemplo",
      priority: 100,
      is_active: true,
      match_type: "CONTAINS",
      pattern: "mercado exemplo",
      direction: "OUT",
      account_id: null,
      set_nature: "EXPENSE",
      set_category_id: "cat-market",
      tag_ids: ["tag-work"],
    });
  });

  it("entrada gera regra só para entradas, e o texto pode ser encurtado", async () => {
    const { user, onSaved } = setup(makeEntry({ amount: "3000.0000", match_text: "salario empresa exemplo ltda" }));

    await user.selectOptions(screen.getByLabelText("Natureza"), "INCOME");
    await user.click(screen.getByLabelText(RULE_BOX));
    const pattern = screen.getByLabelText(/Texto que a regra procura \(só em entradas\)/);
    await user.clear(pattern);
    await user.type(pattern, "  salario empresa ");
    await user.click(screen.getByRole("button", { name: "Salvar classificação" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(true));
    expect(vi.mocked(api.createRule).mock.calls[0][0]).toMatchObject({
      name: "salario empresa",
      pattern: "salario empresa",
      direction: "IN",
      set_nature: "INCOME",
      set_category_id: null,
    });
  });

  it("não deixa criar regra sem natureza de verdade nem com texto vazio", async () => {
    const { user } = setup();

    await user.click(screen.getByLabelText(RULE_BOX));
    await user.clear(screen.getByLabelText(/Texto que a regra procura/));
    expect(screen.getByRole("button", { name: "Salvar classificação" })).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("Natureza"), "UNCLASSIFIED");
    expect(screen.getByLabelText(RULE_BOX)).toBeDisabled();
    expect(screen.getByLabelText(RULE_BOX)).not.toBeChecked();
    expect(screen.queryByLabelText(/Texto que a regra procura/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Salvar classificação" }));

    await waitFor(() => expect(api.classifyCashEntry).toHaveBeenCalled());
    expect(api.createRule).not.toHaveBeenCalled();
  });

  it("se a classificação é recusada, mostra o motivo e não tenta criar a regra", async () => {
    vi.mocked(api.classifyCashEntry).mockRejectedValue(new ApiError(409, "Conflict", '{"detail":"lançamento está estornado"}'));
    const { user, onSaved } = setup();

    await user.click(screen.getByLabelText(RULE_BOX));
    await user.click(screen.getByRole("button", { name: "Salvar classificação" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("lançamento está estornado");
    expect(api.createRule).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Salvar classificação" })).toBeEnabled();
  });

  it("se só a regra falha, diz que o lançamento JÁ foi classificado", async () => {
    vi.mocked(api.createRule).mockRejectedValue(new ApiError(400, "Bad Request", '{"detail":"padrão inválido"}'));
    const { user, onSaved } = setup();

    await user.click(screen.getByLabelText(RULE_BOX));
    await user.click(screen.getByRole("button", { name: "Salvar classificação" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "O lançamento foi classificado, mas a regra não foi criada: padrão inválido",
    );
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("Cancelar não grava nada", async () => {
    const { user, onCancel } = setup();

    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onCancel).toHaveBeenCalled();
    expect(api.classifyCashEntry).not.toHaveBeenCalled();
  });
});
