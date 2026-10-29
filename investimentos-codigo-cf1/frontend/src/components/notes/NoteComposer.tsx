import { useEffect, useRef, useState } from "react";

import type { Note, NoteWrite } from "../../api/notes";
import { describeApiError } from "../../lib/apiErrors";

export type NoteDraft = Partial<NoteWrite> & { id?: string };

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex min-h-11 cursor-pointer items-center justify-between gap-3 px-4 py-2">
      <span>
        <span className="block text-[15px] text-neutral-100">{label}</span>
        <span className="block text-[12px] text-neutral-500">{hint}</span>
      </span>
      {/* Interruptor do iOS. */}
      <span className="relative inline-flex h-[31px] w-[51px] shrink-0 items-center">
        <input
          type="checkbox"
          role="switch"
          className="peer absolute inset-0 cursor-pointer opacity-0"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="h-full w-full rounded-full bg-neutral-700 transition-colors peer-checked:bg-emerald-500" />
        <span className="pointer-events-none absolute left-[2px] h-[27px] w-[27px] rounded-full bg-white shadow transition-transform peer-checked:translate-x-5" />
      </span>
    </label>
  );
}

/**
 * Folha para escrever ou editar uma anotação. No celular sobe de baixo,
 * como as folhas do iOS; no computador, uma janela no centro.
 */
export function NoteComposer({
  draft,
  onSave,
  onClose,
}: {
  draft: NoteDraft;
  onSave: (id: string | undefined, note: NoteWrite) => Promise<Note>;
  onClose: () => void;
}) {
  const [title, setTitle] = useState(draft.title ?? "");
  const [body, setBody] = useState(draft.body ?? "");
  const [tickers, setTickers] = useState((draft.tickers ?? []).join(", "));
  const [pinned, setPinned] = useState(draft.pinned ?? false);
  const [share, setShare] = useState(draft.share_with_claude ?? false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave(draft.id, {
        title: title.trim() || null,
        body: body.trim(),
        quote: draft.quote ?? null,
        source_title: draft.source_title ?? null,
        source_url: draft.source_url ?? null,
        tickers: tickers
          .split(/[,\s]+/)
          .map((t) => t.trim())
          .filter(Boolean),
        pinned,
        share_with_claude: share,
      });
      onClose();
    } catch (err: unknown) {
      setError(describeApiError(err));
    } finally {
      setSaving(false);
    }
  }

  const empty = !title.trim() && !body.trim() && !draft.quote;
  return (
    <div
      className="fixed inset-0 z-[60] flex items-end justify-center bg-black/55 md:items-center"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={draft.id ? "Editar anotação" : "Nova anotação"}
        className="sheet-up max-h-[92dvh] w-full overflow-y-auto rounded-t-[22px] bg-neutral-900 pb-[max(1rem,env(safe-area-inset-bottom))] md:max-w-xl md:rounded-2xl"
        onMouseDown={(e) => e.stopPropagation()}
        data-testid="note-composer"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-neutral-800 bg-neutral-900/95 px-2 py-1 backdrop-blur">
          <button type="button" className="min-h-11 px-3 text-[17px] text-sky-400" onClick={onClose}>
            Cancelar
          </button>
          <p className="text-[17px] font-semibold text-neutral-50">{draft.id ? "Editar" : "Nova anotação"}</p>
          <button
            type="button"
            className="min-h-11 px-3 text-[17px] font-semibold text-sky-400 disabled:opacity-40"
            disabled={saving || empty}
            onClick={() => void save()}
          >
            {saving ? "Salvando…" : "Salvar"}
          </button>
        </div>
        <div className="space-y-4 p-4">
          {draft.quote && (
            <blockquote className="border-l-[3px] border-amber-400/70 pl-3 text-[15px] italic leading-relaxed text-neutral-300">
              {draft.quote}
              {draft.source_title && (
                <footer className="mt-1 text-[12px] not-italic text-neutral-500">{draft.source_title}</footer>
              )}
            </blockquote>
          )}
          <input
            aria-label="Título"
            placeholder="Título (opcional)"
            className="w-full bg-transparent text-[22px] font-semibold text-neutral-50 placeholder:text-neutral-600 focus:outline-none"
            value={title}
            maxLength={120}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            ref={textRef}
            aria-label="Texto"
            placeholder="O que você está pensando?"
            rows={7}
            className="w-full resize-none bg-transparent text-[17px] leading-relaxed text-neutral-100 placeholder:text-neutral-600 focus:outline-none"
            value={body}
            maxLength={10000}
            onChange={(e) => setBody(e.target.value)}
          />
          <input
            aria-label="Ativos"
            placeholder="Ativos (ex.: QQQ, VNQ)"
            className="w-full rounded-xl bg-neutral-800/70 px-4 py-3 text-[16px] uppercase text-neutral-100 placeholder:normal-case placeholder:text-neutral-500 focus:outline-none focus:ring-1 focus:ring-sky-400"
            value={tickers}
            onChange={(e) => setTickers(e.target.value)}
          />
          <div className="divide-y divide-neutral-800 overflow-hidden rounded-xl bg-neutral-800/50">
            <Toggle label="Fixar" hint="Fica no topo da lista" checked={pinned} onChange={setPinned} />
            <Toggle
              label="Usar na conversa com o Claude"
              hint="Vai junto na conversa e na análise diária. Desligado, fica só no seu computador."
              checked={share}
              onChange={setShare}
            />
          </div>
          {error && (
            <p className="text-[15px] text-red-300" role="alert">
              {error}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
