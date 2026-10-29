import { describe, expect, it } from "vitest";

import { CLAUDE_NEW_CHAT, MAX_URL_LENGTH, buildPrompt, claudeLink } from "./askClaude";

describe("levar a pergunta ao Claude", () => {
  it("pergunta e resumo vão juntos, com o pedido de fontes", () => {
    const prompt = buildPrompt("  Participei da alta da Tesla?  ", "# Minha carteira\n| SPY | 22,8% |");

    expect(prompt).toContain("Minha pergunta: Participei da alta da Tesla?");
    expect(prompt).toContain("# Minha carteira\n| SPY | 22,8% |");
    expect(prompt).toContain("cite fonte e data");
    expect(prompt).toContain("analista-da-carteira");
  });

  it("link do Claude com o texto codificado", () => {
    const link = claudeLink("a & b?");
    expect(link).toBe(`${CLAUDE_NEW_CHAT}?q=a%20%26%20b%3F`);
  });

  it("texto grande demais não vira link", () => {
    expect(claudeLink("x".repeat(MAX_URL_LENGTH))).toBeNull();
    // acentos ocupam mais no link: conta o tamanho já codificado
    expect(claudeLink("ç".repeat(1400))).toBeNull();
  });
});
