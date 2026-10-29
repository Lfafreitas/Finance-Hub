import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { ChevronLeft } from "./icons";

/**
 * Barra de navegação do iPhone: some enquanto o título grande da tela
 * está à vista e aparece (com o título pequeno no centro) ao rolar —
 * o "large title" do iOS. Com `back`, mostra o "‹ Mais" à esquerda.
 */
export function CompactBar({
  title,
  back,
  trailing,
}: {
  title: string;
  back?: { label: string; onBack: () => void };
  trailing?: ReactNode;
}) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div
      className={`sticky top-[env(safe-area-inset-top)] z-20 grid h-11 grid-cols-[1fr_auto_1fr] items-center px-2 transition-colors md:hidden ${
        scrolled ? "border-b border-neutral-800/80 bg-neutral-950/85 backdrop-blur-xl" : "border-b border-transparent"
      }`}
      data-testid="compact-bar"
    >
      <div className="justify-self-start">
        {back && (
          <button
            type="button"
            onClick={back.onBack}
            className="flex h-11 items-center gap-0.5 pr-3 text-[17px] text-sky-400"
          >
            <ChevronLeft />
            {back.label}
          </button>
        )}
      </div>
      <p
        className={`max-w-[60vw] truncate text-[17px] font-semibold text-neutral-50 transition-opacity ${
          scrolled ? "opacity-100" : "opacity-0"
        }`}
        aria-hidden={!scrolled}
      >
        {title}
      </p>
      <div className="justify-self-end">{trailing}</div>
    </div>
  );
}
