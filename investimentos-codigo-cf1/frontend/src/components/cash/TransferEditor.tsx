import { type FormEvent, useEffect, useState } from "react";

import { getCashEntries, linkCashTransfer, markInvestmentTransfer } from "../../api/cashflow";
import type { CashflowEntryRead } from "../../api/cashflowTypes";
import type { AccountRead } from "../../api/types";
import { describeApiError } from "../../lib/apiErrors";
import { LINK_WINDOW_DAYS, isCounterpartyCandidate, isOutflow, shiftIsoDate } from "../../lib/cashflow";
import { formatIsoDate } from "../../lib/formatCurrency";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS } from "../../lib/ui";
import { ErrorText } from "./shared";

interface TransferEditorProps {
  entry: CashflowEntryRead;
  accounts: AccountRead[];
  onLinked: () => void;
  onCancel: () => void;
}

type Target = "entry" | "investment";

/**
 * Transforma um lançamento existente em transferência: ligando-o ao
 * lançamento da outra ponta, ou marcando-o como aporte/resgate em uma
 * conta de investimentos. Nenhum valor ou data muda.
 */
export function TransferEditor({ entry, accounts, onLinked, onCancel }: TransferEditorProps) {
  const [candidates, setCandidates] = useState<CashflowEntryRead[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [target, setTarget] = useState<Target>("entry");
  const [counterpartyId, setCounterpartyId] = useState("");
  const [investmentId, setInvestmentId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const outflow = isOutflow(entry.amount);
  const investment = accounts.filter(
    (account) => account.account_type === "BROKERAGE" && account.currency_code === entry.currency_code,
  );
  const accountName = (id: string) => accounts.find((account) => account.id === id)?.name ?? "conta";

  useEffect(() => {
    let cancelled = false;
    getCashEntries(
      {
        start: shiftIsoDate(entry.entry_date, -LINK_WINDOW_DAYS),
        end: shiftIsoDate(entry.entry_date, LINK_WINDOW_DAYS),
      },
      500,
    )
      .then((entries) => {
        if (!cancelled) setCandidates(entries.filter((other) => isCounterpartyCandidate(entry, other)));
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(describeApiError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [entry]);

  const chosen = target === "entry" ? counterpartyId : investmentId;
  const prefix = `transfer-${entry.id}`;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (chosen === "") return;
    setSaving(true);
    setError(null);
    try {
      if (target === "entry") await linkCashTransfer(entry.id, counterpartyId);
      else await markInvestmentTransfer(entry.id, investmentId);
      onLinked();
    } catch (err) {
      setError(describeApiError(err));
      setSaving(false);
    }
  }

  return (
    <form className="space-y-3" onSubmit={handleSubmit} aria-label={`Transferência de ${entry.description}`}>
      <fieldset className="flex flex-wrap gap-4 text-sm">
        <legend className={LABEL_CLASS}>A outra ponta é</legend>
        <label className="inline-flex items-center gap-1.5">
          <input
            type="radio"
            name={`${prefix}-target`}
            checked={target === "entry"}
            disabled={saving}
            onChange={() => setTarget("entry")}
          />
          um lançamento em outra conta de caixa
        </label>
        <label className="inline-flex items-center gap-1.5">
          <input
            type="radio"
            name={`${prefix}-target`}
            checked={target === "investment"}
            disabled={saving}
            onChange={() => setTarget("investment")}
          />
          {outflow ? "um aporte em conta de investimentos" : "um resgate de conta de investimentos"}
        </label>
      </fieldset>

      {target === "entry" ? (
        <div className="max-w-2xl">
          <label className={LABEL_CLASS} htmlFor={`${prefix}-counterparty`}>
            Lançamento da outra ponta
          </label>
          {loadError ? (
            <ErrorText>{loadError}</ErrorText>
          ) : candidates === null ? (
            <p className="text-sm text-neutral-400" role="status">
              Procurando…
            </p>
          ) : candidates.length === 0 ? (
            <p className="text-sm text-neutral-400" data-testid="no-candidates">
              Nenhum lançamento de outra conta com o valor oposto a até {LINK_WINDOW_DAYS} dias desta data. Importe o
              extrato da outra conta primeiro.
            </p>
          ) : (
            <select
              id={`${prefix}-counterparty`}
              className={INPUT_CLASS}
              value={counterpartyId}
              disabled={saving}
              onChange={(event) => setCounterpartyId(event.target.value)}
            >
              <option value="">Selecione…</option>
              {candidates.map((other) => (
                <option key={other.id} value={other.id}>
                  {formatIsoDate(other.entry_date)} · {accountName(other.account_id)} · {other.description}
                </option>
              ))}
            </select>
          )}
        </div>
      ) : (
        <div className="max-w-md">
          <label className={LABEL_CLASS} htmlFor={`${prefix}-investment`}>
            Conta de investimentos
          </label>
          {investment.length === 0 ? (
            <p className="text-sm text-neutral-400" data-testid="no-investment-accounts">
              Nenhuma conta de investimentos em {entry.currency_code}.
            </p>
          ) : (
            <select
              id={`${prefix}-investment`}
              className={INPUT_CLASS}
              value={investmentId}
              disabled={saving}
              onChange={(event) => setInvestmentId(event.target.value)}
            >
              <option value="">Selecione…</option>
              {investment.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name} — {account.institution_name}
                </option>
              ))}
            </select>
          )}
          <p className="mt-1 text-xs text-neutral-500">
            Isto só classifica o lançamento de caixa. O aporte ou resgate do lado dos investimentos continua sendo
            lançado na tela de Investimentos.
          </p>
        </div>
      )}

      <div className="flex gap-2">
        <button type="submit" className={BUTTON_CLASS} disabled={saving || chosen === ""}>
          {saving ? "Salvando…" : "Marcar como transferência"}
        </button>
        <button type="button" className={BUTTON_CLASS} disabled={saving} onClick={onCancel}>
          Cancelar
        </button>
      </div>
      {error && <ErrorText>{error}</ErrorText>}
    </form>
  );
}
