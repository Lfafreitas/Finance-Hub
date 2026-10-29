import { useEffect, useState } from "react";

import { getReconciliationComparison, getTransaction } from "../api/client";
import type {
  AccountRead,
  ReconciliationComparisonRead,
  ReconciliationLogRead,
  TransactionRead,
} from "../api/types";
import {
  fieldLabel,
  formatAbsoluteDifference,
  formatRelativeDifference,
  shortId,
  sourceLabel,
} from "../lib/reconciliationLabels";
import { ReconciliationActions } from "./ReconciliationActions";

interface ReconciliationDetailProps {
  log: ReconciliationLogRead;
  accounts: AccountRead[];
  onResolved: (resolved: ReconciliationLogRead) => void;
}

interface DetailData {
  transactionA: TransactionRead;
  transactionB: TransactionRead;
  comparison: ReconciliationComparisonRead;
}

type DetailState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: DetailData };

function TransactionCard({
  side,
  transaction,
  accounts,
}: {
  side: "A" | "B";
  transaction: TransactionRead;
  accounts: AccountRead[];
}) {
  const account = accounts.find((item) => item.id === transaction.account_id);
  return (
    <div className="rounded-md border border-neutral-800 p-3 text-sm" data-testid={`transaction-card-${side}`}>
      <p className="font-medium text-neutral-100">Transação {side}</p>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-neutral-300">
        <dt className="text-neutral-500">Origem</dt>
        <dd>{sourceLabel(transaction.source)}</dd>
        <dt className="text-neutral-500">Tipo</dt>
        <dd>{transaction.transaction_type}</dd>
        <dt className="text-neutral-500">Situação</dt>
        <dd>{transaction.status === "ACTIVE" ? "Ativa" : "Revertida"}</dd>
        <dt className="text-neutral-500">Conta</dt>
        <dd title={transaction.account_id}>
          {account ? `${account.name} — ${account.institution_name}` : shortId(transaction.account_id)}
        </dd>
        <dt className="text-neutral-500">Ativo (id)</dt>
        <dd className="font-mono text-xs" title={transaction.asset_id ?? undefined}>
          {transaction.asset_id ? shortId(transaction.asset_id) : "—"}
        </dd>
        <dt className="text-neutral-500">Id</dt>
        <dd className="font-mono text-xs" title={transaction.id}>
          {shortId(transaction.id)}
        </dd>
        {transaction.notes && (
          <>
            <dt className="text-neutral-500">Observações</dt>
            <dd>{transaction.notes}</dd>
          </>
        )}
      </dl>
    </div>
  );
}

/**
 * Detalhe de UM par. Montado com `key={log.id}` pelo pai: trocar de
 * par remonta o componente, então o estado sempre começa em "loading"
 * e nunca mostra dados de um par anterior.
 */
export function ReconciliationDetail({ log, accounts, onResolved }: ReconciliationDetailProps) {
  const [state, setState] = useState<DetailState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getTransaction(log.transaction_a_id),
      getTransaction(log.transaction_b_id),
      getReconciliationComparison(log.id),
    ])
      .then(([transactionA, transactionB, comparison]) => {
        if (!cancelled) setState({ status: "ready", data: { transactionA, transactionB, comparison } });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ status: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [log.id, log.transaction_a_id, log.transaction_b_id]);

  if (state.status === "loading") {
    return (
      <p className="text-neutral-400" role="status">
        Carregando detalhe do par…
      </p>
    );
  }

  if (state.status === "error") {
    return (
      <p className="text-red-400" role="alert">
        Não foi possível carregar o detalhe do par: {state.message}
      </p>
    );
  }

  const { transactionA, transactionB, comparison } = state.data;
  const divergent = comparison.classification === "DIVERGENT";

  return (
    <div className="space-y-4" data-testid="reconciliation-detail">
      <div className="flex items-center gap-3">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            divergent ? "bg-amber-900/60 text-amber-200" : "bg-emerald-900/60 text-emerald-200"
          }`}
          data-testid="classification-badge"
        >
          {divergent ? "Divergente" : "Equivalente"}
        </span>
        <span className="text-xs text-neutral-500">
          {divergent
            ? "Há diferença em pelo menos um campo comparado."
            : "Todos os campos comparados são iguais — a decisão continua sendo sua."}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <TransactionCard side="A" transaction={transactionA} accounts={accounts} />
        <TransactionCard side="B" transaction={transactionB} accounts={accounts} />
      </div>

      <table className="w-full text-left text-sm" data-testid="comparison-table">
        <thead>
          <tr className="border-b border-neutral-800 text-neutral-400">
            <th className="py-2 pr-3">Campo</th>
            <th className="py-2 pr-3">Transação A</th>
            <th className="py-2 pr-3">Transação B</th>
            <th className="py-2 pr-3">Diferença</th>
            <th className="py-2 pr-3">Diferença relativa</th>
            <th className="py-2">Situação</th>
          </tr>
        </thead>
        <tbody>
          {comparison.fields.map((field) => (
            <tr
              key={field.field}
              data-testid={`comparison-row-${field.field}`}
              data-equal={field.equal}
              className={`border-b border-neutral-900 ${field.equal ? "" : "bg-amber-950/40 text-amber-100"}`}
            >
              <td className="py-2 pr-3">{fieldLabel(field.field)}</td>
              <td className="py-2 pr-3">{field.value_a ?? "—"}</td>
              <td className="py-2 pr-3">{field.value_b ?? "—"}</td>
              <td className="py-2 pr-3">{formatAbsoluteDifference(field.field, field.absolute_difference)}</td>
              <td className="py-2 pr-3" title={field.relative_difference ?? undefined}>
                {formatRelativeDifference(field.relative_difference)}
              </td>
              <td className="py-2">{field.equal ? "Igual" : "Diferente"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="text-xs text-neutral-500">Motivo registrado na detecção: {comparison.match_reason}</p>

      <ReconciliationActions log={log} onResolved={onResolved} />
    </div>
  );
}
