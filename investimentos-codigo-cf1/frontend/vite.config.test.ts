import { describe, expect, it } from "vitest";

import config, { CLIENT_HOST_HEADER } from "./vite.config";

type Handler = (
  proxyReq: { setHeader: (k: string, v: string) => void },
  req: { headers: Record<string, string> },
) => void;

function proxyReqHandler(): Handler {
  const handlers: Record<string, Handler> = {};
  const proxy = (config.server?.proxy as Record<string, { configure: (p: unknown) => void }>)["/api"];
  proxy.configure({ on: (event: string, fn: Handler) => (handlers[event] = fn) });
  return handlers.proxyReq;
}

describe("proxy /api (quem é local, quem é o celular)", () => {
  it("grava o endereço que o navegador usou, por cima do que o cliente mandar", () => {
    const sent: Record<string, string> = {};
    proxyReqHandler()(
      { setHeader: (k, v) => (sent[k] = v) },
      { headers: { host: "pc.tail.ts.net", [CLIENT_HOST_HEADER]: "localhost:5173" } },
    );
    expect(sent[CLIENT_HOST_HEADER]).toBe("pc.tail.ts.net");
  });

  it("sem Host, manda vazio (o backend trata como remoto)", () => {
    const sent: Record<string, string> = {};
    proxyReqHandler()({ setHeader: (k, v) => (sent[k] = v) }, { headers: {} });
    expect(sent[CLIENT_HOST_HEADER]).toBe("");
  });

  it("só aceita os nomes do Tailscale além de localhost, com cabeçalhos de segurança", () => {
    expect(config.server?.allowedHosts).toEqual([".ts.net"]);
    expect(config.server?.headers).toMatchObject({ "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer" });
  });
});
