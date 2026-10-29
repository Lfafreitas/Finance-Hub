// Movimento do app: poucos e com propósito (abertura, troca de tela,
// controle que desliza). Quem pediu "reduzir movimento" no sistema não
// vê nenhum.

import { flushSync } from "react-dom";

export function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
  } catch {
    return false;
  }
}

export type NavDirection = "push" | "pop" | "fade";

/**
 * Troca de tela com a View Transitions API (Safari 18+, Chrome): a tela
 * antiga sai e a nova entra; "push" entra pela direita (abrir algo da
 * lista Mais), "pop" volta pela esquerda, "fade" é a troca de aba.
 * Sem suporte (ou com movimento reduzido), só troca.
 */
export function navigate(update: () => void, direction: NavDirection = "fade"): void {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
  if (typeof doc.startViewTransition !== "function" || prefersReducedMotion()) {
    update();
    return;
  }
  document.documentElement.dataset.nav = direction;
  doc.startViewTransition(() => {
    flushSync(update);
  });
}

const INTRO_KEY = "dashboard-intro-shown";

/** A abertura animada roda uma vez por sessão (não a cada troca de aba). */
export function shouldPlayIntro(): boolean {
  if (prefersReducedMotion()) return false;
  try {
    if (sessionStorage.getItem(INTRO_KEY)) return false;
    sessionStorage.setItem(INTRO_KEY, "1");
  } catch {
    // Sem sessionStorage (aba privada): toca, e tudo bem tocar de novo.
  }
  return true;
}

/** Curva de saída suave (0..1 → 0..1), para números que sobem até o valor. */
export function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - Math.min(Math.max(t, 0), 1), 3);
}
