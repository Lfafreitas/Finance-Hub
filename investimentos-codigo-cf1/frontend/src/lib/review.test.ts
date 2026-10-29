import { describe, expect, it } from "vitest";

import type { PendingGroup } from "../api/review";
import { isInvoicePayment, periodLabel, ruleDirection, ruleFromGroup, ruleName } from "./review";

function group(overrides: Partial<PendingGroup> = {}): PendingGroup {
  return {
    match_text: "transferencia enviada pelo pix uber",
    currency_code: "BRL",
    sample_description: "Transferência enviada pelo Pix - Uber - 17.895.646/0001-87 - EBANX IP LTDA. (0383)",
    count: 3,
    total: "-44.4600",
    inflows: 0,
    outflows: 3,
    first_date: "2025-01-20",
    last_date: "2026-09-03",
    entry_ids: ["a", "b", "c"],
    preview: [],
    suggestion: null,
    ...overrides,
  };
}

describe("regra a partir de um grupo", () => {
  it("o sentido segue o grupo: só saídas, só entradas ou os dois", () => {
    expect(ruleDirection(group())).toBe("OUT");
    expect(ruleDirection(group({ inflows: 2, outflows: 0 }))).toBe("IN");
    expect(ruleDirection(group({ inflows: 1, outflows: 1 }))).toBe("ANY");
  });

  it("o nome é o movimento e a contraparte, sem documento nem banco", () => {
    expect(ruleName(group())).toBe("Transferência enviada pelo Pix - Uber");
    expect(ruleName(group({ sample_description: "Pagamento de fatura" }))).toBe("Pagamento de fatura");
    expect(ruleName(group({ sample_description: "   " }))).toBe("transferencia enviada pelo pix uber");
  });

  it("a regra usa o texto exato do grupo e a classificação escolhida", () => {
    expect(ruleFromGroup(group(), "EXPENSE", "cat-ride")).toEqual({
      name: "Transferência enviada pelo Pix - Uber",
      priority: 100,
      is_active: true,
      match_type: "CONTAINS",
      pattern: "transferencia enviada pelo pix uber",
      direction: "OUT",
      account_id: null,
      set_nature: "EXPENSE",
      set_category_id: "cat-ride",
      tag_ids: [],
    });
  });

  it("pagamento de fatura é reconhecido pelo texto", () => {
    expect(isInvoicePayment(group({ match_text: "pagamento de fatura" }))).toBe(true);
    expect(isInvoicePayment(group())).toBe(false);
  });

  it("período em meses", () => {
    expect(periodLabel("2025-01-20", "2026-09-03")).toBe("jan/2025 – set/2026");
    expect(periodLabel("2026-09-01", "2026-09-30")).toBe("set/2026");
  });
});
