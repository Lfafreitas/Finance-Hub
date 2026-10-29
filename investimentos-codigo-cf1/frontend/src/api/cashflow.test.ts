import { afterEach, describe, expect, it, vi } from "vitest";

import { cashPreviewFixture } from "../test/cashFixtures";
import {
  applyRules,
  classifyCashEntry,
  correctCashEntry,
  commitCashImport,
  countCashEntries,
  createDefaultCategories,
  deleteCategory,
  getCashBalances,
  getCashEntries,
  getCashSummary,
  getCategoryBreakdown,
  linkCashTransfer,
  markInvestmentTransfer,
  matchInvoicePayments,
  previewCashImport,
  previewRules,
  restoreCashEntry,
  reverseCashEntry,
  unlinkCashTransfer,
} from "./cashflow";

function mockFetch(status: number, body: unknown) {
  const text = JSON.stringify(body);
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    json: async () => JSON.parse(text),
    text: async () => text,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const pathOf = (fetchMock: ReturnType<typeof mockFetch>, call = 0) =>
  String(fetchMock.mock.calls[call][0]).replace(/^(https?:\/\/[^/]+)?\/api/, "");
const bodyOf = (fetchMock: ReturnType<typeof mockFetch>, call = 0) => JSON.parse(fetchMock.mock.calls[call][1].body);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("lista e contagem", () => {
  it("sem filtros, a lista manda só a paginação e a contagem não manda nada", async () => {
    const fetchMock = mockFetch(200, []);

    await getCashEntries();
    await countCashEntries();

    expect(pathOf(fetchMock, 0)).toBe("/cashflow/entries?limit=100&offset=0");
    expect(pathOf(fetchMock, 1)).toBe("/cashflow/entries/count");
  });

  it("lista e contagem montam a mesma consulta a partir dos mesmos filtros", async () => {
    const fetchMock = mockFetch(200, []);
    const filters = {
      account_id: "acc-1",
      start: "2026-08-01",
      end: "2026-08-31",
      include_reversed: true,
      nature: "EXPENSE" as const,
      category_id: "cat-1",
      search: "pão & café",
    };
    const query =
      "account_id=acc-1&start=2026-08-01&end=2026-08-31&include_reversed=true&nature=EXPENSE&category_id=cat-1&search=p%C3%A3o+%26+caf%C3%A9";

    await getCashEntries(filters, 50, 150);
    await countCashEntries(filters);

    expect(pathOf(fetchMock, 0)).toBe(`/cashflow/entries?${query}&limit=50&offset=150`);
    expect(pathOf(fetchMock, 1)).toBe(`/cashflow/entries/count?${query}`);
  });

  it('"sem categoria" e filtros falsos', async () => {
    const fetchMock = mockFetch(200, { total: 0 });

    await countCashEntries({ uncategorized: true, include_reversed: false });

    expect(pathOf(fetchMock)).toBe("/cashflow/entries/count?uncategorized=true");
  });
});

describe("ações sobre lançamentos", () => {
  it("classificação completa vai por PUT", async () => {
    const fetchMock = mockFetch(200, {});

    await classifyCashEntry("e-1", { nature: "EXPENSE", category_id: "c-1", tag_ids: ["t-1"] });

    expect(pathOf(fetchMock)).toBe("/cashflow/entries/e-1/classification");
    expect(fetchMock.mock.calls[0][1].method).toBe("PUT");
    expect(bodyOf(fetchMock)).toEqual({ nature: "EXPENSE", category_id: "c-1", tag_ids: ["t-1"] });
  });

  it("estorno é POST sem corpo", async () => {
    const fetchMock = mockFetch(200, []);

    await reverseCashEntry("e-1");

    expect(pathOf(fetchMock)).toBe("/cashflow/entries/e-1/reverse");
    expect(fetchMock.mock.calls[0][1]).toEqual({ method: "POST" });
  });

  it("restaurar é POST sem corpo; editar manda os valores novos", async () => {
    const fetchMock = mockFetch(200, []);

    await restoreCashEntry("e-1");
    await correctCashEntry("e-2", { entry_date: "2026-08-10", amount: "-9.5", description: "Pão", notes: null });

    expect(pathOf(fetchMock, 0)).toBe("/cashflow/entries/e-1/restore");
    expect(fetchMock.mock.calls[0][1]).toEqual({ method: "POST" });
    expect(pathOf(fetchMock, 1)).toBe("/cashflow/entries/e-2/correct");
    expect(fetchMock.mock.calls[1][1].method).toBe("POST");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      entry_date: "2026-08-10",
      amount: "-9.5",
      description: "Pão",
      notes: null,
    });
  });

  it("ligar com lançamento e marcar aporte mandam campos diferentes na mesma rota", async () => {
    const fetchMock = mockFetch(200, { entries: [] });

    await linkCashTransfer("e-1", "e-2");
    await markInvestmentTransfer("e-1", "acc-9");
    await unlinkCashTransfer("e-1");

    expect(pathOf(fetchMock, 0)).toBe("/cashflow/entries/e-1/transfer");
    expect(bodyOf(fetchMock, 0)).toEqual({ counterparty_entry_id: "e-2" });
    expect(bodyOf(fetchMock, 1)).toEqual({ investment_account_id: "acc-9" });
    expect(fetchMock.mock.calls[2][1]).toEqual({ method: "DELETE" });
  });

  it("casamento de fatura informa se é só prévia", async () => {
    const fetchMock = mockFetch(200, { applied: false, matches: [] });

    await matchInvoicePayments(true);
    await matchInvoicePayments(false);

    expect(pathOf(fetchMock, 0)).toBe("/cashflow/transfers/match?dry_run=true");
    expect(pathOf(fetchMock, 1)).toBe("/cashflow/transfers/match?dry_run=false");
  });
});

