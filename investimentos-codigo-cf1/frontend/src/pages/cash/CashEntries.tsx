import { type FormEvent, Fragment, useCallback, useEffect, useRef, useState } from "react";

import {
  countCashEntries,
  getCashEntries,
  getCategories,
  getRules,
  getTags,
  restoreCashEntry,
  reverseCashEntry,
  unlinkCashTransfer,
} from "../../api/cashflow";
import type {
  CashflowEntryFilters,
  CashflowEntryRead,
  CashflowNature,
  CategoryRead,
  RuleRead,
  TagRead,
} from "../../api/cashflowTypes";
import { getAccounts } from "../../api/client";
import type { AccountRead } from "../../api/types";
import { CashEntryForm } from "../../components/cash/CashEntryForm";
import { ClassifyEditor } from "../../components/cash/ClassifyEditor";
import { EntryEditor } from "../../components/cash/EntryEditor";
import { ConfirmButton, ErrorText, Loading, SMALL_BUTTON_CLASS } from "../../components/cash/shared";
import { TransferEditor } from "../../components/cash/TransferEditor";
import { describeApiError } from "../../lib/apiErrors";
import {
  EMPTY_FILTER_DRAFT,
  type FilterDraft,
  NATURE_LABELS,
  PAGE_SIZE,
  cashAccounts,
  categoryLabel,
  categoryOptions,
  isOutflow,
  toEntryFilters,
  toFilterDraft,
} from "../../lib/cashflow";
import { formatCurrency, formatIsoDate } from "../../lib/formatCurrency";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS, PANEL_CLASS } from "../../lib/ui";
import { exactTitle } from "../../lib/privacy";

const ALL_NATURES: CashflowNature[] = ["UNCLASSIFIED", "EXPENSE", "INCOME", "THIRD_PARTY", "TRANSFER", "ADJUSTMENT"];

interface Lookups {
  accounts: AccountRead[];
  categories: CategoryRead[];
  tags: TagRead[];
  rules: RuleRead[];
}

type LookupState = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: Lookups };

type Editing = { entryId: string; kind: "classify" | "transfer" | "edit" } | null;

interface CashEntriesProps {
  /** Filtros com que a tela abre (ex.: vindo do aviso do Resumo). */
  initialFilters?: CashflowEntryFilters;
}

/**
 * Lançamentos do livro de caixa: filtrar, lançar à mão, classificar,
 * ligar transferências e estornar. Depois de qualquer alteração a
 * página atual é buscada de novo — a tela nunca adivinha o resultado.
 */
