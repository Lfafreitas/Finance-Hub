import { describe, expect, it } from "vitest";

import { daysLeftText, lastMonths, monthLabel } from "./agenda";

describe("agenda", () => {
  it("12 meses terminando no mês da data, atravessando o ano", () => {
    const months = lastMonths("2026-02-10");
    expect(months).toHaveLength(12);
    expect(months[0]).toBe("2025-03");
    expect(months[10]).toBe("2026-01");
    expect(months[11]).toBe("2026-02");
  });

  it("rótulo curto do mês", () => {
    expect(monthLabel("2026-10")).toBe("out/26");
    expect(monthLabel("2025-01")).toBe("jan/25");
  });

  it("prazo em palavras", () => {
    expect(daysLeftText(38)).toBe("faltam 38 dias");
    expect(daysLeftText(1)).toBe("vence amanhã");
    expect(daysLeftText(0)).toBe("vence hoje");
    expect(daysLeftText(-1)).toBe("venceu ontem");
    expect(daysLeftText(-3)).toBe("venceu há 3 dias");
  });
});
