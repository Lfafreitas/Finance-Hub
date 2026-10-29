import type { ReactNode } from "react";

import { ChevronRight } from "./icons";

export interface MoreItem {
  id: string;
  label: string;
  detail?: string;
  onSelect: () => void;
}

export interface MoreGroup {
  title: string;
  items: MoreItem[];
}

/** Lista agrupada do iOS (Ajustes): grupos com cantos arredondados. */
export function MoreMenu({ groups, footer }: { groups: MoreGroup[]; footer?: ReactNode }) {
  return (
    <div className="space-y-7 px-4 pb-8" data-testid="more-menu">
      <h1 className="pt-1 text-[34px] font-bold leading-tight tracking-tight text-neutral-50">Mais</h1>
      {groups.map((group) => (
        <section key={group.title} aria-label={group.title}>
          <h2 className="mb-1.5 px-4 text-[13px] text-neutral-500">{group.title}</h2>
          <ul className="divide-y divide-neutral-800 overflow-hidden rounded-xl bg-neutral-900">
            {group.items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={item.onSelect}
                  className="flex min-h-11 w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-[17px] text-neutral-100 active:bg-neutral-800"
                >
                  <span>{item.label}</span>
                  <span className="flex items-center gap-2 text-[15px] text-neutral-500">
                    {item.detail}
                    <ChevronRight />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
      {footer}
    </div>
  );
}
