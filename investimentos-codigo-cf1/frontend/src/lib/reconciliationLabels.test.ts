import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import { describeResolveError, describeScanError } from "./reconciliationErrors";
import {
  fieldLabel,
  formatAbsoluteDifference,
  formatRelativeDifference,
  shortId,
  sourceLabel,
} from "./reconciliationLabels";

describe("rótulos e formatação", () => {
  it("traduz campos e fontes conhecidos e devolve o próprio valor para os desconhecidos", () => {
    expect(fieldLabel("gross_amount")).toBe("Valor bruto");
    expect(fieldLabel("campo_novo")).toBe("campo_novo");
    expect(sourceLabel("IMPORT_OFX")).toBe("Importação OFX");
  });

  it("abrevia ids longos", () => {
    expect(shortId("11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa")).toBe("11111111…");
    expect(shortId("curto")).toBe("curto");
  });

  it("diferença de data é exibida em dias; outras ficam como vieram", () => {
    expect(formatAbsoluteDifference("transaction_date", "1")).toBe("1 dia");
    expect(formatAbsoluteDifference("transaction_date", "0")).toBe("0 dias");
    expect(formatAbsoluteDifference("gross_amount", "300.0000")).toBe("300.0000");
    expect(formatAbsoluteDifference("currency_code", null)).toBe("—");
  });

  it("diferença relativa é só arredondada para leitura", () => {
    expect(formatRelativeDifference("0.09090909090909090909090909091")).toBe("9,09%");
    expect(formatRelativeDifference("0")).toBe("0,00%");
    expect(formatRelativeDifference("1")).toBe("100,00%");
    expect(formatRelativeDifference(null)).toBe("—");
    expect(formatRelativeDifference("não-numérico")).toBe("não-numérico");
  });
});

describe("mensagens de erro", () => {
  const error = (status: number, detail?: string) =>
    new ApiError(status, "X", detail ? JSON.stringify({ detail }) : "");

  it.each([
    [400, "inconsistentes"],
    [404, "não existe mais"],
    [409, "já foi resolvida"],
    [422, "inválida"],
    [500, "Erro inesperado do servidor (500)"],
  ])("resolve: status %i tem mensagem própria", (status, fragment) => {
    expect(describeResolveError(error(status))).toContain(fragment);
  });

  it("inclui o detalhe devolvido pelo backend", () => {
    expect(describeResolveError(error(400, "SELL depende deste BUY"))).toContain("SELL depende deste BUY");
  });

  it("falha de rede (não é ApiError) tem mensagem própria", () => {
    expect(describeResolveError(new TypeError("Failed to fetch"))).toContain("Não foi possível falar com o servidor");
    expect(describeScanError(new TypeError("Failed to fetch"))).toContain("Não foi possível falar com o servidor");
  });

  it.each([
    [404, "não foi encontrada"],
    [400, "Escopo de busca inválido"],
    [422, "Escopo de busca inválido"],
    [503, "Erro inesperado do servidor (503)"],
  ])("scan: status %i tem mensagem própria", (status, fragment) => {
    expect(describeScanError(error(status))).toContain(fragment);
  });
});
