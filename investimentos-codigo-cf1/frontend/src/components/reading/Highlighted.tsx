import { useContext } from "react";
import type { ReactNode } from "react";

import { QuotesContext } from "../../lib/highlights";

/**
 * Texto com os trechos que o leitor destacou marcados (<mark>). Só marca
 * trecho que aparece inteiro no texto; o resto fica como está.
 */
export function Highlighted({ text, quotes }: { text: string; quotes: string[] }): ReactNode {
  const found = quotes
    .map((q) => q.trim())
    .filter((q) => q.length >= 3)
    .map((q) => ({ q, at: text.indexOf(q) }))
    .filter((m) => m.at >= 0)
    .sort((a, b) => a.at - b.at);
  if (found.length === 0) return text;
  const parts: ReactNode[] = [];
  let cursor = 0;
  for (const { q, at } of found) {
    if (at < cursor) continue; // sobreposto a um já marcado
    if (at > cursor) parts.push(text.slice(cursor, at));
    parts.push(<mark key={at}>{q}</mark>);
    cursor = at + q.length;
  }
  if (cursor < text.length) parts.push(text.slice(cursor));
  return <>{parts}</>;
}

/** `Highlighted` com os trechos do contexto do Jornal. */
export function Hl({ text }: { text: string }) {
  const quotes = useContext(QuotesContext);
  return <Highlighted text={text} quotes={quotes} />;
}
