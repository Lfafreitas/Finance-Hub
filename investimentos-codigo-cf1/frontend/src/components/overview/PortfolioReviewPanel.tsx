import type { InsightReportRead, PortfolioReview, ReviewPoint } from "../../api/insights";
import { formatIsoDate } from "../../lib/formatCurrency";
import { PANEL_CLASS } from "../../lib/ui";

type Kind = keyof Omit<PortfolioReview, "overall">;

// Cada lista tem um ícone além da cor: a cor nunca é a única pista.
const KINDS: { key: Kind; title: string; tone: string; icon: string }[] = [
  { key: "good", title: "Está bem", tone: "text-emerald-300", icon: "M5 12.5l4.5 4.5L19 7.5" },
  { key: "attention", title: "Pede atenção", tone: "text-amber-300", icon: "M12 6v7M12 17.5v.5" },
  { key: "risks", title: "Riscos", tone: "text-red-300", icon: "M12 4L2.5 20h19L12 4zM12 10v4.5M12 17.5v.5" },
  { key: "improve", title: "Pode melhorar", tone: "text-sky-300", icon: "M12 19V6M6.5 11.5L12 6l5.5 5.5" },
];

function PointList({ points }: { points: ReviewPoint[] }) {
  if (points.length === 0) return <p className="text-sm text-neutral-500">Nada a destacar.</p>;
  return (
    <ul className="space-y-3">
      {points.map((point) => (
        <li key={point.title}>
          <p className="text-sm font-medium text-neutral-100">
            {point.title}
            {point.tickers.length > 0 && (
              <span className="ml-2 text-xs font-normal text-neutral-500">{point.tickers.join(", ")}</span>
            )}
          </p>
          <p className="mt-0.5 text-sm leading-relaxed text-neutral-400">{point.detail}</p>
        </li>
      ))}
    </ul>
  );
}

/**
 * A avaliação da carteira que o Claude escreve na análise do dia: o que
 * está bem, o que pede atenção, os riscos e o que poderia melhorar.
 */
export function PortfolioReviewPanel({
  report,
  onOpenReport,
}: {
  report: InsightReportRead | null;
  onOpenReport?: () => void;
}) {
  const review = report?.report.portfolio_review ?? null;
  return (
    <section aria-labelledby="review-title" data-testid="portfolio-review">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="review-title" className="text-[15px] font-semibold tracking-tight text-neutral-100">
          Como a carteira está, na leitura do Claude
        </h2>
        {report && (
          <p className="text-xs text-neutral-500">
            Análise de {formatIsoDate(report.report_date)}
            {onOpenReport && (
              <>
                {" · "}
                <button type="button" className="underline hover:text-neutral-300" onClick={onOpenReport}>
                  Ler a análise completa
                </button>
              </>
            )}
          </p>
        )}
      </div>
      {review === null ? (
        <div className={`${PANEL_CLASS} text-sm text-neutral-400`} data-testid="review-empty">
          {report
            ? "A análise mais recente ainda não traz a avaliação da carteira. Ela passa a vir na próxima análise diária."
            : "A análise diária do Claude ainda não chegou. Ela roda nos dias úteis de manhã, com o computador ligado."}
        </div>
      ) : (
        <div className={`${PANEL_CLASS} space-y-5`}>
          <p className="max-w-3xl text-[15px] leading-relaxed text-neutral-200" data-testid="review-overall">
            {review.overall}
          </p>
          <div className="grid grid-cols-1 gap-x-8 gap-y-6 md:grid-cols-2">
            {KINDS.map((kind) => (
              <div key={kind.key} data-testid={`review-${kind.key}`}>
                <h3 className={`mb-2 flex items-center gap-2 text-sm font-semibold ${kind.tone}`}>
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d={kind.icon} />
                  </svg>
                  {kind.title}
                  <span className="font-normal text-neutral-500">{review[kind.key].length}</span>
                </h3>
                <PointList points={review[kind.key]} />
              </div>
            ))}
          </div>
          <p className="text-xs text-neutral-500">Leitura dos números, não recomendação de compra ou venda.</p>
        </div>
      )}
    </section>
  );
}
