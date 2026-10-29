import { type FormEvent, useCallback, useEffect, useState } from "react";

import {
  applyRules,
  createRule,
  deleteRule,
  getCategories,
  getRules,
  getTags,
  previewRules,
  updateRule,
} from "../../api/cashflow";
import type {
  CashflowNature,
  CategoryRead,
  RuleApplyResult,
  RuleDirection,
  RuleMatchType,
  RuleRead,
  RuleWrite,
  TagRead,
} from "../../api/cashflowTypes";
import { getAccounts } from "../../api/client";
import type { AccountRead } from "../../api/types";
import { ConfirmButton, ErrorText, Loading, SMALL_BUTTON_CLASS } from "../../components/cash/shared";
import { describeApiError } from "../../lib/apiErrors";
import {
  DIRECTION_LABELS,
  MATCH_TYPE_LABELS,
  NATURE_LABELS,
  RULE_NATURES,
  cashAccounts,
  categoryLabel,
  categoryOptions,
  parsePriority,
} from "../../lib/cashflow";
import { formatCurrency, formatIsoDate } from "../../lib/formatCurrency";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS, PANEL_CLASS } from "../../lib/ui";

interface Data {
  rules: RuleRead[];
  categories: CategoryRead[];
  tags: TagRead[];
  accounts: AccountRead[];
}

type State = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: Data };

interface Draft {
  name: string;
  pattern: string;
  matchType: RuleMatchType;
  direction: RuleDirection;
  accountId: string;
  nature: CashflowNature;
  categoryId: string;
  tagIds: ReadonlySet<string>;
  priority: string;
  isActive: boolean;
}

const EMPTY_DRAFT: Draft = {
  name: "",
  pattern: "",
  matchType: "CONTAINS",
  direction: "ANY",
  accountId: "",
  nature: "EXPENSE",
  categoryId: "",
  tagIds: new Set(),
  priority: "100",
  isActive: true,
};

function draftOf(rule: RuleRead): Draft {
  return {
    name: rule.name,
    pattern: rule.pattern,
    matchType: rule.match_type,
    direction: rule.direction,
    accountId: rule.account_id ?? "",
    nature: rule.set_nature,
    categoryId: rule.set_category_id ?? "",
    tagIds: new Set(rule.tag_ids),
    priority: String(rule.priority),
    isActive: rule.is_active,
  };
}

/**
 * Regras de classificação. A primeira regra ativa que casa (menor
 * prioridade primeiro) decide sozinha. Aplicar tem sempre uma prévia
 * antes, e nunca toca no que foi classificado à mão.
 */
