import { afterEach, describe, expect, it, vi } from "vitest";

import { getMonthlyFlows, getOverview, getSpendingInsights } from "./overview";

function mockFetch(body: unknown = {}) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => body,
    text: async () => JSON.stringify(body),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const path = (fetchMock: ReturnType<typeof mockFetch>, call = 0) =>
  String(fetchMock.mock.calls[call][0]).replace(/^(https?:\/\/[^/]+)?\/api/, "");

afterEach(() => vi.unstubAllGlobals());

describe("patrimônio e visão mensal do caixa", () => {
  it("patrimônio é GET sem parâmetros: o usuário vem do servidor", async () => {
    const fetchMock = mockFetch();

    await getOverview();

    expect(path(fetchMock)).toBe("/overview");
    expect(fetchMock.mock.calls[0][1]).toEqual({ method: "GET" });
  });

  it("meses: mês final e quantidade, 6 por padrão", async () => {
    const fetchMock = mockFetch();

    await getMonthlyFlows("2026-08");
    await getMonthlyFlows("2026-08", 12);

    expect(path(fetchMock, 0)).toBe("/cashflow/summary/monthly?end=2026-08&months=6");
    expect(path(fetchMock, 1)).toBe("/cashflow/summary/monthly?end=2026-08&months=12");
  });

  it("achados de gasto do mês", async () => {
    const fetchMock = mockFetch();

    await getSpendingInsights("2026-08");

    expect(path(fetchMock)).toBe("/cashflow/insights?month=2026-08");
  });
});
