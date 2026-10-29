/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// O frontend chama o backend em /api, na MESMA origem da página; o Vite
// repassa para o backend em 127.0.0.1:8000 (que só aceita esse Host). Assim
// o dashboard funciona igual no computador (localhost:5173) e no celular,
// pelo endereço privado do Tailscale (https://<computador>.<rede>.ts.net),
// sem abrir o backend para a rede.
const BACKEND = "http://127.0.0.1:8000";

// Hosts aceitos além de localhost: só os nomes do Tailscale (.ts.net), que
// só existem dentro da rede privada do usuário. Qualquer outro nome continua
// recusado pelo Vite (proteção contra DNS rebinding).
const EXTRA_ALLOWED_HOSTS = [".ts.net"];

// Endereço que o navegador usou, para o backend saber se a chamada é do
// próprio computador (localhost) ou do celular (Tailscale) e exigir o
// Face ID no segundo caso. SEMPRE sobrescrito aqui: o valor que vier do
// navegador é descartado. Ver backend/app/core/remote.py.
export const CLIENT_HOST_HEADER = "x-dashboard-client-host";

// Cabeçalhos de segurança das páginas: nada de abrir dentro de outro site,
// nada de mandar o endereço para links externos, sem câmera/microfone.
const SECURITY_HEADERS = {
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
};

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Sempre na 5173: é a porta que o iniciador e o acesso pelo celular
  // esperam. Se estiver ocupada, melhor falhar avisando do que abrir na 5174.
  server: {
    port: 5173,
    strictPort: true,
    allowedHosts: EXTRA_ALLOWED_HOSTS,
    headers: SECURITY_HEADERS,
    proxy: {
      "/api": {
        target: BACKEND,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, req) => {
            proxyReq.setHeader(CLIENT_HOST_HEADER, req.headers.host ?? "");
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
});
