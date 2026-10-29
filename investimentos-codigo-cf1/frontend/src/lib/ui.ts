// Classes Tailwind compartilhadas pelos formulários das telas de
// trabalho (lançamentos, importação, cadastros).

// No celular, campos e botões têm pelo menos 44 pt de altura (alvo de
// toque do iOS) e texto de 16 px nos campos (menos que isso, o Safari dá
// zoom ao tocar). No computador, o tamanho compacto de sempre.
export const INPUT_CLASS =
  "w-full min-h-11 rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-base text-neutral-100 disabled:opacity-50 md:min-h-0 md:rounded-md md:text-sm";

export const BUTTON_CLASS =
  "min-h-11 rounded-lg border border-neutral-700 px-4 py-2 text-[15px] text-neutral-100 transition-colors hover:border-neutral-600 hover:bg-neutral-800 active:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40 md:min-h-0 md:rounded-md md:px-3 md:text-sm";

export const PANEL_CLASS = "rounded-xl border border-neutral-800 bg-neutral-900 p-5";

/** Título de seção: o que separa as partes da tela (não uma caixa). */
export const SECTION_TITLE_CLASS = "text-[15px] font-semibold tracking-tight text-neutral-100";

export const LABEL_CLASS = "mb-1 block text-xs text-neutral-400";

/** Campo que ocupa só o que precisa (filtros e ações em linha). */
export const COMPACT_INPUT_CLASS =
  "min-h-11 rounded-lg border border-neutral-800 bg-neutral-950 px-2 py-1.5 text-base text-neutral-100 disabled:opacity-50 md:min-h-0 md:rounded-md md:text-sm";

/** Título da tela: grande e em negrito no celular (o "large title" do iOS). */
export const PAGE_TITLE_TEXT_CLASS =
  "text-[34px] font-bold leading-tight tracking-tight text-neutral-50 md:text-[30px]";
export const PAGE_TITLE_CLASS = `mb-5 md:mb-6 ${PAGE_TITLE_TEXT_CLASS}`;
