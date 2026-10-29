import { useCallback, useEffect, useState } from "react";

import { createDefaultCategories, createRule, getCategories } from "../../api/cashflow";
import type { CashflowNature, CategoryRead } from "../../api/cashflowTypes";
import type { PendingGroup, PendingGroups } from "../../api/review";
import { classifyBatch, getPendingGroups } from "../../api/review";
import { ErrorText, Loading } from "../../components/cash/shared";
import { describeApiError } from "../../lib/apiErrors";
import { NATURE_LABELS, RULE_NATURES, categoryLabel, categoryOptions } from "../../lib/cashflow";
import { formatCurrency, formatIsoDate, formatSignedCurrency } from "../../lib/formatCurrency";
import { isInvoicePayment, periodLabel, ruleFromGroup } from "../../lib/review";
import { BUTTON_CLASS, COMPACT_INPUT_CLASS, PANEL_CLASS } from "../../lib/ui";

type Loaded = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: PendingGroups };

const PRIMARY_BUTTON =
  "rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40";

function GroupCard({
  group,
  categories,
  onDone,
}: {
  group: PendingGroup;
  categories: CategoryRead[];
  onDone: (message: string) => void;
}) {
  const suggestion = group.suggestion;
  const [nature, setNature] = useState<CashflowNature>(suggestion?.nature ?? (group.inflows > group.outflows ? "INCOME" : "EXPENSE"));
  const [categoryId, setCategoryId] = useState(suggestion?.category_id ?? "");
  const [withRule, setWithRule] = useState(true);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const currency = group.currency_code;
  const testId = `group-${group.match_text}-${currency}`;

  async function apply(chosenNature: CashflowNature, chosenCategory: string | null) {
    setBusy(true);
    setError(null);
    try {
      await classifyBatch({ entry_ids: group.entry_ids, nature: chosenNature, category_id: chosenCategory, tag_ids: [] });
    } catch (err) {
      setError(describeApiError(err));
      setBusy(false);
      return;
    }
    const plural = group.count === 1 ? "1 lançamento classificado" : `${group.count} lançamentos classificados`;
    if (!withRule) {
      onDone(`${plural}.`);
      return;
    }
    try {
      await createRule(ruleFromGroup(group, chosenNature, chosenCategory));
      onDone(`${plural} e regra criada para os próximos.`);
    } catch (err) {
      onDone(`${plural}, mas a regra não foi criada: ${describeApiError(err)}`);
    }
  }

  const suggestionText = suggestion
    ? [NATURE_LABELS[suggestion.nature], categoryLabel(categories, suggestion.category_id)].filter(Boolean).join(" · ")
    : null;

  return (
    <li className={`${PANEL_CLASS} space-y-3`} data-testid={testId}>
      <div className="flex flex-wrap items-start gap-x-4 gap-y-1">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm text-neutral-100" title={group.sample_description}>
            {group.sample_description}
          </p>
          <p className="text-xs text-neutral-500">
            {group.count === 1 ? "1 lançamento" : `${group.count} lançamentos`} ·{" "}
            {periodLabel(group.first_date, group.last_date)}
          </p>
        </div>
        <p
          className={`text-sm font-medium tabular-nums ${Number(group.total) < 0 ? "text-neutral-100" : "text-emerald-400"}`}
          data-testid={`${testId}-total`}
        >
          {formatSignedCurrency(group.total, currency)}
        </p>
      </div>

      {suggestion && (
        <div className="flex flex-wrap items-center gap-2 text-sm" data-testid={`${testId}-suggestion`}>
          <span className="text-neutral-400">
            Você já classificou assim {suggestion.evidence === 1 ? "1 vez" : `${suggestion.evidence} vezes`}:
          </span>
          <span className="rounded bg-neutral-800 px-2 py-0.5 text-neutral-100">{suggestionText}</span>
          <button
            type="button"
            className={PRIMARY_BUTTON}
            disabled={busy}
            onClick={() => void apply(suggestion.nature, suggestion.category_id)}
          >
            Usar a sugestão
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label={`Natureza de ${group.sample_description}`}
          className={COMPACT_INPUT_CLASS}
          value={nature}
          disabled={busy}
          onChange={(e) => setNature(e.target.value as CashflowNature)}
        >
          {RULE_NATURES.map((item) => (
            <option key={item} value={item}>
              {NATURE_LABELS[item]}
            </option>
          ))}
        </select>
        <select
          aria-label={`Categoria de ${group.sample_description}`}
          className={`${COMPACT_INPUT_CLASS} max-w-64`}
          value={categoryId}
          disabled={busy}
          onChange={(e) => setCategoryId(e.target.value)}
        >
          <option value="">Sem categoria</option>
          {categoryOptions(categories).map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-neutral-400">
          <input type="checkbox" checked={withRule} disabled={busy} onChange={(e) => setWithRule(e.target.checked)} />
          Criar regra para os próximos
        </label>
        <button
          type="button"
          className={BUTTON_CLASS}
          disabled={busy}
          onClick={() => void apply(nature, categoryId === "" ? null : categoryId)}
        >
          {busy ? "Classificando…" : group.count === 1 ? "Classificar" : `Classificar os ${group.count}`}
        </button>
        <button
          type="button"
          className="text-xs text-neutral-400 underline hover:text-neutral-200"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {open ? "Esconder" : "Ver lançamentos"}
        </button>
      </div>
      {error && <ErrorText>{error}</ErrorText>}
      {isInvoicePayment(group) && (
        <p className="text-xs text-amber-300" data-testid={`${testId}-invoice`}>
          Isto é o pagamento da fatura do cartão: não é gasto. Importe as faturas (PDF, OFX ou CSV) na conta do cartão e
          o app liga cada pagamento sozinho como transferência — as compras da fatura é que viram gasto.
        </p>
      )}

      {open && (
        <table className="w-full text-left text-xs" data-testid={`${testId}-preview`}>
          <tbody>
            {group.preview.map((entry) => (
              <tr key={entry.id} className="border-t border-neutral-800/60">
                <td className="py-1 pr-3 whitespace-nowrap text-neutral-400">{formatIsoDate(entry.entry_date)}</td>
                <td className="py-1 pr-3 text-neutral-300">{entry.description}</td>
                <td className="py-1 text-right tabular-nums">{formatCurrency(entry.amount, currency)}</td>
              </tr>
            ))}
            {group.count > group.preview.length && (
              <tr>
                <td colSpan={3} className="pt-1 text-neutral-500">
                  e mais {group.count - group.preview.length}…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </li>
  );
}

/**
 * O que falta classificar, junto pelo mesmo texto: um clique classifica
 * o grupo inteiro e (opcional) cria a regra para as próximas importações.
 * A sugestão é só o que você mesmo já fez com esse texto.
 */
export function CashReview() {
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [categories, setCategories] = useState<CategoryRead[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [creatingDefaults, setCreatingDefaults] = useState(false);

  const load = useCallback(() => {
    return Promise.all([getPendingGroups(50), getCategories()])
      .then(([data, cats]) => {
        setCategories(cats);
        setLoaded({ status: "ready", data });
      })
      .catch((err: unknown) => setLoaded({ status: "error", message: describeApiError(err) }));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loaded.status === "loading") return <Loading />;
  if (loaded.status === "error") return <ErrorText>{`Não foi possível carregar: ${loaded.message}`}</ErrorText>;

  const { data } = loaded;
  return (
    <div className="space-y-4">
      <div className={PANEL_CLASS} data-testid="review-header">
        {data.pending_entries === 0 ? (
          <p className="text-sm text-emerald-300">Tudo classificado. Os próximos extratos passam pelas suas regras.</p>
        ) : (
          <>
            <p className="text-sm text-neutral-100">
              Faltam <strong className="tabular-nums">{data.pending_entries}</strong>{" "}
              {data.pending_entries === 1 ? "lançamento" : "lançamentos"} em{" "}
              <strong className="tabular-nums">{data.pending_groups}</strong>{" "}
              {data.pending_groups === 1 ? "grupo" : "grupos"}.
            </p>
            <p className="mt-1 text-xs text-neutral-500">
              Cada grupo junta lançamentos com o mesmo texto. Classificar o grupo com “Criar regra” marcado também
              classifica sozinho os próximos que chegarem no extrato. Transferências entre contas suas ficam na tela
              Lançamentos (botão Transferência).
            </p>
          </>
        )}
      </div>

      {categories.length === 0 && data.pending_entries > 0 && (
        <div className={`${PANEL_CLASS} flex flex-wrap items-center gap-3 text-sm`} data-testid="no-categories">
          <span className="text-neutral-300">Você ainda não tem categorias.</span>
          <button
            type="button"
            className={BUTTON_CLASS}
            disabled={creatingDefaults}
            onClick={() => {
              setCreatingDefaults(true);
              createDefaultCategories()
                .then(setCategories)
                .catch((err: unknown) => setNotice(`Não foi possível criar as categorias: ${describeApiError(err)}`))
                .finally(() => setCreatingDefaults(false));
            }}
          >
            Criar as categorias padrão
          </button>
        </div>
      )}

      {notice && (
        <p className="text-sm text-emerald-300" role="status" data-testid="review-notice">
          {notice}
        </p>
      )}

      <ul className="space-y-3">
        {data.groups.map((group) => (
          <GroupCard
            key={`${group.match_text}-${group.currency_code}`}
            group={group}
            categories={categories}
            onDone={(message) => {
              setNotice(message);
              void load();
            }}
          />
        ))}
      </ul>
      {data.pending_groups > data.groups.length && (
        <p className="text-xs text-neutral-500">
          Mostrando os {data.groups.length} maiores grupos. Os outros aparecem conforme você classifica.
        </p>
      )}
    </div>
  );
}
