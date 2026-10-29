import { type FormEvent, useState } from "react";

import { correctTransaction, createTransaction } from "../api/client";
import type {
  AccountRead,
  AssetRead,
  CurrencyRead,
  ManualTransactionType,
  TransactionCreate,
  TransactionRead,
} from "../api/types";
import { describeApiError } from "../lib/apiErrors";
import {
  hasNoCashAmount,
  MANUAL_TRANSACTION_TYPES,
  TRANSACTION_TYPE_RULES,
} from "../lib/transactionTypes";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS } from "../lib/ui";

interface TransactionFormProps {
  account: AccountRead;
  assets: AssetRead[];
  currencies: CurrencyRead[];
  /** Chamado só depois de o backend confirmar a criação ou a correção. */
  onCreated: (transaction: TransactionRead) => void;
  /**
   * Lançamento a corrigir. O formulário abre preenchido com ele e, ao
   * enviar, o backend estorna o original e grava um novo — o original
   * continua no histórico como revertido. Conta e ativo não mudam em
   * uma correção.
   */
  correcting?: TransactionRead;
  onCancelCorrection?: () => void;
}

/**
 * Lançamento manual de UMA transação. O formulário só coleta e envia:
 * os valores vão como texto, exatamente como digitados, e toda regra
 * (posição suficiente, moeda do ativo, coerência dos campos) é
 * decidida pelo backend — o erro dele é mostrado como veio.
 */
