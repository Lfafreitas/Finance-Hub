import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

import type { HoldingReading, InsightIndex, InsightReportRead, Signal } from "../api/insights";
import { getInsight, getInsights, writeSnapshot } from "../api/insights";
import { formatRefreshTime } from "../lib/analytics";
import { describeApiError } from "../lib/apiErrors";
import { formatIsoDate } from "../lib/formatCurrency";
import { INPUT_CLASS, LABEL_CLASS, PANEL_CLASS } from "../lib/ui";
import { LookThroughPanel } from "../components/insights/LookThroughPanel";
import { MarketStrip } from "../components/insights/MarketStrip";
import { OpportunityList } from "../components/insights/OpportunityList";
import { SafeLink } from "../components/insights/SafeLink";
import { LEAD_PARAGRAPHS, editionTime, longDate, staleNotice } from "../lib/newspaper";
import type { NoteWrite } from "../api/notes";
import { createNote, getNotes } from "../api/notes";
import type { NoteDraft } from "../components/notes/NoteComposer";
import { NoteComposer } from "../components/notes/NoteComposer";
import { Hl } from "../components/reading/Highlighted";
import { OtherReadings, SourcesPanel } from "../components/reading/OtherReadings";
import { ReadingSettings } from "../components/reading/ReadingSettings";
import type { Selected } from "../components/reading/SelectionToolbar";
import { SelectionToolbar } from "../components/reading/SelectionToolbar";
import { QuotesContext } from "../lib/highlights";
import { askClaudeAbout } from "../lib/notes";
import type { ReadingPrefs } from "../lib/readingPrefs";
import { loadPrefs, readingStyle, savePrefs } from "../lib/readingPrefs";
import { AlertList } from "../components/alerts/AlertList";
import { AskClaudePanel } from "../components/chat/AskClaudePanel";
import { PortfolioReviewPanel } from "../components/overview/PortfolioReviewPanel";
import { METRIC_LABELS, formatMetric, sortMetrics } from "../lib/kpis";

const SIGNAL_LABELS: Record<Signal, { text: string; tone: string }> = {
  POSITIVO: { text: "Leitura positiva", tone: "border-emerald-800 text-emerald-300" },
  NEUTRO: { text: "Neutro", tone: "border-neutral-700 text-neutral-300" },
  ATENCAO: { text: "Atenção", tone: "border-amber-800 text-amber-300" },
};

const MASTHEAD_CLASS =
  "font-serif text-[1.75rem] font-semibold leading-tight tracking-tight text-neutral-50 sm:text-[2rem]";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; index: InsightIndex; shown: InsightReportRead | null };

/**
 * Análises, notícias e resumos de relatórios de grandes casas, escritos
 * todo dia útil pela tarefa agendada do Claude a partir do retrato da
 * carteira. Ao abrir, a tela atualiza esse retrato.
 */
