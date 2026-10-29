import { describe, expect, it } from "vitest";

import { AUTO_REFRESH_MS, formatMonth, formatRefreshTime, quotesAreStale } from "./analytics";

describe("quotesAreStale", () => {
  const now = Date.parse("2026-10-08T15:00:00Z");

  it("nunca buscada, ou data ilegível, conta como velha", () => {
    expect(quotesAreStale(null, now)).toBe(true);
    expect(quotesAreStale("ontem", now)).toBe(true);
  });

  it("até 15 minutos é nova; depois disso, velha", () => {
    expect(quotesAreStale(new Date(now - AUTO_REFRESH_MS).toISOString(), now)).toBe(false);
    expect(quotesAreStale(new Date(now - AUTO_REFRESH_MS - 1000).toISOString(), now)).toBe(true);
    expect(quotesAreStale(new Date(now - 60_000).toISOString(), now)).toBe(false);
  });

  it("intervalo é de 15 minutos", () => {
    expect(AUTO_REFRESH_MS).toBe(900_000);
  });
});

describe("formatação", () => {
  it("mês por extenso curto", () => {
    expect(formatMonth("2026-01")).toBe("jan/2026");
    expect(formatMonth("2026-10")).toBe("out/2026");
    expect(formatMonth("2026-12")).toBe("dez/2026");
    expect(formatMonth("x")).toBe("x");
  });

  it("hora local da última busca", () => {
    const local = new Date(2026, 9, 8, 9, 5);
    expect(formatRefreshTime(local.toISOString())).toBe("08/10 às 09:05");
    expect(formatRefreshTime("lixo")).toBe("lixo");
  });
});
