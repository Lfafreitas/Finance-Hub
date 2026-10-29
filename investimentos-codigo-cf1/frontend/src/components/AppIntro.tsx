import { useEffect, useState } from "react";

import { shouldPlayIntro } from "../lib/motion";

/**
 * Abertura do app (uma vez por sessão): o ícone se desenha — a linha
 * sobe, o ponto acende — e a cortina se abre enquanto o dashboard sobe
 * por baixo. Some sozinha em ~1,4 s; com "reduzir movimento", não existe.
 */
export function AppIntro() {
  const [play] = useState(shouldPlayIntro);
  const [gone, setGone] = useState(false);
  useEffect(() => {
    if (!play) return;
    // O dashboard começa a subir enquanto a cortina se abre.
    const root = document.documentElement.style;
    root.setProperty("--reveal-base", "950ms");
    const timer = window.setTimeout(() => root.removeProperty("--reveal-base"), 3000);
    return () => window.clearTimeout(timer);
  }, [play]);
  if (!play || gone) return null;
  return (
    <div
      className="intro-overlay fixed inset-0 z-[90] flex items-center justify-center bg-neutral-950"
      onAnimationEnd={(e) => {
        if (e.animationName === "intro-leave") setGone(true);
      }}
      aria-hidden="true"
      data-testid="app-intro"
    >
      <svg width="88" height="88" viewBox="0 0 512 512">
        <rect width="512" height="512" rx="112" fill="#141b20" />
        <path d="M112 400h288" stroke="#24313a" strokeWidth="20" strokeLinecap="round" />
        <path
          className="intro-line"
          d="M112 336l96-88 80 48 112-136"
          fill="none"
          stroke="#8fc1e3"
          strokeWidth="40"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle className="intro-dot" cx="400" cy="160" r="30" fill="#4cc38a" />
      </svg>
    </div>
  );
}
