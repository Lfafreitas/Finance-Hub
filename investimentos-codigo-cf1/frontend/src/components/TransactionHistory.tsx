import { useState } from "react";

import { reverseTransaction } from "../api/client";
import type { AssetRead, TransactionRead } from "../api/types";
import { describeApiError } from "../lib/apiErrors";
import { sourceLabel } from "../lib/reconciliationLabels";
import { MANUAL_TRANSACTION_TYPES, transactionTypeLabel } from "../lib/transactionTypes";

interface TransactionHistoryProps {
  transactions: TransactionRead[];
  assets: AssetRead[];
  /** Abre o lançamento no formulário de correção. */
  onCorrect: (transaction: TransactionRead) => void;
  /** Chamado depois de o backend confirmar um estorno. */
  onReversed: () => void;
}

const ACTION_CLASS =
  "rounded border border-neutral-700 px-2 py-0.5 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-40";

function isTransferLeg(transaction: TransactionRead): boolean {
  return transaction.transaction_type === "TRANSFER_OUT" || transaction.transaction_type === "TRANSFER_IN";
}

/**
 * Histórico completo de uma conta, incluindo as revertidas
 * (rastreabilidade). Um lançamento ativo pode ser editado ou
 * excluído; nada é apagado — o excluído continua na lista, riscado.
 * Pernas de transferência não têm ação: o backend não corrige nem
 * estorna uma perna isolada.
 */
export function TransactionHistory({ transactions, assets, onCorrect, onReversed }: TransactionHistoryProps) {
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (transactions.length === 0) {
    return <p className="text-neutral-500">Nenhum lançamento nesta conta.</p>;
  }

  async function handleReverse(id: string) {
    setBusy(true);
    setError(null);
    try {
      await reverseTransaction(id);
      setConfirmingId(null);
      onReversed();
    } catch (err) {
      setError(describeApiError(err));
      setConfirmingId(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="overflow-x-auto">
      {error && (
        <p className="mb-2 text-sm text-red-400" role="alert">
          {error}
        </p>
      )}
      <table className="w-full text-left text-sm" data-testid="transaction-history">
        <thead>
          <tr className="border-b border-neutral-800 text-neutral-400">
            <th className="py-2 pr-3">Data</th>
            <th className="py-2 pr-3">Tipo</th>
            <th className="py-2 pr-3">Ativo</th>
            <th className="py-2 pr-3">Quantidade</th>
            <th className="py-2 pr-3">Preço</th>
            <th className="py-2 pr-3">Valor bruto</th>
            <th className="py-2 pr-3">Moeda</th>
            <th className="py-2 pr-3">Origem</th>
            <th className="py-2 pr-3">Situação</th>
            <th className="py-2">Ações</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((transaction) => {
            const asset = assets.find((item) => item.id === transaction.asset_id);
            const reversed = transaction.status === "REVERSED";
            const struck = reversed ? "text-neutral-500 line-through" : "";
            const canReverse = !reversed && !isTransferLeg(transaction);
            const canCorrect =
              canReverse && (MANUAL_TRANSACTION_TYPES as string[]).includes(transaction.transaction_type);
            const what = `${transactionTypeLabel(transaction.transaction_type)} de ${transaction.transaction_date}`;
            return (
              <tr key={transaction.id} className="border-b border-neutral-900">
                <td className={`py-2 pr-3 whitespace-nowrap ${struck}`}>{transaction.transaction_date}</td>
                <td className={`py-2 pr-3 ${struck}`}>{transactionTypeLabel(transaction.transaction_type)}</td>
                <td className={`py-2 pr-3 ${struck}`}>{asset ? asset.ticker : "—"}</td>
                <td className={`py-2 pr-3 ${struck}`}>{transaction.quantity ?? "—"}</td>
                <td className={`py-2 pr-3 ${struck}`}>{transaction.unit_price ?? "—"}</td>
                <td className={`py-2 pr-3 ${struck}`}>{transaction.gross_amount}</td>
                <td className={`py-2 pr-3 ${struck}`}>{transaction.currency_code}</td>
                <td className={`py-2 pr-3 ${struck}`}>{sourceLabel(transaction.source)}</td>
                <td className={`py-2 pr-3 ${reversed ? "text-neutral-500" : ""}`}>
                  {reversed ? "Revertida" : "Ativa"}
                </td>
                <td className="py-2 whitespace-nowrap">
                  {confirmingId === transaction.id ? (
                    <span className="flex gap-1">
                      <button
                        type="button"
                        className={ACTION_CLASS}
                        disabled={busy}
                        onClick={() => void handleReverse(transaction.id)}
                      >
                        Confirmar exclusão
                      </button>
                      <button
                        type="button"
                        className={ACTION_CLASS}
                        disabled={busy}
                        onClick={() => setConfirmingId(null)}
                      >
                        Manter
                      </button>
                    </span>
                  ) : (
                    <span className="flex gap-1">
                      {canCorrect && (
                        <button
                          type="button"
                          className={ACTION_CLASS}
                          aria-label={`Editar ${what}`}
                          onClick={() => onCorrect(transaction)}
                        >
                          Editar
                        </button>
                      )}
                      {canReverse && (
                        <button
                          type="button"
                          className={ACTION_CLASS}
                          aria-label={`Excluir ${what}`}
                          onClick={() => {
                            setError(null);
                            setConfirmingId(transaction.id);
                          }}
                        >
                          Excluir
                        </button>
                      )}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