export function TransactionForm({
  account,
  assets,
  currencies,
  onCreated,
  correcting,
  onCancelCorrection,
}: TransactionFormProps) {
  // O estado inicial vem do lançamento em correção; quem usa o
  // formulário troca a `key` para remontá-lo a cada lançamento.
  const [type, setType] = useState<ManualTransactionType>(
    (correcting?.transaction_type as ManualTransactionType | undefined) ?? "BUY",
  );
  const [assetId, setAssetId] = useState(correcting?.asset_id ?? "");
  const [quantity, setQuantity] = useState(correcting?.quantity ?? "");
  const [unitPrice, setUnitPrice] = useState(correcting?.unit_price ?? "");
  const [fees, setFees] = useState(correcting?.fees ?? "");
  const [grossAmount, setGrossAmount] = useState(correcting?.gross_amount ?? "");
  const [date, setDate] = useState(correcting?.transaction_date ?? "");
  const [cashCurrency, setCashCurrency] = useState<string | null>(correcting?.currency_code ?? null);
  const [notes, setNotes] = useState(correcting?.notes ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const rule = TRANSACTION_TYPE_RULES[type];
  const noCash = hasNoCashAmount(type);
  const asset = rule.asset === "hidden" ? undefined : assets.find((item) => item.id === assetId);
  // Com ativo, a moeda é a DO ATIVO (o backend exige); sem ativo, a
  // escolhida para o movimento, começando pela moeda da conta.
  const currency = asset ? asset.currency_code : (cashCurrency ?? account.currency_code);

  const missing =
    date === "" ||
    (rule.asset === "required" && !asset) ||
    (rule.quantity === "required" && quantity.trim() === "") ||
    (rule.unitPrice === "required" && unitPrice.trim() === "") ||
    (!noCash && grossAmount.trim() === "");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const payload: TransactionCreate = {
      account_id: account.id,
      transaction_type: type,
      gross_amount: noCash ? "0" : grossAmount.trim(),
      currency_code: currency,
      transaction_date: date,
    };
    if (asset) payload.asset_id = asset.id;
    if (rule.quantity !== "hidden" && quantity.trim() !== "") payload.quantity = quantity.trim();
    if (rule.unitPrice !== "hidden" && unitPrice.trim() !== "") payload.unit_price = unitPrice.trim();
    if (!noCash && fees.trim() !== "") payload.fees = fees.trim();
    if (notes.trim() !== "") payload.notes = notes.trim();

    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      if (correcting) {
        // A tela fecha a correção ao receber o novo lançamento.
        onCreated(await correctTransaction(correcting.id, payload));
        return;
      }
      const created = await createTransaction(payload);
      setSuccess("Lançamento criado.");
      setQuantity("");
      setUnitPrice("");
      setFees("");
      setGrossAmount("");
      setNotes("");
      onCreated(created);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      className="space-y-3"
      onSubmit={handleSubmit}
      aria-label={correcting ? "Editar lançamento" : "Novo lançamento"}
    >
      {correcting && (
        <p className="text-xs text-amber-300" data-testid="correction-note">
          Ao salvar, o lançamento original fica no histórico como revertido e um novo é gravado com estes valores.
          Conta e ativo não mudam em uma correção.
        </p>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div>
          <label className={LABEL_CLASS} htmlFor="tx-type">
            Tipo
          </label>
          <select
            id="tx-type"
            className={INPUT_CLASS}
            value={type}
            disabled={submitting}
            onChange={(event) => setType(event.target.value as ManualTransactionType)}
          >
            {MANUAL_TRANSACTION_TYPES.map((item) => (
              <option key={item} value={item}>
                {TRANSACTION_TYPE_RULES[item].label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL_CLASS} htmlFor="tx-date">
            Data
          </label>
          <input
            id="tx-date"
            type="date"
            className={INPUT_CLASS}
            value={date}
            disabled={submitting}
            onChange={(event) => setDate(event.target.value)}
          />
        </div>

        {rule.asset !== "hidden" && (
          <div>
            <label className={LABEL_CLASS} htmlFor="tx-asset">
              Ativo{rule.asset === "optional" ? " (opcional)" : ""}
            </label>
            <select
              id="tx-asset"
              className={INPUT_CLASS}
              value={assetId}
              disabled={submitting || correcting !== undefined}
              onChange={(event) => setAssetId(event.target.value)}
            >
              <option value="">{rule.asset === "optional" ? "Sem ativo" : "Selecione…"}</option>
              {assets.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.ticker} ({item.country}, {item.currency_code})
                </option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label className={LABEL_CLASS} htmlFor="tx-currency">
            Moeda
          </label>
          {asset ? (
            <p id="tx-currency" className="px-1 py-2 text-sm text-neutral-300" data-testid="tx-currency-fixed">
              {asset.currency_code} (moeda do ativo)
            </p>
          ) : (
            <select
              id="tx-currency"
              className={INPUT_CLASS}
              value={currency}
              disabled={submitting}
              onChange={(event) => setCashCurrency(event.target.value)}
            >
              {/* A moeda da conta aparece mesmo se a lista ainda não carregou. */}
              {[...new Set([account.currency_code, ...currencies.map((item) => item.code)])].map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          )}
        </div>

        {rule.quantity !== "hidden" && (
          <div>
            <label className={LABEL_CLASS} htmlFor="tx-quantity">
              Quantidade
            </label>
            <input
              id="tx-quantity"
              inputMode="decimal"
              className={INPUT_CLASS}
              value={quantity}
              disabled={submitting}
              onChange={(event) => setQuantity(event.target.value)}
            />
            {rule.quantityHint && <p className="mt-1 text-xs text-neutral-500">{rule.quantityHint}</p>}
          </div>
        )}

        {rule.unitPrice !== "hidden" && (
          <div>
            <label className={LABEL_CLASS} htmlFor="tx-unit-price">
              Preço unitário
            </label>
            <input
              id="tx-unit-price"
              inputMode="decimal"
              className={INPUT_CLASS}
              value={unitPrice}
              disabled={submitting}
              onChange={(event) => setUnitPrice(event.target.value)}
            />
          </div>
        )}

        {!noCash && (
          <>
            <div>
              <label className={LABEL_CLASS} htmlFor="tx-gross">
                Valor bruto
              </label>
              <input
                id="tx-gross"
                inputMode="decimal"
                className={INPUT_CLASS}
                value={grossAmount}
                disabled={submitting}
                onChange={(event) => setGrossAmount(event.target.value)}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="tx-fees">
                Taxas (opcional)
              </label>
              <input
                id="tx-fees"
                inputMode="decimal"
                className={INPUT_CLASS}
                value={fees}
                disabled={submitting}
                onChange={(event) => setFees(event.target.value)}
              />
            </div>
          </>
        )}

        <div className="col-span-2">
          <label className={LABEL_CLASS} htmlFor="tx-notes">
            Observações (opcional)
          </label>
          <input
            id="tx-notes"
            className={INPUT_CLASS}
            value={notes}
            disabled={submitting}
            onChange={(event) => setNotes(event.target.value)}
          />
        </div>
      </div>

      <p className="text-xs text-neutral-500">
        Use ponto como separador decimal (ex.: 1234.56). O valor bruto é o que consta na nota — o sistema não o
        calcula a partir de quantidade e preço.
      </p>

      <div className="flex gap-2">
        <button type="submit" className={BUTTON_CLASS} disabled={submitting || missing}>
          {submitting ? "Enviando…" : correcting ? "Salvar correção" : "Lançar"}
        </button>
        {correcting && (
          <button type="button" className={BUTTON_CLASS} onClick={onCancelCorrection} disabled={submitting}>
            Cancelar correção
          </button>
        )}
      </div>

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
