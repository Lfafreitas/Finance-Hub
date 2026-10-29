import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

import type { PortfolioAnalytics } from "../api/analytics";
import { getPortfolioAnalytics, refreshQuotes } from "../api/analytics";
import { getAccounts, getAssetClasses, getDashboardSummary, getPortfolios } from "../api/client";
import type { Overview } from "../api/overview";
import { getOverview } from "../api/overview";
import type { InsightReportRead } from "../api/insights";
import { getInsights } from "../api/insights";
import type {
  Agenda,
  Allocation,
  Benchmarks,
  DividendsSummary,
  FinancialHealth,
  PortfolioKpis as Kpis,
} from "../api/performance";
import {
  getAgenda,
  getAllocation,
  getBenchmarks,
  getDividendsSummary,
  getFinancialHealth,
  getKpis,
} from "../api/performance";
import { getPendingGroups } from "../api/review";
import type { AccountRead, AssetClassRead, DashboardSummary, PortfolioRead } from "../api/types";
import { type AttentionItem, AttentionList } from "../components/AttentionList";
import { CurrencyBlock } from "../components/CurrencyBlock";
import { InconsistentPositions } from "../components/InconsistentPositions";
import { AgendaPanel } from "../components/overview/AgendaPanel";
import { AllocationPanel } from "../components/overview/AllocationPanel";
import { BenchmarkPanel } from "../components/overview/BenchmarkPanel";
import { FinancialHealthPanel } from "../components/overview/FinancialHealthPanel";
import { FlowPulseCard } from "../components/overview/FlowPulseCard";
import { PatrimonyHistory } from "../components/overview/PatrimonyHistory";
import { PatrimonyOverview } from "../components/overview/PatrimonyOverview";
import { PortfolioKpis } from "../components/overview/PortfolioKpis";
import { PortfolioReviewPanel } from "../components/overview/PortfolioReviewPanel";
import { PortfolioSelector } from "../components/PortfolioSelector";
import { describeApiError } from "../lib/apiErrors";
import { AUTO_REFRESH_MS, formatRefreshTime, quotesAreStale } from "../lib/analytics";
import { readingsByTicker } from "../lib/kpis";
import { PAGE_TITLE_TEXT_CLASS } from "../lib/ui";

/** Para onde o Dashboard pode mandar o usuário resolver alguma coisa. */
export type DashboardTarget =
  | { page: "review" }
  | { page: "prices" }
  | { page: "insights" }
  | { page: "registry" }
  | { page: "transactions"; accountId: string };

// A subida em sequência das partes só acontece na primeira vez que o
// dashboard aparece na sessão; trocar de aba e voltar não repete.
let dashboardRevealed = false;

/** Ordem na subida em sequência (CSS `.reveal`), com teto para quem chega tarde. */
function order(i: number): CSSProperties {
  return { "--i": Math.min(i, 5) } as CSSProperties;
}

