import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import { makeImportRow } from "../test/workFixtures";
import { describeApiError } from "./apiErrors";
import { isRowSelectable } from "./importRows";
import { hasNoCashAmount, MANUAL_TRANSACTION_TYPES, TRANSACTION_TYPE_RULES, transactionTypeLabel } from "./transactionTypes";

describe("describeApiError", () => {
  it("usa o detalhe do backend quando existe", () => {
    expect(describeApiError(new ApiError(400, "X", JSON.stringify({ detail: "motivo exato" })))).toBe("motivo exato");
  });

  it("tem frase própria para 413, 422 e demais status sem detalhe", () => {
    expect(describeApiError(new ApiError(413, "X", ""))).toContain("limite");
    expect(describeApiError(new ApiError(422, "X", ""))).toContain("inválidos");
    expect(describeApiError(new ApiError(503, "X", ""))).toContain("503");
  });

  it("falha de rede diz que nada foi alterado", () => {
    expect(describeApiError(new TypeError("Failed to fetch"))).toContain("Nada foi alterado");
  });
});

describe("isRowSelectable", () => {
  it("só linhas sem erro e que não são duplicata exata", () => {
    expect(isRowSelectable(makeImportRow())).toBe(true);
    expect(isRowSelectable(makeImportRow({ possible_duplicate: true }))).toBe(true);
    expect(isRowSelectable(makeImportRow({ error: "x" }))).toBe(false);
    expect(isRowSelectable(makeImportRow({ is_exact_duplicate: true }))).toBe(false);
  });
});

describe("regras de formulário por tipo", () => {
  it("espelham as pré-condições do backend", () => {
    expect(TRANSACTION_TYPE_RULES.BUY).toMatchObject({ asset: "required", quantity: "required", unitPrice: "required" });
    expect(TRANSACTION_TYPE_RULES.SELL).toMatchObject({ asset: "required", quantity: "required", unitPrice: "required" });
    for (const type of ["DEPOSIT", "WITHDRAWAL"] as const) {
      expect(TRANSACTION_TYPE_RULES[type]).toMatchObject({ asset: "hidden", quantity: "hidden", unitPrice: "hidden" });
    }
    for (const type of ["BONUS_SHARES", "STOCK_SPLIT", "REVERSE_SPLIT"] as const) {
      expect(TRANSACTION_TYPE_RULES[type]).toMatchObject({ asset: "required", quantity: "required", unitPrice: "hidden" });
      expect(hasNoCashAmount(type)).toBe(true);
    }
    expect(hasNoCashAmount("BUY")).toBe(false);
  });

  it("não oferece transferência nem conversão de câmbio no lançamento manual", () => {
    expect(MANUAL_TRANSACTION_TYPES).not.toContain("TRANSFER_OUT");
    expect(MANUAL_TRANSACTION_TYPES).not.toContain("TRANSFER_IN");
    expect(MANUAL_TRANSACTION_TYPES).not.toContain("FX_CONVERSION");
    expect(MANUAL_TRANSACTION_TYPES).toHaveLength(11);
  });

  it("rotula também os tipos que só aparecem no histórico", () => {
    expect(transactionTypeLabel("TRANSFER_OUT")).toBe("Transferência (saída)");
    expect(transactionTypeLabel("BUY")).toBe("Compra");
    expect(transactionTypeLabel("NOVO_TIPO")).toBe("NOVO_TIPO");
  });
});
