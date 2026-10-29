import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  correctTransaction,
  deleteAccount,
  getPendingReconciliations,
  getReconciliationComparison,
  getTransaction,
  resolveReconciliation,
  reverseTransaction,
  scanReconciliation,
  updatePortfolio,
} from "./client";

function mockFetch(status: number, body: unknown, statusText = "OK") {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: async () => JSON.parse(text),
    text: async () => text,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("client — requests", () => {
  it("GET não envia corpo nem Content-Type", async () => {
    const fetchMock = mockFetch(200, []);

    await getPendingReconciliations();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/reconciliation\/pending$/);
    expect(init).toEqual({ method: "GET" });
  });

  it("busca transação e comparação pelos caminhos corretos", async () => {
    const fetchMock = mockFetch(200, {});

    await getTransaction("tx-1");
    await getReconciliationComparison("log-1");

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/transactions\/tx-1$/);
    expect(fetchMock.mock.calls[1][0]).toMatch(/\/reconciliation\/log-1\/comparison$/);
  });

  it("resolve envia POST com JSON da decisão", async () => {
    const fetchMock = mockFetch(200, {});

    await resolveReconciliation("log-1", { decision: "MERGE", surviving_transaction_id: "tx-1" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/reconciliation\/log-1\/resolve$/);
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(init.body)).toEqual({ decision: "MERGE", surviving_transaction_id: "tx-1" });
  });

  it("scan sem escopo envia objeto vazio; com escopo envia só o campo escolhido", async () => {
    const fetchMock = mockFetch(200, { created_count: 0, created: [] });

    await scanReconciliation();
    await scanReconciliation({ account_id: "acc-1" });
    await scanReconciliation({ portfolio_id: "pf-1" });

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/reconciliation\/scan$/);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({});
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ account_id: "acc-1" });
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ portfolio_id: "pf-1" });
  });
});

describe("client — edição, exclusão, correção e estorno", () => {
  it("atualizar envia PUT com o cadastro inteiro para o id", async () => {
    const fetchMock = mockFetch(200, { id: "pf-1", name: "Nova" });

    const result = await updatePortfolio("pf-1", { name: "Nova" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/portfolios\/pf-1$/);
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ name: "Nova" });
    expect(result).toEqual({ id: "pf-1", name: "Nova" });
  });

  it("excluir envia DELETE sem corpo e aceita a resposta 204 vazia", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      statusText: "No Content",
      json: async () => {
        throw new Error("204 não tem corpo");
      },
      text: async () => "",
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(deleteAccount("acc-1")).resolves.toBeUndefined();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/accounts\/acc-1$/);
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
  });

  it("corrigir e estornar usam as rotas do lançamento", async () => {
    const fetchMock = mockFetch(200, {});

    await correctTransaction("tx-1", {
      account_id: "acc-1",
      transaction_type: "DEPOSIT",
      gross_amount: "10",
      currency_code: "BRL",
      transaction_date: "2026-01-01",
    });
    await reverseTransaction("tx-1");

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/transactions\/tx-1\/correct$/);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).gross_amount).toBe("10");
    expect(fetchMock.mock.calls[1][0]).toMatch(/\/transactions\/tx-1\/reverse$/);
    expect(fetchMock.mock.calls[1][1].method).toBe("POST");
    expect(fetchMock.mock.calls[1][1].body).toBeUndefined();
  });
});

describe("client — erros", () => {
  it("resposta não-2xx vira ApiError com status e detail do backend", async () => {
    mockFetch(409, { detail: "reconciliação já está IGNORED" }, "Conflict");

    const error = await resolveReconciliation("log-1", { decision: "IGNORE" }).catch((err) => err);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(error.detail).toBe("reconciliação já está IGNORED");
    expect(error.message).toContain("409 Conflict");
  });

  it("422 do FastAPI (lista de erros) é resumido em uma mensagem", async () => {
    mockFetch(422, { detail: [{ msg: "MERGE exige surviving_transaction_id" }, { msg: "outro" }] });

    const error = await resolveReconciliation("log-1", { decision: "MERGE" }).catch((err) => err);

    expect(error.status).toBe(422);
    expect(error.detail).toBe("MERGE exige surviving_transaction_id; outro");
  });

  it("corpo de erro que não é JSON não quebra: detail fica nulo", async () => {
    mockFetch(500, "Internal Server Error", "Internal Server Error");

    const error = await getPendingReconciliations().catch((err) => err);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.detail).toBeNull();
    expect(error.message).toContain("500");
  });
});

