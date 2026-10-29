export interface AttentionItem {
  key: string;
  text: string;
  actionLabel?: string;
  onAction?: () => void;
}

/**
 * O que pede uma ação sua agora, numa lista curta no topo. Cada item diz
 * o que é e leva direto para onde se resolve.
 */
export function AttentionList({ items }: { items: AttentionItem[] }) {
  if (items.length === 0) return null;
  return (
    <ul
      className="divide-y divide-neutral-800 rounded-xl border border-neutral-800 bg-neutral-900/50"
      aria-label="Pede sua atenção"
      data-testid="attention-list"
    >
      {items.map((item) => (
        <li
          key={item.key}
          className="flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm text-neutral-200"
          data-testid={`attention-${item.key}`}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            className="shrink-0 text-amber-300"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
            <path d="M12 7.5v5.5M12 16.5v.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <span className="flex-1">{item.text}</span>
          {item.actionLabel && item.onAction && (
            <button
              type="button"
              className="font-medium text-sky-300 underline-offset-4 hover:underline"
              onClick={item.onAction}
            >
              {item.actionLabel}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
