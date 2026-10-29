import { useState } from "react";
import type { ReactNode } from "react";

import { PrivacyToggle } from "../PrivacyToggle";

// Barra lateral do computador, no jeito dos apps do Mac (Música, Mail):
// todas as telas à vista, agrupadas por livro, um clique para qualquer
// uma. No tablet (md) vira uma coluna só de ícones; os nomes aparecem
// do lg em diante. Cada grupo recolhe e lembra se estava recolhido.

export interface SidebarItem {
  id: string;
  label: string;
  icon: ReactNode;
  active: boolean;
  badge?: number;
  onSelect: () => void;
}

export interface SidebarGroup {
  id: string;
  title: string;
  items: SidebarItem[];
}

const COLLAPSED_KEY = "sidebar-collapsed-v1";

function readCollapsed(): string[] {
  try {
    const raw = localStorage.getItem(COLLAPSED_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function saveCollapsed(ids: string[]): void {
  try {
    localStorage.setItem(COLLAPSED_KEY, JSON.stringify(ids));
  } catch {
    // Sem armazenamento (aba privada): só não lembra.
  }
}

export function Sidebar({ groups, hidden }: { groups: SidebarGroup[]; hidden: boolean }) {
  const [collapsed, setCollapsed] = useState<string[]>(readCollapsed);

  function toggle(id: string) {
    const next = collapsed.includes(id) ? collapsed.filter((x) => x !== id) : [...collapsed, id];
    setCollapsed(next);
    saveCollapsed(next);
  }

  return (
    <aside
      className="sticky top-0 hidden h-dvh w-[72px] shrink-0 flex-col border-r border-neutral-800/80 bg-[#0d1215] md:flex lg:w-60"
      data-testid="sidebar"
    >
      <div className="flex h-16 items-center gap-2.5 px-5 lg:px-5">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="shrink-0">
          <path
            d="M3 17l5-5 4 3 8-9"
            stroke="var(--color-sky-400)"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path d="M3 21h18" stroke="var(--color-neutral-600)" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <span className="hidden text-[15px] font-semibold tracking-tight text-neutral-50 lg:inline">
          Dashboard Financeiro
        </span>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-4" aria-label="Navegação principal">
        {groups.map((group) => {
          const isCollapsed = collapsed.includes(group.id);
          const anyActive = group.items.some((item) => item.active);
          const titleId = `sidebar-${group.id}`;
          return (
            <div key={group.id} role="group" aria-labelledby={titleId} className="mt-4 first:mt-1">
              <button
                type="button"
                id={titleId}
                className="hidden w-full items-center justify-between rounded-md px-2 py-1 text-left text-[12px] font-semibold text-neutral-500 hover:text-neutral-300 lg:flex"
                aria-expanded={!isCollapsed}
                onClick={() => toggle(group.id)}
              >
                {group.title}
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                  className={`transition-transform duration-200 ${isCollapsed ? "-rotate-90" : ""}`}
                >
                  <path
                    d="m6 9 6 6 6-6"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              <div className="mx-2 mb-2 border-t border-neutral-800 lg:hidden" aria-hidden="true" />
              <ul className={`mt-1 space-y-0.5 ${isCollapsed ? "lg:hidden" : ""}`}>
                {group.items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      aria-current={item.active ? "page" : undefined}
                      title={item.label}
                      onClick={item.onSelect}
                      className={`group relative flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-[14px] transition-colors lg:py-1.5 ${
                        item.active
                          ? "bg-neutral-800 text-neutral-50"
                          : "text-neutral-400 hover:bg-neutral-900 hover:text-neutral-100"
                      }`}
                    >
                      <span
                        className={`shrink-0 transition-colors ${item.active ? "text-sky-400" : "text-neutral-500 group-hover:text-neutral-300"}`}
                      >
                        {item.icon}
                      </span>
                      <span className="sr-only truncate lg:not-sr-only">{item.label}</span>
                      {item.badge !== undefined && item.badge > 0 && (
                        <span
                          className="absolute right-1.5 top-1 min-w-4 rounded-full bg-red-500 px-1 text-center text-[10px] font-semibold leading-4 text-white lg:static lg:ml-auto lg:min-w-5 lg:text-[11px] lg:leading-5"
                          aria-label={`${item.badge} não lido(s)`}
                        >
                          {item.badge}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
              {isCollapsed && anyActive && (
                <p className="hidden px-2 text-[12px] text-neutral-500 lg:block">
                  {group.items.find((item) => item.active)?.label}
                </p>
              )}
            </div>
          );
        })}
      </nav>

      <div className="border-t border-neutral-800/80 p-3 [&>button]:ml-0 [&>button]:w-full [&>button]:justify-center lg:[&>button]:justify-start">
        <PrivacyToggle hidden={hidden} labelClass="hidden lg:inline" />
      </div>
    </aside>
  );
}

// --- Ícones da barra lateral (18 px, traço 1,7) ------------------------------

const s = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

function Glyph({ children }: { children: ReactNode }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      {children}
    </svg>
  );
}

const ICONS = {
  overview: (
    <Glyph>
      <path d="M3.5 10.5 12 3.5l8.5 7V20a1 1 0 0 1-1 1h-5v-6h-5v6h-5a1 1 0 0 1-1-1z" {...s} />
    </Glyph>
  ),
  analyses: (
    <Glyph>
      <path d="M4 20V12M10 20V7M16 20v-9M21 20H3" {...s} />
    </Glyph>
  ),
  news: (
    <Glyph>
      <path d="M4 4.5h12.5v14a2 2 0 0 0 2 2H6a2 2 0 0 1-2-2z" {...s} />
      <path d="M16.5 8.5H20v10a2 2 0 0 1-2 2M7.5 8h5.5M7.5 11.5h5.5M7.5 15h3.5" {...s} />
    </Glyph>
  ),
  list: (
    <Glyph>
      <path d="M9 6h11M9 12h11M9 18h11" {...s} />
      <circle cx="4.5" cy="6" r="1" fill="currentColor" />
      <circle cx="4.5" cy="12" r="1" fill="currentColor" />
      <circle cx="4.5" cy="18" r="1" fill="currentColor" />
    </Glyph>
  ),
  import: (
    <Glyph>
      <path d="M12 3.5v11m0 0-4-4m4 4 4-4" {...s} />
      <path d="M4 14.5V18a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3.5" {...s} />
    </Glyph>
  ),
  prices: (
    <Glyph>
      <path d="M3 17l5-5 4 3 8-9" {...s} />
      <path d="M15 6h5v5" {...s} />
    </Glyph>
  ),
  reconcile: (
    <Glyph>
      <path d="M4 12a8 8 0 0 1 13.7-5.6L20 8.5M20 4v4.5h-4.5" {...s} />
      <path d="M20 12a8 8 0 0 1-13.7 5.6L4 15.5M4 20v-4.5h4.5" {...s} />
    </Glyph>
  ),
  wallet: (
    <Glyph>
      <rect x="3" y="6" width="18" height="14" rx="2.5" {...s} />
      <path d="M5.5 6 15 3.5a1.5 1.5 0 0 1 1.9 1.4V6" {...s} />
      <circle cx="16.5" cy="13" r="1.3" fill="currentColor" />
    </Glyph>
  ),
  classify: (
    <Glyph>
      <path d="M3.5 12.6V5a1.5 1.5 0 0 1 1.5-1.5h7.6L20.5 11.4a1.5 1.5 0 0 1 0 2.1l-7 7a1.5 1.5 0 0 1-2.1 0z" {...s} />
      <circle cx="8" cy="8" r="1.4" fill="currentColor" />
    </Glyph>
  ),
  folder: (
    <Glyph>
      <path
        d="M3.5 7a1.5 1.5 0 0 1 1.5-1.5h4.4l2 2.2H19a1.5 1.5 0 0 1 1.5 1.5V18a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 18z"
        {...s}
      />
    </Glyph>
  ),
  rules: (
    <Glyph>
      <path d="M4 6h10M4 12h6M4 18h10" {...s} />
      <path d="m15 15 2.5 2.5L22 13" {...s} />
      <circle cx="18" cy="6" r="2" {...s} />
    </Glyph>
  ),
  notes: (
    <Glyph>
      <path d="M5 3.5h10l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-12A1.5 1.5 0 0 1 4 19V5a1.5 1.5 0 0 1 1-1.5z" {...s} />
      <path d="M8 10h8M8 13.5h8M8 17h5" {...s} />
    </Glyph>
  ),
  registry: (
    <Glyph>
      <path d="M3.5 20.5h17M5 20.5V9l7-5 7 5v11.5M9 20.5v-6h6v6" {...s} />
    </Glyph>
  ),
  security: (
    <Glyph>
      <rect x="5" y="10.5" width="14" height="10" rx="2" {...s} />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" {...s} />
    </Glyph>
  ),
};

export type SidebarIconName = keyof typeof ICONS;

export function SidebarIcon({ name }: { name: SidebarIconName }) {
  return ICONS[name];
}