export function CashEntries({ initialFilters = {} }: CashEntriesProps) {
  const [lookups, setLookups] = useState<LookupState>({ status: "loading" });
  const [draft, setDraft] = useState<FilterDraft>(() => toFilterDraft(initialFilters));
  const [filters, setFilters] = useState<CashflowEntryFilters>(initialFilters);
  const [offset, setOffset] = useState(0);
  const [entries, setEntries] = useState<CashflowEntryRead[] | null>(null);
  const [total, setTotal] = useState(0);
  const [listError, setListError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const loadLookups = useCallback(
    () =>
      Promise.all([getAccounts(), getCategories(), getTags(), getRules()])
        .then(([accounts, categories, tags, rules]) =>
          setLookups({ status: "ready", data: { accounts, categories, tags, rules } }),
        )
        .catch((err: unknown) => setLookups({ status: "error", message: describeApiError(err) })),
    [],
  );

  useEffect(() => {
    void loadLookups();
  }, [loadLookups]);

  // Cada busca recebe um número; só a mais recente pode escrever na tela.
  const latestRequest = useRef(0);

  const loadEntries = useCallback(() => {
    const requestId = ++latestRequest.current;
    return Promise.all([getCashEntries(filters, PAGE_SIZE, offset), countCashEntries(filters)])
      .then(([page, count]) => {
        if (requestId !== latestRequest.current) return;
        if (page.length === 0 && offset > 0 && count.total > 0) {
          // A página atual esvaziou (ex.: estorno do último item): volta para a última que existe.
          setOffset(Math.floor((count.total - 1) / PAGE_SIZE) * PAGE_SIZE);
          return;
        }
        setEntries(page);
        setTotal(count.total);
        setListError(null);
      })
      .catch((err: unknown) => {
        if (requestId === latestRequest.current) setListError(describeApiError(err));
      });
  }, [filters, offset]);

  useEffect(() => {
    void loadEntries();
  }, [loadEntries]);

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setEditing(null);
    setNotice(null);
    setOffset(0);
    setFilters(toEntryFilters(draft));
  }

  function clearFilters() {
    setDraft(EMPTY_FILTER_DRAFT);
    setEditing(null);
    setNotice(null);
    setOffset(0);
    setFilters({});
  }

  async function afterChange(message: string, reloadLookups = false) {
    setEditing(null);
    if (reloadLookups) await loadLookups();
    await loadEntries();
    // O aviso só aparece com a lista já atualizada.
    setNotice(message);
  }

  if (lookups.status === "loading") return <Loading />;
  if (lookups.status === "error") {
    return <ErrorText>{`Não foi possível carregar os cadastros: ${lookups.message}`}</ErrorText>;
  }

  const { accounts, categories, tags, rules } = lookups.data;
  const cash = cashAccounts(accounts);
  if (cash.length === 0) {
    return (
      <p className="text-neutral-400" data-testid="no-cash-accounts">
        Nenhuma conta de caixa cadastrada. Crie em Cadastros uma conta do tipo corrente, reserva, cartão ou dinheiro.
      </p>
    );
  }

  const accountName = (id: string | null) => accounts.find((account) => account.id === id)?.name ?? "—";
  const tagName = (id: string) => tags.find((tag) => tag.id === id)?.name ?? "tag";
  const ruleName = (id: string) => rules.find((rule) => rule.id === id)?.name ?? "regra excluída";
  const set = (patch: Partial<FilterDraft>) => setDraft((current) => ({ ...current, ...patch }));

  function classification(entry: CashflowEntryRead) {
    if (entry.nature === "TRANSFER") {
      const arrow = isOutflow(entry.amount) ? "→" : "←";
      return (
        <>
          <span>Transferência</span>
          <span className="block text-xs text-neutral-500">
            {arrow} {accountName(entry.counterparty_account_id)}
          </span>
        </>
      );
    }
    const category = categoryLabel(categories, entry.category_id);
    const origin =
      entry.classified_by_rule_id !== null
        ? `regra: ${ruleName(entry.classified_by_rule_id)}`
        : entry.nature === "UNCLASSIFIED" && entry.category_id === null
          ? null
          : "manual";
    return (
      <>
        <span className={`whitespace-nowrap ${entry.nature === "UNCLASSIFIED" ? "text-amber-300" : ""}`}>
          {NATURE_LABELS[entry.nature]}
        </span>
        {category && <span className="block text-xs text-neutral-400">{category}</span>}
        {origin && <span className="block text-xs text-neutral-500">{origin}</span>}
      </>
    );
  }

  const first = total === 0 ? 0 : offset + 1;
  const last = offset + (entries?.length ?? 0);

  return (
    <div className="space-y-6">
      <div>
        <button type="button" className={BUTTON_CLASS} aria-expanded={showForm} onClick={() => setShowForm((open) => !open)}>
          {showForm ? "Fechar formulário" : "Novo lançamento"}
        </button>
        {showForm && (
          <div className="mt-3">
            <CashEntryForm accounts={accounts} onCreated={() => void afterChange("Registro gravado.")} />
          </div>
        )}
      </div>

      <form className={PANEL_CLASS} onSubmit={applyFilters} aria-label="Filtros">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div>
            <label className={LABEL_CLASS} htmlFor="f-account">
              Conta
            </label>
            <select id="f-account" className={INPUT_CLASS} value={draft.accountId} onChange={(e) => set({ accountId: e.target.value })}>
              <option value="">Todas</option>
              {cash.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="f-start">
              De
            </label>
            <input id="f-start" type="date" className={INPUT_CLASS} value={draft.start} onChange={(e) => set({ start: e.target.value })} />
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="f-end">
              Até
            </label>
            <input id="f-end" type="date" className={INPUT_CLASS} value={draft.end} onChange={(e) => set({ end: e.target.value })} />
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="f-nature">
              Natureza
            </label>
            <select id="f-nature" className={INPUT_CLASS} value={draft.nature} onChange={(e) => set({ nature: e.target.value })}>
              <option value="">Todas</option>
              {ALL_NATURES.map((nature) => (
                <option key={nature} value={nature}>
                  {NATURE_LABELS[nature]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="f-category">
              Categoria
            </label>
            <select id="f-category" className={INPUT_CLASS} value={draft.category} onChange={(e) => set({ category: e.target.value })}>
              <option value="">Todas</option>
              <option value="none">Sem categoria</option>
              {categoryOptions(categories).map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="col-span-2">
            <label className={LABEL_CLASS} htmlFor="f-search">
              Texto na descrição
            </label>
            <input
              id="f-search"
              className={INPUT_CLASS}
              value={draft.search}
              maxLength={100}
              onChange={(e) => set({ search: e.target.value })}
            />
          </div>
          <label className="flex items-end gap-2 pb-2 text-sm">
            <input type="checkbox" checked={draft.includeReversed} onChange={(e) => set({ includeReversed: e.target.checked })} />
            Mostrar excluídos
          </label>
        </div>
        <div className="mt-3 flex gap-2">
          <button type="submit" className={BUTTON_CLASS}>
            Filtrar
          </button>
          <button type="button" className={BUTTON_CLASS} onClick={clearFilters}>
            Limpar filtros
          </button>
        </div>
      </form>

      {notice && (
        <p className="text-sm text-emerald-300" role="status" data-testid="entries-notice">
          {notice}
        </p>
      )}
      {listError && <ErrorText>{listError}</ErrorText>}

      {entries === null ? (
        !listError && <Loading />
      ) : (
        <div className={PANEL_CLASS}>
          <p className="mb-3 text-xs text-neutral-500" data-testid="entries-count">
            {total === 0 ? "Nenhum lançamento com estes filtros." : `Mostrando ${first}–${last} de ${total}`}
          </p>
          {entries.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm" data-testid="entries-table">
                <thead>
                  <tr className="border-b border-neutral-800 text-neutral-400">
                    <th className="py-2 pr-3">Data</th>
                    <th className="py-2 pr-3">Conta</th>
                    <th className="py-2 pr-3">Descrição</th>
                    <th className="py-2 pr-3 text-right">Valor</th>
                    <th className="py-2 pr-3">Classificação</th>
                    <th className="py-2">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => {
                    const reversed = entry.status === "REVERSED";
                    const isTransfer = entry.nature === "TRANSFER";
                    const open = editing?.entryId === entry.id ? editing.kind : null;
                    // Valor e data de lançamento importado vêm do banco: só a classificação muda.
                    const editable = entry.source === "MANUAL" && !isTransfer;
                    return (
                      <Fragment key={entry.id}>
                        <tr
                          data-testid={`entry-${entry.id}`}
                          className={`border-b border-neutral-900 align-top ${reversed ? "text-neutral-500" : ""}`}
                        >
                          <td className="py-2 pr-3 whitespace-nowrap">{formatIsoDate(entry.entry_date)}</td>
                          <td className="py-2 pr-3">{accountName(entry.account_id)}</td>
                          <td className={`py-2 pr-3 ${reversed ? "line-through" : ""}`}>
                            {entry.description}
                            {entry.notes && <span className="block text-xs text-neutral-500">{entry.notes}</span>}
                            {entry.tag_ids.length > 0 && (
                              <span className="mt-1 flex flex-wrap gap-1">
                                {entry.tag_ids.map((id) => (
                                  <span key={id} className="rounded bg-neutral-800 px-1.5 text-xs text-neutral-300">
                                    {tagName(id)}
                                  </span>
                                ))}
                              </span>
                            )}
                          </td>
                          <td
                            className={`py-2 pr-3 text-right whitespace-nowrap tabular-nums ${
                              reversed ? "line-through" : isOutflow(entry.amount) ? "text-neutral-100" : "text-emerald-400"
                            }`}
                            title={exactTitle(entry.amount)}
                          >
                            {formatCurrency(entry.amount, entry.currency_code)}
                          </td>
                          <td className="py-2 pr-3">{reversed ? "Excluído" : classification(entry)}</td>
                          <td className="py-2">
                            {reversed && (
                              <ConfirmButton
                                label="Restaurar"
                                confirmLabel={isTransfer ? "Confirmar: volta com as duas pontas" : "Confirmar: volta a valer"}
                                ariaLabel={`Restaurar ${entry.description}`}
                                onConfirm={async () => {
                                  const restored = await restoreCashEntry(entry.id);
                                  await afterChange(
                                    restored.length === 1
                                      ? "Lançamento restaurado."
                                      : `${restored.length} lançamentos restaurados (as pontas da transferência).`,
                                  );
                                }}
                              />
                            )}
                            {!reversed && (
                              <span className="flex flex-wrap gap-1">
                                {editable && (
                                  <button
                                    type="button"
                                    className={SMALL_BUTTON_CLASS}
                                    aria-label={`Editar ${entry.description}`}
                                    aria-expanded={open === "edit"}
                                    onClick={() => setEditing(open === "edit" ? null : { entryId: entry.id, kind: "edit" })}
                                  >
                                    Editar
                                  </button>
                                )}
                                {!isTransfer && (
                                  <>
                                    <button
                                      type="button"
                                      className={SMALL_BUTTON_CLASS}
                                      aria-label={`Classificar ${entry.description}`}
                                      aria-expanded={open === "classify"}
                                      onClick={() => setEditing(open === "classify" ? null : { entryId: entry.id, kind: "classify" })}
                                    >
                                      Classificar
                                    </button>
                                    <button
                                      type="button"
                                      className={SMALL_BUTTON_CLASS}
                                      aria-label={`Marcar ${entry.description} como transferência`}
                                      aria-expanded={open === "transfer"}
                                      onClick={() => setEditing(open === "transfer" ? null : { entryId: entry.id, kind: "transfer" })}
                                    >
                                      Transferência
                                    </button>
                                  </>
                                )}
                                {isTransfer && (
                                  <ConfirmButton
                                    label="Desfazer transferência"
                                    confirmLabel="Confirmar: volta a não classificado"
                                    ariaLabel={`Desfazer a transferência de ${entry.description}`}
                                    onConfirm={async () => {
                                      await unlinkCashTransfer(entry.id);
                                      await afterChange("Transferência desfeita: os lançamentos voltaram a não classificado.");
                                    }}
                                  />
                                )}
                                <ConfirmButton
                                  label="Excluir"
                                  confirmLabel={isTransfer ? "Confirmar: excluir as duas pontas" : "Confirmar exclusão"}
                                  ariaLabel={`Excluir ${entry.description}`}
                                  onConfirm={async () => {
                                    const reversedEntries = await reverseCashEntry(entry.id);
                                    await afterChange(
                                      reversedEntries.length === 1
                                        ? "Lançamento excluído. Ele fica em “Mostrar excluídos” e pode ser restaurado."
                                        : `${reversedEntries.length} lançamentos excluídos (as pontas da transferência). Eles ficam em “Mostrar excluídos”.`,
                                    );
                                  }}
                                />
                              </span>
                            )}
                          </td>
                        </tr>
                        {open !== null && (
                          <tr className="border-b border-neutral-900 bg-neutral-950/60">
                            <td colSpan={6} className="p-3" data-testid={`editor-${entry.id}`}>
                              {open === "edit" ? (
                                <EntryEditor
                                  entry={entry}
                                  onCancel={() => setEditing(null)}
                                  onSaved={() =>
                                    void afterChange("Lançamento editado. A versão antiga fica em “Mostrar excluídos”.")
                                  }
                                />
                              ) : open === "classify" ? (
                                <ClassifyEditor
                                  entry={entry}
                                  categories={categories}
                                  tags={tags}
                                  onCancel={() => setEditing(null)}
                                  onSaved={(ruleCreated) =>
                                    void afterChange(
                                      ruleCreated ? "Lançamento classificado e regra criada." : "Lançamento classificado.",
                                      ruleCreated,
                                    )
                                  }
                                />
                              ) : (
                                <TransferEditor
                                  entry={entry}
                                  accounts={accounts}
                                  onCancel={() => setEditing(null)}
                                  onLinked={() => void afterChange("Lançamento marcado como transferência.")}
                                />
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {total > PAGE_SIZE && (
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                className={BUTTON_CLASS}
                disabled={offset === 0}
                onClick={() => {
                  setEditing(null);
                  setOffset(Math.max(0, offset - PAGE_SIZE));
                }}
              >
                Anteriores
              </button>
              <button
                type="button"
                className={BUTTON_CLASS}
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => {
                  setEditing(null);
                  setOffset(offset + PAGE_SIZE);
                }}
              >
                Próximos
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
