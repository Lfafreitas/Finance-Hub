import { describe, expect, it } from "vitest";

import {
  formatCompactCurrency,
  formatCurrency,
  formatIsoDate,
  formatPercent,
  formatQuantity,
  formatSignedCurrency,
  formatSignedPercent,
} from "./formatCurrency";

describe("formatCurrency", () => {
  it("formata na moeda informada, sem converter o valor", () => {
    expect(formatCurrency("1000.00", "BRL")).toMatch(/^R\$\s1\.000,00$/);
    expect(formatCurrency("1000.00", "USD")).toMatch(/^US\$\s1\.000,00$/);
    expect(formatCurrency("1000.00", "EUR")).toMatch(/1\.000,00/);
    expect(formatCurrency("1000.00", "EUR")).not.toMatch(/R\$|US\$/);
  });

  it("mantém o sinal de valores negativos", () => {
    expect(formatCurrency("-888.00", "USD")).toMatch(/-.*888,00/);
  });

  it("código que o Intl não aceita cai no código cru + valor do backend", () => {
    expect(formatCurrency("1000.00", "X")).toBe("X 1000.00");
  });

  it("valor não numérico é devolvido como veio", () => {
    expect(formatCurrency("n/d", "BRL")).toBe("n/d");
  });
});

describe("formatPercent e formatIsoDate", () => {
  it("fração vira percentual com duas casas", () => {
    expect(formatPercent("0.1")).toBe("10,00%");
    expect(formatPercent("-0.0525")).toBe("-5,25%");
    expect(formatPercent("x")).toBe("x");
  });

  it("data ISO vira DD/MM/AAAA sem deslocar o dia", () => {
    expect(formatIsoDate("2026-06-29")).toBe("29/06/2026");
    expect(formatIsoDate("2026-01-01")).toBe("01/01/2026");
    expect(formatIsoDate("sem data")).toBe("sem data");
  });
});

describe("formatQuantity e precisão de preço", () => {
  it("quantidade perde só os zeros à direita", () => {
    expect(formatQuantity("150.00000000")).toBe("150");
    expect(formatQuantity("0.12345678")).toBe("0,12345678");
    expect(formatQuantity("1234.5")).toBe("1.234,5");
    expect(formatQuantity("x")).toBe("x");
  });

  it("preço unitário pode mostrar até 8 casas; dinheiro agregado fica em 2", () => {
    expect(formatCurrency("30.67666666666666666666666667", "BRL", 8)).toMatch(/R\$\s30,67666667/);
    expect(formatCurrency("30.67666666666666666666666667", "BRL")).toMatch(/R\$\s30,68$/);
    expect(formatCurrency("33.00000000", "BRL", 8)).toMatch(/R\$\s33,00$/);
  });
});

describe("valores com sinal e eixo compacto (Visual-1)", () => {
  const nb = (value: string) => value.replace(/\u00a0/g, " ");

  it("ganho leva +, perda leva -, zero fica sem sinal", () => {
    expect(nb(formatSignedCurrency("10.7", "USD"))).toBe("+US$ 10,70");
    expect(nb(formatSignedCurrency("-5", "BRL"))).toBe("-R$ 5,00");
    expect(nb(formatSignedCurrency("0.0000", "BRL"))).toBe("R$ 0,00");
    expect(formatSignedCurrency("abc", "BRL")).toBe("abc");
  });

  it("percentual com sinal a partir da fração do backend", () => {
    expect(formatSignedPercent("0.0357")).toBe("+3,57%");
    expect(formatSignedPercent("-0.0245")).toBe("-2,45%");
    expect(formatSignedPercent("0")).toBe("0,00%");
    expect(formatSignedPercent("x")).toBe("x");
  });

  it("eixo compacto: milhares abreviados, na moeda do gráfico", () => {
    expect(nb(formatCompactCurrency(1200, "BRL"))).toBe("R$ 1,2 mil");
    expect(nb(formatCompactCurrency(300, "USD"))).toBe("US$ 300");
  });
});
