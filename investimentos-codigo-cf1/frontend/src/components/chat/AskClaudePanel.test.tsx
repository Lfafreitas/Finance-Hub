import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as insightsApi from "../../api/insights";
import { setPrivate } from "../../lib/privacy";
import { AskClaudePanel } from "./AskClaudePanel";

vi.mock("../../api/insights", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/insights")>()),
  getChatContext: vi.fn(),
}));

const CONTEXT = "# Minha carteira\n| SPY | ETF | 22,8% | US$ 174,50 |";

// userEvent.setup() troca a área de transferência; a falsa entra depois.
function setup(writeText: ReturnType<typeof vi.fn>) {
  const user = userEvent.setup();
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  return user;
}

describe("AskClaudePanel", () => {
  let writeText: ReturnType<typeof vi.fn>;
  let open: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.mocked(insightsApi.getChatContext).mockResolvedValue({ text: CONTEXT });
    writeText = vi.fn().mockResolvedValue(undefined);
    open = vi.fn();
    vi.stubGlobal("open", open);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    setPrivate(false);
  });

  it("sem pergunta não abre nada", async () => {
    render(<AskClaudePanel />);
    await waitFor(() => expect(insightsApi.getChatContext).toHaveBeenCalled());

    expect(screen.getByRole("button", { name: "Abrir no Claude" })).toBeDisabled();
  });

  it("sugestão vira a pergunta; abrir leva pergunta + resumo no link e na área de transferência", async () => {
    const user = setup(writeText);
    render(<AskClaudePanel />);
    await screen.findByText(/Ver o resumo que vai junto/);

    await user.click(screen.getByRole("button", { name: /A Tesla subiu/ }));
    expect(screen.getByLabelText("Sua pergunta")).toHaveValue(
      "A Tesla subiu com os anúncios recentes. Quanto disso chegou na minha carteira pelo SPY?",
    );
    await user.click(screen.getByRole("button", { name: "Abrir no Claude" }));

    expect(writeText).toHaveBeenCalledTimes(1);
    const prompt = writeText.mock.calls[0][0] as string;
    expect(prompt).toContain("Minha pergunta: A Tesla subiu");
    expect(prompt).toContain(CONTEXT);
    expect(open.mock.calls[0][0]).toMatch(/^https:\/\/claude\.ai\/new\?q=/);
    expect(decodeURIComponent((open.mock.calls[0][0] as string).split("?q=")[1])).toBe(prompt);
    expect(screen.getByTestId("ask-status")).toHaveTextContent("Abri o Claude com a pergunta e o resumo");
  });

  it("resumo grande: abre conversa vazia e avisa para colar", async () => {
    vi.mocked(insightsApi.getChatContext).mockResolvedValue({ text: "ç".repeat(3000) });
    const user = setup(writeText);
    render(<AskClaudePanel />);
    await screen.findByText(/Ver o resumo que vai junto/);

    await user.type(screen.getByLabelText("Sua pergunta"), "oi");
    await user.click(screen.getByRole("button", { name: "Abrir no Claude" }));

    expect(open.mock.calls[0][0]).toBe("https://claude.ai/new");
    expect(screen.getByTestId("ask-status")).toHaveTextContent("cole com Ctrl+V");
  });

  it("sem acesso à área de transferência mostra o texto para copiar à mão", async () => {
    writeText.mockRejectedValue(new Error("negado"));
    const user = setup(writeText);
    render(<AskClaudePanel />);
    await screen.findByText(/Ver o resumo que vai junto/);

    await user.type(screen.getByLabelText("Sua pergunta"), "oi");
    await user.click(screen.getByRole("button", { name: "Só copiar" }));

    expect(screen.getByTestId("ask-status")).toHaveTextContent("Não consegui copiar sozinho");
    expect(open).not.toHaveBeenCalled();
  });

  it("modo privacidade esconde o resumo na tela", async () => {
    setPrivate(true);
    render(<AskClaudePanel />);

    expect(await screen.findByTestId("ask-context")).toHaveTextContent("Escondido no modo privacidade");
  });
});