describe("resumo, categorias e regras", () => {
  it("resumo e quebra recebem o período; saldos não", async () => {
    const fetchMock = mockFetch(200, {});

    await getCashSummary("2026-08-01", "2026-08-31");
    await getCategoryBreakdown("2026-08-01", "2026-08-31");
    await getCashBalances();

    expect(pathOf(fetchMock, 0)).toBe("/cashflow/summary?start=2026-08-01&end=2026-08-31");
    expect(pathOf(fetchMock, 1)).toBe("/cashflow/summary/categories?start=2026-08-01&end=2026-08-31");
    expect(pathOf(fetchMock, 2)).toBe("/cashflow/balances");
  });

  it("categorias sugeridas e exclusão (204 sem corpo)", async () => {
    const fetchMock = mockFetch(204, "");

    await createDefaultCategories().catch(() => undefined);
    await expect(deleteCategory("c-1")).resolves.toBeUndefined();

    expect(pathOf(fetchMock, 0)).toBe("/cashflow/categories/defaults");
    expect(fetchMock.mock.calls[1][1]).toEqual({ method: "DELETE" });
  });

  it("prévia e aplicação das regras usam rotas diferentes com o mesmo corpo", async () => {
    const fetchMock = mockFetch(200, { applied: false, examined: 0, changes: [] });

    await previewRules({ reevaluate: true });
    await applyRules({ reevaluate: true });

    expect(pathOf(fetchMock, 0)).toBe("/cashflow/rules/preview");
    expect(pathOf(fetchMock, 1)).toBe("/cashflow/rules/apply");
    expect(bodyOf(fetchMock, 0)).toEqual(bodyOf(fetchMock, 1));
    expect(bodyOf(fetchMock, 0)).toEqual({ reevaluate: true });
  });
});

describe("importação", () => {
  const file = new File(["x"], "extrato.ofx");

  it("prévia é multipart; o perfil só vai quando escolhido", async () => {
    const fetchMock = mockFetch(200, cashPreviewFixture);

    await previewCashImport("acc-1", file, null);
    await previewCashImport("acc-1", file, "NUBANK_CARD_CSV");

    const auto = fetchMock.mock.calls[0][1].body as FormData;
    const chosen = fetchMock.mock.calls[1][1].body as FormData;
    expect(pathOf(fetchMock)).toBe("/cashflow/imports/preview");
    expect(auto.get("account_id")).toBe("acc-1");
    expect(auto.get("file")).toBeInstanceOf(File);
    expect(auto.has("profile")).toBe(false);
    expect(chosen.get("profile")).toBe("NUBANK_CARD_CSV");
    expect(fetchMock.mock.calls[0][1].headers).toBeUndefined();
  });

  it("commit devolve a prévia intacta + os índices e a escolha do saldo inicial", async () => {
    const fetchMock = mockFetch(200, {});

    await commitCashImport(cashPreviewFixture, [0, 3], true);

    const { file_already_imported: _ignored, ...signedPart } = cashPreviewFixture;
    expect(pathOf(fetchMock)).toBe("/cashflow/imports/commit");
    expect(bodyOf(fetchMock)).toEqual({
      ...signedPart,
      included_row_indexes: [0, 3],
      create_opening_adjustment: true,
    });
  });
});
