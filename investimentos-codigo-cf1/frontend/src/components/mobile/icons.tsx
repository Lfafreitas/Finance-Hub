// Ícones da barra de abas, no traço dos SF Symbols (linha 1,8, cantos
// arredondados). Preenchidos quando a aba está ativa, como no iOS.

type IconProps = { active: boolean };

const stroke = { stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;

export function HomeIcon({ active }: IconProps) {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M3.5 10.5 12 3.5l8.5 7V20a1 1 0 0 1-1 1h-5v-6h-5v6h-5a1 1 0 0 1-1-1z"
        fill={active ? "currentColor" : "none"}
        {...stroke}
      />
    </svg>
  );
}

export function ChartIcon({ active }: IconProps) {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="4" y="12" width="4" height="8" rx="1" fill={active ? "currentColor" : "none"} {...stroke} />
      <rect x="10" y="7" width="4" height="13" rx="1" fill={active ? "currentColor" : "none"} {...stroke} />
      <rect x="16" y="3.5" width="4" height="16.5" rx="1" fill={active ? "currentColor" : "none"} {...stroke} />
    </svg>
  );
}

export function NewsIcon({ active }: IconProps) {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 4.5h12.5v14a2 2 0 0 0 2 2H6a2 2 0 0 1-2-2z" fill={active ? "currentColor" : "none"} {...stroke} />
      <path d="M16.5 8.5H20v10a2 2 0 0 1-2 2" fill="none" {...stroke} />
      <path d="M7 8h6.5M7 11.5h6.5M7 15h4" {...stroke} stroke={active ? "var(--color-neutral-950)" : "currentColor"} />
    </svg>
  );
}

export function WalletIcon({ active }: IconProps) {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="6" width="18" height="14" rx="2.5" fill={active ? "currentColor" : "none"} {...stroke} />
      <path d="M5.5 6 15 3.5a1.5 1.5 0 0 1 1.9 1.4V6" fill="none" {...stroke} />
      <circle cx="16.5" cy="13" r="1.4" fill={active ? "var(--color-neutral-950)" : "currentColor"} />
    </svg>
  );
}

export function MoreIcon({ active }: IconProps) {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill={active ? "currentColor" : "none"} {...stroke} />
      {[8, 12, 16].map((cx) => (
        <circle key={cx} cx={cx} cy="12" r="1.3" fill={active ? "var(--color-neutral-950)" : "currentColor"} />
      ))}
    </svg>
  );
}

export function ChevronRight() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
      <path d="m9 5 7 7-7 7" fill="none" {...stroke} strokeWidth={2.4} />
    </svg>
  );
}

export function ChevronLeft() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
      <path d="m15 4-8 8 8 8" fill="none" {...stroke} strokeWidth={2.4} />
    </svg>
  );
}
