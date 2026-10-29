// Peças comuns dos gráficos interativos: o "scrub" (passar o mouse ou o
// dedo sobre a linha troca o número grande do topo pelo daquele dia, como
// no app Ações do iPhone), a linha-guia, o ponto ativo e a animação de
// entrada. Quem pediu "reduzir movimento" vê tudo parado.

import { useCallback, useState } from "react";
import type { KeyboardEvent } from "react";
import type { MouseHandlerDataParam } from "recharts";

import { prefersReducedMotion } from "../../lib/motion";
import { AXIS_TEXT_COLOR } from "../../lib/chartColors";

/** Fundo dos painéis: o anel do ponto ativo usa a mesma cor (separa da linha). */
export const SURFACE = "#141b1f";

/** Linha vertical que segue o mouse/dedo. */
export const CROSSHAIR = { stroke: AXIS_TEXT_COLOR, strokeWidth: 1, strokeDasharray: "3 3" };

export function activeDot(color: string) {
  return { r: 5, fill: color, stroke: SURFACE, strokeWidth: 2 };
}

/** Animação de entrada (e de troca de período) dos gráficos do Recharts. */
export function chartMotion(): { isAnimationActive: boolean; animationDuration: number; animationEasing: "ease-out" } {
  const active = import.meta.env.MODE !== "test" && !prefersReducedMotion();
  return { isAnimationActive: active, animationDuration: 650, animationEasing: "ease-out" };
}

/** Índice do ponto sob o mouse, a partir do estado que o Recharts entrega. */
export function scrubIndex(
  state: Pick<MouseHandlerDataParam, "activeTooltipIndex" | "isTooltipActive"> | null | undefined,
  length: number,
): number | null {
  if (!state || !state.isTooltipActive) return null;
  const index = Number(state.activeTooltipIndex);
  if (!Number.isInteger(index) || index < 0 || index >= length) return null;
  return index;
}

/** Próximo índice ao usar as setas do teclado (← → Home End); null = sair. */
export function stepIndex(current: number | null, key: string, length: number): number | null | undefined {
  if (length === 0) return undefined;
  const last = length - 1;
  switch (key) {
    // Sem foco, o gráfico mostra o último ponto: a seta parte dele.
    case "ArrowLeft":
      return Math.max(0, (current ?? last) - 1);
    case "ArrowRight":
      return Math.min(last, (current ?? last) + 1);
    case "Home":
      return 0;
    case "End":
      return last;
    case "Escape":
      return null;
    default:
      return undefined;
  }
}

/**
 * Estado do scrub de um gráfico: `index` é o ponto em foco (null = o
 * último, o "hoje"). `chartProps` vai no gráfico do Recharts e
 * `keyboardProps` no contêiner, para navegar pelas setas.
 */
export function useScrub(length: number) {
  const [index, setIndex] = useState<number | null>(null);
  const onMouseMove = useCallback(
    (state: MouseHandlerDataParam) => {
      const next = scrubIndex(state, length);
      if (next !== null) setIndex(next);
    },
    [length],
  );
  const clear = useCallback(() => setIndex(null), []);
  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      const next = stepIndex(index, event.key, length);
      if (next === undefined) return;
      event.preventDefault();
      setIndex(next);
    },
    [index, length],
  );
  return {
    index,
    setIndex,
    focus: index ?? (length > 0 ? length - 1 : null),
    chartProps: { onMouseMove, onMouseLeave: clear, onTouchEnd: clear },
    keyboardProps: { tabIndex: 0, onKeyDown, onBlur: clear },
  };
}

/** Tooltip vazio: a leitura fica no topo do gráfico; só a linha-guia aparece. */
export function NoTooltip() {
  return null;
}
