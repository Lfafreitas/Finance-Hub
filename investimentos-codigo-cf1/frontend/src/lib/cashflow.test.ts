import { describe, expect, it } from "vitest";

import { allAccounts, categories, makeEntry, makeImportRow } from "../test/cashFixtures";
import {
  EMPTY_FILTER_DRAFT,
  cashAccounts,
  categoryLabel,
  categoryOptions,
  currentMonth,
  isCashRowImportable,
  isCounterpartyCandidate,
  isOutflow,
  monthRange,
  negateAmount,
  parseAmountInput,
  parsePriority,
  shiftIsoDate,
  toEntryFilters,
  toFilterDraft,
  todayIso,
} from "./cashflow";

describe("contas e categorias", () => {
  it("cashAccounts tira só as contas de investimentos", () => {
    expect(cashAccounts(allAccounts).map((a) => a.name)).toEqual(["Conta Corrente", "Cartão", "Reserva"]);
  });

  it("categoryOptions: mãe em ordem alfabética, cada uma seguida das filhas", () => {
    expect(categoryOptions(categories)).toEqual([
      { id: "cat-food", label: "Alimentação", isChild: false },
      { id: "cat-market", label: "Alimentação › Mercado", isChild: true },
      { id: "cat-home", label: "Moradia", isChild: false },
    ]);
  });

  it("categoryLabel devolve o caminho, e null sem categoria ou com id desconhecido", () => {
    expect(categoryLabel(categories, "cat-market")).toBe("Alimentação › Mercado");
    expect(categoryLabel(categories, "cat-home")).toBe("Moradia");
    expect(categoryLabel(categories, null)).toBeNull();
    expect(categoryLabel(categories, "sumiu")).toBeNull();
  });
});

describe("datas", () => {
  it("todayIso e currentMonth usam a data local", () => {
    const lastNightOfMonth = new Date(2026, 0, 31, 23, 30);
    expect(todayIso(lastNightOfMonth)).toBe("2026-01-31");
    expect(currentMonth(lastNightOfMonth)).toBe("2026-01");
    expect(todayIso(new Date(2026, 8, 5, 0, 10))).toBe("2026-09-05");
  });

  it("monthRange dá o primeiro e o último dia, inclusive em fevereiro bissexto", () => {
    expect(monthRange("2026-08")).toEqual({ start: "2026-08-01", end: "2026-08-31" });
    expect(monthRange("2026-02")).toEqual({ start: "2026-02-01", end: "2026-02-28" });
    expect(monthRange("2028-02")).toEqual({ start: "2028-02-01", end: "2028-02-29" });
    expect(monthRange("2026-12")).toEqual({ start: "2026-12-01", end: "2026-12-31" });
    expect(monthRange("2026-04")?.end).toBe("2026-04-30");
  });

  it("monthRange recusa o que não é um mês", () => {
    expect(monthRange("")).toBeNull();
    expect(monthRange("2026-13")).toBeNull();
    expect(monthRange("2026-00")).toBeNull();
    expect(monthRange("2026-8")).toBeNull();
    expect(monthRange("2026-08-01")).toBeNull();
  });

  it("shiftIsoDate atravessa mês e ano", () => {
    expect(shiftIsoDate("2026-08-05", -10)).toBe("2026-07-26");
    expect(shiftIsoDate("2026-12-25", 10)).toBe("2027-01-04");
    expect(shiftIsoDate("2026-03-01", 0)).toBe("2026-03-01");
  });
});

