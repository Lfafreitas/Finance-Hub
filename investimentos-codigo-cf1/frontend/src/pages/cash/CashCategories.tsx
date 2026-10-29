import { type FormEvent, useCallback, useEffect, useState } from "react";

import {
  createCategory,
  createDefaultCategories,
  createTag,
  deleteCategory,
  deleteTag,
  getCategories,
  getTags,
  updateCategory,
  updateTag,
} from "../../api/cashflow";
import type { CategoryRead, TagRead } from "../../api/cashflowTypes";
import { ConfirmButton, ErrorText, Loading, SMALL_BUTTON_CLASS } from "../../components/cash/shared";
import { describeApiError } from "../../lib/apiErrors";
import { categoryOptions } from "../../lib/cashflow";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS, PANEL_CLASS } from "../../lib/ui";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; categories: CategoryRead[]; tags: TagRead[] };

function CategoriesPanel({ categories, onChanged }: { categories: CategoryRead[]; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState<CategoryRead | null>(null);
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const roots = categories
    .filter((category) => category.parent_id === null)
    .sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
  const options = categoryOptions(categories);

  function reset() {
    setEditing(null);
    setName("");
    setParentId("");
  }

  function startEdit(category: CategoryRead) {
    setEditing(category);
    setName(category.name);
    setParentId(category.parent_id ?? "");
    setError(null);
    setNotice(null);
  }

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const message = await action();
      await onChanged();
      setNotice(message);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const payload = { name: name.trim(), parent_id: parentId === "" ? null : parentId };
    void run(async () => {
      if (editing) await updateCategory(editing.id, payload);
      else await createCategory(payload);
      reset();
      return editing ? "Categoria alterada." : "Categoria criada.";
    });
  }

  return (
    <div className={PANEL_CLASS}>
      <h2 className="mb-3 text-[15px] font-semibold tracking-tight text-neutral-100">Categorias</h2>
      <form className="space-y-3" onSubmit={handleSubmit} aria-label="Categoria">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <label className={LABEL_CLASS} htmlFor="cat-name">
              Nome
            </label>
            <input
              id="cat-name"
              className={INPUT_CLASS}
              value={name}
              maxLength={80}
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="cat-parent">
              Dentro de
            </label>
            <select
              id="cat-parent"
              className={INPUT_CLASS}
              value={parentId}
              disabled={busy}
              onChange={(event) => setParentId(event.target.value)}
            >
              <option value="">Nenhuma (categoria principal)</option>
              {roots
                .filter((root) => root.id !== editing?.id)
                .map((root) => (
                  <option key={root.id} value={root.id}>
                    {root.name}
                  </option>
                ))}
            </select>
          </div>
        </div>
        {editing && (
          <p className="text-xs text-amber-300" data-testid="category-editing">
            Editando: {editing.name}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="submit" className={BUTTON_CLASS} disabled={busy || name.trim() === ""}>
            {editing ? "Salvar alterações" : "Adicionar categoria"}
          </button>
          {editing && (
            <button type="button" className={BUTTON_CLASS} disabled={busy} onClick={reset}>
              Cancelar edição
            </button>
          )}
          <button
            type="button"
            className={BUTTON_CLASS}
            disabled={busy}
            onClick={() =>
              void run(async () => {
                await createDefaultCategories();
                return "Categorias sugeridas criadas. As que já existiam foram mantidas.";
              })
            }
          >
            Criar categorias sugeridas
          </button>
        </div>
        {error && <ErrorText>{error}</ErrorText>}
        {notice && (
          <p className="text-sm text-emerald-300" role="status">
            {notice}
          </p>
        )}
      </form>

      <p className="mt-3 text-xs text-neutral-500">
        Dois níveis: categoria e subcategoria. Só é possível excluir o que não está em uso.
      </p>
      <div className="mt-3 text-sm">
        {options.length === 0 ? (
          <p className="text-neutral-500">Nenhuma categoria cadastrada.</p>
        ) : (
          <ul data-testid="category-list">
            {options.map((option) => {
              const category = categories.find((item) => item.id === option.id);
              if (!category) return null;
              return (
                <li
                  key={option.id}
                  className={`flex flex-wrap items-center justify-between gap-2 border-b border-neutral-900 py-1.5 ${
                    option.isChild ? "pl-6 text-neutral-300" : "font-medium"
                  }`}
                >
                  <span>{category.name}</span>
                  <span className="flex flex-wrap gap-1">
                    <button
                      type="button"
                      className={SMALL_BUTTON_CLASS}
                      aria-label={`Editar categoria ${option.label}`}
                      onClick={() => startEdit(category)}
                    >
                      Editar
                    </button>
                    <ConfirmButton
                      label="Excluir"
                      confirmLabel="Confirmar exclusão"
                      ariaLabel={`Excluir categoria ${option.label}`}
                      onConfirm={async () => {
                        await deleteCategory(category.id);
                        if (editing?.id === category.id) reset();
                        await onChanged();
                      }}
                    />
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function TagsPanel({ tags, onChanged }: { tags: TagRead[]; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState<TagRead | null>(null);
  const [name, setName] = useState("");
  const [group, setGroup] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setEditing(null);
    setName("");
    setGroup("");
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const payload = { name: name.trim(), tag_group: group.trim() };
    try {
      if (editing) await updateTag(editing.id, payload);
      else await createTag(payload);
      reset();
      await onChanged();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={PANEL_CLASS}>
      <h2 className="mb-3 text-[15px] font-semibold tracking-tight text-neutral-100">Tags</h2>
      <form className="space-y-3" onSubmit={handleSubmit} aria-label="Tag">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <label className={LABEL_CLASS} htmlFor="tag-name">
              Nome da tag
            </label>
            <input
              id="tag-name"
              className={INPUT_CLASS}
              value={name}
              maxLength={80}
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="tag-group">
              Grupo (opcional)
            </label>
            <input
              id="tag-group"
              className={INPUT_CLASS}
              value={group}
              maxLength={40}
              placeholder="ex.: pessoa, viagem"
              disabled={busy}
              onChange={(event) => setGroup(event.target.value)}
            />
          </div>
        </div>
        {editing && (
          <p className="text-xs text-amber-300" data-testid="tag-editing">
            Editando: {editing.name}
          </p>
        )}
        <div className="flex gap-2">
          <button type="submit" className={BUTTON_CLASS} disabled={busy || name.trim() === ""}>
            {editing ? "Salvar alterações" : "Adicionar tag"}
          </button>
          {editing && (
            <button type="button" className={BUTTON_CLASS} disabled={busy} onClick={reset}>
              Cancelar edição
            </button>
          )}
        </div>
        {error && <ErrorText>{error}</ErrorText>}
      </form>

      <p className="mt-3 text-xs text-neutral-500">
        Tag é uma marca livre, além da categoria. Excluir uma tag só a tira dos lançamentos; o resto fica como está.
      </p>
      <div className="mt-3 text-sm">
        {tags.length === 0 ? (
          <p className="text-neutral-500">Nenhuma tag cadastrada.</p>
        ) : (
          <ul data-testid="tag-list">
            {tags.map((tag) => {
              const label = tag.tag_group ? `${tag.tag_group}: ${tag.name}` : tag.name;
              return (
                <li key={tag.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-900 py-1.5">
                  <span>{label}</span>
                  <span className="flex flex-wrap gap-1">
                    <button
                      type="button"
                      className={SMALL_BUTTON_CLASS}
                      aria-label={`Editar tag ${label}`}
                      onClick={() => {
                        setEditing(tag);
                        setName(tag.name);
                        setGroup(tag.tag_group);
                        setError(null);
                      }}
                    >
                      Editar
                    </button>
                    <ConfirmButton
                      label="Excluir"
                      confirmLabel="Confirmar exclusão"
                      ariaLabel={`Excluir tag ${label}`}
                      onConfirm={async () => {
                        await deleteTag(tag.id);
                        if (editing?.id === tag.id) reset();
                        await onChanged();
                      }}
                    />
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

/** Categorias (dois níveis) e tags do controle financeiro. */
export function CashCategories() {
  const [state, setState] = useState<State>({ status: "loading" });

  const load = useCallback(
    () =>
      Promise.all([getCategories(), getTags()])
        .then(([categories, tags]) => setState({ status: "ready", categories, tags }))
        .catch((err: unknown) => setState({ status: "error", message: describeApiError(err) })),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") {
    return <ErrorText>{`Não foi possível carregar as categorias: ${state.message}`}</ErrorText>;
  }
  return (
    <div className="space-y-6">
      <CategoriesPanel categories={state.categories} onChanged={load} />
      <TagsPanel tags={state.tags} onChanged={load} />
    </div>
  );
}
