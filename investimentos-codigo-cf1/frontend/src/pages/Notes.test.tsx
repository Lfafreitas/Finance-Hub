import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Note } from "../api/notes";
import * as notesApi from "../api/notes";
import { Notes } from "./Notes";

vi.mock("../api/notes");

function note(over: Partial<Note> = {}): Note {
  return {
    id: "n1",
    title: "Tese do QQQ",
    body: "Esperar os balanços.",
    quote: null,
    source_title: null,
    source_url: null,
    tickers: ["QQQ"],
    pinned: false,
    share_with_claude: false,
    created_at: "2026-10-28T10:00:00Z",
    updated_at: "2026-10-28T10:00:00Z",
    ...over,
  };
}

describe("Notes", () => {
  beforeEach(() => vi.resetAllMocks());

  it("vazio convida a escrever", async () => {
    vi.mocked(notesApi.getNotes).mockResolvedValue([]);
    render(<Notes />);
    expect(await screen.findByTestId("notes-empty")).toHaveTextContent("Nenhuma anotação ainda.");
  });

  it("fixadas primeiro, com trecho, ativos e a marca do Claude", async () => {
    vi.mocked(notesApi.getNotes).mockResolvedValue([
      note({ id: "p", title: "Fixada", pinned: true, share_with_claude: true }),
      note({
        id: "q",
        title: null,
        body: "",
        quote: "Trecho lido.",
        source_title: "Jornal",
        source_url: "https://x.example.com",
      }),
    ]);
    render(<Notes />);

    const fixed = await screen.findByRole("region", { name: "Fixadas" });
    expect(within(fixed).getByTestId("note")).toHaveTextContent("Claude");
    const all = screen.getByRole("region", { name: "Todas" });
    expect(within(all).getByText("Trecho lido.").tagName).toBe("BLOCKQUOTE");
    expect(within(all).getByRole("link", { name: "Jornal" })).toHaveAttribute("href", "https://x.example.com");
  });

  it("nova anotação: escreve, marca para o Claude e salva", async () => {
    const user = userEvent.setup();
    vi.mocked(notesApi.getNotes).mockResolvedValue([]);
    vi.mocked(notesApi.createNote).mockResolvedValue(note());
    render(<Notes />);

    await user.click(await screen.findByRole("button", { name: "Nova anotação" }));
    const sheet = screen.getByTestId("note-composer");
    const save = within(sheet).getByRole("button", { name: "Salvar" });
    expect(save).toBeDisabled();
    await user.type(within(sheet).getByLabelText("Texto"), "Pensando em cripto 3%.");
    await user.type(within(sheet).getByLabelText("Ativos"), "btc, eth");
    await user.click(within(sheet).getByRole("switch", { name: /Usar na conversa com o Claude/ }));
    await user.click(save);

    expect(notesApi.createNote).toHaveBeenCalledWith({
      title: null,
      body: "Pensando em cripto 3%.",
      quote: null,
      source_title: null,
      source_url: null,
      tickers: ["btc", "eth"],
      pinned: false,
      share_with_claude: true,
    });
    expect(screen.queryByTestId("note-composer")).toBeNull();
  });

  it("fixar regrava só o 'fixada'; apagar pede confirmação", async () => {
    const user = userEvent.setup();
    vi.mocked(notesApi.getNotes).mockResolvedValue([note()]);
    vi.mocked(notesApi.updateNote).mockResolvedValue(note({ pinned: true }));
    vi.mocked(notesApi.deleteNote).mockResolvedValue(undefined);
    render(<Notes />);

    const card = await screen.findByTestId("note");
    await user.click(within(card).getByRole("button", { name: "Fixar" }));
    expect(notesApi.updateNote).toHaveBeenCalledWith(
      "n1",
      expect.objectContaining({ pinned: true, title: "Tese do QQQ" }),
    );
    await user.click(within(card).getByRole("button", { name: "Apagar" }));
    expect(notesApi.deleteNote).not.toHaveBeenCalled();
    await user.click(within(card).getByRole("button", { name: "Apagar de vez" }));
    expect(notesApi.deleteNote).toHaveBeenCalledWith("n1");
  });

  it("tocar na anotação abre para editar", async () => {
    const user = userEvent.setup();
    vi.mocked(notesApi.getNotes).mockResolvedValue([note()]);
    vi.mocked(notesApi.updateNote).mockResolvedValue(note({ body: "Novo." }));
    render(<Notes />);

    await user.click(await screen.findByText("Esperar os balanços."));
    const sheet = screen.getByTestId("note-composer");
    expect(within(sheet).getByLabelText("Título")).toHaveValue("Tese do QQQ");
    await user.clear(within(sheet).getByLabelText("Texto"));
    await user.type(within(sheet).getByLabelText("Texto"), "Novo.");
    await user.click(within(sheet).getByRole("button", { name: "Salvar" }));
    expect(notesApi.updateNote).toHaveBeenCalledWith(
      "n1",
      expect.objectContaining({ body: "Novo.", tickers: ["QQQ"] }),
    );
  });
});
