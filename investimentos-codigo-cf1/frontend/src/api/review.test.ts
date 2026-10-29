import { afterEach, describe, expect, it, vi } from "vitest";

import { getPerformanceHistory } from "./performance";
import { classifyBatch, getPendingGroups } from "./review";

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

describe("revisão e evolução", () => {
  it("grupos pendentes com limite", async () => {
    const fetchMock = mockFetch();

    await getPendingGroups();
    await getPendingGroups(10);

    expect(path(fetchMock, 0)).toBe("/cashflow/pending/groups?limit=50");
    expect(path(fetchMock, 1)).toBe("/cashflow/pending/groups?limit=10");
  });

  it("lote é POST com os ids e a classificação", async () => {
    const fetchMock = mockFetch({ classified: 2 });

    await classifyBatch({ entry_ids: ["a", "b"], nature: "EXPENSE", category_id: null, tag_ids: [] });

    expect(path(fetchMock)).toBe("/cashflow/entries/classify-batch");
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      entry_ids: ["a", "b"],
      nature: "EXPENSE",
      category_id: null,
      tag_ids: [],
    });
  });

  it("evolução com e sem período", async () => {
    const fetchMock = mockFetch();

    await getPerformanceHistory(90);
    await getPerformanceHistory(null);

    expect(path(fetchMock, 0)).toBe("/performance/history?days=90");
    expect(path(fetchMock, 1)).toBe("/performance/history");
  });
});
