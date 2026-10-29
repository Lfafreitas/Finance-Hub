import { useEffect, useState } from "react";

import { countCashEntries, getCashBalances, getCashSummary, getCategoryBreakdown } from "../../api/cashflow";
import type { MonthlyFlows, SpendingInsights } from "../../api/overview";
import { getMonthlyFlows, getSpendingInsights } from "../../api/overview";
import type {
  CashflowAccountBalance,
  CashflowBalances,
  CashflowCurrencyBalance,
  CashflowCurrencySummary,
  CashflowSummary,
  CategoryBreakdown,
} from "../../api/cashflowTypes";
import { ErrorText, Loading } from "../../components/cash/shared";
import { ImprovementPanel } from "../../components/cash/summary/ImprovementPanel";
import { KpiTile } from "../../components/cash/summary/KpiTile";
import { MonthlyFlowChart } from "../../components/cash/summary/MonthlyFlowChart";
import { WhereMoneyWent } from "../../components/cash/summary/WhereMoneyWent";
import { ACCOUNT_TYPE_LABELS } from "../../lib/accountTypes";
import { describeApiError } from "../../lib/apiErrors";
import { currentMonth, monthRange } from "../../lib/cashflow";
import { formatCurrency, formatIsoDate, formatSignedCurrency } from "../../lib/formatCurrency";
import { INPUT_CLASS, LABEL_CLASS, PANEL_CLASS } from "../../lib/ui";

interface SummaryData {
  balances: CashflowBalances;
  summary: CashflowSummary;
  breakdown: CategoryBreakdown;
  unclassified: number;
  monthly: MonthlyFlows;
  insights: SpendingInsights;
}

/** O resultado guarda o mês a que pertence: resposta de outro mês não é mostrada. */
type Loaded = { month: string } & ({ status: "error"; message: string } | { status: "ready"; data: SummaryData });

function Line({ label, value, currency, testId }: { label: string; value: string; currency: string; testId: string }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm">
      <dt className="text-neutral-400">{label}</dt>
      <dd className="tabular-nums" data-testid={testId}>
        {formatCurrency(value, currency)}
      </dd>
    </div>
  );
}

