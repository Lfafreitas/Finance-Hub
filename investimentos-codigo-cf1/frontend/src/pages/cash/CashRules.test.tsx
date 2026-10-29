import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/cashflow";
import type { RuleApplyResult } from "../../api/cashflowTypes";
import * as client from "../../api/client";
import { ApiError } from "../../api/client";
import { allAccounts, categories, makeRule, tags } from "../../test/cashFixtures";
import { CashRules } from "./CashRules";

vi.mock("../../api/cashflow");
vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getAccounts: vi.fn(),
}));

const marketRule = makeRule();
const rentRule = makeRule({
  id: "rule-2",
  name: "Aluguel",
  priority: 10,
  is_active: false,
  match_type: "STARTS_WITH",
  pattern: "imobiliaria",
  direction: "ANY",
  account_id: "acc-checking",
  set_category_id: "cat-home",
  tag_ids: ["tag-work"],
});

const previewResult: RuleApplyResult = {
  applied: false,
  examined: 9,
  changes: [
    {
      entry_id: "e-1",
      description: "Mercado Exemplo",
      match_text: "mercado exemplo",
      amount: "-100.0000",
      currency_code: "BRL",
      entry_date: "2026-08-10",
      rule_id: "rule-1",
      rule_name: "Mercado do bairro",
      nature: "EXPENSE",
      category_id: "cat-market",
      tag_ids: [],
    },
    {
      entry_id: "e-2",
      description: "Compra no exterior",
      match_text: "compra no exterior",
      amount: "-20.0000",
      currency_code: "USD",
      entry_date: "2026-08-11",
      rule_id: null,
      rule_name: null,
      nature: "UNCLASSIFIED",
      category_id: null,
      tag_ids: [],
    },
  ],
};

const form = () => screen.getByRole("form", { name: "Regra" });

async function fillBasics(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Nome da regra"), " Streaming ");
  await user.type(screen.getByLabelText("Texto"), " spotify ");
}

