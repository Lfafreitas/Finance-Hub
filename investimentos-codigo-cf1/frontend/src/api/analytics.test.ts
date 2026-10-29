import { afterEach, describe, expect, it, vi } from "vitest";

import { getPortfolioAnalytics, refreshQuotes } from "./analytics";
import { getInsight, getInsights, writeSnapshot } from "./insights";

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

describe("análises e cotações", () => {
  it("análises sem parâmetros, com carteira e com data final", async () => {
    const fetchMock = mockFetch();

    await getPortfolioAnalytics(null, null);
    await getPortfolioAnalytics("p-1", "2027-06-30");

    expect(path(fetchMock, 0)).toBe("/analytics/portfolio");
    expect(path(fetchMock, 1)).toBe("/analytics/portfolio?portfolio_id=p-1&until=2027-06-30");
    expect(fetchMock.mock.calls[0][1]).toEqual({ method: "GET" });
  });

  it("buscar cotações é POST: muda dados no servidor", async () => {
    const fetchMock = mockFetch();

    await refreshQuotes();

    expect(path(fetchMock)).toBe("/prices/refresh");
    expect(fetchMock.mock.calls[0][1]).toEqual({ method: "POST" });
  });
});

describe("análises do Claude", () => {
  it("índice, um dia e o retrato da carteira", async () => {
    const fetchMock = mockFetch();

    await getInsights();
    await getInsight("2026-10-08");
    await writeSnapshot();

    expect(path(fetchMock, 0)).toBe("/insights");
    expect(path(fetchMock, 1)).toBe("/insights/2026-10-08");
    expect(path(fetchMock, 2)).toBe("/insights/snapshot");
    expect(fetchMock.mock.calls[2][1]).toEqual({ method: "POST" });
  });
});
