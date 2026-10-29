import { type FormEvent, useState } from "react";

import { createTransfer } from "../api/client";
import type { AccountRead, TransferCreate, TransferRead } from "../api/types";
import { describeApiError } from "../lib/apiErrors";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS } from "../lib/ui";

interface TransferFormProps {
  accounts: AccountRead[];
  onCreated: (transfer: TransferRead) => void;
}

/** Transferência entre duas contas próprias: o backend grava as duas pernas juntas. */
export function TransferForm({ accounts, onCreated }: TransferFormProps) {
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [amount, setAmount] = useState("");
  const [fees, setFees] = useState("");
  const [date, setDate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const missing = fromId === "" || toId === "" || fromId === toId || amount.trim() === "" || date === "";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const payload: TransferCreate = {
      from_account_id: fromId,
      to_account_id: toId,
      gross_amount: amount.trim(),
      transaction_date: date,
    };
    if (fees.trim() !== "") payload.fees = fees.trim();

    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const transfer = await createTransfer(payload);
      setSuccess("Transferência registrada.");
      setAmount("");
      setFees("");
      onCreated(transfer);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  const options = accounts.map((account) => (
    <option key={account.id} value={account.id}>
      {account.name} — {account.institution_name} ({account.currency_code})
    </option>
  ));

  return (
    <form className="space-y-3" onSubmit={handleSubmit} aria-label="Nova transferência">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <div>
          <label className={LABEL_CLASS} htmlFor="tr-from">
            Conta de origem
          </label>
          <select id="tr-from" className={INPUT_CLASS} value={fromId} disabled={submitting} onChange={(e) => setFromId(e.target.value)}>
            <option value="">Selecione…</option>
            {options}
          </select>
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="tr-to">
            Conta de destino
          </label>
          <select id="tr-to" className={INPUT_CLASS} value={toId} disabled={submitting} onChange={(e) => setToId(e.target.value)}>
            <option value="">Selecione…</option>
            {options}
          </select>
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="tr-amount">
            Valor
          </label>
          <input id="tr-amount" inputMode="decimal" className={INPUT_CLASS} value={amount} disabled={submitting} onChange={(e) => setAmount(e.target.value)} />
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="tr-fees">
            Taxas (opcional)
          </label>
          <input id="tr-fees" inputMode="decimal" className={INPUT_CLASS} value={fees} disabled={submitting} onChange={(e) => setFees(e.target.value)} />
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="tr-date">
            Data
          </label>
          <input id="tr-date" type="date" className={INPUT_CLASS} value={date} disabled={submitting} onChange={(e) => setDate(e.target.value)} />
        </div>
      </div>

      {fromId !== "" && fromId === toId && (
        <p className="text-xs text-amber-300">Origem e destino precisam ser contas diferentes.</p>
      )}

      <button type="submit" className={BUTTON_CLASS} disabled={submitting || missing}>
        {submitting ? "Enviando…" : "Transferir"}
      </button>

      {success && (
        <p className="text-sm text-emerald-300" role="status">
          {success}
        </p>
      )}
      {error && (
        <p className="text-sm text-red-400" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
