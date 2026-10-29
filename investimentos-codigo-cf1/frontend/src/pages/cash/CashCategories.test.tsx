import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/cashflow";
import { ApiError } from "../../api/client";
import { categories, food, market, tags, tripTag } from "../../test/cashFixtures";
import { CashCategories } from "./CashCategories";

vi.mock("../../api/cashflow");

const categoryForm = () => screen.getByRole("form", { name: "Categoria" });
const tagForm = () => screen.getByRole("form", { name: "Tag" });

describe("CashCategories — categorias", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.getCategories).mockResolvedValue(categories);
    vi.mocked(api.getTags).mockResolvedValue(tags);
  });

  it("lista em árvore: mãe seguida das filhas", async () => {
    render(<CashCategories />);

    const list = await screen.findByTestId("category-list");
    expect(Array.from(list.querySelectorAll("li > span:first-child")).map((s) => s.textContent)).toEqual([
      "Alimentação",
      "Mercado",
      "Moradia",
    ]);
  });

  it("sem categorias, diz isso", async () => {
    vi.mocked(api.getCategories).mockResolvedValue([]);

    render(<CashCategories />);

    expect(await screen.findByText("Nenhuma categoria cadastrada.")).toBeInTheDocument();
  });

  it("cria categoria principal e subcategoria; só mães podem ser escolhidas como pai", async () => {
    const user = userEvent.setup();
    vi.mocked(api.createCategory).mockResolvedValue(food);
    render(<CashCategories />);
    await screen.findByTestId("category-list");
    const parent = screen.getByLabelText("Dentro de");
    expect(Array.from(parent.querySelectorAll("option")).map((o) => o.textContent)).toEqual([
      "Nenhuma (categoria principal)",
      "Alimentação",
      "Moradia",
    ]);

    await user.type(screen.getByLabelText("Nome"), "  Lazer ");
    await user.click(screen.getByRole("button", { name: "Adicionar categoria" }));
    await within(categoryForm()).findByText("Categoria criada.");
    expect(api.createCategory).toHaveBeenLastCalledWith({ name: "Lazer", parent_id: null });
    expect(screen.getByLabelText("Nome")).toHaveValue("");

    await user.type(screen.getByLabelText("Nome"), "Padaria");
    await user.selectOptions(parent, "cat-food");
    await user.click(screen.getByRole("button", { name: "Adicionar categoria" }));
    await waitFor(() => expect(api.createCategory).toHaveBeenLastCalledWith({ name: "Padaria", parent_id: "cat-food" }));
    expect(api.getCategories).toHaveBeenCalledTimes(3);
  });

  it("nome em branco não pode ser enviado", async () => {
    const user = userEvent.setup();
    render(<CashCategories />);
    await screen.findByTestId("category-list");

    await user.type(screen.getByLabelText("Nome"), "   ");

    expect(screen.getByRole("button", { name: "Adicionar categoria" })).toBeDisabled();
  });

  it("editar preenche o formulário, salva por PUT e a categoria não pode ser pai de si mesma", async () => {
    const user = userEvent.setup();
    vi.mocked(api.updateCategory).mockResolvedValue(market);
    render(<CashCategories />);
    await screen.findByTestId("category-list");

    await user.click(screen.getByRole("button", { name: "Editar categoria Alimentação › Mercado" }));
    expect(screen.getByTestId("category-editing")).toHaveTextContent("Editando: Mercado");
    expect(screen.getByLabelText("Nome")).toHaveValue("Mercado");
    expect(screen.getByLabelText("Dentro de")).toHaveValue("cat-food");
    await user.clear(screen.getByLabelText("Nome"));
    await user.type(screen.getByLabelText("Nome"), "Supermercado");
    await user.selectOptions(screen.getByLabelText("Dentro de"), "cat-home");
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await within(categoryForm()).findByText("Categoria alterada.");
    expect(api.updateCategory).toHaveBeenCalledWith("cat-market", { name: "Supermercado", parent_id: "cat-home" });
    expect(api.createCategory).not.toHaveBeenCalled();
    expect(screen.queryByTestId("category-editing")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Editar categoria Alimentação" }));
    const parents = Array.from(screen.getByLabelText("Dentro de").querySelectorAll("option")).map((o) => o.textContent);
    expect(parents).toEqual(["Nenhuma (categoria principal)", "Moradia"]);
    await user.click(screen.getByRole("button", { name: "Cancelar edição" }));
    expect(screen.getByLabelText("Nome")).toHaveValue("");
  });

  it("recusa do backend ao salvar aparece e o formulário fica como estava", async () => {
    const user = userEvent.setup();
    vi.mocked(api.createCategory).mockRejectedValue(new ApiError(409, "Conflict", '{"detail":"já existe uma categoria com este nome"}'));
    render(<CashCategories />);
    await screen.findByTestId("category-list");

    await user.type(screen.getByLabelText("Nome"), "Moradia");
    await user.click(screen.getByRole("button", { name: "Adicionar categoria" }));

    expect(await within(categoryForm()).findByRole("alert")).toHaveTextContent("já existe uma categoria com este nome");
    expect(screen.getByLabelText("Nome")).toHaveValue("Moradia");
  });

  it("excluir pede confirmação; categoria em uso mostra o motivo na linha", async () => {
    const user = userEvent.setup();
    vi.mocked(api.deleteCategory).mockRejectedValue(new ApiError(409, "Conflict", '{"detail":"categoria em uso por 3 lançamentos"}'));
    render(<CashCategories />);
    const list = await screen.findByTestId("category-list");

    await user.click(screen.getByRole("button", { name: "Excluir categoria Moradia" }));
    expect(api.deleteCategory).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirmar exclusão" }));

    expect(await within(list).findByRole("alert")).toHaveTextContent("categoria em uso por 3 lançamentos");
    expect(api.deleteCategory).toHaveBeenCalledWith("cat-home");
  });

  it("exclusão aceita recarrega a lista", async () => {
    const user = userEvent.setup();
    vi.mocked(api.deleteCategory).mockResolvedValue(undefined);
    render(<CashCategories />);
    await screen.findByTestId("category-list");
    vi.mocked(api.getCategories).mockResolvedValue([food, market]);

    await user.click(screen.getByRole("button", { name: "Excluir categoria Moradia" }));
    await user.click(screen.getByRole("button", { name: "Confirmar exclusão" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "Excluir categoria Moradia" })).not.toBeInTheDocument());
  });

  it("categorias sugeridas são pedidas ao backend e a lista é recarregada", async () => {
    const user = userEvent.setup();
    vi.mocked(api.createDefaultCategories).mockResolvedValue(categories);
    render(<CashCategories />);
    await screen.findByTestId("category-list");

    await user.click(screen.getByRole("button", { name: "Criar categorias sugeridas" }));

    await within(categoryForm()).findByText(/As que já existiam foram mantidas/);
    expect(api.createDefaultCategories).toHaveBeenCalledTimes(1);
    expect(api.getCategories).toHaveBeenCalledTimes(2);
  });

  it("falha ao carregar aparece como erro", async () => {
    vi.mocked(api.getCategories).mockRejectedValue(new Error("rede"));

    render(<CashCategories />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar as categorias");
  });
});

