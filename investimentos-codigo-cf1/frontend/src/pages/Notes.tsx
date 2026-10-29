import { useCallback, useEffect, useState } from "react";

import type { Note, NoteWrite } from "../api/notes";
import { createNote, deleteNote, getNotes, updateNote } from "../api/notes";
import type { NoteDraft } from "../components/notes/NoteComposer";
import { NoteComposer } from "../components/notes/NoteComposer";
import { SafeLink } from "../components/insights/SafeLink";
import { formatRefreshTime } from "../lib/analytics";
import { describeApiError } from "../lib/apiErrors";
import { toWrite } from "../lib/notes";

function NoteCard({
  note,
  onEdit,
  onTogglePin,
  onDelete,
}: {
  note: Note;
  onEdit: () => void;
  onTogglePin: () => void;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  return (
    <article
      className="group rounded-2xl bg-neutral-900 p-4 ring-1 ring-neutral-800 transition-colors hover:ring-neutral-700"
      data-testid="note"
    >
      <button type="button" className="block w-full text-left" onClick={onEdit}>
        {note.title && <h3 className="text-[17px] font-semibold leading-snug text-neutral-50">{note.title}</h3>}
        {note.quote && (
          <blockquote className="mt-2 border-l-[3px] border-amber-400/70 pl-3 text-[15px] italic leading-relaxed text-neutral-300">
            {note.quote}
          </blockquote>
        )}
        {note.body && (
          <p className="mt-2 line-clamp-5 whitespace-pre-line text-[15px] leading-relaxed text-neutral-300">
            {note.body}
          </p>
        )}
      </button>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-[12px] text-neutral-500">
        {note.tickers.map((t) => (
          <span key={t} className="rounded bg-neutral-800 px-1.5 py-px font-medium text-neutral-300">
            {t}
          </span>
        ))}
        {note.share_with_claude && (
          <span className="rounded bg-sky-400/15 px-1.5 py-px text-sky-300" title="Vai junto na conversa com o Claude">
            Claude
          </span>
        )}
        {note.source_url ? (
          <SafeLink url={note.source_url}>{note.source_title ?? "fonte"}</SafeLink>
        ) : (
          note.source_title && <span>{note.source_title}</span>
        )}
        <span className="ml-auto">{formatRefreshTime(note.updated_at)}</span>
      </div>
      <div className="mt-2 flex gap-1">
        <button
          type="button"
          className="min-h-9 rounded-lg px-2.5 text-[13px] text-neutral-400 hover:bg-neutral-800"
          onClick={onTogglePin}
        >
          {note.pinned ? "Desafixar" : "Fixar"}
        </button>
        {confirming ? (
          <>
            <button
              type="button"
              className="min-h-9 rounded-lg px-2.5 text-[13px] text-red-300 hover:bg-neutral-800"
              onClick={onDelete}
            >
              Apagar de vez
            </button>
            <button
              type="button"
              className="min-h-9 rounded-lg px-2.5 text-[13px] text-neutral-400 hover:bg-neutral-800"
              onClick={() => setConfirming(false)}
            >
              Cancelar
            </button>
          </>
        ) : (
          <button
            type="button"
            className="min-h-9 rounded-lg px-2.5 text-[13px] text-neutral-400 hover:bg-neutral-800"
            onClick={() => setConfirming(true)}
          >
            Apagar
          </button>
        )}
      </div>
    </article>
  );
}

/**
 * Anotações: pensamentos sobre a carteira (ou qualquer assunto) e os
 * trechos destacados no Jornal. Ficam no computador; só as marcadas vão
 * para a conversa com o Claude.
 */
export function Notes() {
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState<NoteDraft | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getNotes(search)
      .then((list) => {
        setNotes(list);
        setError(null);
      })
      .catch((err: unknown) => setError(describeApiError(err)));
  }, [search]);

  useEffect(() => {
    const timer = window.setTimeout(load, search ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [load, search]);

  async function save(id: string | undefined, note: NoteWrite): Promise<Note> {
    const saved = id ? await updateNote(id, note) : await createNote(note);
    load();
    return saved;
  }

  async function act(action: () => Promise<unknown>) {
    try {
      await action();
      load();
    } catch (err: unknown) {
      setError(describeApiError(err));
    }
  }

  const pinned = (notes ?? []).filter((n) => n.pinned);
  const others = (notes ?? []).filter((n) => !n.pinned);
  const card = (note: Note) => (
    <NoteCard
      key={note.id}
      note={note}
      onEdit={() => setDraft({ ...toWrite(note), id: note.id })}
      onTogglePin={() => void act(() => updateNote(note.id, { ...toWrite(note), pinned: !note.pinned }))}
      onDelete={() => void act(() => deleteNote(note.id))}
    />
  );

  return (
    <div className="space-y-6" data-testid="notes-page">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          aria-label="Buscar nas anotações"
          placeholder="Buscar"
          className="min-h-11 flex-1 rounded-xl bg-neutral-900 px-4 text-[16px] text-neutral-100 ring-1 ring-neutral-800 placeholder:text-neutral-500 focus:outline-none focus:ring-sky-400 md:max-w-sm"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button
          type="button"
          className="min-h-11 rounded-xl bg-sky-400 px-4 text-[15px] font-semibold text-neutral-950 active:opacity-80"
          onClick={() => setDraft({})}
        >
          Nova anotação
        </button>
      </div>
      {error && (
        <p className="text-sm text-red-400" role="alert">
          {error}
        </p>
      )}
      {notes !== null && notes.length === 0 && (
        <div className="rounded-2xl bg-neutral-900 p-6 text-center ring-1 ring-neutral-800" data-testid="notes-empty">
          <p className="text-[17px] text-neutral-200">{search ? "Nada encontrado." : "Nenhuma anotação ainda."}</p>
          {!search && (
            <p className="mt-1 text-[15px] text-neutral-500">
              Escreva uma tese, uma dúvida ou um lembrete. No Jornal, selecione um trecho para destacar ou anotar.
            </p>
          )}
        </div>
      )}
      {pinned.length > 0 && (
        <section aria-label="Fixadas">
          <h2 className="mb-2 px-1 text-[13px] text-neutral-500">Fixadas</h2>
          <div className="grid gap-3 md:grid-cols-2">{pinned.map(card)}</div>
        </section>
      )}
      {others.length > 0 && (
        <section aria-label="Todas">
          {pinned.length > 0 && <h2 className="mb-2 px-1 text-[13px] text-neutral-500">Todas</h2>}
          <div className="grid gap-3 md:grid-cols-2">{others.map(card)}</div>
        </section>
      )}
      {draft && <NoteComposer draft={draft} onSave={save} onClose={() => setDraft(null)} />}
    </div>
  );
}
