import type { PositionSummary } from "../api/types";
import { formatCurrency, formatIsoDate, formatQuantity } from "../lib/formatCurrency";
import { exactTitle } from "../lib/privacy";

interface PositionsTableProps {
  positions: PositionSummary[];
  /** Quando existe, cada linha ganha um atalho para os lançamentos da conta. */
  onOpenTransactions?: (accountId: string) => void;
}

/**
 * Célula de dinheiro: formatada para leitura na moeda da posição, com
 * o valor EXATO do backend no `title`. `precise` = até 8 casas, para
 * preços unitários. Sem valor ou sem moeda, "—".
 */
function Money({
  value,
  currency,
  precise = false,
}: {
  value: string | null;
  currency: string | null;
  precise?: boolean;
}) {
  if (value === null || currency === null) return <>—</>;
  return <span title={exactTitle(value)}>{formatCurrency(value, currency, precise ? 8 : 2)}</span>;
}

export function PositionsTable({ positions, onOpenTransactions }: PositionsTableProps) {
  if (positions.length === 0) {
    return <p className="text-neutral-500">Nenhuma posição encontrada.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm" data-testid="positions-table">
        <thead>
          <tr className="border-b border-neutral-800 text-neutral-400">
            <th className="py-2 pr-4">Ativo</th>
            <th className="py-2 pr-4">Quantidade</th>
            <th className="py-2 pr-4">Preço médio</th>
            <th className="py-2 pr-4">Custo de aquisição</th>
            <th className="py-2 pr-4">Resultado realizado</th>
            <th className="py-2 pr-4">Proventos</th>
            <th className="py-2 pr-4">Cotação</th>
            <th className="py-2 pr-4">Valor de mercado</th>
            <th className="py-2">P&L não realizado</th>
            {onOpenTransactions && <th className="py-2 pl-4">Ações</th>}
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => {
            const currency = position.currency_code;
            return (
              <tr
                key={`${position.account_id}-${position.asset_id}`}
                className="border-b border-neutral-900 whitespace-nowrap"
              >
                <td className="py-2 pr-4 text-neutral-100">{position.asset_ticker}</td>
                <td className="py-2 pr-4" title={exactTitle(position.quantity)}>
                  {formatQuantity(position.quantity)}
                </td>
                <td className="py-2 pr-4">
                  <Money value={position.average_cost} currency={currency} precise />
                </td>
                <td className="py-2 pr-4">
                  <Money value={position.total_cost_basis} currency={currency} />
                </td>
                <td className="py-2 pr-4">
                  <Money value={position.realized_gain} currency={currency} />
                </td>
                <td className="py-2 pr-4">
                  <Money value={position.dividends_received} currency={currency} />
                </td>
                <td className="py-2 pr-4">
                  {position.market_price === null || position.market_price_date === null ? (
                    "—"
                  ) : (
                    <>
                      <Money value={position.market_price} currency={currency} precise />{" "}
                      <span className="text-xs text-neutral-500">
                        ({formatIsoDate(position.market_price_date)})
                      </span>
                    </>
                  )}
                </td>
                <td
                  className={`py-2 pr-4 ${position.market_value === null ? "text-neutral-500" : ""}`}
                  title={position.unavailable_reason ?? undefined}
                >
                  {position.market_value === null ? (
                    "Indisponível"
                  ) : (
                    <Money value={position.market_value} currency={currency} />
                  )}
                </td>
                <td className="py-2">
                  <Money value={position.unrealized_pnl} currency={currency} />
                </td>
                {onOpenTransactions && (
                  <td className="py-2 pl-4">
                    <button
                      type="button"
                      className="rounded border border-neutral-700 px-2 py-0.5 text-xs text-neutral-200 hover:bg-neutral-800"
                      aria-label={`Lançamentos de ${position.asset_ticker}`}
                      onClick={() => onOpenTransactions(position.account_id)}
                    >
                      Lançamentos
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
