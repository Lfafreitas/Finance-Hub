import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/cashflow";
import type { CashflowEntryRead } from "../../api/cashflowTypes";
import * as client from "../../api/client";
import { ApiError } from "../../api/client";
import { allAccounts, brokerage, categories, makeEntry, makeRule, tags } from "../../test/cashFixtures";
import { CashEntries } from "./CashEntries";

vi.mock("../../api/cashflow");
vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getAccounts: vi.fn(),
}));

const market = makeEntry({ id: "e-market", description: "Mercado Exemplo", amount: "-100.0000" });
const salary = makeEntry({
  id: "e-salary",
  description: "Salário",
  amount: "3000.0000",
  nature: "INCOME",
  match_text: "salario",
  notes: "mês de agosto",
});
const byRule = makeEntry({
  id: "e-rule",
  description: "Padaria",
  amount: "-20.0000",
  nature: "EXPENSE",
  category_id: "cat-market",
  classified_by_rule_id: "rule-1",
  tag_ids: ["tag-work"],
});
const transferOut = makeEntry({
  id: "e-out",
  description: "Pagamento de fatura",
  amount: "-500.0000",
  nature: "TRANSFER",
  counterparty_account_id: "acc-card",
  transfer_group_id: "g-1",
});
const reversed = makeEntry({ id: "e-rev", description: "Lançado errado", status: "REVERSED" });

function mockList(entries: CashflowEntryRead[], total = entries.length) {
  vi.mocked(api.getCashEntries).mockResolvedValue(entries);
  vi.mocked(api.countCashEntries).mockResolvedValue({ total });
}

const row = (id: string) => screen.getByTestId(`entry-${id}`);

describe("CashEntries — lista", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(client.getAccounts).mockResolvedValue(allAccounts);
    vi.mocked(api.getCategories).mockResolvedValue(categories);
    vi.mocked(api.getTags).mockResolvedValue(tags);
    vi.mocked(api.getRules).mockResolvedValue([makeRule()]);
    mockList([market, salary, byRule, transferOut]);
  });

  it("sem conta de caixa, orienta a cadastrar e não oferece nada", async () => {
    vi.mocked(client.getAccounts).mockResolvedValue([brokerage]);

    render(<CashEntries />);

    expect(await screen.findByTestId("no-cash-accounts")).toHaveTextContent("Cadastros");
    expect(screen.queryByRole("button", { name: "Novo lançamento" })).not.toBeInTheDocument();
  });

  it("lista com conta, valor na moeda do lançamento e total", async () => {
    render(<CashEntries />);

    await screen.findByTestId("entries-table");
    expect(screen.getByTestId("entries-count")).toHaveTextContent("Mostrando 1–4 de 4");
    expect(row("e-market")).toHaveTextContent("10/08/2026");
    expect(row("e-market")).toHaveTextContent("Conta Corrente");
    expect(row("e-market").textContent?.replace(/ /g, " ")).toContain("-R$ 100,00");
    expect(row("e-salary").textContent?.replace(/ /g, " ")).toContain("R$ 3.000,00");
    expect(row("e-salary")).toHaveTextContent("mês de agosto");
    expect(api.getCashEntries).toHaveBeenCalledWith({}, 50, 0);
    expect(api.countCashEntries).toHaveBeenCalledWith({});
  });

  it("explica de onde veio a classificação: regra, manual ou nenhuma", async () => {
    render(<CashEntries />);

    await screen.findByTestId("entries-table");
    expect(row("e-rule")).toHaveTextContent("Gasto");
    expect(row("e-rule")).toHaveTextContent("Alimentação › Mercado");
    expect(row("e-rule")).toHaveTextContent("regra: Mercado do bairro");
    expect(row("e-rule")).toHaveTextContent("reembolsável");
    expect(row("e-salary")).toHaveTextContent("Renda");
    expect(row("e-salary")).toHaveTextContent("manual");
    expect(row("e-market")).toHaveTextContent("Não classificado");
    expect(row("e-market")).not.toHaveTextContent("manual");
    expect(row("e-market")).not.toHaveTextContent("regra:");
  });

  it("transferência mostra a outra conta e o sentido; não pode ser classificada", async () => {
    render(<CashEntries />);

    await screen.findByTestId("entries-table");
    const transfer = row("e-out");
    expect(transfer).toHaveTextContent("Transferência");
    expect(transfer).toHaveTextContent("→ Cartão");
    expect(within(transfer).queryByRole("button", { name: /^Classificar/ })).not.toBeInTheDocument();
    expect(within(transfer).queryByRole("button", { name: /como transferência$/ })).not.toBeInTheDocument();
    expect(within(transfer).getByRole("button", { name: /^Desfazer a transferência/ })).toBeInTheDocument();
  });

  it("excluído aparece marcado e só pode ser restaurado", async () => {
    mockList([reversed]);

    render(<CashEntries />);

    await screen.findByTestId("entries-table");
    expect(row("e-rev")).toHaveTextContent("Excluído");
    expect(within(row("e-rev")).getAllByRole("button").map((b) => b.textContent)).toEqual(["Restaurar"]);
  });

  it("sem resultado, diz isso em vez de uma tabela vazia", async () => {
    mockList([]);

    render(<CashEntries />);

    expect(await screen.findByTestId("entries-count")).toHaveTextContent("Nenhum lançamento com estes filtros.");
    expect(screen.queryByTestId("entries-table")).not.toBeInTheDocument();
  });

  it("erro ao listar aparece com o motivo do servidor", async () => {
    vi.mocked(api.getCashEntries).mockRejectedValue(new ApiError(400, "Bad Request", '{"detail":"início do período depois do fim"}'));

    render(<CashEntries />);

    expect(await screen.findByRole("alert")).toHaveTextContent("início do período depois do fim");
  });
});

