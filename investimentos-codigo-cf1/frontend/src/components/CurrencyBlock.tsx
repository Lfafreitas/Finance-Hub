import type { ConcentrationRead } from "../api/analytics";
import type { DashboardCurrencyTotals, PositionSummary } from "../api/types";
import { formatIsoDate } from "../lib/formatCurrency";
import { AllocationChart } from "./AllocationChart";
import { ContributionChart } from "./ContributionChart";
import { IndicatorCard } from "./IndicatorCard";
import { PositionsTable } from "./PositionsTable";

interface CurrencyBlockProps {
  /** Totais de UMA moeda, como vieram do backend. */
  block: DashboardCurrencyTotals;
  /** Só as posições DESTA moeda — quem chama já filtrou. */
  positions: PositionSummary[];
  /** Pesos das análises desta moeda (pode faltar se a análise não carregou). */
  concentration?: ConcentrationRead | null;
  /** Abre os lançamentos da conta da posição. */
  onOpenTransactions?: (accountId: string) => void;
}

/**
 * Tudo o que é dinheiro de UMA moeda: cards, gráficos e posições. O
 * componente só conhece o bloco que recebeu — não tem acesso ao resumo
 * inteiro nem a outro bloco, então não há como misturar moedas aqui.
 */
function signTone(value: string | null): "neutral" | "positive" | "negative" {
  if (value === null) return "neutral";
  return Number(value) >= 0 ? "positive" : "negative";
}

export function CurrencyBlock({ block, positions, concentration = null, onOpenTransactions }: CurrencyBlockProps) {
  const currency = block.currency_code;
  const marketReason = block.market_data_unavailable_reason;

  return (
    <div className="space-y-6" data-testid={`currency-block-${currency}`}>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <IndicatorCard label="Valor investido (custo)" value={block.total_cost_basis} currencyCode={currency} />
        <IndicatorCard
          label="Resultado realizado"
          value={block.total_realized_gain}
          currencyCode={currency}
          tone={Number(block.total_realized_gain) >= 0 ? "positive" : "negative"}
        />
        <IndicatorCard label="Proventos recebidos" value={block.total_dividends_received} currencyCode={currency} />
        <IndicatorCard label="Aportes líquidos" value={block.net_contributions} currencyCode={currency} />
        <IndicatorCard
          label="Patrimônio a mercado"
          value={block.market_value}
          currencyCode={currency}
          unavailableReason={marketReason}
        />
        <IndicatorCard
          label="P&L não realizado"
          value={block.unrealized_pnl}
          currencyCode={currency}
          tone={signTone(block.unrealized_pnl)}
          unavailableReason={marketReason}
        />
        <IndicatorCard
          label="Rentabilidade atual"
          value={block.current_return}
          currencyCode={currency}
          format="percent"
          tone={signTone(block.current_return)}
          unavailableReason={marketReason ?? "Sem custo de aquisição em posições abertas."}
        />
      </div>

      {block.market_data_as_of !== null && (
        <p className="text-xs text-neutral-500" data-testid="market-data-as-of">
          Valores de mercado a preços informados — cotação mais antiga usada: {formatIsoDate(block.market_data_as_of)}.
          Patrimônio a mercado considera só ativos, não o saldo em dinheiro.
        </p>
      )}

      {positions.length === 0 && (
        <p className="text-sm text-neutral-400" data-testid="cash-only-note">
          Esta moeda tem apenas movimentações de caixa — nenhuma posição em ativo.
        </p>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
          <h2 className="mb-2 text-[15px] font-semibold tracking-tight text-neutral-100">Distribuição da carteira</h2>
          {/* `key` por moeda: trocar de aba remonta o gráfico, sem
              carregar estado/animação do bloco anterior. */}
          <AllocationChart key={currency} currency={currency} concentration={concentration} allocation={block.allocation} />
        </div>
        <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
          <h2 className="mb-2 text-[15px] font-semibold tracking-tight text-neutral-100">Quanto você já aportou</h2>
          <ContributionChart key={currency} currency={currency} points={block.contribution_evolution} />
        </div>
      </div>

      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
        <h2 className="mb-2 text-[15px] font-semibold tracking-tight text-neutral-100">Posições</h2>
        <PositionsTable positions={positions} onOpenTransactions={onOpenTransactions} />
      </div>
    </div>
  );
}
