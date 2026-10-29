import { useCallback, useEffect, useState } from "react";

import type { AlertIndex } from "../../api/insights";
import { getAlerts, markAlertRead, markAllAlertsRead } from "../../api/insights";
import { describeApiError } from "../../lib/apiErrors";
import { formatRefreshTime } from "../../lib/analytics";
import { PANEL_CLASS } from "../../lib/ui";
import { SafeLink } from "../insights/SafeLink";

/**
 * Alertas da checagem de hora em hora dos últimos 7 dias. Na maioria
 * dos dias a lista fica vazia — é o esperado.
 */
export function AlertList({ compactWhenEmpty = false }: { compactWhenEmpty?: boolean } = {}) {
  const [index, setIndex] = useState<AlertIndex | null>(null);
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback((next: AlertIndex) => {
    setIndex(next);
    window.dispatchEvent(new Event("alerts-changed"));
  }, []);

  useEffect(() => {
    getAlerts(7)
      .then(setIndex)
      .catch((err: unknown) => setError(describeApiError(err)));
  }, []);

  if (error) return <p className="text-sm text-amber-300">Não foi possível ler os alertas: {error}</p>;
  if (index === null) return null;
  if (compactWhenEmpty && index.alerts.length === 0) {
    return (
      <p className="text-xs text-neutral-500" data-testid="no-alerts">
        Nenhum alerta sério nos últimos 7 dias (a checagem roda de hora em hora nos dias úteis).
      </p>
    );
  }

  return (
    <section className={PANEL_CLASS} aria-labelledby="alerts-title" data-testid="alert-list">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="alerts-title" className="text-[15px] font-semibold tracking-tight text-neutral-100">
          Alertas dos últimos 7 dias
        </h2>
        {index.unread_count > 0 && (
          <button
            type="button"
            className="text-xs text-neutral-400 underline hover:text-neutral-200"
            onClick={() =>
              markAllAlertsRead()
                .then(apply)
                .catch(() => undefined)
            }
          >
            Marcar todos como lidos
          </button>
        )}
      </div>
      {index.alerts.length === 0 ? (
        <p className="text-sm text-neutral-500" data-testid="no-alerts">
          Nenhuma notícia séria nos últimos 7 dias. A checagem roda de hora em hora nos dias úteis e só avisa quando
          algo pode mexer de verdade com a carteira.
        </p>
      ) : (
        <ul className="space-y-4">
          {index.alerts.map(({ alert, read }) => (
            <li
              key={alert.id}
              data-testid={`alert-${alert.id}`}
              className={`border-l-2 pl-3 ${
                alert.severity === "CRITICA" ? "border-red-500" : "border-amber-500"
              } ${read ? "opacity-70" : ""}`}
            >
              <p className="text-xs text-neutral-500">
                {alert.severity === "CRITICA" ? "Crítico" : "Alto impacto"}, {formatRefreshTime(alert.detected_at)}
                {alert.tickers.length > 0 && `, ${alert.tickers.join(", ")}`}
                {!read && <span className="ml-2 rounded bg-neutral-800 px-1.5 py-0.5 text-neutral-200">novo</span>}
              </p>
              <p className="mt-1 font-medium text-neutral-100">{alert.title}</p>
              <p className="mt-1 text-sm text-neutral-300">{alert.summary}</p>
              <p className="mt-1 text-sm text-neutral-400">Para a sua carteira: {alert.why_it_matters}</p>
              <p className="mt-1 flex flex-wrap items-center gap-x-3 text-xs">
                {alert.sources.map((source) => (
                  <SafeLink key={source.url} url={source.url}>
                    {source.title}
                  </SafeLink>
                ))}
                {!read && (
                  <button
                    type="button"
                    className="text-neutral-400 underline hover:text-neutral-200"
                    onClick={() =>
                      markAlertRead(alert.id)
                        .then(apply)
                        .catch(() => undefined)
                    }
                  >
                    Marcar como lido
                  </button>
                )}
              </p>
            </li>
          ))}
        </ul>
      )}
      {index.invalid_files.length > 0 && (
        <p className="mt-3 text-xs text-amber-300">
          {index.invalid_files.length} arquivo(s) de alerta recusado(s):{" "}
          {index.invalid_files.map((f) => f.file_name).join(", ")}
        </p>
      )}
    </section>
  );
}
