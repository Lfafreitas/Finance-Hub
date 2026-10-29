import { describe, expect, it } from "vitest";

import { CLASS_COLORS, SERIES, classColor } from "./chartColors";

// As 16 classes que a migração inicial cadastra.
const SEEDED = [
  "BDR",
  "BOND",
  "CDB",
  "CRYPTO",
  "DEBENTURE",
  "ETF_BR",
  "ETF_US",
  "FII",
  "FUND",
  "LCA",
  "LCI",
  "REIT",
  "SAVINGS",
  "STOCK_BR",
  "STOCK_US",
  "TESOURO_DIRETO",
];

describe("cor de cada classe de ativo", () => {
  // Regressão: numa carteira em reais, ETF (Brasil) e Tesouro Direto caíam
  // os dois na cor "sobra" e a barra de exposição virava uma cor só.
  it("ETF (Brasil) e Tesouro Direto têm cores diferentes", () => {
    expect(classColor("ETF_BR")).not.toBe(classColor("TESOURO_DIRETO"));
  });

  it("toda classe cadastrada tem cor própria da família, sem cair na cor de sobra por acaso", () => {
    for (const code of SEEDED) expect(CLASS_COLORS[code], code).toBeDefined();
  });

  it("a mesma família tem a mesma cor; famílias diferentes, cores diferentes", () => {
    expect(classColor("ETF_BR")).toBe(classColor("ETF_US"));
    expect(new Set(["TESOURO_DIRETO", "CDB", "LCI", "LCA", "DEBENTURE", "SAVINGS", "BOND"].map(classColor)).size).toBe(
      1,
    );
    expect(classColor("FII")).toBe(classColor("REIT"));
    const families = ["ETF_US", "BOND", "STOCK_US", "REIT", "FUND", "CRYPTO"].map(classColor);
    expect(new Set(families).size).toBe(6);
  });

  it("classe desconhecida usa a última cor da paleta", () => {
    expect(classColor("NOVA_CLASSE")).toBe(SERIES[5]);
  });
});
