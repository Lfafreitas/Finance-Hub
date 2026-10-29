import type { ReactElement } from "react";

export interface TabItem {
  id: string;
  label: string;
  icon: (props: { active: boolean }) => ReactElement;
  badge?: number;
}

/**
 * Barra de abas do iPhone no desenho mais novo do iOS: uma cápsula de
 * vidro flutuando sobre o conteúdo, com a aba ativa marcada por uma
 * pílula que desliza até ela. Respeita a área do indicador de início.
 */
export function TabBar({
  tabs,
  active,
  onSelect,
}: {
  tabs: TabItem[];
  active: string;
  onSelect: (id: string) => void;
}) {
  const index = Math.max(
    0,
    tabs.findIndex((t) => t.id === active),
  );
  return (
    <nav
      aria-label="Abas"
      className="pointer-events-none fixed inset-x-0 bottom-0 z-30 px-3 pb-[max(10px,env(safe-area-inset-bottom))] md:hidden"
      data-testid="tab-bar"
    >
      <div className="pointer-events-auto relative mx-auto max-w-md rounded-full border border-white/10 bg-neutral-900/90 p-1 shadow-[0_10px_30px_rgba(0,0,0,0.55),inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-2xl backdrop-saturate-150">
        <span
          aria-hidden="true"
          className="absolute inset-y-1 left-1 rounded-full bg-white/[0.09] transition-transform duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)]"
          style={{ width: `calc((100% - 8px) / ${tabs.length})`, transform: `translateX(${index * 100}%)` }}
        />
        <ul className="relative flex">
          {tabs.map((tab) => {
            const isActive = tab.id === active;
            const Icon = tab.icon;
            return (
              <li key={tab.id} className="flex-1">
                <button
                  type="button"
                  onClick={() => onSelect(tab.id)}
                  aria-current={isActive ? "page" : undefined}
                  className={`relative flex h-[54px] w-full flex-col items-center justify-center gap-0.5 rounded-full text-[10px] font-medium transition-[color,transform] duration-200 active:scale-[0.92] ${
                    isActive ? "text-sky-400" : "text-neutral-400"
                  }`}
                >
                  <Icon active={isActive} />
                  {tab.label}
                  {tab.badge ? (
                    <span
                      className="absolute left-1/2 top-1 ml-2 min-w-[18px] rounded-full bg-red-500 px-1 text-center text-[11px] font-semibold leading-[18px] text-white"
                      aria-label={`${tab.badge} não lido(s)`}
                    >
                      {tab.badge > 9 ? "9+" : tab.badge}
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}
