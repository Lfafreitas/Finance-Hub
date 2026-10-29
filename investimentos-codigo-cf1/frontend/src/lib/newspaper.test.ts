import { describe, expect, it } from "vitest";

import { editionAgeDays, editionTime, longDate, staleNotice } from "./newspaper";

describe("jornal da carteira", () => {
  it("data por extenso, sem depender do fuso", () => {
    expect(longDate("2026-10-27")).toBe("terça-feira, 27 de outubro de 2026");
    expect(longDate("lixo")).toBe("lixo");
  });

  it("idade da edição em dias corridos", () => {
    expect(editionAgeDays("2026-10-27", new Date(2026, 9, 27, 23, 0))).toBe(0);
    expect(editionAgeDays("2026-10-23", new Date(2026, 9, 27, 8, 0))).toBe(4);
  });

  it("edição de sexta ainda vale no fim de semana e na segunda", () => {
    expect(staleNotice("2026-10-23", new Date(2026, 9, 24))).toBeNull(); // sábado
    expect(staleNotice("2026-10-23", new Date(2026, 9, 25))).toBeNull(); // domingo
    expect(staleNotice("2026-10-23", new Date(2026, 9, 26))).toBeNull(); // segunda
    expect(staleNotice("2026-10-23", new Date(2026, 9, 27))).toContain("4 dias atrás"); // terça
    expect(staleNotice("2026-10-26", new Date(2026, 9, 27))).toBeNull(); // de ontem
    expect(staleNotice("2026-10-22", new Date(2026, 9, 24))).toContain("2 dias atrás"); // quinta, no sábado
  });

  it("hora da edição", () => {
    expect(editionTime("2026-10-27T07:51:00")).toBe("07h51");
    expect(editionTime("x")).toBeNull();
  });
});