export function Dashboard({ onOpen }: { onOpen?: (target: DashboardTarget) => void } = {}) {
  const [reveal] = useState(() => (dashboardRevealed ? "" : "reveal"));
  useEffect(() => {
    dashboardRevealed = true;
  }, []);
  const [portfolios, setPortfolios] = useState<PortfolioRead[]>([]);
  const [accounts, setAccounts] = useState<AccountRead[]>([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(null);
  const [selectedCurrency, setSelectedCurrency] = useState<string | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [analytics, setAnalytics] = useState<PortfolioAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Muda depois de buscar cotações: tudo o que depende de preço é relido.
  const [reloadKey, setReloadKey] = useState(0);
  const [pendingCash, setPendingCash] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [lastAutoRefresh, setLastAutoRefresh] = useState(0);
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [agenda, setAgenda] = useState<Agenda | null>(null);
  const [dividends, setDividends] = useState<DividendsSummary | null>(null);
  const [benchmarks, setBenchmarks] = useState<Benchmarks | null>(null);
  const [allocation, setAllocation] = useState<Allocation | null>(null);
  const [health, setHealth] = useState<FinancialHealth[]>([]);
  const [assetClasses, setAssetClasses] = useState<AssetClassRead[]>([]);
  const [report, setReport] = useState<InsightReportRead | null>(null);

  useEffect(() => {
    getPortfolios()
      .then(setPortfolios)
      .catch(() => {
        // Falha ao listar carteiras não impede o consolidado de funcionar.
      });
    getAccounts()
      .then(setAccounts)
      .catch(() => {
        // Contas só dão NOME à conta no aviso de posições inconsistentes.
      });
    getPendingGroups(1)
      .then((data) => setPendingCash(data.pending_entries))
      .catch(() => {
        // Sem a contagem, só o aviso some.
      });
    getInsights()
      .then((index) => setReport(index.latest))
      .catch(() => {
        // Sem a análise do Claude, os painéis dela mostram que ela não chegou.
      });
  }, []);

  useEffect(() => {
    getKpis()
      .then(setKpis)
      .catch(() => setKpis(null));
    getAgenda()
      .then(setAgenda)
      .catch(() => setAgenda(null));
    getDividendsSummary()
      .then(setDividends)
      .catch(() => setDividends(null));
    getBenchmarks()
      .then(setBenchmarks)
      .catch(() => setBenchmarks(null));
    getAllocation()
      .then(setAllocation)
      .catch(() => setAllocation(null));
    getFinancialHealth()
      .then((data) => setHealth(data.currencies))
      .catch(() => setHealth([]));
    getAssetClasses()
      .then(setAssetClasses)
      .catch(() => setAssetClasses([]));
  }, [reloadKey]);

  useEffect(() => {
    getOverview()
      .then(setOverview)
      .catch(() => {
        // Sem o patrimônio consolidado, o resto do dashboard continua.
      });
  }, [reloadKey]);

  function fetchQuotes() {
    setRefreshing(true);
    setRefreshError(null);
    setLastAutoRefresh(Date.now());
    refreshQuotes()
      .then(() => setReloadKey((key) => key + 1))
      .catch((err: unknown) => setRefreshError(describeApiError(err)))
      .finally(() => setRefreshing(false));
  }

  // Cotação velha (mais de 15 min) é buscada sozinha, no máximo uma vez a cada 15 min.
  useEffect(() => {
    if (analytics === null || refreshing) return;
    const now = Date.now();
    if (quotesAreStale(analytics.quotes_refreshed_at, now) && now - lastAutoRefresh > AUTO_REFRESH_MS) {
      fetchQuotes();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analytics]);

  useEffect(() => {
    // Pesos pelo valor de mercado para a distribuição; sem eles, o
    // gráfico usa o custo do próprio resumo.
    getPortfolioAnalytics(selectedPortfolioId, null)
      .then(setAnalytics)
      .catch(() => setAnalytics(null));
  }, [selectedPortfolioId, reloadKey]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getDashboardSummary(selectedPortfolioId)
      .then(setSummary)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [selectedPortfolioId, reloadKey]);

  // Um bloco por moeda, na ordem EXATA do backend. O bloco ativo é
  // derivado a cada render: se a moeda selecionada não existe neste
  // resumo (ex.: depois de trocar de carteira), vale o primeiro bloco —
  // nunca um bloco "fantasma" de um resumo anterior.
  const blocks = summary?.totals_by_currency ?? [];
  const activeBlock = blocks.find((block) => block.currency_code === selectedCurrency) ?? blocks[0] ?? null;
  const positions = summary?.positions ?? [];
  const inconsistentPositions = positions.filter((position) => position.currency_code === null);
  const unpriced = [...new Set((overview?.totals_by_currency ?? []).flatMap((block) => block.unpriced))].sort();

  const attention: AttentionItem[] = [];
  if (refreshError) {
    attention.push({
      key: "quotes",
      text: `Não consegui buscar as cotações agora: ${refreshError}`,
      actionLabel: "Tentar de novo",
      onAction: fetchQuotes,
    });
  }
  if (pendingCash > 0) {
    attention.push({
      key: "classify",
      text: `${pendingCash} ${pendingCash === 1 ? "lançamento" : "lançamentos"} do controle financeiro sem classificação: gastos e renda ficam incompletos.`,
      actionLabel: onOpen ? "Classificar" : undefined,
      onAction: onOpen ? () => onOpen({ page: "review" }) : undefined,
    });
  }
  if (unpriced.length > 0) {
    attention.push({
      key: "unpriced",
      text: `Sem cotação: ${unpriced.join(", ")}. Entram pelo valor aplicado e o rendimento deles não aparece.`,
      actionLabel: onOpen ? "Informar cotação" : undefined,
      onAction: onOpen ? () => onOpen({ page: "prices" }) : undefined,
    });
  }

  return (
    <div className="px-4 pb-16 pt-1 text-neutral-100 md:px-6 md:pt-8">
      <div className="mx-auto max-w-6xl">
        <div style={order(0)} className={`${reveal} mb-8 flex flex-wrap items-end justify-between gap-3`}>
          <div>
            <h1 className={PAGE_TITLE_TEXT_CLASS}>Visão geral</h1>
            <p className="mt-1 text-xs text-neutral-500" data-testid="quotes-status">
              {refreshing
                ? "Buscando cotações…"
                : analytics?.quotes_refreshed_at
                  ? `Cotações de ${formatRefreshTime(analytics.quotes_refreshed_at)}`
                  : "Cotações ainda não buscadas"}
              {!refreshing && (
                <>
                  {" · "}
                  <button type="button" className="underline hover:text-neutral-300" onClick={fetchQuotes}>
                    Atualizar agora
                  </button>
                </>
              )}
            </p>
          </div>
          <PortfolioSelector
            portfolios={portfolios}
            selectedPortfolioId={selectedPortfolioId}
            onChange={setSelectedPortfolioId}
          />
        </div>

        {loading && (
          <p className="text-neutral-400" role="status">
            Carregando…
          </p>
        )}

        {error && !loading && (
          <p className="text-red-400" role="alert">
            Não foi possível carregar o dashboard: {error}
          </p>
        )}

        {/* Ordem pensada para a leitura de 5 segundos: quanto tenho, o que
            pede atenção, como o Claude vê a carteira — depois o detalhe. */}
        {overview && (
          <div className={`${reveal} mb-6`} style={order(1)}>
            <PatrimonyOverview overview={overview} />
          </div>
        )}

        {attention.length > 0 && (
          <div className={`${reveal} mb-12`} style={order(2)}>
            <AttentionList items={attention} />
          </div>
        )}

        {/* No computador largo, a leitura do Claude e o caixa lado a lado. */}
        <div className="mb-12 gap-6 xl:flex xl:items-start">
          <div className={`${reveal} min-w-0 xl:flex-[7]`} style={order(3)}>
            <PortfolioReviewPanel
              report={report}
              onOpenReport={onOpen ? () => onOpen({ page: "insights" }) : undefined}
            />
          </div>
          <div className={`${reveal} mt-12 min-w-0 empty:hidden xl:mt-9 xl:flex-[5]`} style={order(4)}>
            <FlowPulseCard reloadKey={reloadKey} />
          </div>
        </div>

        <div className={`${reveal} mb-12`} style={order(4)}>
          <PatrimonyHistory key={reloadKey} />
        </div>

        {benchmarks && benchmarks.comparisons.length > 0 && (
          <div className={`${reveal} mb-12`} style={order(5)}>
            <BenchmarkPanel benchmarks={benchmarks} />
          </div>
        )}

        {agenda && (
          <div className={`${reveal} mb-12`} style={order(6)}>
            <AgendaPanel
              agenda={agenda}
              dividends={dividends}
              onOpenRegistry={onOpen ? () => onOpen({ page: "registry" }) : undefined}
            />
          </div>
        )}

        {allocation && allocation.currencies.length > 0 && (
          <div className={`${reveal} mb-12`} style={order(7)}>
            <AllocationPanel allocation={allocation} assetClasses={assetClasses} onChange={setAllocation} />
          </div>
        )}

        {health.length > 0 && (
          <div className={`${reveal} mb-12`} style={order(8)}>
            <FinancialHealthPanel
              currencies={health}
              onOpenReview={onOpen ? () => onOpen({ page: "review" }) : undefined}
            />
          </div>
        )}

        {kpis &&
          kpis.totals_by_currency.map((block) => (
            <div key={block.currency_code} className={`${reveal} mb-12`} style={order(9)}>
              <PortfolioKpis block={block} readings={readingsByTicker(report)} />
            </div>
          ))}

        {summary && !loading && !error && (
          <div className="space-y-6">
            <h2 className="text-[15px] font-semibold tracking-tight text-neutral-100">
              Investimentos{selectedPortfolioId ? "" : " · todas as contas"}
            </h2>
            <InconsistentPositions positions={inconsistentPositions} accounts={accounts} />

            {activeBlock === null && (
              <p className="text-neutral-500" data-testid="dashboard-empty">
                Nenhuma movimentação neste escopo.
              </p>
            )}

            {activeBlock !== null && (
              <>
                {blocks.length > 1 ? (
                  <div className="flex flex-wrap items-center gap-3">
                    <div
                      className="flex rounded-lg bg-neutral-900 p-1 ring-1 ring-neutral-800"
                      role="tablist"
                      aria-label="Moeda"
                    >
                      {blocks.map((block) => {
                        const active = block.currency_code === activeBlock.currency_code;
                        return (
                          <button
                            key={block.currency_code}
                            type="button"
                            role="tab"
                            aria-selected={active}
                            onClick={() => setSelectedCurrency(block.currency_code)}
                            className={`rounded-md px-3 py-1 text-sm transition-colors ${
                              active ? "bg-neutral-800 text-neutral-50" : "text-neutral-400 hover:text-neutral-100"
                            }`}
                          >
                            {block.currency_code}
                          </button>
                        );
                      })}
                    </div>
                    <p className="text-xs text-neutral-500">Valores nunca são somados entre moedas.</p>
                  </div>
                ) : (
                  <p className="text-xs text-neutral-500" data-testid="single-currency-label">
                    Valores em {activeBlock.currency_code}
                  </p>
                )}

                <CurrencyBlock
                  key={activeBlock.currency_code}
                  block={activeBlock}
                  onOpenTransactions={onOpen ? (accountId) => onOpen({ page: "transactions", accountId }) : undefined}
                  concentration={
                    analytics?.blocks.find((b) => b.currency_code === activeBlock.currency_code)?.concentration ?? null
                  }
                  positions={positions.filter((position) => position.currency_code === activeBlock.currency_code)}
                />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
