import type { CurrencySpendingInsights } from "../../../api/overview";
import { formatCurrency, formatPercent } from "../../../lib/formatCurrency";
import { PANEL_CLASS } from "../../../lib/ui";

function Card({ title, children, testId }: { title: string; children: React.ReactNode; testId: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-3" data-testid={testId}>
      <p className="mb-1 text-sm font-medium text-neutral-200">{title}</p>
      <div className="space-y-1 text-sm text-neutral-400">{children}</div>
    </div>
  );
}

/**
 * Onde dá para melhorar: só o que os seus próprios lançamentos
 * mostram, comparado com o seu histórico. Nenhum julgamento de "gasto
 * bom ou ruim".
 */
export function ImprovementPanel({ insights }: { insights: CurrencySpendingInsights | undefined }) {
  if (!insights) return null;
  const currency = insights.currency_code;
  const money = (value: string) => formatCurrency(value, currency);
  const cards: React.ReactNode[] = [];

  if (insights.unclassified_share !== null && Number(insights.unclassified_share) >= 0.2) {
    cards.push(
      <Card key="unclassified" testId="insight-unclassified" title="Classifique para ver o quadro completo">
        <p>
          {money(insights.unclassified_outflow)} em saídas ainda sem classificação ({formatPercent(insights.unclassified_share)}
          {" "}das saídas do mês). Enquanto isso, gastos e comparações ficam incompletos.
        </p>
      </Card>,
    );
  }
  if (insights.above_normal.length > 0) {
    cards.push(
      <Card key="above" testId="insight-above" title="Acima do seu normal">
        {insights.above_normal.map((item) => (
          <p key={item.key}>
            <span className="text-neutral-200">{item.label}</span>: {money(item.current)} este mês, contra uma média de{" "}
            {money(item.average)} nos 3 meses anteriores (+{money(item.difference)}).
          </p>
        ))}
      </Card>,
    );
  } else if (insights.history_months < 2) {
    cards.push(
      <Card key="history" testId="insight-history" title="Comparação com o seu normal">
        <p>Precisa de pelo menos 2 meses anteriores com gastos registrados. Importe os extratos antigos para liberar.</p>
      </Card>,
    );
  }
  if (insights.recurring.length > 0) {
    cards.push(
      <Card key="recurring" testId="insight-recurring" title={`Se repetem todo mês · ${money(insights.recurring_total)}/mês`}>
        <p>Apareceram nos 3 últimos meses — assinaturas e contas fixas. Vale revisar o que ainda usa.</p>
        <ul className="mt-1 space-y-0.5">
          {insights.recurring.slice(0, 8).map((item) => (
            <li key={item.label} className="flex justify-between gap-3">
              <span className="text-neutral-300">{item.label}</span>
              <span className="tabular-nums">{money(item.monthly_average)}/mês</span>
            </li>
          ))}
        </ul>
      </Card>,
    );
  }
  if (insights.small_count > 0) {
    cards.push(
      <Card key="small" testId="insight-small" title="Gastos pequenos que somam">
        <p>
          {insights.small_count} compras abaixo de {money(insights.small_limit)} somaram {money(insights.small_total)} no mês.
        </p>
      </Card>,
    );
  }
  if (insights.top_share !== null && insights.top_categories.length > 1) {
    cards.push(
      <Card key="top" testId="insight-top" title="Onde está o seu gasto">
        <p>
          As {insights.top_categories.length} maiores categorias somam {formatPercent(insights.top_share)} dos gastos:{" "}
          {insights.top_categories
            .map((c) => `${c.label ?? "Sem categoria"} (${formatPercent(c.share)})`)
            .join(", ")}
          . É onde um ajuste pequeno muda mais.
        </p>
      </Card>,
    );
  }

  return (
    <div className={PANEL_CLASS} data-testid={`improvements-${currency}`}>
      <h3 className="text-sm font-medium text-neutral-300">Onde dá para melhorar</h3>
      <p className="mb-3 text-xs text-neutral-500">Comparado com o seu próprio histórico; nada aqui é julgamento de gasto.</p>
      {cards.length === 0 ? (
        <p className="text-sm text-neutral-500">Nada fora do seu padrão neste mês.</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">{cards}</div>
      )}
    </div>
  );
}