describe("CashRules — cadastro", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(client.getAccounts).mockResolvedValue(allAccounts);
    vi.mocked(api.getRules).mockResolvedValue([rentRule, marketRule]);
    vi.mocked(api.getCategories).mockResolvedValue(categories);
    vi.mocked(api.getTags).mockResolvedValue(tags);
    vi.mocked(api.createRule).mockResolvedValue(marketRule);
    vi.mocked(api.updateRule).mockResolvedValue(marketRule);
  });

  it("lista na ordem do backend, com a condição e o resultado por extenso", async () => {
    render(<CashRules />);

    await screen.findByTestId("rule-list");
    const market = screen.getByTestId("rule-rule-1");
    expect(market).toHaveTextContent('descrição contém "mercado exemplo" · só saídas');
    expect(market).toHaveTextContent("Gasto · Alimentação › Mercado");
    expect(market).not.toHaveTextContent("desativada");
    const rent = screen.getByTestId("rule-rule-2");
    expect(rent).toHaveTextContent('descrição começa com "imobiliaria" · conta Conta Corrente');
    expect(rent).toHaveTextContent("Gasto · Moradia · reembolsável");
    expect(rent).toHaveTextContent("desativada");
    const order = Array.from(screen.getByTestId("rule-list").querySelectorAll("tbody tr")).map((tr) => tr.getAttribute("data-testid"));
    expect(order).toEqual(["rule-rule-2", "rule-rule-1"]);
  });

  it("uma regra só pode decidir natureza de verdade, e só para conta de caixa", async () => {
    render(<CashRules />);

    await screen.findByTestId("rule-list");
    const options = (label: string) => Array.from(screen.getByLabelText(label).querySelectorAll("option")).map((o) => o.textContent);
    expect(options("Classificar como")).toEqual(["Gasto", "Renda", "Terceiros", "Ajuste"]);
    expect(options("Conta")).toEqual(["Qualquer conta", "Conta Corrente", "Cartão", "Reserva"]);
  });

  it("cria com os padrões: contém, qualquer sentido, qualquer conta, prioridade 100, ativa", async () => {
    const user = userEvent.setup();
    render(<CashRules />);
    await screen.findByTestId("rule-list");
    expect(screen.getByRole("button", { name: "Adicionar regra" })).toBeDisabled();

    await fillBasics(user);
    await user.click(screen.getByRole("button", { name: "Adicionar regra" }));

    await waitFor(() =>
      expect(api.createRule).toHaveBeenCalledWith({
        name: "Streaming",
        priority: 100,
        is_active: true,
        match_type: "CONTAINS",
        pattern: "spotify",
        direction: "ANY",
        account_id: null,
        set_nature: "EXPENSE",
        set_category_id: null,
        tag_ids: [],
      }),
    );
    await waitFor(() => expect(screen.getByLabelText("Nome da regra")).toHaveValue(""));
    expect(api.getRules).toHaveBeenCalledTimes(2);
  });

  it("envia tudo o que foi escolhido", async () => {
    const user = userEvent.setup();
    render(<CashRules />);
    await screen.findByTestId("rule-list");

    await fillBasics(user);
    await user.selectOptions(screen.getByLabelText("Quando a descrição"), "EQUALS");
    await user.selectOptions(screen.getByLabelText("Sentido"), "IN");
    await user.selectOptions(screen.getByLabelText("Conta"), "acc-card");
    await user.selectOptions(screen.getByLabelText("Classificar como"), "THIRD_PARTY");
    await user.selectOptions(screen.getByLabelText("Categoria"), "cat-home");
    await user.clear(screen.getByLabelText("Prioridade (menor decide primeiro)"));
    await user.type(screen.getByLabelText("Prioridade (menor decide primeiro)"), "5");
    await user.click(screen.getByLabelText("Regra ativa"));
    await user.click(within(form()).getByLabelText("viagem: praia"));
    await user.click(screen.getByRole("button", { name: "Adicionar regra" }));

    await waitFor(() =>
      expect(api.createRule).toHaveBeenCalledWith({
        name: "Streaming",
        priority: 5,
        is_active: false,
        match_type: "EQUALS",
        pattern: "spotify",
        direction: "IN",
        account_id: "acc-card",
        set_nature: "THIRD_PARTY",
        set_category_id: "cat-home",
        tag_ids: ["tag-trip"],
      }),
    );
  });

  it.each(["", "abc", "-1", "100001", "1.5"])("prioridade inválida %j bloqueia o envio", async (bad) => {
    const user = userEvent.setup();
    render(<CashRules />);
    await screen.findByTestId("rule-list");

    await fillBasics(user);
    const priority = screen.getByLabelText("Prioridade (menor decide primeiro)");
    await user.clear(priority);
    if (bad) await user.type(priority, bad);

    expect(screen.getByRole("button", { name: "Adicionar regra" })).toBeDisabled();
    expect(priority).toHaveAttribute("aria-invalid", "true");
  });

  it("editar carrega a regra inteira e salva por PUT", async () => {
    const user = userEvent.setup();
    render(<CashRules />);
    await screen.findByTestId("rule-list");

    await user.click(screen.getByRole("button", { name: "Editar regra Aluguel" }));
    expect(screen.getByTestId("rule-editing")).toHaveTextContent("Editando: Aluguel");
    expect(screen.getByLabelText("Texto")).toHaveValue("imobiliaria");
    expect(screen.getByLabelText("Quando a descrição")).toHaveValue("STARTS_WITH");
    expect(screen.getByLabelText("Conta")).toHaveValue("acc-checking");
    expect(screen.getByLabelText("Categoria")).toHaveValue("cat-home");
    expect(screen.getByLabelText("Prioridade (menor decide primeiro)")).toHaveValue("10");
    expect(screen.getByLabelText("Regra ativa")).not.toBeChecked();
    expect(within(form()).getByLabelText("reembolsável")).toBeChecked();
    await user.click(screen.getByLabelText("Regra ativa"));
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(api.updateRule).toHaveBeenCalledWith("rule-2", {
        name: "Aluguel",
        priority: 10,
        is_active: true,
        match_type: "STARTS_WITH",
        pattern: "imobiliaria",
        direction: "ANY",
        account_id: "acc-checking",
        set_nature: "EXPENSE",
        set_category_id: "cat-home",
        tag_ids: ["tag-work"],
      }),
    );
    expect(api.createRule).not.toHaveBeenCalled();
  });

  it("cancelar a edição limpa o formulário sem salvar", async () => {
    const user = userEvent.setup();
    render(<CashRules />);
    await screen.findByTestId("rule-list");

    await user.click(screen.getByRole("button", { name: "Editar regra Aluguel" }));
    await user.click(screen.getByRole("button", { name: "Cancelar edição" }));

    expect(screen.getByLabelText("Nome da regra")).toHaveValue("");
    expect(screen.getByLabelText("Prioridade (menor decide primeiro)")).toHaveValue("100");
    expect(api.updateRule).not.toHaveBeenCalled();
  });

  it("recusa do backend aparece no formulário", async () => {
    const user = userEvent.setup();
    vi.mocked(api.createRule).mockRejectedValue(new ApiError(404, "Not Found", '{"detail":"categoria não encontrada"}'));
    render(<CashRules />);
    await screen.findByTestId("rule-list");

    await fillBasics(user);
    await user.click(screen.getByRole("button", { name: "Adicionar regra" }));

    expect(await within(form()).findByRole("alert")).toHaveTextContent("categoria não encontrada");
    expect(screen.getByLabelText("Nome da regra")).toHaveValue(" Streaming ");
  });

  it("excluir pede confirmação e recarrega", async () => {
    const user = userEvent.setup();
    vi.mocked(api.deleteRule).mockResolvedValue(undefined);
    render(<CashRules />);
    await screen.findByTestId("rule-list");

    await user.click(screen.getByRole("button", { name: "Excluir regra Aluguel" }));
    expect(api.deleteRule).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirmar exclusão" }));

    await waitFor(() => expect(api.deleteRule).toHaveBeenCalledWith("rule-2"));
    await waitFor(() => expect(api.getRules).toHaveBeenCalledTimes(2));
  });

  it("sem regras, diz isso", async () => {
    vi.mocked(api.getRules).mockResolvedValue([]);

    render(<CashRules />);

    expect(await screen.findByText("Nenhuma regra cadastrada.")).toBeInTheDocument();
  });
});

