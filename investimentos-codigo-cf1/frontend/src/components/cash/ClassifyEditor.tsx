import { type FormEvent, useState } from "react";

import { classifyCashEntry, createRule } from "../../api/cashflow";
import type { CashflowEntryRead, CashflowNature, CategoryRead, TagRead } from "../../api/cashflowTypes";
import { describeApiError } from "../../lib/apiErrors";
import { MANUAL_NATURES, NATURE_LABELS, categoryOptions, isOutflow } from "../../lib/cashflow";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS } from "../../lib/ui";
import { ErrorText } from "./shared";

interface ClassifyEditorProps {
  entry: CashflowEntryRead;
  categories: CategoryRead[];
  tags: TagRead[];
  /** Chamado depois de gravar; `ruleCreated` diz se uma regra nova nasceu junto. */
  onSaved: (ruleCreated: boolean) => void;
  onCancel: () => void;
}

/**
 * Classificação manual de um lançamento: natureza, categoria e tags de
 * uma vez. Opcionalmente cria uma regra com o mesmo destino, para os
 * próximos lançamentos com o mesmo texto.
 */
export function ClassifyEditor({ entry, categories, tags, onSaved, onCancel }: ClassifyEditorProps) {
  const [nature, setNature] = useState<CashflowNature>(entry.nature === "UNCLASSIFIED" ? "EXPENSE" : entry.nature);
  const [categoryId, setCategoryId] = useState(entry.category_id ?? "");
  const [tagIds, setTagIds] = useState<ReadonlySet<string>>(new Set(entry.tag_ids));
  const [withRule, setWithRule] = useState(false);
  const [pattern, setPattern] = useState(entry.match_text);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Regra precisa de uma natureza de verdade.
  const ruleAllowed = nature !== "UNCLASSIFIED";
  const wantsRule = withRule && ruleAllowed;
  const canSave = !saving && (!wantsRule || pattern.trim() !== "");
  const prefix = `classify-${entry.id}`;

  function toggleTag(id: string) {
    setTagIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const category = categoryId === "" ? null : categoryId;
    const chosenTags = tags.filter((tag) => tagIds.has(tag.id)).map((tag) => tag.id);
    try {
      await classifyCashEntry(entry.id, { nature, category_id: category, tag_ids: chosenTags });
    } catch (err) {
      setError(describeApiError(err));
      setSaving(false);
      return;
    }
    if (!wantsRule) {
      onSaved(false);
      return;
    }
    try {
      const text = pattern.trim();
      await createRule({
        name: text.slice(0, 120),
        priority: 100,
        is_active: true,
        match_type: "CONTAINS",
        pattern: text,
        direction: isOutflow(entry.amount) ? "OUT" : "IN",
        account_id: null,
        set_nature: nature,
        set_category_id: category,
        tag_ids: chosenTags,
      });
      onSaved(true);
    } catch (err) {
      // A classificação JÁ foi gravada; só a regra falhou.
      setError(`O lançamento foi classificado, mas a regra não foi criada: ${describeApiError(err)}`);
      setWithRule(false);
      setSaving(false);
    }
  }

  return (
    <form className="space-y-3" onSubmit={handleSubmit} aria-label={`Classificar ${entry.description}`}>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div>
          <label className={LABEL_CLASS} htmlFor={`${prefix}-nature`}>
            Natureza
          </label>
          <select
            id={`${prefix}-nature`}
            className={INPUT_CLASS}
            value={nature}
            disabled={saving}
            onChange={(event) => setNature(event.target.value as CashflowNature)}
          >
            {MANUAL_NATURES.map((item) => (
              <option key={item} value={item}>
                {NATURE_LABELS[item]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor={`${prefix}-category`}>
            Categoria
          </label>
          <select
            id={`${prefix}-category`}
            className={INPUT_CLASS}
            value={categoryId}
            disabled={saving}
            onChange={(event) => setCategoryId(event.target.value)}
          >
            <option value="">Sem categoria</option>
            {categoryOptions(categories).map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {tags.length > 0 && (
        <fieldset>
          <legend className={LABEL_CLASS}>Tags</legend>
          <div className="flex flex-wrap gap-3 text-sm">
            {tags.map((tag) => (
              <label key={tag.id} className="inline-flex items-center gap-1.5">
                <input type="checkbox" checked={tagIds.has(tag.id)} disabled={saving} onChange={() => toggleTag(tag.id)} />
                {tag.tag_group ? `${tag.tag_group}: ${tag.name}` : tag.name}
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <div>
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={wantsRule}
            disabled={saving || !ruleAllowed}
            onChange={(event) => setWithRule(event.target.checked)}
          />
          Criar regra para os próximos lançamentos com este texto
        </label>
        {wantsRule && (
          <div className="mt-2 max-w-md">
            <label className={LABEL_CLASS} htmlFor={`${prefix}-pattern`}>
              Texto que a regra procura ({isOutflow(entry.amount) ? "só em saídas" : "só em entradas"})
            </label>
            <input
              id={`${prefix}-pattern`}
              className={INPUT_CLASS}
              value={pattern}
              maxLength={200}
              disabled={saving}
              onChange={(event) => setPattern(event.target.value)}
            />
            <p className="mt-1 text-xs text-neutral-500">
              A regra vale para o que for importado daqui em diante. Para aplicar ao que já existe, use a tela Regras.
            </p>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <button type="submit" className={BUTTON_CLASS} disabled={!canSave}>
          {saving ? "Salvando…" : "Salvar classificação"}
        </button>
        <button type="button" className={BUTTON_CLASS} disabled={saving} onClick={onCancel}>
          Cancelar
        </button>
      </div>
      {error && <ErrorText>{error}</ErrorText>}
    </form>
  );
}