export function Insights() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [newsFilter, setNewsFilter] = useState<string>("");
  const [loadingDay, setLoadingDay] = useState(false);
  const [dayError, setDayError] = useState<string | null>(null);
  const [prefs, setPrefs] = useState<ReadingPrefs>(loadPrefs);
  const [quotes, setQuotes] = useState<string[]>([]);
  const [draft, setDraft] = useState<NoteDraft | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const articleRef = useRef<HTMLElement>(null);

  // Trechos já destacados (anotações com citação) aparecem marcados.
  useEffect(() => {
    getNotes()
      .then((notes) => setQuotes(notes.map((n) => n.quote).filter((q): q is string => !!q)))
      .catch(() => setQuotes([]));
  }, []);

  function changePrefs(next: ReadingPrefs) {
    setPrefs(next);
    savePrefs(next);
  }

  function sourceOf(selected: Selected, fallback: string) {
    return { source_title: selected.sourceTitle ?? fallback, source_url: selected.sourceUrl };
  }

  async function saveNote(_id: string | undefined, note: NoteWrite) {
    const created = await createNote(note);
    if (created.quote) setQuotes((q) => [...q, created.quote!]);
    setSaved("Anotação salva");
    return created;
  }

  useEffect(() => {
    writeSnapshot().catch((err: unknown) => setSnapshotError(describeApiError(err)));
    getInsights()
      .then((index) => setState({ status: "ready", index, shown: index.latest }))
      .catch((err: unknown) => setState({ status: "error", message: describeApiError(err) }));
  }, []);

  function openDay(day: string) {
    if (state.status !== "ready") return;
    setLoadingDay(true);
    setDayError(null);
    getInsight(day)
      .then((shown) => {
        setState({ ...state, shown });
        setNewsFilter("");
      })
      .catch((err: unknown) => setDayError(describeApiError(err)))
      .finally(() => setLoadingDay(false));
  }

  if (state.status === "loading") {
    return (
      <p className="text-neutral-400" role="status">
        Carregando…
      </p>
    );
  }
  if (state.status === "error") {
    return (
      <p className="text-red-400" role="alert">
        Não foi possível carregar as análises: {state.message}
      </p>
    );
  }

  const { index, shown } = state;
  // Só a edição mais nova pode estar "atrasada"; uma antiga foi escolhida.
  const stale =
    shown && index.latest && shown.report_date === index.latest.report_date ? staleNotice(shown.report_date) : null;
  return (
    <div className="space-y-6">
      {snapshotError && (
        <p className="text-sm text-amber-300" role="alert" data-testid="snapshot-error">
          O retrato da carteira não foi atualizado ({snapshotError}). A próxima análise usa o último retrato gravado.
        </p>
      )}
      {index.invalid_files.length > 0 && (
        <details className="text-sm text-amber-300" data-testid="invalid-files">
          <summary className="cursor-pointer">
            {index.invalid_files.length === 1
              ? "1 arquivo de análise foi recusado"
              : `${index.invalid_files.length} arquivos de análise foram recusados`}
          </summary>
          <ul className="mt-2 space-y-1 text-xs text-neutral-400">
            {index.invalid_files.map((file) => (
              <li key={file.file_name}>
                {file.file_name}: {file.error}
              </li>
            ))}
          </ul>
        </details>
      )}

      {shown === null ? (
        <>
          <AlertList />
          <div className={PANEL_CLASS} data-testid="no-insights">
            <h2 className="mb-2 text-[15px] font-semibold tracking-tight text-neutral-100">Nenhuma análise ainda</h2>
            <p className="text-sm text-neutral-400">
              A análise do Claude roda nos dias úteis de manhã, com o seu computador ligado. Ela lê o retrato da
              carteira que este app grava na pasta “claude-analises” e deixa o relatório do dia na mesma pasta.
            </p>
            <p className="mt-2 text-xs text-neutral-500">
              {index.snapshot_written_at
                ? `Retrato da carteira atualizado em ${formatRefreshTime(index.snapshot_written_at)}.`
                : "O retrato da carteira ainda não foi gravado."}
            </p>
          </div>
          <AskClaudePanel />
        </>
      ) : (
        <QuotesContext.Provider value={quotes}>
          <article
            ref={articleRef}
            className="reading space-y-10"
            style={readingStyle(prefs)}
            data-tint={prefs.tint}
            data-testid="newspaper"
            aria-labelledby="headline"
          >
            <ReadingProgress target={articleRef} />
            {/* Cabeçalho do jornal: data da edição, troca de dia e o mercado. */}
            <header className="border-b border-neutral-700 pb-3">
              <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
                <div>
                  {/* O nome do jornal é o título da página; a data da edição logo abaixo. */}
                  <h1 className={MASTHEAD_CLASS}>Jornal da carteira</h1>
                  <p className="mt-1 text-sm text-neutral-400" data-testid="report-date">
                    <span className="first-letter:uppercase">{longDate(shown.report_date)}</span>
                    {editionTime(shown.report.generated_at) &&
                      ` · edição das ${editionTime(shown.report.generated_at)}`}
                    <span className="sr-only"> (Análise de {formatIsoDate(shown.report_date)})</span>
                  </p>
                </div>
                <div className="flex flex-wrap items-end gap-4">
                  <ReadingSettings prefs={prefs} onChange={changePrefs} />
                  <a href="#ask-title" className="pb-2 text-sm text-sky-300 underline-offset-4 hover:underline">
                    Perguntar ao Claude
                  </a>
                  {index.history.length > 1 && (
                    <div>
                      <label className={LABEL_CLASS} htmlFor="insights-day">
                        Outra edição
                      </label>
                      <select
                        id="insights-day"
                        className={`${INPUT_CLASS} max-w-[16rem]`}
                        value={shown.report_date}
                        disabled={loadingDay}
                        onChange={(event) => openDay(event.target.value)}
                      >
                        {index.history.map((item) => (
                          <option key={item.report_date} value={item.report_date}>
                            {formatIsoDate(item.report_date)} — {item.headline}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
              </div>
              {stale && (
                <p className="mt-2 text-sm text-amber-300" data-testid="stale-edition">
                  {stale}
                </p>
              )}
              {(shown.report.market ?? []).length > 0 && (
                <div className="mt-3 border-t border-neutral-800 pt-1">
                  <MarketStrip items={shown.report.market ?? []} />
                </div>
              )}
            </header>
            {dayError && (
              <p className="text-sm text-red-400" role="alert">
                {dayError}
              </p>
            )}

            <AlertList compactWhenEmpty />

            {/* Manchete do dia e, ao lado, a agenda do que acompanhar. */}
            <div className="grid gap-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <div>
                <h2
                  id="headline"
                  className="font-serif text-[1.75rem] font-medium leading-tight tracking-tight text-neutral-50 sm:text-[2.125rem]"
                  data-testid="headline"
                  style={prefs.font !== "padrao" ? { fontFamily: "var(--read-font)" } : undefined}
                >
                  {shown.report.headline}
                </h2>
                <div
                  className="mt-4 space-y-4 text-neutral-300"
                  data-testid="summary"
                  data-quote-source={`Jornal da carteira · ${formatIsoDate(shown.report_date)}`}
                >
                  {shown.report.summary.slice(0, LEAD_PARAGRAPHS).map((paragraph, i) => (
                    <p key={i} className={`read-body ${i === 0 ? "text-neutral-100" : ""}`}>
                      <Hl text={paragraph} />
                    </p>
                  ))}
                  {shown.report.summary.length > LEAD_PARAGRAPHS && (
                    <ReadMore key={shown.report_date} paragraphs={shown.report.summary.slice(LEAD_PARAGRAPHS)} />
                  )}
                </div>
              </div>
              {shown.report.watch.length > 0 && (
                <aside className="lg:border-l lg:border-neutral-800 lg:pl-8" data-testid="watch">
                  <h3 className="font-serif text-lg font-medium text-neutral-50">O que acompanhar</h3>
                  <ul className="mt-3 divide-y divide-neutral-800 text-sm">
                    {shown.report.watch.map((item) => (
                      <li key={item.topic} className="py-3 first:pt-0">
                        {item.date && <p className="text-xs tabular-nums text-sky-300">{formatIsoDate(item.date)}</p>}
                        <p className="font-medium text-neutral-100">{item.topic}</p>
                        <p className="mt-0.5 text-neutral-400">{item.why}</p>
                      </li>
                    ))}
                  </ul>
                </aside>
              )}
            </div>

            <OpportunityList items={shown.report.opportunities ?? []} />

            {shown.report.portfolio_review && <PortfolioReviewPanel report={shown} />}

            {/* Manchetes e, na coluna ao lado, grandes casas e empresas dos ETFs. */}
            <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <div className="min-w-0">
                {shown.report.news.length > 0 && (
                  <NewsList report={shown} filter={newsFilter} onFilter={setNewsFilter} />
                )}
              </div>
              <div className="min-w-0 space-y-8">
                <LookThroughPanel />
                {shown.report.research.length > 0 && (
                  <section data-testid="research">
                    <h3 className="font-serif text-lg font-medium text-neutral-50">Grandes casas</h3>
                    <p className="mt-0.5 text-xs text-neutral-500">
                      Resumo feito pelo Claude; o texto completo fica na fonte.
                    </p>
                    <ul className="mt-3 divide-y divide-neutral-800 text-sm">
                      {shown.report.research.map((item) => (
                        <li
                          key={item.url}
                          className="py-3 first:pt-0"
                          data-quote-source={`${item.house} · ${item.title}`}
                          data-quote-url={item.url}
                        >
                          <p className="text-xs text-neutral-500">
                            {item.house}
                            {item.published_at ? ` · ${formatIsoDate(item.published_at)}` : ""}
                          </p>
                          <SafeLink url={item.url}>{item.title}</SafeLink>
                          <p className="read-small mt-1 text-neutral-300">
                            <Hl text={item.summary} />
                          </p>
                          {item.relevance && (
                            <p className="mt-1 text-xs text-neutral-400">Para a sua carteira: {item.relevance}</p>
                          )}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </div>
            </div>

            {(shown.report.papers ?? []).length > 0 && <OtherReadings papers={shown.report.papers ?? []} />}
            <SourcesPanel />

            {shown.report.holdings.length > 0 && (
              <section className="space-y-3" data-testid="holdings">
                <h3 className="font-serif text-xl font-medium text-neutral-50">Seus ativos</h3>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {shown.report.holdings.map((holding) => (
                    <HoldingCard key={holding.ticker} holding={holding} />
                  ))}
                </div>
              </section>
            )}

            <AskClaudePanel />

            <p className="text-xs text-neutral-500" data-testid="disclaimer">
              {shown.report.disclaimer}
            </p>
            <SelectionToolbar
              container={articleRef}
              actions={{
                onHighlight: (sel) => {
                  void saveNote(undefined, {
                    title: null,
                    body: "",
                    quote: sel.text,
                    ...sourceOf(sel, `Jornal da carteira · ${formatIsoDate(shown.report_date)}`),
                    tickers: [],
                    pinned: false,
                    share_with_claude: false,
                  }).then(() => setSaved("Trecho destacado e guardado nas anotações"));
                },
                onNote: (sel) =>
                  setDraft({
                    quote: sel.text,
                    ...sourceOf(sel, `Jornal da carteira · ${formatIsoDate(shown.report_date)}`),
                  }),
                onAsk: (sel) =>
                  askClaudeAbout(
                    `Sobre este trecho do jornal: “${sel.text}”. O que isso significa para a minha carteira?`,
                  ),
              }}
            />
            {draft && <NoteComposer draft={draft} onSave={saveNote} onClose={() => setDraft(null)} />}
            {saved && <Toast text={saved} onDone={() => setSaved(null)} />}
          </article>
        </QuotesContext.Provider>
      )}
    </div>
  );
}

/** Linha fina no topo que enche conforme a leitura do Jornal avança. */
function ReadingProgress({ target }: { target: RefObject<HTMLElement | null> }) {
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    const update = () => {
      const el = target.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const total = rect.height - window.innerHeight;
      setProgress(total > 0 ? Math.min(1, Math.max(0, -rect.top / total)) : 0);
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, [target]);
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-x-0 top-[env(safe-area-inset-top)] z-[35] h-[2px] origin-left bg-sky-400/80"
      style={{ transform: `scaleX(${progress})` }}
      data-testid="reading-progress"
    />
  );
}

/** Aviso rápido no rodapé (some sozinho). */
function Toast({ text, onDone }: { text: string; onDone: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onDone, 2600);
    return () => window.clearTimeout(timer);
  }, [text, onDone]);
  return (
    <div
      role="status"
      className="sheet-up fixed inset-x-0 bottom-[calc(96px+env(safe-area-inset-bottom))] z-[55] mx-auto w-fit rounded-full bg-neutral-100 px-4 py-2 text-[15px] font-medium text-neutral-950 shadow-lg md:bottom-8"
    >
      {text}
    </div>
  );
}

/**
 * O resto do texto, como leitura no iPhone: as primeiras linhas aparecem
 * esmaecendo até sumir, e "Continuar lendo" abre tudo.
 */
function ReadMore({ paragraphs }: { paragraphs: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div data-testid="read-more">
      <div
        className={`space-y-3 overflow-hidden transition-[max-height] duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] ${
          open ? "max-h-[400rem]" : "max-h-[6.5rem] [mask-image:linear-gradient(to_bottom,black,transparent)]"
        }`}
        aria-hidden={!open}
        data-testid="read-more-text"
      >
        {paragraphs.map((paragraph, i) => (
          <p key={i} className="read-body">
            <Hl text={paragraph} />
          </p>
        ))}
      </div>
      {!open && (
        <button
          type="button"
          className="mt-1 min-h-11 text-[15px] font-medium text-sky-300 active:opacity-70"
          onClick={() => setOpen(true)}
        >
          Continuar lendo
        </button>
      )}
    </div>
  );
}

function HoldingCard({ holding }: { holding: HoldingReading }) {
  const signal = SIGNAL_LABELS[holding.signal];
  return (
    <div className={PANEL_CLASS} data-testid={`holding-${holding.ticker}`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="font-semibold">{holding.ticker}</span>
        <span className={`rounded border px-2 py-0.5 text-xs ${signal.tone}`}>{signal.text}</span>
      </div>
      <p className="text-sm text-neutral-300">{holding.reading}</p>
      {holding.metrics.length > 0 && (
        <dl className="mt-3 space-y-1 text-sm">
          {holding.metrics.map((metric) => (
            <div key={metric.label} className="flex justify-between gap-3">
              <dt className="text-neutral-400">{metric.label}</dt>
              <dd className="text-right tabular-nums">
                {metric.value}
                {metric.context && <span className="block text-xs text-neutral-500">{metric.context}</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {(holding.key_metrics ?? []).length > 0 && (
        <dl
          className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-neutral-800 pt-3 text-sm"
          data-testid={`key-metrics-${holding.ticker}`}
        >
          {sortMetrics(holding.key_metrics ?? []).map((metric) => (
            <div key={metric.code} className="flex justify-between gap-2">
              <dt className="text-neutral-400">{METRIC_LABELS[metric.code]}</dt>
              <dd className="tabular-nums" title={`${metric.source}, ${formatIsoDate(metric.as_of)}`}>
                {formatMetric(metric)}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {holding.sources.length > 0 && (
        <p className="mt-3 flex flex-wrap gap-x-3 text-xs">
          {holding.sources.map((source) => (
            <SafeLink key={source.url} url={source.url}>
              {source.title}
            </SafeLink>
          ))}
        </p>
      )}
    </div>
  );
}

function NewsList({
  report,
  filter,
  onFilter,
}: {
  report: InsightReportRead;
  filter: string;
  onFilter: (value: string) => void;
}) {
  const tickers = Array.from(
    new Set(report.report.news.map((item) => item.ticker).filter((t): t is string => t !== null)),
  ).sort();
  const items = report.report.news.filter((item) => filter === "" || item.ticker === filter);
  return (
    <section data-testid="news">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-serif text-xl font-medium text-neutral-50">Manchetes</h3>
        {tickers.length > 0 && (
          <div className="flex flex-wrap gap-1" role="group" aria-label="Filtrar notícias">
            {["", ...tickers].map((ticker) => (
              <button
                key={ticker || "todas"}
                type="button"
                aria-pressed={filter === ticker}
                onClick={() => onFilter(ticker)}
                className={`rounded px-2 py-0.5 text-xs ${
                  filter === ticker ? "bg-neutral-800 text-neutral-100" : "text-neutral-400 hover:text-neutral-100"
                }`}
              >
                {ticker || "Todas"}
              </button>
            ))}
          </div>
        )}
      </div>
      <ul className="divide-y divide-neutral-800 border-t border-neutral-700 text-sm">
        {items.map((item) => (
          <li
            key={item.url}
            className="py-4"
            data-testid="news-item"
            data-quote-source={`${item.source} · ${item.title}`}
            data-quote-url={item.url}
          >
            <p className="text-xs text-neutral-500">
              {item.ticker ? `${item.ticker} · ` : ""}
              {item.topic} · {item.source}
              {item.published_at ? ` · ${formatIsoDate(item.published_at)}` : ""}
            </p>
            <p className="mt-1 text-base leading-snug">
              <SafeLink url={item.url}>{item.title}</SafeLink>
            </p>
            <p className="read-small mt-1 text-neutral-300">
              <Hl text={item.summary} />
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