describe("CashRules — aplicar", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(client.getAccounts).mockResolvedValue(allAccounts);
    vi.mocked(api.getRules).mockResolvedValue([marketRule]);
    vi.mocked(api.getCategories).mockResolvedValue(categories);
    vi.mocked(api.getTags).mockResolvedValue(tags);
    vi.mocked(api.previewRules).mockResolvedValue(previewResult);
    vi.mocked(api.applyRules).mockResolvedValue({ ...previewResult, applied: true });
    vi.mocked(api.createRule).mockResolvedValue(marketRule);
  });

  it("só dá para aplicar depois de ver a prévia", async () => {
    const user = userEvent.setup();
    render(<CashRules />);
    await screen.findByTestId("rule-list");
    expect(screen.queryByRole("button", { name: /^Aplicar a/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Ver o que mudaria" }));

    expect(await screen.findByTestId("preview-summary")).toHaveTextContent(
      "9 lançamentos avaliados · 2 mudariam. Nada foi gravado.",
    );
    expect(api.previewRules).toHaveBeenCalledWith({ reevaluate: false });
    expect(api.applyRules).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Aplicar a 2 lançamentos" })).toBeInTheDocument();
  });

  it("a prévia mostra cada mudança na moeda do lançamento", async () => {
    const user = userEvent.setup();
    render(<CashRules />);
    await screen.findByTestId("rule-list");

    await user.click(screen.getByRole("button", { name: "Ver o que mudaria" }));

    const rows = Array.from((await screen.findByTestId("preview-changes")).querySelectorAll("tbody tr"));
    const cells = (tr: Element) => Array.from(tr.querySelectorAll("td")).map((td) => td.textContent?.replace(/ /g, " "));
    expect(cells(rows[0])).toEqual(["10/08/2026", "Mercado Exemplo", "-R$ 100,00", "Mercado do bairro", "Gasto · Alimentação › Mercado"]);
    expect(cells(rows[1])).toEqual([
      "11/08/2026",
      "Compra no exterior",
      "-US$ 20,00",
      "nenhuma (volta a não classificado)",
      "Não classificado",
    ]);
  });

  it("aplicar usa a mesma opção da prévia e informa quantos mudaram", async () => {
    const user = userEvent.setup();
    render(<CashRules />);
    await screen.findByTestId("rule-list");

    await user.click(screen.getByLabelText("Reavaliar também o que uma regra já classificou"));
    await user.click(screen.getByRole("button", { name: "Ver o que mudaria" }));
    await user.click(await screen.findByRole("button", { name: "Aplicar a 2 lançamentos" }));

    expect(await screen.findByTestId("apply-notice")).toHaveTextContent("2 lançamentos classificados.");
    expect(api.previewRules).toHaveBeenCalledWith({ reevaluate: true });
    expect(api.applyRules).toHaveBeenCalledWith({ reevaluate: true });
    expect(screen.queryByTestId("preview-changes")).not.toBeInTheDocument();
  });

  it("prévia sem mudanças não oferece o botão de aplicar", async () => {
    const user = userEvent.setup();
    vi.mocked(api.previewRules).mockResolvedValue({ applied: false, examined: 1, changes: [] });
    render(<CashRules />);
    await screen.findByTestId("rule-list");

    await user.click(screen.getByRole("button", { name: "Ver o que mudaria" }));

    expect(await screen.findByTestId("preview-summary")).toHaveTextContent("1 lançamento avaliado · 0 mudariam");
    expect(screen.queryByRole("button", { name: /^Aplicar a/ })).not.toBeInTheDocument();
  });

  it("mudar a opção de reavaliar descarta a prévia", async () => {
    const user = userEvent.setup();
    render(<CashRules />);
    await screen.findByTestId("rule-list");
    await user.click(screen.getByRole("button", { name: "Ver o que mudaria" }));
    await screen.findByTestId("preview-changes");

    await user.click(screen.getByLabelText("Reavaliar também o que uma regra já classificou"));

    expect(screen.queryByTestId("preview-changes")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Aplicar a/ })).not.toBeInTheDocument();
  });

  it("criar ou mudar uma regra descarta a prévia que estava na tela", async () => {
    const user = userEvent.setup();
    render(<CashRules />);
    await screen.findByTestId("rule-list");
    await user.click(screen.getByRole("button", { name: "Ver o que mudaria" }));
    await screen.findByTestId("preview-changes");

    await fillBasics(user);
    await user.click(screen.getByRole("button", { name: "Adicionar regra" }));

    await waitFor(() => expect(screen.queryByTestId("preview-changes")).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /^Aplicar a/ })).not.toBeInTheDocument();
  });

  it("erro ao aplicar aparece e a prévia continua", async () => {
    const user = userEvent.setup();
    vi.mocked(api.applyRules).mockRejectedValue(new ApiError(500, "Internal Server Error", "boom"));
    render(<CashRules />);
    await screen.findByTestId("rule-list");
    await user.click(screen.getByRole("button", { name: "Ver o que mudaria" }));
    await user.click(await screen.findByRole("button", { name: "Aplicar a 2 lançamentos" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Erro inesperado do servidor (500).");
    expect(screen.getByTestId("preview-changes")).toBeInTheDocument();
    expect(screen.queryByTestId("apply-notice")).not.toBeInTheDocument();
  });
});
