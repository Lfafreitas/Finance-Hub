import { useEffect, useState } from "react";

import { easeOutCubic, prefersReducedMotion } from "./motion";

// Cada número conta uma vez por abertura do app (não a cada troca de aba).
const played = new Set<string>();

function animate(key: string): boolean {
  return (
    import.meta.env.MODE !== "test" &&
    !played.has(key) &&
    !prefersReducedMotion() &&
    typeof requestAnimationFrame === "function"
  );
}

/**
 * O número sobe até o valor na primeira vez que aparece (abertura do
 * dashboard). Depois disso, mudanças aparecem direto: dado financeiro não
 * fica "contando" toda vez que atualiza.
 */
export function useCountUp(key: string, target: number, ms = 800): number {
  const [animating] = useState(() => animate(key));
  const [value, setValue] = useState(0);
  const [done, setDone] = useState(!animating);

  useEffect(() => {
    if (!animating) return;
    played.add(key);
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = easeOutCubic((now - start) / ms);
      setValue(target * t);
      if (t < 1) frame = requestAnimationFrame(tick);
      else setDone(true);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [animating, key, target, ms]);

  return done ? target : value;
}