describe("valores", () => {
  it("isOutflow e negateAmount só olham o sinal do texto", () => {
    expect(isOutflow("-10.0000")).toBe(true);
    expect(isOutflow("10.0000")).toBe(false);
    expect(negateAmount("-10.5000")).toBe("10.5000");
    expect(negateAmount("10.5000")).toBe("-10.5000");
  });

  it("parseAmountInput aceita vírgula ou ponto decimal", () => {
    expect(parseAmountInput("1.234,56")).toBe("1234.56");
    expect(parseAmountInput("1234,5")).toBe("1234.5");
    expect(parseAmountInput("1234.56")).toBe("1234.56");
    expect(parseAmountInput(" 50 ")).toBe("50");
    expect(parseAmountInput("0,0001")).toBe("0.0001");
    expect(parseAmountInput("1 234,56")).toBe("1234.56");
  });

  it("parseAmountInput recusa zero, negativo, texto e mais de 4 casas", () => {
    for (const bad of ["", "0", "0,00", "000.0", "-5", "abc", "1,2,3", "1,23456", "1.", ",5", "+5"]) {
      expect(parseAmountInput(bad), bad).toBeNull();
    }
  });

  it("parsePriority aceita inteiros de 0 a 100000", () => {
    expect(parsePriority("0")).toBe(0);
    expect(parsePriority(" 100 ")).toBe(100);
    expect(parsePriority("100000")).toBe(100000);
    for (const bad of ["", "100001", "-1", "1.5", "dez", "1000000"]) {
      expect(parsePriority(bad), bad).toBeNull();
    }
  });
});

describe("isCounterpartyCandidate", () => {
  const entry = makeEntry({ id: "a", amount: "-500.0000" });
  const good = makeEntry({ id: "b", account_id: "acc-savings", amount: "500.0000" });

  it("aceita outra conta, mesma moeda e valor exatamente oposto", () => {
    expect(isCounterpartyCandidate(entry, good)).toBe(true);
  });

  it.each([
    ["o próprio lançamento", { id: "a" }],
    ["mesma conta", { account_id: "acc-checking" }],
    ["outra moeda", { currency_code: "USD" }],
    ["estornado", { status: "REVERSED" as const }],
    ["já é transferência", { nature: "TRANSFER" as const }],
    ["mesmo sinal", { amount: "-500.0000" }],
    ["valor diferente", { amount: "500.0100" }],
  ])("recusa: %s", (_name, overrides) => {
    expect(isCounterpartyCandidate(entry, { ...good, ...overrides })).toBe(false);
  });
});

describe("importação", () => {
  it("só linha sem erro e não duplicada pode entrar", () => {
    expect(isCashRowImportable(makeImportRow())).toBe(true);
    expect(isCashRowImportable(makeImportRow({ error: "data inválida" }))).toBe(false);
    expect(isCashRowImportable(makeImportRow({ is_duplicate: true }))).toBe(false);
  });
});

describe("filtros da lista", () => {
  it("rascunho vazio não gera nenhum filtro", () => {
    expect(toEntryFilters(EMPTY_FILTER_DRAFT)).toEqual({});
    expect(toEntryFilters({ ...EMPTY_FILTER_DRAFT, search: "   " })).toEqual({});
  });

  it("converte cada campo preenchido", () => {
    expect(
      toEntryFilters({
        accountId: "acc-1",
        start: "2026-08-01",
        end: "2026-08-31",
        nature: "EXPENSE",
        category: "cat-food",
        search: "  mercado ",
        includeReversed: true,
      }),
    ).toEqual({
      account_id: "acc-1",
      start: "2026-08-01",
      end: "2026-08-31",
      nature: "EXPENSE",
      category_id: "cat-food",
      search: "mercado",
      include_reversed: true,
    });
  });

  it('"none" vira "sem categoria", nunca um id', () => {
    expect(toEntryFilters({ ...EMPTY_FILTER_DRAFT, category: "none" })).toEqual({ uncategorized: true });
  });

  it("toFilterDraft é o caminho de volta", () => {
    const filters = { start: "2026-08-01", end: "2026-08-31", nature: "UNCLASSIFIED" as const };
    expect(toEntryFilters(toFilterDraft(filters))).toEqual(filters);
    expect(toFilterDraft({ uncategorized: true }).category).toBe("none");
    expect(toFilterDraft({})).toEqual(EMPTY_FILTER_DRAFT);
  });
});
