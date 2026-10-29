import type { Note, NoteWrite } from "../api/notes";

/** Dados da anotação para regravar (ex.: só trocar "fixada"). */
export function toWrite(note: Note): NoteWrite {
  return {
    title: note.title,
    body: note.body,
    quote: note.quote,
    source_title: note.source_title,
    source_url: note.source_url,
    tickers: note.tickers,
    pinned: note.pinned,
    share_with_claude: note.share_with_claude,
  };
}

/** Evento para mandar uma pergunta pronta ao painel "Conversar com o Claude". */
export const ASK_CLAUDE_EVENT = "ask-claude";

export function askClaudeAbout(question: string): void {
  window.dispatchEvent(new CustomEvent(ASK_CLAUDE_EVENT, { detail: { question } }));
}