function BalancesPanel({
  currency,
  accounts,
  totals,
  asOf,
}: {
  currency: string;
  accounts: CashflowAccountBalance[];
  totals: CashflowCurrencyBalance | undefined;
  asOf: string;
}) {
  return (
    <div className={PANEL_CLASS} data-testid={`balances-${currency}`}>
      <h3 className="mb-2 text-sm font-medium text-neutral-300">Saldos em {formatIsoDate(asOf)}</h3>
      <table className="w-full text-left text-sm">
        <tbody>
          {accounts.map((account) => (
            <tr key={account.account_id} className="border-b border-neutral-900">
              <td className="py-1.5 pr-3">{account.account_name}</td>
              <td className="py-1.5 pr-3 text-neutral-500">{ACCOUNT_TYPE_LABELS[account.account_type]}</td>
              <td className="py-1.5 text-right tabular-nums" data-testid={`balance-${account.account_id}`}>
                {formatCurrency(account.balance, currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {totals && (
        <dl className="mt-3">
          <Line label="Disponível (corrente e dinheiro)" value={totals.liquid} currency={currency} testId={`liquid-${currency}`} />
          <Line label="Reserva" value={totals.reserve} currency={currency} testId={`reserve-${currency}`} />
          <Line
            label="Cartão (negativo = fatura em aberto)"
            value={totals.card}
            currency={currency}
            testId={`card-${currency}`}
          />
        </dl>
      )}
    </div>
  );
}

/**
 * Os dois lados da identidade do período, com os números que o backend
 * calculou: tudo o que entrou foi para gasto, investimento ou variação
 * de saldo. Nenhuma conta é feita aqui.
 */
function PeriodPanel({ block }: { block: CashflowCurrencySummary }) {
  const currency = block.currency_code;
  return (
    <div className={PANEL_CLASS} data-testid={`period-${currency}`}>
      <h3 className="mb-2 text-sm font-medium text-neutral-300">
        Movimento do período · {block.entry_count} lançamento{block.entry_count === 1 ? "" : "s"}
      </h3>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <dl>
          <p className="mb-1 text-sm text-neutral-400">De onde veio</p>
          <Line label="Renda" value={block.income} currency={currency} testId={`income-${currency}`} />
          <Line label="Terceiros (líquido)" value={block.third_party_net} currency={currency} testId={`third-${currency}`} />
          <Line label="Ajustes" value={block.adjustments_net} currency={currency} testId={`adjust-${currency}`} />
          <Line
            label="Não classificado"
            value={block.unclassified_net}
            currency={currency}
            testId={`unclassified-${currency}`}
          />
          <Line
            label="Transferências em trânsito"
            value={block.internal_transfers_net}
            currency={currency}
            testId={`transit-${currency}`}
          />
        </dl>
        <dl>
          <p className="mb-1 text-sm text-neutral-400">Para onde foi</p>
          <Line label="Gastos" value={block.expenses} currency={currency} testId={`expenses-${currency}`} />
          <Line label="Investido (líquido)" value={block.net_invested} currency={currency} testId={`invested-${currency}`} />
          <Line
            label="Variação do disponível"
            value={block.liquid_variation}
            currency={currency}
            testId={`liquid-var-${currency}`}
          />
          <Line
            label="Variação da reserva"
            value={block.reserve_variation}
            currency={currency}
            testId={`reserve-var-${currency}`}
          />
          <Line
            label="Variação do saldo do cartão"
            value={block.card_balance_variation}
            currency={currency}
            testId={`card-var-${currency}`}
          />
        </dl>
      </div>
      <p className="mt-3 text-xs text-neutral-500">
        As duas colunas somam o mesmo valor. “Em trânsito” é a transferência entre contas suas em que só uma das pontas
        caiu dentro do mês.
      </p>
    </div>
  );
}

/**
 * Resumo do controle financeiro: saldos de hoje e o movimento de um
 * mês, uma seção por moeda — moedas nunca são somadas.
 */
export function CashSummary({
  onOpenUnclassified,
  onOpenReview,
}: {
  onOpenUnclassified?: (month: string) => void;
  onOpenReview?: () => void;
}) {
  const [month, setMonth] = useState(currentMonth);
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  const range = monthRange(month);

  useEffect(() => {
    const period = monthRange(month);
    if (period === null) return;
    let cancelled = false;
    Promise.all([
      getCashBalances(),
      getCashSummary(period.start, period.end),
      getCategoryBreakdown(period.start, period.end),
      countCashEntries({ start: period.start, end: period.end, nature: "UNCLASSIFIED" }),
      getMonthlyFlows(month, 6),
      getSpendingInsights(month),
    ])
      .then(([balances, summary, breakdown, count, monthly, insights]) => {
        if (!cancelled) {
          setLoaded({
            month,
            status: "ready",
            data: { balances, summary, breakdown, unclassified: count.total, monthly, insights },
          });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoaded({ month, status: "error", message: describeApiError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [month]);

  const picker = (
    <div className="max-w-xs">
      <label className={LABEL_CLASS} htmlFor="summary-month">
        Mês
      </label>
      <input
        id="summary-month"
        type="month"
        className={INPUT_CLASS}
        value={month}
        onChange={(event) => setMonth(event.target.value)}
      />
    </div>
  );

  if (range === null) {
    return (
      <div className="space-y-4">
        {picker}
        <p className="text-sm text-neutral-400">Escolha um mês.</p>
      </div>
    );
  }
  const state = loaded !== null && loaded.month === month ? loaded : null;
  if (state === null) {
    return (
      <div className="space-y-4">
        {picker}
        <Loading />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="space-y-4">
        {picker}
        <ErrorText>{`Não foi possível carregar o resumo: ${state.message}`}</ErrorText>
      </div>
    );
  }

  const { balances, summary, breakdown, unclassified, monthly, insights } = state.data;
  if (balances.accounts.length === 0) {
    return (
      <p className="text-neutral-400" data-testid="no-cash-accounts">
        Nenhuma conta de caixa cadastrada. Crie em Cadastros uma conta do tipo corrente, reserva, cartão ou dinheiro.
      </p>
    );
  }

  // Uma seção por moeda que apareça em qualquer um dos três blocos.
  const currencies = Array.from(
    new Set([
      ...balances.accounts.map((account) => account.currency_code),
      ...summary.totals_by_currency.map((block) => block.currency_code),
    ]),
  ).sort();

  return (
    <div className="space-y-6">
      {picker}

      {unclassified > 0 && (
        <div
          className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-900 bg-amber-950/40 p-3 text-sm text-amber-200"
          data-testid="unclassified-warning"
        >
          <span>
            {unclassified === 1
              ? "1 lançamento do mês ainda não foi classificado"
              : `${unclassified} lançamentos do mês ainda não foram classificados`}
            : enquanto isso, gastos e renda ficam incompletos.
          </span>
          {onOpenReview && (
            <button type="button" className="font-medium underline" onClick={onOpenReview}>
              Classificar em grupos
            </button>
          )}
          {onOpenUnclassified && (
            <button type="button" className="underline" onClick={() => onOpenUnclassified(month)}>
              Ver esses lançamentos
            </button>
          )}
        </div>
      )}

      {currencies.map((currency) => {
        const period = summary.totals_by_currency.find((block) => block.currency_code === currency);
        const categories = breakdown.totals_by_currency.find((block) => block.currency_code === currency);
        const flows = monthly.totals_by_currency.find((block) => block.currency_code === currency);
        const thisMonth = flows?.months[flows.months.length - 1];
        const totals = balances.totals_by_currency.find((block) => block.currency_code === currency);
        const surplus = thisMonth?.surplus ?? "0";
        // Moeda sem nenhum lançamento no mês nem nos anteriores: só saldos.
        const quiet = !period && !flows;
        return (
          <section key={currency} className="space-y-4" aria-label={`Resumo em ${currency}`}>
            <h2 className="text-base font-semibold">{currency}</h2>
            {!quiet && (
              <>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                  <KpiTile label="Entradas" value={formatCurrency(period?.income ?? "0", currency)} hint="renda do mês" testId={`kpi-income-${currency}`} />
                  <KpiTile label="Saídas" value={formatCurrency(period?.expenses ?? "0", currency)} hint="gastos do mês" testId={`kpi-expenses-${currency}`} />
                  <KpiTile
                    label="Sobra"
                    value={formatSignedCurrency(surplus, currency)}
                    hint="entradas − saídas"
                    tone={Number(surplus) > 0 ? "positive" : Number(surplus) < 0 ? "negative" : "neutral"}
                    testId={`kpi-surplus-${currency}`}
                  />
                  <KpiTile label="Investido" value={formatCurrency(period?.net_invested ?? "0", currency)} hint="aportes − resgates" testId={`kpi-invested-${currency}`} />
                  <KpiTile label="Reserva" value={formatCurrency(totals?.reserve ?? "0", currency)} hint={`saldo em ${formatIsoDate(balances.as_of)}`} testId={`kpi-reserve-${currency}`} />
                </div>

                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  {flows ? (
                    <MonthlyFlowChart currency={currency} months={flows.months} />
                  ) : (
                    <div className={PANEL_CLASS}>
                      <p className="text-sm text-neutral-500">Sem lançamentos nos últimos meses.</p>
                    </div>
                  )}
                  <WhereMoneyWent currency={currency} breakdown={categories} period={period} />
                </div>

                <ImprovementPanel insights={insights.totals_by_currency.find((block) => block.currency_code === currency)} />
              </>
            )}

            <BalancesPanel
              currency={currency}
              accounts={balances.accounts.filter((account) => account.currency_code === currency)}
              totals={totals}
              asOf={balances.as_of}
            />
            {period ? (
              <details className="group">
                <summary className="cursor-pointer text-sm text-neutral-400 hover:text-neutral-200">
                  Conferência do mês (de onde veio e para onde foi cada real)
                </summary>
                <div className="mt-3">
                  <PeriodPanel block={period} />
                </div>
              </details>
            ) : (
              <p className="text-sm text-neutral-500" data-testid={`no-movement-${currency}`}>
                Nenhum lançamento em {currency} neste mês.
              </p>
            )}
          </section>
        );
      })}
    </div>
  );
}
