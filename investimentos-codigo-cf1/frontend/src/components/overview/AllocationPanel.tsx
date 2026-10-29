import { useState } from "react";

import type { AssetClassRead } from "../../api/types";
import type { Allocation, AllocationRow, CurrencyAllocation } from "../../api/performance";
import { setAllocationTargets } from "../../api/performance";
import { describeApiError } from "../../lib/apiErrors";
import { classColor } from "../../lib/chartColors";
import { parseRatePercent, rateToPercentText } from "../../lib/fixedIncome";
import { formatCurrency, formatPercent } from "../../lib/formatCurrency";
import { BUTTON_CLASS, COMPACT_INPUT_CLASS, PANEL_CLASS, SECTION_TITLE_CLASS } from "../../lib/ui";

const CURRENCY_TITLES: Record<string, string> = { BRL: "Em reais", USD: "Em dólar" };
const NEAR = 0.02; // até 2 p.p. do alvo conta como "no alvo"

/** "+12,3 p.p." / "-4,0 p.p." */
function pointsText(gap: string): string {
  const pp = Number(gap) * 100;
  const text = Math.abs(pp).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return `${pp > 0 ? "+" : pp < 0 ? "-" : ""}${text} p.p.`;
}

function Row({ row, currency }: { row: AllocationRow; currency: string }) {
  const current = Number(row.current_weight) * 100;
  const target = row.target_weight === null ? null : Number(row.target_weight) * 100;
  const gap = row.gap === null ? null : Number(row.gap);
  const status = gap === null ? null : Math.abs(gap) <= NEAR ? "no alvo" : gap > 0 ? "acima do alvo" : "abaixo do alvo";
  return (
    <li className="py-3" data-testid={`allocation-${currency}-${row.asset_class}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-sm">
        <span className="flex items-center gap-2 text-neutral-100">
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: classColor(row.asset_class) }}
            aria-hidden="true"
          />
          {row.label}
        </span>
        <span className="tabular-nums text-neutral-300">
          {formatPercent(row.current_weight)}
          {row.target_weight !== null && (
            <span className="text-neutral-500"> de alvo {formatPercent(row.target_weight)}</span>
          )}
        </span>
      </div>
      {/* Barra do peso atual com o traço do alvo por cima. */}
      <div className="relative mt-2 h-2 rounded-full bg-neutral-800">
        <div
          className="h-full rounded-full"
          style={{ width: `${Math.min(current, 100)}%`, backgroundColor: classColor(row.asset_class) }}
        />
        {target !== null && (
          <span
            className="absolute -top-1 h-4 w-0.5 rounded-full bg-neutral-50"
            style={{ left: `calc(${Math.min(target, 100)}% - 1px)` }}
            aria-hidden="true"
          />
        )}
      </div>
      {status !== null && row.gap !== null && row.value_gap !== null && (
        <p
          className={`mt-1.5 text-xs ${status === "no alvo" ? "text-neutral-400" : "text-neutral-300"}`}
          data-testid={`allocation-status-${currency}-${row.asset_class}`}
        >
          {status === "no alvo" ? "No alvo" : `${pointsText(row.gap)}, ${status}`}
          {status !== "no alvo" &&
            ` (≈ ${formatCurrency(String(Math.abs(Number(row.value_gap))), currency)} ${
              Number(row.value_gap) > 0 ? "abaixo" : "acima"
            })`}
        </p>
      )}
    </li>
  );
}

function Editor({
  block,
  assetClasses,
  onSaved,
  onCancel,
}: {
  block: CurrencyAllocation;
  assetClasses: AssetClassRead[];
  onSaved: (allocation: Allocation) => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(block.rows.map((r) => [r.asset_class, rateToPercentText(r.target_weight)])),
  );
  const [extra, setExtra] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const labels = new Map([
    ...assetClasses.map((c) => [c.code, c.label] as const),
    ...block.rows.map((r) => [r.asset_class, r.label] as const),
  ]);
  const parsed = Object.entries(values).map(([code, text]) => [code, parseRatePercent(text, 2)] as const);
  const invalid = parsed.some(([, v]) => v === "invalid");
  const sum = parsed.reduce((acc, [, v]) => acc + (v && v !== "invalid" ? Math.round(Number(v) * 10000) : 0), 0);
  const ok = !invalid && sum === 10000;
  const currency = block.currency_code;

  async function save(targets: { asset_class_code: string; target_weight: string }[]) {
    setSaving(true);
    setError(null);
    try {
      onSaved(await setAllocationTargets(currency, targets));
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      className="mt-3 space-y-3"
      aria-label={`Alvos em ${currency}`}
      onSubmit={(event) => {
        event.preventDefault();
        if (!ok) return;
        void save(
          parsed
            .filter(([, v]) => v !== null && v !== "invalid" && Number(v) > 0)
            .map(([code, v]) => ({ asset_class_code: code, target_weight: v as string })),
        );
      }}
    >
      <ul className="space-y-2">
        {Object.keys(values).map((code) => (
          <li key={code} className="flex items-center justify-between gap-3 text-sm">
            <label htmlFor={`target-${currency}-${code}`} className="text-neutral-200">
              {labels.get(code) ?? code}
            </label>
            <span className="flex items-center gap-1.5">
              <input
                id={`target-${currency}-${code}`}
                inputMode="decimal"
                placeholder="0"
                className={`${COMPACT_INPUT_CLASS} w-20 text-right tabular-nums`}
                value={values[code]}
                aria-invalid={parseRatePercent(values[code], 2) === "invalid"}
                onChange={(e) => setValues({ ...values, [code]: e.target.value })}
              />
              <span className="text-neutral-400">%</span>
            </span>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor={`add-class-${currency}`}>
          Adicionar classe
        </label>
        <select
          id={`add-class-${currency}`}
          className={COMPACT_INPUT_CLASS}
          value={extra}
          onChange={(e) => {
            const code = e.target.value;
            if (code) setValues({ ...values, [code]: "" });
            setExtra("");
          }}
        >
          <option value="">Adicionar classe…</option>
          {assetClasses
            .filter((c) => !(c.code in values))
            .map((c) => (
              <option key={c.code} value={c.code}>
                {c.label}
              </option>
            ))}
        </select>
        <p
          className={`ml-auto text-sm tabular-nums ${ok ? "text-emerald-300" : "text-amber-300"}`}
          data-testid={`target-sum-${currency}`}
        >
          Soma: {(sum / 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%
          {!ok && !invalid && " — precisa dar 100%"}
          {invalid && " — use números como 30 ou 12,5"}
        </p>
      </div>
      {error && (
        <p className="text-sm text-red-400" role="alert">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="submit" className={BUTTON_CLASS} disabled={!ok || saving}>
          Salvar alvos
        </button>
        <button type="button" className={BUTTON_CLASS} onClick={onCancel} disabled={saving}>
          Cancelar
        </button>
        {block.has_targets && (
          <button type="button" className={`${BUTTON_CLASS} ml-auto`} onClick={() => void save([])} disabled={saving}>
            Apagar alvos
          </button>
        )}
      </div>
    </form>
  );
}

/**
 * Alocação por classe: o peso atual e o alvo que você definir (por moeda).
 * Mostra a distância até o alvo — a decisão do que fazer é sua.
 */
export function AllocationPanel({
  allocation,
  assetClasses,
  onChange,
}: {
  allocation: Allocation;
  assetClasses: AssetClassRead[];
  onChange: (allocation: Allocation) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  if (allocation.currencies.length === 0) return null;
  return (
    <section aria-labelledby="allocation-title" data-testid="allocation">
      <h2 id="allocation-title" className={`mb-3 ${SECTION_TITLE_CLASS}`}>
        Alocação por classe
      </h2>
      <div className={`grid grid-cols-1 gap-4 ${allocation.currencies.length > 1 ? "lg:grid-cols-2" : ""}`}>
        {allocation.currencies.map((block) => (
          <div key={block.currency_code} className={PANEL_CLASS} data-testid={`allocation-${block.currency_code}`}>
            <div className="flex items-baseline justify-between gap-2">
              <p className="text-sm text-neutral-400">
                {CURRENCY_TITLES[block.currency_code] ?? `Em ${block.currency_code}`}
              </p>
              {editing !== block.currency_code && (
                <button
                  type="button"
                  className="text-sm text-sky-300 underline-offset-4 hover:underline"
                  onClick={() => setEditing(block.currency_code)}
                >
                  {block.has_targets ? "Editar alvos" : "Definir alvos"}
                </button>
              )}
            </div>
            {editing === block.currency_code ? (
              <Editor
                block={block}
                assetClasses={assetClasses}
                onCancel={() => setEditing(null)}
                onSaved={(next) => {
                  setEditing(null);
                  onChange(next);
                }}
              />
            ) : (
              <>
                <ul className="mt-1 divide-y divide-neutral-800">
                  {block.rows
                    .filter((r) => Number(r.value) > 0 || (r.target_weight !== null && Number(r.target_weight) > 0))
                    .map((row) => (
                      <Row key={row.asset_class} row={row} currency={block.currency_code} />
                    ))}
                </ul>
                <p className="mt-2 text-xs text-neutral-500">
                  {block.has_targets
                    ? "O traço branco é o seu alvo. Até 2 p.p. de diferença conta como no alvo. É a sua régua, não uma recomendação."
                    : "Defina quanto quer em cada classe para ver a distância até o alvo."}
                </p>
              </>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