describe("CashEntries — filtros e páginas", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(client.getAccounts).mockResolvedValue(allAccounts);
    vi.mocked(api.getCategories).mockResolvedValue(categories);
    vi.mocked(api.getTags).mockResolvedValue(tags);
    vi.mocked(api.getRules).mockResolvedValue([]);
    mockList([market]);
  });

  it("o filtro de conta só oferece contas de caixa", async () => {
    render(<CashEntries />);

    const select = await screen.findByLabelText("Conta");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent)).toEqual([
      "Todas",
      "Conta Corrente",
      "Cartão",
      "Reserva",
    ]);
  });

  it("os filtros só valem depois de Filtrar, e lista e contagem recebem os mesmos", async () => {
    const user = userEvent.setup();
    render(<CashEntries />);
    await screen.findByTestId("entries-table");
    vi.mocked(api.getCashEntries).mockClear();
    vi.mocked(api.countCashEntries).mockClear();

    await user.selectOptions(screen.getByLabelText("Conta"), "acc-card");
    await user.selectOptions(screen.getByLabelText("Natureza"), "EXPENSE");
    await user.selectOptions(screen.getByLabelText("Categoria"), "cat-food");
    await user.type(screen.getByLabelText("Texto na descrição"), " uber ");
    await user.click(screen.getByLabelText("Mostrar excluídos"));
    expect(api.getCashEntries).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    const filters = {
      account_id: "acc-card",
      nature: "EXPENSE",
      category_id: "cat-food",
      search: "uber",
      include_reversed: true,
    };
    await waitFor(() => expect(api.getCashEntries).toHaveBeenCalledWith(filters, 50, 0));
    expect(api.countCashEntries).toHaveBeenCalledWith(filters);
  });

  it('"Sem categoria" vira o filtro próprio, não um id', async () => {
    const user = userEvent.setup();
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    await user.selectOptions(screen.getByLabelText("Categoria"), "none");
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    await waitFor(() => expect(api.getCashEntries).toHaveBeenLastCalledWith({ uncategorized: true }, 50, 0));
  });

  it("abre já filtrada quando recebe filtros iniciais, e Limpar volta a tudo", async () => {
    const user = userEvent.setup();
    const initial = { start: "2026-08-01", end: "2026-08-31", nature: "UNCLASSIFIED" as const };
    render(<CashEntries initialFilters={initial} />);

    await screen.findByTestId("entries-table");
    expect(api.getCashEntries).toHaveBeenCalledWith(initial, 50, 0);
    expect(screen.getByLabelText("Natureza")).toHaveValue("UNCLASSIFIED");
    expect(screen.getByLabelText("De")).toHaveValue("2026-08-01");

    await user.click(screen.getByRole("button", { name: "Limpar filtros" }));

    await waitFor(() => expect(api.getCashEntries).toHaveBeenLastCalledWith({}, 50, 0));
    expect(screen.getByLabelText("Natureza")).toHaveValue("");
  });

  it("pagina de 50 em 50 e não deixa passar do fim", async () => {
    const user = userEvent.setup();
    mockList([market], 120);
    render(<CashEntries />);
    await screen.findByTestId("entries-table");
    expect(screen.getByRole("button", { name: "Anteriores" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Próximos" }));
    await waitFor(() => expect(api.getCashEntries).toHaveBeenLastCalledWith({}, 50, 50));
    await user.click(screen.getByRole("button", { name: "Próximos" }));
    await waitFor(() => expect(api.getCashEntries).toHaveBeenLastCalledWith({}, 50, 100));

    expect(screen.getByRole("button", { name: "Próximos" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Anteriores" }));
    await waitFor(() => expect(api.getCashEntries).toHaveBeenLastCalledWith({}, 50, 50));
  });

  it("até 50 lançamentos não há paginação; filtrar volta para a primeira página", async () => {
    const user = userEvent.setup();
    mockList([market], 50);
    const { unmount } = render(<CashEntries />);
    await screen.findByTestId("entries-table");
    expect(screen.queryByRole("button", { name: "Próximos" })).not.toBeInTheDocument();
    unmount();

    mockList([market], 51);
    render(<CashEntries />);
    await screen.findByTestId("entries-table");
    await user.click(screen.getByRole("button", { name: "Próximos" }));
    await waitFor(() => expect(api.getCashEntries).toHaveBeenLastCalledWith({}, 50, 50));
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    await waitFor(() => expect(api.getCashEntries).toHaveBeenLastCalledWith({}, 50, 0));
  });

  it("se a página atual esvazia, volta para a última que existe", async () => {
    const user = userEvent.setup();
    mockList([market], 51);
    render(<CashEntries />);
    await screen.findByTestId("entries-table");
    vi.mocked(api.getCashEntries).mockImplementation(async (_filters, _limit, offset) => (offset === 0 ? [market] : []));
    vi.mocked(api.countCashEntries).mockResolvedValue({ total: 50 });

    await user.click(screen.getByRole("button", { name: "Próximos" }));

    await waitFor(() => expect(api.getCashEntries).toHaveBeenLastCalledWith({}, 50, 0));
    expect(await screen.findByTestId("entries-count")).toHaveTextContent("Mostrando 1–1 de 50");
  });
});

describe("CashEntries — ações", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(client.getAccounts).mockResolvedValue(allAccounts);
    vi.mocked(api.getCategories).mockResolvedValue(categories);
    vi.mocked(api.getTags).mockResolvedValue(tags);
    vi.mocked(api.getRules).mockResolvedValue([]);
    mockList([market, transferOut]);
  });

  it("excluir pede confirmação e só então chama o backend; depois recarrega", async () => {
    const user = userEvent.setup();
    vi.mocked(api.reverseCashEntry).mockResolvedValue([{ ...market, status: "REVERSED" }]);
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    await user.click(screen.getByRole("button", { name: "Excluir Mercado Exemplo" }));
    expect(api.reverseCashEntry).not.toHaveBeenCalled();
    vi.mocked(api.getCashEntries).mockClear();
    await user.click(screen.getByRole("button", { name: "Confirmar exclusão" }));

    expect(await screen.findByTestId("entries-notice")).toHaveTextContent("Lançamento excluído. Ele fica em “Mostrar excluídos” e pode ser restaurado.");
    expect(api.reverseCashEntry).toHaveBeenCalledWith("e-market");
    expect(api.getCashEntries).toHaveBeenCalledTimes(1);
  });

  it("cancelar a confirmação não exclui nada", async () => {
    const user = userEvent.setup();
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    await user.click(screen.getByRole("button", { name: "Excluir Mercado Exemplo" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(api.reverseCashEntry).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Excluir Mercado Exemplo" })).toBeInTheDocument();
  });

  it("excluir transferência avisa que as pontas vão juntas", async () => {
    const user = userEvent.setup();
    vi.mocked(api.reverseCashEntry).mockResolvedValue([transferOut, { ...transferOut, id: "e-in" }]);
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    await user.click(screen.getByRole("button", { name: "Excluir Pagamento de fatura" }));
    await user.click(screen.getByRole("button", { name: "Confirmar: excluir as duas pontas" }));

    expect(await screen.findByTestId("entries-notice")).toHaveTextContent("2 lançamentos excluídos");
  });

  it("recusa do backend na exclusão aparece na linha e nada é recarregado", async () => {
    const user = userEvent.setup();
    vi.mocked(api.reverseCashEntry).mockRejectedValue(new ApiError(409, "Conflict", '{"detail":"lançamento já está estornado"}'));
    render(<CashEntries />);
    await screen.findByTestId("entries-table");
    vi.mocked(api.getCashEntries).mockClear();

    await user.click(screen.getByRole("button", { name: "Excluir Mercado Exemplo" }));
    await user.click(screen.getByRole("button", { name: "Confirmar exclusão" }));

    expect(await within(row("e-market")).findByRole("alert")).toHaveTextContent("lançamento já está estornado");
    expect(api.getCashEntries).not.toHaveBeenCalled();
    expect(screen.queryByTestId("entries-notice")).not.toBeInTheDocument();
  });

  it("desfazer transferência pede confirmação e chama a rota certa", async () => {
    const user = userEvent.setup();
    vi.mocked(api.unlinkCashTransfer).mockResolvedValue({ entries: [] });
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    await user.click(screen.getByRole("button", { name: "Desfazer a transferência de Pagamento de fatura" }));
    expect(api.unlinkCashTransfer).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirmar: volta a não classificado" }));

    expect(await screen.findByTestId("entries-notice")).toHaveTextContent("Transferência desfeita");
    expect(api.unlinkCashTransfer).toHaveBeenCalledWith("e-out");
    expect(api.reverseCashEntry).not.toHaveBeenCalled();
  });

  it("abre um editor por vez e fecha ao clicar de novo", async () => {
    const user = userEvent.setup();
    vi.mocked(api.getCashEntries).mockResolvedValue([market, { ...market, id: "e-2", description: "Farmácia" }]);
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    await user.click(screen.getByRole("button", { name: "Classificar Mercado Exemplo" }));
    expect(screen.getByTestId("editor-e-market")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Classificar Farmácia" }));
    expect(screen.queryByTestId("editor-e-market")).not.toBeInTheDocument();
    expect(screen.getByTestId("editor-e-2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Classificar Farmácia" }));
    expect(screen.queryByTestId("editor-e-2")).not.toBeInTheDocument();
  });

  it("classificar pela lista grava, recarrega e avisa", async () => {
    const user = userEvent.setup();
    vi.mocked(api.classifyCashEntry).mockResolvedValue({ ...market, nature: "EXPENSE" });
    render(<CashEntries />);
    await screen.findByTestId("entries-table");
    vi.mocked(api.getCashEntries).mockClear();
    vi.mocked(api.getRules).mockClear();

    await user.click(screen.getByRole("button", { name: "Classificar Mercado Exemplo" }));
    await user.click(screen.getByRole("button", { name: "Salvar classificação" }));

    expect(await screen.findByTestId("entries-notice")).toHaveTextContent("Lançamento classificado.");
    expect(screen.queryByTestId("editor-e-market")).not.toBeInTheDocument();
    expect(api.getCashEntries).toHaveBeenCalledTimes(1);
    expect(api.getRules).not.toHaveBeenCalled();
  });

  it("classificar criando regra recarrega também as regras", async () => {
    const user = userEvent.setup();
    vi.mocked(api.classifyCashEntry).mockResolvedValue({ ...market, nature: "EXPENSE" });
    vi.mocked(api.createRule).mockResolvedValue(makeRule());
    render(<CashEntries />);
    await screen.findByTestId("entries-table");
    vi.mocked(api.getRules).mockClear();

    await user.click(screen.getByRole("button", { name: "Classificar Mercado Exemplo" }));
    await user.click(screen.getByLabelText("Criar regra para os próximos lançamentos com este texto"));
    await user.click(screen.getByRole("button", { name: "Salvar classificação" }));

    expect(await screen.findByTestId("entries-notice")).toHaveTextContent("Lançamento classificado e regra criada.");
    expect(api.getRules).toHaveBeenCalledTimes(1);
  });

  it("o formulário de novo lançamento abre e fecha, e gravar recarrega a lista", async () => {
    const user = userEvent.setup();
    vi.mocked(api.createCashEntry).mockResolvedValue(market);
    render(<CashEntries />);
    await screen.findByTestId("entries-table");
    expect(screen.queryByRole("form", { name: "Novo lançamento de caixa" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Novo lançamento" }));
    const form = screen.getByRole("form", { name: "Novo lançamento de caixa" });
    await user.selectOptions(within(form).getByLabelText("Conta"), "acc-checking");
    await user.type(within(form).getByLabelText("Valor"), "10");
    await user.type(within(form).getByLabelText("Descrição"), "Café");
    vi.mocked(api.getCashEntries).mockClear();
    await user.click(within(form).getByRole("button", { name: "Registrar lançamento" }));

    await waitFor(() => expect(api.getCashEntries).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "Fechar formulário" }));
    expect(screen.queryByRole("form", { name: "Novo lançamento de caixa" })).not.toBeInTheDocument();
  });
});

describe("CashEntries — restaurar e editar", () => {
  const manual = makeEntry({
    id: "e-manual",
    description: "Feira",
    amount: "-80.0000",
    source: "MANUAL",
    nature: "EXPENSE",
    notes: "sábado",
  });

  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(client.getAccounts).mockResolvedValue(allAccounts);
    vi.mocked(api.getCategories).mockResolvedValue(categories);
    vi.mocked(api.getTags).mockResolvedValue(tags);
    vi.mocked(api.getRules).mockResolvedValue([]);
    mockList([manual, market, transferOut, reversed]);
  });

  it("restaurar pede confirmação, chama o backend e recarrega", async () => {
    const user = userEvent.setup();
    vi.mocked(api.restoreCashEntry).mockResolvedValue([{ ...reversed, status: "ACTIVE" }]);
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    await user.click(screen.getByRole("button", { name: "Restaurar Lançado errado" }));
    expect(api.restoreCashEntry).not.toHaveBeenCalled();
    vi.mocked(api.getCashEntries).mockClear();
    await user.click(screen.getByRole("button", { name: "Confirmar: volta a valer" }));

    expect(await screen.findByTestId("entries-notice")).toHaveTextContent("Lançamento restaurado.");
    expect(api.restoreCashEntry).toHaveBeenCalledWith("e-rev");
    expect(api.getCashEntries).toHaveBeenCalledTimes(1);
  });

  it("restaurar transferência avisa que as pontas voltam juntas", async () => {
    const user = userEvent.setup();
    const reversedTransfer = { ...transferOut, id: "e-out-rev", status: "REVERSED" as const };
    mockList([reversedTransfer]);
    vi.mocked(api.restoreCashEntry).mockResolvedValue([transferOut, { ...transferOut, id: "e-in" }]);
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    await user.click(screen.getByRole("button", { name: "Restaurar Pagamento de fatura" }));
    await user.click(screen.getByRole("button", { name: "Confirmar: volta com as duas pontas" }));

    expect(await screen.findByTestId("entries-notice")).toHaveTextContent("2 lançamentos restaurados");
  });

  it("recusa do backend ao restaurar aparece na linha", async () => {
    const user = userEvent.setup();
    vi.mocked(api.restoreCashEntry).mockRejectedValue(
      new ApiError(409, "Conflict", '{"detail":"este lançamento foi editado: a versão nova é a que vale."}'),
    );
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    await user.click(screen.getByRole("button", { name: "Restaurar Lançado errado" }));
    await user.click(screen.getByRole("button", { name: "Confirmar: volta a valer" }));

    expect(await within(row("e-rev")).findByRole("alert")).toHaveTextContent("foi editado");
  });

  it("só lançamento manual que não é transferência pode ser editado", async () => {
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    expect(within(row("e-manual")).getByRole("button", { name: "Editar Feira" })).toBeInTheDocument();
    expect(within(row("e-market")).queryByRole("button", { name: /^Editar/ })).not.toBeInTheDocument();
    expect(within(row("e-out")).queryByRole("button", { name: /^Editar/ })).not.toBeInTheDocument();
    expect(within(row("e-rev")).queryByRole("button", { name: /^Editar/ })).not.toBeInTheDocument();
  });

  it("transferência lançada à mão também não é editada", async () => {
    mockList([{ ...transferOut, id: "e-manual-transfer", source: "MANUAL" }]);
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    expect(within(row("e-manual-transfer")).queryByRole("button", { name: /^Editar/ })).not.toBeInTheDocument();
    expect(within(row("e-manual-transfer")).getByRole("button", { name: /^Excluir/ })).toBeInTheDocument();
  });

  it("editar abre preenchido e envia os valores novos com o sinal do sentido", async () => {
    const user = userEvent.setup();
    vi.mocked(api.correctCashEntry).mockResolvedValue({ ...manual, id: "e-new" });
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    await user.click(screen.getByRole("button", { name: "Editar Feira" }));
    const form = screen.getByRole("form", { name: "Editar Feira" });
    expect(within(form).getByLabelText("Valor")).toHaveValue("80,00");
    expect(within(form).getByLabelText("Sentido")).toHaveValue("out");
    expect(within(form).getByLabelText("Data")).toHaveValue("2026-08-10");
    expect(within(form).getByLabelText("Notas")).toHaveValue("sábado");

    await user.clear(within(form).getByLabelText("Valor"));
    await user.type(within(form).getByLabelText("Valor"), "1.234,5");
    await user.clear(within(form).getByLabelText("Descrição"));
    await user.type(within(form).getByLabelText("Descrição"), "Feira do mês");
    await user.clear(within(form).getByLabelText("Notas"));
    vi.mocked(api.getCashEntries).mockClear();
    await user.click(within(form).getByRole("button", { name: "Salvar edição" }));

    expect(api.correctCashEntry).toHaveBeenCalledWith("e-manual", {
      entry_date: "2026-08-10",
      amount: "-1234.5",
      description: "Feira do mês",
      notes: null,
    });
    expect(await screen.findByTestId("entries-notice")).toHaveTextContent("Lançamento editado.");
    expect(api.getCashEntries).toHaveBeenCalledTimes(1);
  });

  it("entrada vai positiva; valor inválido não deixa salvar", async () => {
    const user = userEvent.setup();
    vi.mocked(api.correctCashEntry).mockResolvedValue(manual);
    render(<CashEntries />);
    await screen.findByTestId("entries-table");

    await user.click(screen.getByRole("button", { name: "Editar Feira" }));
    const form = screen.getByRole("form", { name: "Editar Feira" });
    await user.clear(within(form).getByLabelText("Valor"));
    await user.type(within(form).getByLabelText("Valor"), "abc");
    expect(within(form).getByRole("button", { name: "Salvar edição" })).toBeDisabled();

    await user.clear(within(form).getByLabelText("Valor"));
    await user.type(within(form).getByLabelText("Valor"), "10");
    await user.selectOptions(within(form).getByLabelText("Sentido"), "in");
    await user.click(within(form).getByRole("button", { name: "Salvar edição" }));

    expect(api.correctCashEntry).toHaveBeenCalledWith("e-manual", expect.objectContaining({ amount: "10" }));
  });

  it("recusa do backend na edição aparece no formulário e nada é recarregado", async () => {
    const user = userEvent.setup();
    vi.mocked(api.correctCashEntry).mockRejectedValue(
      new ApiError(400, "Bad Request", '{"detail":"a data do lançamento não pode estar no futuro"}'),
    );
    render(<CashEntries />);
    await screen.findByTestId("entries-table");
    vi.mocked(api.getCashEntries).mockClear();

    await user.click(screen.getByRole("button", { name: "Editar Feira" }));
    await user.click(screen.getByRole("button", { name: "Salvar edição" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("não pode estar no futuro");
    expect(api.getCashEntries).not.toHaveBeenCalled();
    expect(screen.getByRole("form", { name: "Editar Feira" })).toBeInTheDocument();
  });
});
