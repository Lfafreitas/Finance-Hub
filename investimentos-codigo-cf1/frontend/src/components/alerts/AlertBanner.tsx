import { useCallback, useEffect, useState } from "react";

import type { AlertIndex } from "../../api/insights";
import { getAlerts, markAllAlertsRead } from "../../api/insights";

const POLL_MS = 5 * 60 * 1000;

/**
 * Faixa no topo quando a checagem de hora em hora do Claude encontrou
 * uma notícia séria que você ainda não viu. Some quando tudo é lido.
 */
export function AlertBanner({ onOpen }: { onOpen: () => void }) {
  const [index, setIndex] = useState<AlertIndex | null>(null);

  const load = useCallback(() => {
    getAlerts(2)
      .then(setIndex)
      .catch(() => {
        // Sem alertas legíveis, a faixa só não aparece (o backend tem a sua faixa).
      });
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, POLL_MS);
    window.addEventListener("alerts-changed", load);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("alerts-changed", load);
    };
  }, [load]);

  const unread = index?.alerts.filter((a) => !a.read) ?? [];
  if (unread.length === 0) return null;
  const latest = unread[0].alert;
  const critical = unread.some((a) => a.alert.severity === "CRITICA");
  // Faixa escura com um traço colorido à esquerda: chama atenção sem
  // pintar o topo inteiro; o rótulo diz a gravidade (não só a cor).
  const tone = critical
    ? "bg-red-950/40 shadow-[inset_4px_0_0_var(--color-red-400)]"
    : "bg-neutral-900 shadow-[inset_4px_0_0_var(--color-amber-300)]";
  const labelTone = critical ? "text-red-300" : "text-amber-300";

  return (
    <div
      role="alert"
      className={`border-b border-neutral-800 px-6 py-2.5 text-sm text-neutral-100 ${tone}`}
      data-testid="alert-banner"
    >
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-1">
        <span className={`font-semibold ${labelTone}`}>
          {critical ? "Alerta crítico" : "Alerta"}
          {latest.tickers.length > 0 ? ` (${latest.tickers.join(", ")})` : ""}:
        </span>
        <span className="min-w-[14rem] flex-1">{latest.title}</span>
        {unread.length > 1 && <span className="text-xs opacity-80">+{unread.length - 1} não lido(s)</span>}
        <button type="button" className="font-medium text-sky-300 underline-offset-4 hover:underline" onClick={onOpen}>
          Ver detalhes
        </button>
        <button
          type="button"
          className="text-xs text-neutral-400 hover:text-neutral-100"
          onClick={() =>
            markAllAlertsRead()
              .then(setIndex)
              .then(() => window.dispatchEvent(new Event("alerts-changed")))
              .catch(() => undefined)
          }
        >
          Marcar como lido
        </button>
      </div>
    </div>
  );
}
