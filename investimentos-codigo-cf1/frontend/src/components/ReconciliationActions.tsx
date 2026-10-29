import { useState } from "react";

import { resolveReconciliation } from "../api/client";
import type { ReconciliationDecision, ReconciliationLogRead } from "../api/types";
import { describeResolveError } from "../lib/reconciliationErrors";
import { shortId } from "../lib/reconciliationLabels";

interface ReconciliationActionsProps {
  log: ReconciliationLogRead;
  /** Chamado só depois de o backend CONFIRMAR a resolução. */
  onResolved: (resolved: ReconciliationLogRead) => void;
}

type Survivor = "A" | "B";

export function ReconciliationActions({ log, onResolved }: ReconciliationActionsProps) {
  const [survivor, setSurvivor] = useState<Survivor | null>(null);
  const [pendingDecision, setPendingDecision] = useState<ReconciliationDecision | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const survivorId = survivor === "A" ? log.transaction_a_id : survivor === "B" ? log.transaction_b_id : null;
  const reversedId = survivor === "A" ? log.transaction_b_id : survivor === "B" ? log.transaction_a_id : null;

  function confirmationText(decision: ReconciliationDecision): string {
    if (decision === "MERGE" && survivorId && reversedId) {
      return (
        `Mesclar: a transação ${survivor} (${shortId(survivorId)}) permanece e a outra ` +
        `(${shortId(reversedId)}) será REVERTIDA e deixará de contar nos cálculos. Não pode ser desfeito.`
      );
    }
    if (decision === "KEEP_BOTH") {
      return "Manter as duas: as duas transações continuam ativas e este par não será mais apresentado. Não pode ser desfeito.";
    }
    return "Ignorar: nenhuma transação é alterada e este par não será mais apresentado. Não pode ser desfeito.";
  }

  async function submit(decision: ReconciliationDecision) {
    setSubmitting(true);
    setError(null);
    try {
      const resolved = await resolveReconciliation(
        log.id,
        decision === "MERGE" && survivorId
          ? { decision, surviving_transaction_id: survivorId }
          : { decision },
      );
      setPendingDecision(null);
      onResolved(resolved);
    } catch (err) {
      setPendingDecision(null);
      setError(describeResolveError(err));
    } finally {
      setSubmitting(false);
    }
  }

  const buttonClass =
    "rounded-md border border-neutral-700 px-3 py-2 text-sm text-neutral-100 hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40";

  return (
    <div className="space-y-3" data-testid="reconciliation-actions">
      <fieldset className="space-y-1">
        <legend className="text-sm text-neutral-400">
          Para mesclar, escolha a transação que deve permanecer:
        </legend>
        {(["A", "B"] as const).map((side) => (
          <label key={side} className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name={`survivor-${log.id}`}
              value={side}
              checked={survivor === side}
              onChange={() => setSurvivor(side)}
              disabled={submitting}
            />
            Manter a transação {side}
          </label>
        ))}
      </fieldset>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={buttonClass}
          disabled={submitting}
          onClick={() => setPendingDecision("IGNORE")}
        >
          Ignorar
        </button>
        <button
          type="button"
          className={buttonClass}
          disabled={submitting}
          onClick={() => setPendingDecision("KEEP_BOTH")}
        >
          Manter as duas
        </button>
        <button
          type="button"
          className={`${buttonClass} border-amber-700 text-amber-200`}
          disabled={submitting || survivor === null}
          title={survivor === null ? "Escolha primeiro a transação que deve permanecer" : undefined}
          onClick={() => setPendingDecision("MERGE")}
        >
          Mesclar
        </button>
      </div>

      {pendingDecision && (
        <div className="rounded-md border border-amber-800 bg-amber-950/40 p-3 text-sm" role="alertdialog" aria-label="Confirmar decisão">
          <p className="text-amber-100">{confirmationText(pendingDecision)}</p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              className={`${buttonClass} border-amber-600`}
              disabled={submitting}
              onClick={() => submit(pendingDecision)}
            >
              {submitting ? "Enviando…" : "Confirmar"}
            </button>
            <button
              type="button"
              className={buttonClass}
              disabled={submitting}
              onClick={() => setPendingDecision(null)}
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="text-sm text-red-400" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