describe("client — importação, lançamentos e cadastros", () => {
  it("preview envia multipart sem Content-Type manual (o navegador define o boundary)", async () => {
    const { previewImport } = await import("./client");
    const fetchMock = mockFetch(200, { rows: [] });
    const file = new File(["x"], "extrato.csv");

    await previewImport("acc-1", "OFX", file);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/imports\/preview$/);
    expect(init.method).toBe("POST");
    expect(init.headers).toBeUndefined();
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.body.get("account_id")).toBe("acc-1");
    expect(init.body.get("source_format")).toBe("OFX");
    expect(init.body.get("file")).toBe(file);
  });

  it("commit devolve linhas e assinatura como vieram, só acrescentando os índices", async () => {
    const { commitImport } = await import("./client");
    const fetchMock = mockFetch(200, {});
    const preview = {
      account_id: "acc-1",
      source_format: "CSV",
      signature: "sig",
      rows: [{ row_index: 0, gross_amount: "100.00" }],
    };

    await commitImport(preview as never, [0]);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/imports\/commit$/);
    expect(JSON.parse(init.body)).toEqual({ ...preview, included_row_indexes: [0] });
  });

  it("lançamento, transferência, histórico e cadastros usam as rotas certas", async () => {
    const client = await import("./client");
    const fetchMock = mockFetch(200, {});

    await client.createTransaction({} as never);
    await client.createTransfer({} as never);
    await client.getAccountTransactions("acc-1");
    await client.createAsset({} as never);
    await client.createAccount({} as never);
    await client.createInstitution({} as never);
    await client.createPortfolio({} as never);
    await client.getAssets();
    await client.getInstitutions();
    await client.getCurrencies();
    await client.getAssetClasses();

    const calls = fetchMock.mock.calls.map(([url, init]) => `${init.method} ${String(url).replace(/^\/api/, "")}`);
    expect(calls).toEqual([
      "POST /transactions",
      "POST /transfers",
      "GET /accounts/acc-1/transactions",
      "POST /assets",
      "POST /accounts",
      "POST /institutions",
      "POST /portfolios",
      "GET /assets",
      "GET /institutions",
      "GET /currencies",
      "GET /asset-classes",
    ]);
  });
});

describe("client — mesma origem (acesso pelo celular)", () => {
  it("chama o backend em /api na própria origem da página, nunca em localhost:8000", async () => {
    // Regressão: com o backend fixo em localhost:8000, o dashboard aberto no
    // celular tentava falar com o próprio celular e não carregava nada.
    const client = await import("./client");
    const fetchMock = mockFetch(200, []);

    await client.getAssets();

    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/assets");
  });
});

describe("client — cotações", () => {
  it("cotação é enviada por PUT no ativo; última cotação por GET", async () => {
    const client = await import("./client");
    const fetchMock = mockFetch(200, {});

    await client.setAssetPrice("asset-1", { price_date: "2026-06-30", price: "187.45" });
    await client.getLatestPrices();

    const [putUrl, putInit] = fetchMock.mock.calls[0];
    expect(putUrl).toMatch(/\/assets\/asset-1\/prices$/);
    expect(putInit.method).toBe("PUT");
    expect(JSON.parse(putInit.body)).toEqual({ price_date: "2026-06-30", price: "187.45" });
    expect(fetchMock.mock.calls[1][0]).toMatch(/\/prices\/latest$/);
  });
});

describe("client — trava do celular", () => {
  it("401 de uma rota de dados avisa o app para trancar; 401 do próprio /auth não", async () => {
    const client = await import("./client");
    const locked = vi.fn();
    window.addEventListener(client.LOCKED_EVENT, locked);
    mockFetch(401, { detail: "Bloqueado: desbloqueie com Face ID." });

    await expect(client.getAssets()).rejects.toMatchObject({ status: 401 });
    expect(locked).toHaveBeenCalledTimes(1);

    await expect(client.request("/auth/login/verify", { method: "POST" })).rejects.toMatchObject({ status: 401 });
    expect(locked).toHaveBeenCalledTimes(1);
    window.removeEventListener(client.LOCKED_EVENT, locked);
  });
});
