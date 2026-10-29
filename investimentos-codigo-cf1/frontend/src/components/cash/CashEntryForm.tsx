import { type FormEvent, useState } from "react";

import { createCashEntry, createCashTransfer } from "../../api/cashflow";
import type { CashflowNature } from "../../api/cashflowTypes";
import type { AccountRead } from "../../api/types";
import { ACCOUNT_TYPE_LABELS } from "../../lib/accountTypes";
import { describeApiError } from "../../lib/apiErrors";
import { MANUAL_NATURES, NATURE_LABELS, cashAccounts, parseAmountInput, todayIso } from "../../lib/cashflow";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS, PANEL_CLASS } from "../../lib/ui";
import { ErrorText } from "./shared";

interface CashEntryFormProps {
  /** Todas as contas: as de investimentos só aparecem como ponta de transferência. */
  accounts: AccountRead[];
  onCreated: () => void;
}

type Mode = "entry" | "transfer";

function accountLabel(account: AccountRead): string {
  return `${account.name} — ${ACCOUNT_TYPE_LABELS[account.account_type]} (${account.currency_code})`;
}

/**
 * Lançamento manual ou transferência. O valor é sempre digitado
 * positivo; o sentido (entrada/saída) decide o sinal enviado.
 */
export function CashEntryForm({ accounts, onCreated }: CashEntryFormProps) {
  const [mode, setMode] = useState<Mode>("entry");
  const [accountId, setAccountId] = useState("");
  const [toAccountId, setToAccountId] = useState("");
  const [direction, setDirection] = useState<"out" | "in">("out");
  const [date, setDate] = useState(todayIso);
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [nature, setNature] = useState<CashflowNature>("UNCLASSIFIED");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const cash = cashAccounts(accounts);
  const parsed = parseAmountInput(amount);
  const amountInvalid = amount.trim() !== "" && parsed === null;
  const missing =
    accountId === "" ||
    date === "" ||
    parsed === null ||
    description.trim() === "" ||
    (mode === "transfer" && (toAccountId === "" || toAccountId === accountId));

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (parsed === null) return;
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    const cleanNotes = notes.trim() === "" ? null : notes.trim();
    try {
      if (mode === "entry") {
        await createCashEntry({
          account_id: accountId,
          entry_date: date,
          amount: direction === "out" ? `-${parsed}` : parsed,
          description: description.trim(),
          nature,
          notes: cleanNotes,
        });
        setSuccess("Lançamento registrado.");
      } else {
        await createCashTransfer({
          from_account_id: accountId,
          to_account_id: toAccountId,
          entry_date: date,
          amount: parsed,
          description: description.trim(),
          notes: cleanNotes,
        });
        setSuccess("Transferência registrada.");
      }
      setAmount("");
      setDescription("");
      setNotes("");
      onCreated();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className={PANEL_CLASS} onSubmit={handleSubmit} aria-label="Novo lançamento de caixa">
      <div className="mb-3 flex gap-2" role="group" aria-label="Tipo de registro">
        {(["entry", "transfer"] as const).map((item) => (
          <button
            key={item}
            type="button"
            aria-pressed={mode === item}
            className={`rounded-md px-3 py-1 text-sm ${
              mode === item ? "bg-neutral-800 text-neutral-100" : "text-neutral-400 hover:text-neutral-100"
            }`}
            onClick={() => {
              setMode(item);
              setError(null);
              setSuccess(null);
            }}
          >
            {item === "entry" ? "Lançamento" : "Transferência entre contas"}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="col-span-2">
          <label className={LABEL_CLASS} htmlFor="ce-account">
            {mode === "entry" ? "Conta" : "Sai de"}
          </label>
          <select
            id="ce-account"
            className={INPUT_CLASS}
            value={accountId}
            disabled={submitting}
            onChange={(event) => setAccountId(event.target.value)}
          >
            <option value="">Selecione…</option>
            {(mode === "entry" ? cash : accounts).map((account) => (
              <option key={account.id} value={account.id}>
                {accountLabel(account)}
              </option>
            ))}
          </select>
        </div>

        {mode === "transfer" ? (
          <div className="col-span-2">
            <label className={LABEL_CLASS} htmlFor="ce-to-account">
              Entra em
            </label>
            <select
              id="ce-to-account"
              className={INPUT_CLASS}
              value={toAccountId}
              disabled={submitting}
              onChange={(event) => setToAccountId(event.target.value)}
            >
              <option value="">Selecione…</option>
              {accounts
                .filter((account) => account.id !== accountId)
                .map((account) => (
                  <option key={account.id} value={account.id}>
                    {accountLabel(account)}
                  </option>
                ))}
            </select>
          </div>
        ) : (
          <>
            <div>
              <label className={LABEL_CLASS} htmlFor="ce-direction">
                Sentido
              </label>
              <select
                id="ce-direction"
                className={INPUT_CLASS}
                value={direction}
                disabled={submitting}
                onChange={(event) => setDirection(event.target.value as "out" | "in")}
              >
                <option value="out">Saída</option>
                <option value="in">Entrada</option>
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="ce-nature">
                Natureza
              </label>
              <select
                id="ce-nature"
                className={INPUT_CLASS}
                value={nature}
                disabled={submitting}
                onChange={(event) => setNature(event.target.value as CashflowNature)}
              >
                {MANUAL_NATURES.map((item) => (
                  <option key={item} value={item}>
                    {NATURE_LABELS[item]}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}

        <div>
          <label className={LABEL_CLASS} htmlFor="ce-date">
            Data
          </label>
          <input
            id="ce-date"
            type="date"
            className={INPUT_CLASS}
            value={date}
            max={todayIso()}
            disabled={submitting}
            onChange={(event) => setDate(event.target.value)}
          />
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="ce-amount">
            Valor
          </label>
          <input
            id="ce-amount"
            inputMode="decimal"
            placeholder="0,00"
            className={INPUT_CLASS}
            value={amount}
            disabled={submitting}
            aria-invalid={amountInvalid}
            onChange={(event) => setAmount(event.target.value)}
          />
        </div>
        <div className="col-span-2">
          <label className={LABEL_CLASS} htmlFor="ce-description">
            Descrição
          </label>
          <input
            id="ce-description"
            className={INPUT_CLASS}
            value={description}
            maxLength={255}
            disabled={submitting}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>
        <div className="col-span-2 md:col-span-4">
          <label className={LABEL_CLASS} htmlFor="ce-notes">
            Observação (opcional)
          </label>
          <input
            id="ce-notes"
            className={INPUT_CLASS}
            value={notes}
            disabled={submitting}
            onChange={(event) => setNotes(event.target.value)}
          />
        </div>
      </div>

      {amountInvalid && (
        <p className="mt-2 text-xs text-amber-300" data-testid="amount-hint">
          Digite um valor positivo, com até 4 casas decimais (ex.: 1.234,56).
        </p>
      )}
      <p className="mt-2 text-xs text-neutral-500">
        Para corrigir depois, use Editar na lista (lançamento manual) ou Excluir e lance de novo (transferência ou outra conta).
      </p>

      <button type="submit" className={`${BUTTON_CLASS} mt-3`} disabled={submitting || missing}>
        {submitting ? "Salvando…" : mode === "entry" ? "Registrar lançamento" : "Registrar transferência"}
      </button>
      {error && <ErrorText>{error}</ErrorText>}
      {success && (
        <p className="mt-2 text-sm text-emerald-300" role="status">
          {success}
        </p>
      )}
    </form>
  );
}