export function CashRules() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [editing, setEditing] = useState<RuleRead | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [reevaluate, setReevaluate] = useState(false);
  const [preview, setPreview] = useState<RuleApplyResult | null>(null);
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applyNotice, setApplyNotice] = useState<string | null>(null);

  const load = useCallback(
    () =>
      Promise.all([getRules(), getCategories(), getTags(), getAccounts()])
        .then(([rules, categories, tags, accounts]) =>
          setState({ status: "ready", data: { rules, categories, tags, accounts: cashAccounts(accounts) } }),
        )
        .catch((err: unknown) => setState({ status: "error", message: describeApiError(err) })),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") {
    return <ErrorText>{`Não foi possível carregar as regras: ${state.message}`}</ErrorText>;
  }
  const { rules, categories, tags, accounts } = state.data;

  const set = (patch: Partial<Draft>) => setDraft((current) => ({ ...current, ...patch }));
  const priority = parsePriority(draft.priority);
  const canSave = !saving && draft.name.trim() !== "" && draft.pattern.trim() !== "" && priority !== null;

  /** Mudou uma regra: a prévia mostrada deixou de valer. */
  function invalidatePreview() {
    setPreview(null);
    setApplyNotice(null);
    setApplyError(null);
  }

  function resetForm() {
    setEditing(null);
    setDraft(EMPTY_DRAFT);
    setFormError(null);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (priority === null) return;
    const payload: RuleWrite = {
      name: draft.name.trim(),
      priority,
      is_active: draft.isActive,
      match_type: draft.matchType,
      pattern: draft.pattern.trim(),
      direction: draft.direction,
      account_id: draft.accountId === "" ? null : draft.accountId,
      set_nature: draft.nature,
      set_category_id: draft.categoryId === "" ? null : draft.categoryId,
      tag_ids: tags.filter((tag) => draft.tagIds.has(tag.id)).map((tag) => tag.id),
    };
    setSaving(true);
    setFormError(null);
    try {
      if (editing) await updateRule(editing.id, payload);
      else await createRule(payload);
      resetForm();
      invalidatePreview();
      await load();
    } catch (err) {
      setFormError(describeApiError(err));
    } finally {
      setSaving(false);
    }
  }

  async function handlePreview() {
    setApplying(true);
    setApplyError(null);
    setApplyNotice(null);
    try {
      setPreview(await previewRules({ reevaluate }));
    } catch (err) {
      setApplyError(describeApiError(err));
    } finally {
      setApplying(false);
    }
  }

  async function handleApply() {
    setApplying(true);
    setApplyError(null);
    try {
      const result = await applyRules({ reevaluate });
      setPreview(null);
      setApplyNotice(
        result.changes.length === 1
          ? "1 lançamento classificado."
          : `${result.changes.length} lançamentos classificados.`,
      );
    } catch (err) {
      setApplyError(describeApiError(err));
    } finally {
      setApplying(false);
    }
  }

  const tagLabel = (id: string) => tags.find((tag) => tag.id === id)?.name ?? "tag";
  const accountName = (id: string) => accounts.find((account) => account.id === id)?.name ?? "conta";

  function condition(rule: RuleRead): string {
    const parts = [`descrição ${MATCH_TYPE_LABELS[rule.match_type]} "${rule.pattern}"`];
    if (rule.direction !== "ANY") parts.push(DIRECTION_LABELS[rule.direction].toLowerCase());
    if (rule.account_id !== null) parts.push(`conta ${accountName(rule.account_id)}`);
    return parts.join(" · ");
  }

  function outcome(nature: CashflowNature, categoryId: string | null, tagIds: string[]): string {
    const parts = [NATURE_LABELS[nature]];
    const category = categoryLabel(categories, categoryId);
    if (category) parts.push(category);
    if (tagIds.length > 0) parts.push(tagIds.map(tagLabel).join(", "));
    return parts.join(" · ");
  }

  return (
    <div className="space-y-6">
      <div className={PANEL_CLASS}>
        <h2 className="mb-3 text-[15px] font-semibold tracking-tight text-neutral-100">{editing ? "Editar regra" : "Nova regra"}</h2>
        <form className="space-y-3" onSubmit={handleSubmit} aria-label="Regra">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="col-span-2">
              <label className={LABEL_CLASS} htmlFor="rule-name">
                Nome da regra
              </label>
              <input
                id="rule-name"
                className={INPUT_CLASS}
                value={draft.name}
                maxLength={120}
                disabled={saving}
                onChange={(event) => set({ name: event.target.value })}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="rule-match">
                Quando a descrição
              </label>
              <select
                id="rule-match"
                className={INPUT_CLASS}
                value={draft.matchType}
                disabled={saving}
                onChange={(event) => set({ matchType: event.target.value as RuleMatchType })}
              >
                {(Object.keys(MATCH_TYPE_LABELS) as RuleMatchType[]).map((item) => (
                  <option key={item} value={item}>
                    {MATCH_TYPE_LABELS[item]}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="rule-pattern">
                Texto
              </label>
              <input
                id="rule-pattern"
                className={INPUT_CLASS}
                value={draft.pattern}
                maxLength={200}
                disabled={saving}
                onChange={(event) => set({ pattern: event.target.value })}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="rule-direction">
                Sentido
              </label>
              <select
                id="rule-direction"
                className={INPUT_CLASS}
                value={draft.direction}
                disabled={saving}
                onChange={(event) => set({ direction: event.target.value as RuleDirection })}
              >
                {(Object.keys(DIRECTION_LABELS) as RuleDirection[]).map((item) => (
                  <option key={item} value={item}>
                    {DIRECTION_LABELS[item]}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="rule-account">
                Conta
              </label>
              <select
                id="rule-account"
                className={INPUT_CLASS}
                value={draft.accountId}
                disabled={saving}
                onChange={(event) => set({ accountId: event.target.value })}
              >
                <option value="">Qualquer conta</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="rule-nature">
                Classificar como
              </label>
              <select
                id="rule-nature"
                className={INPUT_CLASS}
                value={draft.nature}
                disabled={saving}
                onChange={(event) => set({ nature: event.target.value as CashflowNature })}
              >
                {RULE_NATURES.map((item) => (
                  <option key={item} value={item}>
                    {NATURE_LABELS[item]}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="rule-category">
                Categoria
              </label>
              <select
                id="rule-category"
                className={INPUT_CLASS}
                value={draft.categoryId}
                disabled={saving}
                onChange={(event) => set({ categoryId: event.target.value })}
              >
                <option value="">Sem categoria</option>
                {categoryOptions(categories).map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="rule-priority">
                Prioridade (menor decide primeiro)
              </label>
              <input
                id="rule-priority"
                inputMode="numeric"
                className={INPUT_CLASS}
                value={draft.priority}
                disabled={saving}
                aria-invalid={priority === null}
                onChange={(event) => set({ priority: event.target.value })}
              />
            </div>
            <label className="flex items-end gap-2 pb-2 text-sm">
              <input
                type="checkbox"
                checked={draft.isActive}
                disabled={saving}
                onChange={(event) => set({ isActive: event.target.checked })}
              />
              Regra ativa
            </label>
          </div>

          {tags.length > 0 && (
            <fieldset>
              <legend className={LABEL_CLASS}>Tags que a regra coloca</legend>
              <div className="flex flex-wrap gap-3 text-sm">
                {tags.map((tag) => (
                  <label key={tag.id} className="inline-flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={draft.tagIds.has(tag.id)}
                      disabled={saving}
                      onChange={() => {
                        const next = new Set(draft.tagIds);
                        if (next.has(tag.id)) next.delete(tag.id);
                        else next.add(tag.id);
                        set({ tagIds: next });
                      }}
                    />
                    {tag.tag_group ? `${tag.tag_group}: ${tag.name}` : tag.name}
                  </label>
                ))}
              </div>
            </fieldset>
          )}

          <p className="text-xs text-neutral-500">
            O texto é comparado com a descrição já limpa (sem acentos, maiúsculas, parcela ou intermediário de
            pagamento). Na lista de lançamentos, a classificação com “criar regra” já preenche esse texto.
          </p>
          {editing && (
            <p className="text-xs text-amber-300" data-testid="rule-editing">
              Editando: {editing.name}
            </p>
          )}
          <div className="flex gap-2">
            <button type="submit" className={BUTTON_CLASS} disabled={!canSave}>
              {saving ? "Salvando…" : editing ? "Salvar alterações" : "Adicionar regra"}
            </button>
            {editing && (
              <button type="button" className={BUTTON_CLASS} disabled={saving} onClick={resetForm}>
                Cancelar edição
              </button>
            )}
          </div>
          {formError && <ErrorText>{formError}</ErrorText>}
        </form>
      </div>

      <div className={PANEL_CLASS}>
        <h2 className="mb-3 text-[15px] font-semibold tracking-tight text-neutral-100">Regras, na ordem em que são testadas</h2>
        {rules.length === 0 ? (
          <p className="text-sm text-neutral-500">Nenhuma regra cadastrada.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" data-testid="rule-list">
              <thead>
                <tr className="border-b border-neutral-800 text-neutral-400">
                  <th className="py-2 pr-3">Prioridade</th>
                  <th className="py-2 pr-3">Regra</th>
                  <th className="py-2 pr-3">Classifica como</th>
                  <th className="py-2">Ações</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => (
                  <tr
                    key={rule.id}
                    data-testid={`rule-${rule.id}`}
                    className={`border-b border-neutral-900 align-top ${rule.is_active ? "" : "text-neutral-500"}`}
                  >
                    <td className="py-2 pr-3 tabular-nums">{rule.priority}</td>
                    <td className="py-2 pr-3">
                      {rule.name}
                      {!rule.is_active && <span className="ml-2 text-xs text-amber-300">desativada</span>}
                      <span className="block text-xs text-neutral-500">{condition(rule)}</span>
                    </td>
                    <td className="py-2 pr-3">{outcome(rule.set_nature, rule.set_category_id, rule.tag_ids)}</td>
                    <td className="py-2">
                      <span className="flex flex-wrap gap-1">
                        <button
                          type="button"
                          className={SMALL_BUTTON_CLASS}
                          aria-label={`Editar regra ${rule.name}`}
                          onClick={() => {
                            setEditing(rule);
                            setDraft(draftOf(rule));
                            setFormError(null);
                          }}
                        >
                          Editar
                        </button>
                        <ConfirmButton
                          label="Excluir"
                          confirmLabel="Confirmar exclusão"
                          ariaLabel={`Excluir regra ${rule.name}`}
                          onConfirm={async () => {
                            await deleteRule(rule.id);
                            if (editing?.id === rule.id) resetForm();
                            invalidatePreview();
                            await load();
                          }}
                        />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-xs text-neutral-500">
          Excluir uma regra não desfaz o que ela já classificou: os lançamentos ficam como estão.
        </p>
      </div>

      <div className={PANEL_CLASS}>
        <h2 className="mb-3 text-[15px] font-semibold tracking-tight text-neutral-100">Aplicar as regras aos lançamentos existentes</h2>
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={reevaluate}
            disabled={applying}
            onChange={(event) => {
              setReevaluate(event.target.checked);
              invalidatePreview();
            }}
          />
          Reavaliar também o que uma regra já classificou
        </label>
        <p className="mt-1 text-xs text-neutral-500">
          Classificação feita à mão e transferências nunca são alteradas.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className={BUTTON_CLASS} disabled={applying} onClick={handlePreview}>
            Ver o que mudaria
          </button>
          {preview && preview.changes.length > 0 && (
            <button type="button" className={BUTTON_CLASS} disabled={applying} onClick={handleApply}>
              {applying
                ? "Aplicando…"
                : `Aplicar a ${preview.changes.length} lançamento${preview.changes.length === 1 ? "" : "s"}`}
            </button>
          )}
        </div>
        {applyError && <ErrorText>{applyError}</ErrorText>}
        {applyNotice && (
          <p className="mt-2 text-sm text-emerald-300" role="status" data-testid="apply-notice">
            {applyNotice}
          </p>
        )}
        {preview && (
          <div className="mt-3">
            <p className="text-xs text-neutral-500" data-testid="preview-summary">
              {preview.examined} lançamento{preview.examined === 1 ? "" : "s"} avaliado
              {preview.examined === 1 ? "" : "s"} · {preview.changes.length} mudaria
              {preview.changes.length === 1 ? "" : "m"}. Nada foi gravado.
            </p>
            {preview.changes.length > 0 && (
              <div className="mt-2 overflow-x-auto">
                <table className="w-full text-left text-sm" data-testid="preview-changes">
                  <thead>
                    <tr className="border-b border-neutral-800 text-neutral-400">
                      <th className="py-2 pr-3">Data</th>
                      <th className="py-2 pr-3">Lançamento</th>
                      <th className="py-2 pr-3 text-right">Valor</th>
                      <th className="py-2 pr-3">Regra</th>
                      <th className="py-2">Passaria a ser</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.changes.map((change) => (
                      <tr key={change.entry_id} className="border-b border-neutral-900 align-top">
                        <td className="py-2 pr-3 whitespace-nowrap">{formatIsoDate(change.entry_date)}</td>
                        <td className="py-2 pr-3">{change.description}</td>
                        <td className="py-2 pr-3 text-right whitespace-nowrap tabular-nums">
                          {formatCurrency(change.amount, change.currency_code)}
                        </td>
                        <td className="py-2 pr-3">{change.rule_name ?? "nenhuma (volta a não classificado)"}</td>
                        <td className="py-2">{outcome(change.nature, change.category_id, change.tag_ids)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
