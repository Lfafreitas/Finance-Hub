// Modo privacidade: esconde valores em dinheiro e quantidades na tela
// (percentuais continuam visíveis). A escolha fica neste navegador.
//
// Todo dinheiro passa por `lib/formatCurrency`, que consulta `isPrivate()`;
// o App assina `subscribePrivacy` e redesenha a árvore inteira quando muda.

const KEY = "dashboard:privacy";
const listeners = new Set<() => void>();

function read(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

let hidden = read();

export function isPrivate(): boolean {
  return hidden;
}

export function setPrivate(value: boolean): void {
  hidden = value;
  try {
    window.localStorage.setItem(KEY, value ? "1" : "0");
  } catch {
    // Sem armazenamento (janela anônima): vale só até fechar a aba.
  }
  listeners.forEach((listener) => listener());
}

export function subscribePrivacy(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export const MASK = "•••••";

/** `title` com o valor exato do backend — some no modo privacidade. */
export function exactTitle(value: string | null | undefined): string | undefined {
  return hidden || value == null ? undefined : value;
}
