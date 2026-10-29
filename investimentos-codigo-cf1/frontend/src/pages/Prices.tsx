import { type FormEvent, useCallback, useEffect, useState } from "react";

import { getLatestPrices, setAssetPrice } from "../api/client";
import type { AssetLatestPrice } from "../api/types";
import { describeApiError } from "../lib/apiErrors";
import { formatIsoDate } from "../lib/formatCurrency";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS, PANEL_CLASS } from "../lib/ui";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; prices: AssetLatestPrice[] };

/**
 * Cotações informadas à mão. O sistema não busca preço em lugar
 * nenhum: o valor de mercado do Dashboard usa a última cotação
 * informada aqui para cada ativo, sempre na moeda do próprio ativo.
 */
export function Prices() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [assetId, setAssetId] = useState("");
  const [priceDate, setPriceDate] = useState("");
  const [price, setPrice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = useCallback(() => {
    return getLatestPrices()
      .then((prices) => setState({ status: "ready", prices }))
      .catch((err: Error) => setState({ status: "error", message: err.message }));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      await setAssetPrice(assetId, { price_date: priceDate, price: price.trim() });
      setSuccess("Cotação registrada.");
      setPrice("");
      await load();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (state.status === "loading") {
    return (
      <p className="text-neutral-400" role="status">
        Carregando…
      </p>
    );
  }
  if (state.status === "error") {
    return (
      <p className="text-red-400" role="alert">
        Não foi possível carregar as cotações: {state.message}
      </p>
    );
  }
  if (state.prices.length === 0) {
    return (
      <p className="text-neutral-400" data-testid="no-assets">
        Nenhum ativo cadastrado. Cadastre um ativo em Cadastros antes de informar cotações.
      </p>
    );
  }

  const selected = state.prices.find((item) => item.asset_id === assetId);

  return (
    <div className="space-y-6">
      <form className={PANEL_CLASS} onSubmit={handleSubmit} aria-label="Informar cotação">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <label className={LABEL_CLASS} htmlFor="price-asset">
              Ativo
            </label>
            <select
              id="price-asset"
              className={INPUT_CLASS}
              value={assetId}
              disabled={submitting}
              onChange={(event) => setAssetId(event.target.value)}
            >
              <option value="">Selecione…</option>
              {state.prices.map((item) => (
                <option key={item.asset_id} value={item.asset_id}>
                  {item.asset_ticker} ({item.currency_code})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="price-date">
              Data da cotação
            </label>
            <input
              id="price-date"
              type="date"
              className={INPUT_CLASS}
              value={priceDate}
              disabled={submitting}
              onChange={(event) => setPriceDate(event.target.value)}
            />
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="price-value">
              Preço por unidade{selected ? ` (${selected.currency_code})` : ""}
            </label>
            <input
              id="price-value"
              inputMode="decimal"
              className={INPUT_CLASS}
              value={price}
              disabled={submitting}
              onChange={(event) => setPrice(event.target.value)}
            />
          </div>
        </div>
        <p className="mt-3 text-xs text-neutral-500">
          O preço é sempre na moeda do ativo. Informar de novo a mesma data substitui a cotação anterior. Use ponto
          como separador decimal.
        </p>
        <button
          type="submit"
          className={`${BUTTON_CLASS} mt-3`}
          disabled={submitting || assetId === "" || priceDate === "" || price.trim() === ""}
        >
          {submitting ? "Salvando…" : "Registrar cotação"}
        </button>
        {success && (
          <p className="mt-2 text-sm text-emerald-300" role="status">
            {success}
          </p>
        )}
        {error && (
          <p className="mt-2 text-sm text-red-400" role="alert">
            {error}
          </p>
        )}
      </form>

      <div className={PANEL_CLASS}>
        <h2 className="mb-3 text-[15px] font-semibold tracking-tight text-neutral-100">Última cotação de cada ativo</h2>
        <table className="w-full text-left text-sm" data-testid="latest-prices">
          <thead>
            <tr className="border-b border-neutral-800 text-neutral-400">
              <th className="py-2 pr-3">Ativo</th>
              <th className="py-2 pr-3">Nome</th>
              <th className="py-2 pr-3">Moeda</th>
              <th className="py-2 pr-3">Preço</th>
              <th className="py-2">Data</th>
            </tr>
          </thead>
          <tbody>
            {state.prices.map((item) => (
              <tr key={item.asset_id} className="border-b border-neutral-900">
                <td className="py-2 pr-3 text-neutral-100">{item.asset_ticker}</td>
                <td className="py-2 pr-3">{item.asset_name}</td>
                <td className="py-2 pr-3">{item.currency_code}</td>
                <td className={`py-2 pr-3 ${item.price === null ? "text-neutral-500" : ""}`}>
                  {item.price ?? "Sem cotação"}
                </td>
                <td className="py-2">{item.price_date === null ? "—" : formatIsoDate(item.price_date)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
