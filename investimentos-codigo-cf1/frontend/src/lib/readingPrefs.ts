// Preferências de leitura do Jornal, guardadas NESTE aparelho (o iPhone e
// o computador podem ter as suas). Pensadas para dislexia: fontes feitas
// para legibilidade, letras e palavras mais espaçadas, linhas mais curtas,
// fundo menos contrastante.

import type { CSSProperties } from "react";

export type ReadingFont = "padrao" | "atkinson" | "lexend" | "opendyslexic";
export type Spacing = "normal" | "espacado" | "amplo";
export type Tint = "escuro" | "papel";

export interface ReadingPrefs {
  font: ReadingFont;
  size: number; // px do texto corrido
  spacing: Spacing;
  width: "estreita" | "normal";
  tint: Tint;
}

export const DEFAULT_PREFS: ReadingPrefs = {
  font: "padrao",
  size: 17,
  spacing: "normal",
  width: "normal",
  tint: "escuro",
};
export const MIN_SIZE = 14;
export const MAX_SIZE = 26;

export const FONTS: { id: ReadingFont; label: string; family: string; hint: string }[] = [
  { id: "padrao", label: "Padrão", family: "var(--font-sans)", hint: "a do app" },
  {
    id: "atkinson",
    label: "Atkinson",
    family: '"Atkinson Hyperlegible Next", var(--font-sans)',
    hint: "letras bem diferentes entre si",
  },
  { id: "lexend", label: "Lexend", family: '"Lexend", var(--font-sans)', hint: "leitura mais fluida" },
  {
    id: "opendyslexic",
    label: "OpenDyslexic",
    family: '"OpenDyslexic", var(--font-sans)',
    hint: "feita para dislexia",
  },
];

const SPACING: Record<Spacing, { line: number; letter: string; word: string }> = {
  normal: { line: 1.6, letter: "0", word: "0" },
  espacado: { line: 1.85, letter: "0.02em", word: "0.08em" },
  amplo: { line: 2.1, letter: "0.05em", word: "0.16em" },
};

const KEY = "reading-prefs-v1";

export function loadPrefs(): ReadingPrefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<ReadingPrefs>;
    const merged = { ...DEFAULT_PREFS, ...parsed };
    if (!FONTS.some((f) => f.id === merged.font)) merged.font = DEFAULT_PREFS.font;
    if (!(merged.spacing in SPACING)) merged.spacing = DEFAULT_PREFS.spacing;
    merged.size = clampSize(Number(merged.size));
    return merged;
  } catch {
    return DEFAULT_PREFS;
  }
}

export function savePrefs(prefs: ReadingPrefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    // Sem armazenamento (aba privada): vale só nesta abertura.
  }
}

export function clampSize(size: number): number {
  if (!Number.isFinite(size)) return DEFAULT_PREFS.size;
  return Math.min(MAX_SIZE, Math.max(MIN_SIZE, Math.round(size)));
}

/** Variáveis CSS que a classe `.reading` usa. */
export function readingStyle(prefs: ReadingPrefs): CSSProperties {
  const font = FONTS.find((f) => f.id === prefs.font) ?? FONTS[0];
  const spacing = SPACING[prefs.spacing];
  return {
    "--read-font": font.family,
    "--read-size": `${prefs.size}px`,
    "--read-line": String(spacing.line),
    "--read-letter": spacing.letter,
    "--read-word": spacing.word,
    "--read-width": prefs.width === "estreita" ? "58ch" : "70ch",
  } as CSSProperties;
}
