import { type FormEvent, useState } from "react";

import { correctCashEntry } from "../../api/cashflow";
import type { CashflowEntryRead } from "../../api/cashflowTypes";
import { describeApiError } from "../../lib/apiErrors";
import { isOutflow, parseAmountInput } from "../../lib/cashflow";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS } from "../../lib/ui";
import { ErrorText } from "./shared";

interface EntryEditorProps {
  entry: CashflowEntryRead;
  onCancel: () => void;
  onSaved: () => void;
}

/** "-80.0000" → "80,00" para o campo de valor. */
function amountForInput(amount: string): string {
  return Math.abs(Number(amount)).toFixed(2).replace(".", ",");
}

/**
 * Edita data, valor, descrição e notas de um lançamento manual. O
 * servidor guarda o original como excluído e grava a versão nova; a
 * classificação vai junto.
 */
export function EntryEditor({ entry, onCancel, onSaved }: EntryEditorProps) {
  const [direction, setDirection] = useState<"out" | "in">(isOutflow(entry.amount) ? "out" : "in");
  const [date, setDate] = useState(entry.entry_date);
  const [amount, setAmount] = useState(amountForInput(entry.amount));
  const [description, setDescription] = useState(entry.description);
  const [notes, setNotes] = useState(entry.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsed = parseAmountInput(amount);
  const invalid = date === "" || parsed === null || description.trim() === "";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (parsed === null) return;
    setSaving(true);
    setError(null);
    try {
      await correctCashEntry(entry.id, {
        entry_date: date,
        amount: direction === "out" ? `-${parsed}` : parsed,
        description: description.trim(),
        notes: notes.trim() === "" ? null : notes.trim(),
      });
      onSaved();
    } catch (err) {
      setError(describeApiError(err));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-label={`Editar ${entry.description}`} className="space-y-3">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <div>
          <label className={LABEL_CLASS} htmlFor={`ed-date-${entry.id}`}>
            Data
          </label>
          <input
            id={`ed-date-${entry.id}`}
            type="date"
            className={INPUT_CLASS}
            value={date}
            disabled={saving}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor={`ed-direction-${entry.id}`}>
            Sentido
          </label>
          <select
            id={`ed-direction-${entry.id}`}
            className={INPUT_CLASS}
            value={direction}
            disabled={saving}
            onChange={(e) => setDirection(e.target.value as "out" | "in")}
          >
            <option value="out">Saída</option>
            <option value="in">Entrada</option>
          </select>
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor={`ed-amount-${entry.id}`}>
            Valor
          </label>
          <input
            id={`ed-amount-${entry.id}`}
            inputMode="decimal"
            className={INPUT_CLASS}
            value={amount}
            disabled={saving}
            aria-invalid={amount.trim() !== "" && parsed === null}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
        <div className="col-span-2">
          <label className={LABEL_CLASS} htmlFor={`ed-description-${entry.id}`}>
            Descrição
          </label>
          <input
            id={`ed-description-${entry.id}`}
            className={INPUT_CLASS}
            value={description}
            maxLength={255}
            disabled={saving}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <div className="col-span-2 md:col-span-5">
          <label className={LABEL_CLASS} htmlFor={`ed-notes-${entry.id}`}>
            Notas
          </label>
          <input
            id={`ed-notes-${entry.id}`}
            className={INPUT_CLASS}
            value={notes}
            disabled={saving}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
      </div>
      <p className="text-xs text-neutral-500">
        A versão antiga fica em “Mostrar excluídos”. A classificação continua a mesma.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <button type="submit" className={BUTTON_CLASS} disabled={saving || invalid}>
          {saving ? "Salvando…" : "Salvar edição"}
        </button>
        <button type="button" className={BUTTON_CLASS} disabled={saving} onClick={onCancel}>
          Cancelar
        </button>
        {error && <ErrorText>{error}</ErrorText>}
      </div>
    </form>
  );
}
