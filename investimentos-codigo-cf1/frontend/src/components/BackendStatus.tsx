import { useEffect, useState } from "react";

import { getHealth } from "../api/client";

/** De quanto em quanto tempo o app confere se o backend responde. */
export const HEALTH_EVERY_MS = 30_000;

/**
 * Faixa no topo quando o backend local não responde: sem ela, cada tela
 * mostraria o próprio erro sem dizer a causa comum.
 */
export function BackendStatus() {
  const [down, setDown] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      getHealth()
        .then(() => {
          if (!cancelled) setDown(false);
        })
        .catch(() => {
          if (!cancelled) setDown(true);
        });
    };
    check();
    const timer = window.setInterval(check, HEALTH_EVERY_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  if (!down) return null;
  return (
    <div className="border-b border-red-900 bg-red-950/60 px-6 py-2 text-sm text-red-200" role="alert" data-testid="backend-down">
      <div className="mx-auto max-w-7xl">
        O backend não está respondendo em 127.0.0.1:8000. Ligue o uvicorn (na pasta backend) — os números da tela podem
        estar desatualizados.
      </div>
    </div>
  );
}
