import { useEffect, useState } from "react";
import type { RefObject } from "react";

export interface Selected {
  text: string;
  sourceTitle: string | null;
  sourceUrl: string | null;
}

export interface SelectionActions {
  onHighlight: (s: Selected) => void;
  onNote: (s: Selected) => void;
  onAsk: (s: Selected) => void;
}

function readSelection(container: HTMLElement | null): { selected: Selected; rect: DOMRect } | null {
  const selection = window.getSelection();
  if (!container || !selection || selection.isCollapsed || selection.rangeCount === 0) return null;
  const text = selection.toString().replace(/\s+/g, " ").trim();
  if (text.length < 3) return null;
  const range = selection.getRangeAt(0);
  if (!container.contains(range.commonAncestorContainer)) return null;
  const start = range.startContainer instanceof Element ? range.startContainer : range.startContainer.parentElement;
  const source = start?.closest<HTMLElement>("[data-quote-source]");
  return {
    selected: {
      text: text.slice(0, 2000),
      sourceTitle: source?.dataset.quoteSource ?? null,
      sourceUrl: source?.dataset.quoteUrl ?? null,
    },
    rect: range.getBoundingClientRect(),
  };
}

const BUTTON =
  "flex min-h-12 min-w-11 flex-1 flex-col items-center justify-center gap-1 rounded-xl px-2 text-[12px] text-neutral-200 transition-colors hover:bg-white/10 active:scale-95";

/**
 * Barra que aparece ao selecionar um trecho do Jornal: destacar (guarda
 * nas anotações e marca no texto), anotar, copiar e perguntar ao Claude.
 * No celular fica ABAIXO da seleção, para não brigar com o menu do iOS.
 */
export function SelectionToolbar({
  container,
  actions,
}: {
  container: RefObject<HTMLElement | null>;
  actions: SelectionActions;
}) {
  const [state, setState] = useState<{ selected: Selected; rect: DOMRect } | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const update = () => {
      setState(readSelection(container.current));
      setCopied(false);
    };
    document.addEventListener("selectionchange", update);
    return () => document.removeEventListener("selectionchange", update);
  }, [container]);

  if (!state) return null;
  const touch = window.matchMedia?.("(pointer: coarse)").matches ?? false;
  const width = 296;
  const left = Math.min(Math.max(8, state.rect.left + state.rect.width / 2 - width / 2), window.innerWidth - width - 8);
  const top = touch ? state.rect.bottom + 14 : Math.max(8, state.rect.top - 66);
  const done = () => {
    window.getSelection()?.removeAllRanges();
    setState(null);
  };

  return (
    <div
      role="toolbar"
      aria-label="Trecho selecionado"
      className="fixed z-50 flex gap-0.5 rounded-2xl border border-white/10 font-sans tracking-normal [word-spacing:normal] bg-neutral-900/95 p-1 shadow-[0_12px_32px_rgba(0,0,0,0.55)] backdrop-blur-xl"
      style={{ top, left, width }}
      onMouseDown={(e) => e.preventDefault()}
      data-testid="selection-toolbar"
    >
      <button
        type="button"
        className={BUTTON}
        onClick={() => {
          actions.onHighlight(state.selected);
          done();
        }}
      >
        <span className="h-3 w-5 rounded-sm bg-amber-400/70" aria-hidden="true" />
        Destacar
      </button>
      <button
        type="button"
        className={BUTTON}
        onClick={() => {
          actions.onNote(state.selected);
          done();
        }}
      >
        <span aria-hidden="true">✎</span>
        Anotar
      </button>
      <button
        type="button"
        className={BUTTON}
        onClick={() => {
          void navigator.clipboard?.writeText(state.selected.text).then(
            () => setCopied(true),
            () => setCopied(false),
          );
        }}
      >
        <span aria-hidden="true">⧉</span>
        {copied ? "Copiado" : "Copiar"}
      </button>
      <button
        type="button"
        className={BUTTON}
        onClick={() => {
          actions.onAsk(state.selected);
          done();
        }}
      >
        <span aria-hidden="true">✦</span>
        Perguntar
      </button>
    </div>
  );
}
