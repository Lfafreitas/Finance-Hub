import { describe, expect, it } from "vitest";

import { isFixedIncome, parseRatePercent, rateToPercentText } from "./fixedIncome";

describe("taxa de renda fixa", () => {
  it("percentual digitado vira fração exata", () => {
    expect(parseRatePercent("3,85")).toBe("0.0385");
    expect(parseRatePercent("3.8")).toBe("0.038");
    expect(parseRatePercent("12")).toBe("0.12");
    expect(parseRatePercent("0,5")).toBe("0.005");
    expect(parseRatePercent("100")).toBe("1");
    expect(parseRatePercent(" 4,1234 % ")).toBe("0.041234");
  });

  it("vazio é sem taxa; texto estranho ou acima de 100% é inválido", () => {
    expect(parseRatePercent("")).toBeNull();
    expect(parseRatePercent("abc")).toBe("invalid");
    expect(parseRatePercent("-1")).toBe("invalid");
    expect(parseRatePercent("101")).toBe("invalid");
    expect(parseRatePercent("3,85,1")).toBe("invalid");
  });

  it("fração do backend volta para o campo em %", () => {
    expect(rateToPercentText("0.038500")).toBe("3,85");
    expect(rateToPercentText(null)).toBe("");
  });

  it("só renda fixa tem vencimento", () => {
    expect(isFixedIncome("BOND")).toBe(true);
    expect(isFixedIncome("CDB")).toBe(true);
    expect(isFixedIncome("ETF_US")).toBe(false);
  });
});

describe("peso em % com casas limitadas", () => {
  it("aceita até o número de casas pedido", () => {
    expect(parseRatePercent("33,33", 2)).toBe("0.3333");
    expect(parseRatePercent("33,333", 2)).toBe("invalid");
  });
});
