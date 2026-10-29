import { useEffect, useRef, useState } from "react";

import type { ReadingPrefs } from "../../lib/readingPrefs";
import { FONTS, MAX_SIZE, MIN_SIZE, clampSize } from "../../lib/readingPrefs";

const CELL = "rounded-xl bg-neutral-800/70 p-1.5";
const OPTION = "min-h-10 rounded-lg px-3 text-[14px] transition-colors";

/**
 * Botão "Aa" do Jornal, como o do app Livros: fonte (com opções feitas
 * para dislexia), tamanho, espaçamento, largura da linha e fundo.
 */
export function ReadingSettings({ prefs, onChange }: { prefs: ReadingPrefs; onChange: (p: ReadingPrefs) => void }) {
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !panel.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const set = (patch: Partial<ReadingPrefs>) => onChange({ ...prefs, ...patch });

  return (
    <div className="relative" ref={panel}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label="Ajustes de leitura"
        className="flex h-10 min-w-10 items-center justify-center rounded-full bg-neutral-800/80 px-3 font-serif text-[17px] text-neutral-100 transition-transform active:scale-95"
      >
        Aa
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Ajustes de leitura"
          className="sheet-up fixed inset-x-3 bottom-[calc(92px+env(safe-area-inset-bottom))] z-40 space-y-2 md:absolute md:inset-x-auto md:bottom-auto md:right-0 md:top-12 md:w-[22rem] rounded-2xl border border-white/10 bg-neutral-900/95 p-2 shadow-[0_16px_40px_rgba(0,0,0,0.55)] backdrop-blur-xl"
          data-testid="reading-settings"
        >
          <div className={`${CELL} grid grid-cols-2 gap-1`} role="group" aria-label="Fonte">
            {FONTS.map((font) => (
              <button
                key={font.id}
                type="button"
                aria-pressed={prefs.font === font.id}
                onClick={() => set({ font: font.id })}
                className={`${OPTION} py-1.5 text-left ${prefs.font === font.id ? "bg-neutral-600 text-neutral-50" : "text-neutral-300"}`}
                style={{ fontFamily: font.family }}
              >
                <span className="block text-[15px]">{font.label}</span>
                <span className="block text-[11px] text-neutral-400">{font.hint}</span>
              </button>
            ))}
          </div>

          <div className="grid grid-cols-[auto_1fr] gap-2">
            <div className={`${CELL} flex items-center gap-1`} role="group" aria-label="Tamanho do texto">
              <button
                type="button"
                className={`${OPTION} text-neutral-200`}
                aria-label="Diminuir texto"
                disabled={prefs.size <= MIN_SIZE}
                onClick={() => set({ size: clampSize(prefs.size - 1) })}
              >
                A−
              </button>
              <span className="w-8 text-center tabular-nums text-neutral-100" aria-live="polite">
                {prefs.size}
              </span>
              <button
                type="button"
                className={`${OPTION} text-[17px] text-neutral-200`}
                aria-label="Aumentar texto"
                disabled={prefs.size >= MAX_SIZE}
                onClick={() => set({ size: clampSize(prefs.size + 1) })}
              >
                A+
              </button>
            </div>
            <div className={`${CELL} grid grid-cols-2 gap-1`} role="group" aria-label="Fundo">
              {(
                [
                  ["escuro", "Escuro"],
                  ["papel", "Papel"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  aria-pressed={prefs.tint === id}
                  onClick={() => set({ tint: id })}
                  className={`${OPTION} ${prefs.tint === id ? "bg-neutral-600 text-neutral-50" : "text-neutral-300"}`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className={`${CELL} grid grid-cols-3 gap-1`} role="group" aria-label="Espaçamento">
            {(
              [
                ["normal", "Normal"],
                ["espacado", "Espaçado"],
                ["amplo", "Amplo"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                aria-pressed={prefs.spacing === id}
                onClick={() => set({ spacing: id })}
                className={`${OPTION} ${prefs.spacing === id ? "bg-neutral-600 text-neutral-50" : "text-neutral-300"}`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className={`${CELL} grid grid-cols-2 gap-1`} role="group" aria-label="Largura da linha">
            {(
              [
                ["estreita", "Linhas curtas"],
                ["normal", "Linhas normais"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                aria-pressed={prefs.width === id}
                onClick={() => set({ width: id })}
                className={`${OPTION} ${prefs.width === id ? "bg-neutral-600 text-neutral-50" : "text-neutral-300"}`}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="px-2 pb-1 text-[12px] text-neutral-500">Fica salvo neste aparelho.</p>
        </div>
      )}
    </div>
  );
}
