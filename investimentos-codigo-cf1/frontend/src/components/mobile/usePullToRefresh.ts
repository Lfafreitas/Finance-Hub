import { useEffect, useState } from "react";

const THRESHOLD = 72;

function standalone(): boolean {
  const nav = navigator as Navigator & { standalone?: boolean };
  return nav.standalone === true || window.matchMedia?.("(display-mode: standalone)").matches === true;
}

/**
 * "Puxar para atualizar" no app da Tela de Início (lá o iOS não tem o
 * do Safari). Devolve quanto já foi puxado (0..1) para o indicador.
 */
export function usePullToRefresh(onRefresh: () => void, enabled = standalone()): number {
  const [pull, setPull] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let startY: number | null = null;
    let distance = 0;
    const start = (e: TouchEvent) => {
      startY = window.scrollY <= 0 ? e.touches[0].clientY : null;
      distance = 0;
    };
    const move = (e: TouchEvent) => {
      if (startY === null) return;
      distance = Math.max(0, e.touches[0].clientY - startY);
      setPull(Math.min(distance / THRESHOLD, 1));
    };
    const end = () => {
      if (startY !== null && distance >= THRESHOLD) onRefresh();
      startY = null;
      setPull(0);
    };
    window.addEventListener("touchstart", start, { passive: true });
    window.addEventListener("touchmove", move, { passive: true });
    window.addEventListener("touchend", end);
    return () => {
      window.removeEventListener("touchstart", start);
      window.removeEventListener("touchmove", move);
      window.removeEventListener("touchend", end);
    };
  }, [enabled, onRefresh]);
  return pull;
}
