import { useCallback, useEffect, useRef, useState } from "react";

import type { PortfolioAnalytics, QuoteRefreshResult } from "../api/analytics";
import { getPortfolioAnalytics, refreshQuotes } from "../api/analytics";
import { writeSnapshot } from "../api/insights";
import { getPortfolios } from "../api/client";
import type { PortfolioRead } from "../api/types";
import { ConcentrationPanel } from "../components/analytics/ConcentrationPanel";
import { ContributionsPanel } from "../components/analytics/ContributionsPanel";
import { ScenariosPanel } from "../components/analytics/ScenariosPanel";
import { PortfolioSelector } from "../components/PortfolioSelector";
import { AUTO_REFRESH_MS, formatRefreshTime, quotesAreStale } from "../lib/analytics";
import { describeApiError } from "../lib/apiErrors";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS, PANEL_CLASS } from "../lib/ui";

type State = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: PortfolioAnalytics };

/**
 * Análises da carteira: cenários até uma data, ritmo de aporte e
 * concentração, por moeda. As cotações são buscadas sozinhas ao abrir
 * a tela (se tiverem mais de 15 minutos) e a cada 15 minutos enquanto
 * ela estiver aberta; os números se recalculam a cada busca.
 */
export function Analyses() {
  const [portfolios, setPortfolios] = useState<PortfolioRead[]>([]);
  const [portfolioId, setPortfolioId] = useState<string | null>(null);
  const [until, setUntil] = useState("");
  const [currency, setCurrency] = useState<string | null>(null);
  const [state, setState] = useState<State>({ status: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const [refreshResult, setRefreshResult] = useState<QuoteRefreshResult | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  // Só a busca mais recente escreve na tela.
  const latest = useRef(0);

  const load = useCallback(() => {
    const id = ++latest.current;
    return getPortfolioAnalytics(portfolioId, until || null)
      .then((data) => {
        if (id === latest.current) setState({ status: "ready", data });
        return data;
      })
      .catch((err: unknown) => {
        if (id === latest.current) setState({ status: "error", message: describeApiError(err) });
        return null;
      });
  }, [portfolioId, until]);

  const refresh = useCallback(() => {
    setRefreshing(true);
    setRefreshError(null);
    return refreshQuotes()
      .then((result) => setRefreshResult(result))
      .catch((err: unknown) => setRefreshError(describeApiError(err)))
      .then(() => load())
      .then(() => {
        // O retrato que a análise diária do Claude lê acompanha as cotações novas.
        writeSnapshot().catch(() => undefined);
      })
      .finally(() => setRefreshing(false));
  }, [load]);

  useEffect(() => {
    getPortfolios()
      .then(setPortfolios)
      .catch(() => {
        // Sem a lista de carteiras, o consolidado continua funcionando.
      });
  }, []);

  // Ao abrir (e ao trocar carteira ou data): carrega e, se as cotações
  // estiverem velhas, busca e carrega de novo.
  useEffect(() => {
    void load().then((data) => {
      if (data !== null && quotesAreStale(data.quotes_refreshed_at, Date.now())) void refresh();
    });
  }, [load, refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => void refresh(), AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const problems = refreshResult?.items.filter((item) => item.status !== "OK") ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap items-end gap-3">
          <PortfolioSelector portfolios={portfolios} selectedPortfolioId={portfolioId} onChange={setPortfolioId} />
          <div>
            <label className={LABEL_CLASS} htmlFor="analyses-until">
              Cenários até
            </label>
            <input
              id="analyses-until"
              type="date"
              className={INPUT_CLASS}
              value={until}
              onChange={(event) => setUntil(event.target.value)}
            />
          </div>
        </div>
        <div className="text-right">
          <button type="button" className={BUTTON_CLASS} disabled={refreshing} onClick={() => void refresh()}>
            {refreshing ? "Buscando cotações…" : "Atualizar cotações agora"}
          </button>
          <p className="mt-1 text-xs text-neutral-500" data-testid="quotes-refreshed">
            {state.status === "ready" && state.data.quotes_refreshed_at
              ? `Cotações automáticas de ${formatRefreshTime(state.data.quotes_refreshed_at)} · atualiza sozinho a cada 15 min`
              : "Cotações automáticas ainda não buscadas"}
          </p>
        </div>
      </div>

      {refreshError && (
        <p className="text-sm text-amber-300" role="alert" data-testid="refresh-error">
          Não foi possível buscar as cotações agora ({refreshError}). Os números usam a última cotação gravada.
        </p>
      )}
      {problems.length > 0 && (
        <details className="text-sm text-amber-300" data-testid="refresh-problems">
          <summary className="cursor-pointer">
            {problems.length === 1 ? "1 ativo sem cotação automática" : `${problems.length} ativos sem cotação automática`}
          </summary>
          <ul className="mt-2 space-y-1 text-xs text-neutral-400">
            {problems.map((item) => (
              <li key={item.asset_id}>
                {item.ticker}: {item.message}
              </li>
            ))}
          </ul>
        </details>
      )}

      {state.status === "loading" && (
        <p className="text-neutral-400" role="status">
          Carregando…
        </p>
      )}
      {state.status === "error" && (
        <p className="text-red-400" role="alert">
          Não foi possível carregar as análises: {state.message}
        </p>
      )}
      {state.status === "ready" && state.data.blocks.length === 0 && (
        <p className="text-neutral-500" data-testid="analyses-empty">
          Nenhuma posição neste escopo.
        </p>
      )}
      {state.status === "ready" && state.data.blocks.length > 0 && (
        <AnalysesBlocks data={state.data} currency={currency} onCurrency={setCurrency} />
      )}

      <p className="text-xs text-neutral-500">
        Leitura de números, não recomendação de compra ou venda. Cenários são uma régua de incerteza, não previsão.
      </p>
    </div>
  );
}

function AnalysesBlocks({
  data,
  currency,
  onCurrency,
}: {
  data: PortfolioAnalytics;
  currency: string | null;
  onCurrency: (currency: string) => void;
}) {
  const active = data.blocks.find((block) => block.currency_code === currency) ?? data.blocks[0];
  const average = active.contributions?.projections.find((p) => p.pace === "AVERAGE") ?? null;
  return (
    <div className="space-y-6">
      {data.blocks.length > 1 ? (
        <div className="flex gap-2" role="tablist" aria-label="Moeda">
          {data.blocks.map((block) => (
            <button
              key={block.currency_code}
              type="button"
              role="tab"
              aria-selected={block.currency_code === active.currency_code}
              onClick={() => onCurrency(block.currency_code)}
              className={`rounded-md px-3 py-1.5 text-sm ${
                block.currency_code === active.currency_code
                  ? "bg-neutral-800 text-neutral-100"
                  : "text-neutral-400 hover:text-neutral-100"
              }`}
            >
              {block.currency_code}
            </button>
          ))}
        </div>
      ) : (
        <p className="text-xs text-neutral-500">Valores em {active.currency_code}</p>
      )}

      {active.alerts.length > 0 && (
        <div className={`${PANEL_CLASS} border-amber-900`} data-testid={`alerts-${active.currency_code}`}>
          <h3 className="mb-2 text-sm font-medium text-amber-300">Atenção</h3>
          <ul className="space-y-1 text-sm text-amber-200">
            {active.alerts.map((alert) => (
              <li key={alert}>{alert}</li>
            ))}
          </ul>
        </div>
      )}

      <ScenariosPanel
        key={`s-${active.currency_code}`}
        currency={active.currency_code}
        scenarios={active.scenarios}
        unavailableReason={active.scenarios_unavailable_reason}
        remainingAtAverage={average?.remaining_total ?? null}
      />
      <ContributionsPanel currency={active.currency_code} pace={active.contributions} />
      <ConcentrationPanel currency={active.currency_code} concentration={active.concentration} />
    </div>
  );
}