describe("CashCategories — tags", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.getCategories).mockResolvedValue(categories);
    vi.mocked(api.getTags).mockResolvedValue(tags);
  });

  it("lista com o grupo na frente quando existe", async () => {
    render(<CashCategories />);

    const list = await screen.findByTestId("tag-list");
    expect(Array.from(list.querySelectorAll("li > span:first-child")).map((s) => s.textContent)).toEqual([
      "viagem: praia",
      "reembolsável",
    ]);
  });

  it("cria com nome e grupo", async () => {
    const user = userEvent.setup();
    vi.mocked(api.createTag).mockResolvedValue(tripTag);
    render(<CashCategories />);
    await screen.findByTestId("tag-list");

    await user.type(screen.getByLabelText("Nome da tag"), " serra ");
    await user.type(screen.getByLabelText("Grupo (opcional)"), " viagem ");
    await user.click(screen.getByRole("button", { name: "Adicionar tag" }));

    await waitFor(() => expect(api.createTag).toHaveBeenCalledWith({ name: "serra", tag_group: "viagem" }));
    await waitFor(() => expect(screen.getByLabelText("Nome da tag")).toHaveValue(""));
    expect(api.getTags).toHaveBeenCalledTimes(2);
  });

  it("edita por PUT e exclui com confirmação", async () => {
    const user = userEvent.setup();
    vi.mocked(api.updateTag).mockResolvedValue(tripTag);
    vi.mocked(api.deleteTag).mockResolvedValue(undefined);
    render(<CashCategories />);
    await screen.findByTestId("tag-list");

    await user.click(screen.getByRole("button", { name: "Editar tag viagem: praia" }));
    expect(screen.getByTestId("tag-editing")).toHaveTextContent("Editando: praia");
    expect(screen.getByLabelText("Grupo (opcional)")).toHaveValue("viagem");
    await user.clear(screen.getByLabelText("Grupo (opcional)"));
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => expect(api.updateTag).toHaveBeenCalledWith("tag-trip", { name: "praia", tag_group: "" }));
    expect(api.createTag).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Excluir tag reembolsável" }));
    expect(api.deleteTag).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirmar exclusão" }));
    await waitFor(() => expect(api.deleteTag).toHaveBeenCalledWith("tag-work"));
  });

  it("tag repetida: o motivo do backend aparece no formulário", async () => {
    const user = userEvent.setup();
    vi.mocked(api.createTag).mockRejectedValue(new ApiError(409, "Conflict", '{"detail":"tag já existe neste grupo"}'));
    render(<CashCategories />);
    await screen.findByTestId("tag-list");

    await user.type(screen.getByLabelText("Nome da tag"), "praia");
    await user.click(screen.getByRole("button", { name: "Adicionar tag" }));

    expect(await within(tagForm()).findByRole("alert")).toHaveTextContent("tag já existe neste grupo");
  });
});
