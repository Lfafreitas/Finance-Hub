import { useEffect, useState } from "react";

import type { PaperItem } from "../../api/insights";
import type { ReadingSource } from "../../api/notes";
import { createSource, deleteSource, getSources, updateSource } from "../../api/notes";
import { describeApiError } from "../../lib/apiErrors";
import { formatIsoDate } from "../../lib/formatCurrency";
import { SafeLink } from "../insights/SafeLink";
import { Hl } from "./Highlighted";

/** O que saiu de novo nas fontes que o usuário cadastrou (relatório v4). */
export function OtherReadings({ papers }: { papers: PaperItem[] }) {
  const bySource = new Map<string, PaperItem[]>();
  for (const paper of papers) bySource.set(paper.source, [...(bySource.get(paper.source) ?? []), paper]);
  return (
    <section aria-labelledby="papers-title" className="space-y-4" data-testid="papers">
      <div>
        <h3 id="papers-title" className="font-serif text-xl font-medium text-neutral-50">
          Outras leituras
        </h3>
        <p className="mt-0.5 text-[13px] text-neutral-500">
          O que saiu nas suas fontes, resumido pelo Claude. O texto completo fica no link.
        </p>
      </div>
      {papers.length === 0 ? (
        <p className="text-[15px] text-neutral-400" data-testid="papers-empty">
          Nada novo nas suas fontes nesta edição.
        </p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {[...bySource.entries()].map(([source, items]) => (
            <div key={source} className="read-surface rounded-2xl bg-neutral-900 p-4 ring-1 ring-neutral-800">
              <p className="mb-2 text-[13px] font-medium text-sky-300">{source}</p>
              <ul className="divide-y divide-neutral-800">
                {items.map((paper) => (
                  <li
                    key={paper.url + paper.title}
                    className="py-3 first:pt-0 last:pb-0"
                    data-quote-source={`${paper.source} · ${paper.title}`}
                    data-quote-url={paper.url}
                    data-testid="paper"
                  >
                    <p className="read-body font-medium leading-snug">
                      <SafeLink url={paper.url}>{paper.title}</SafeLink>
                    </p>
                    {paper.published_at && (
                      <p className="mt-0.5 text-[12px] text-neutral-500">{formatIsoDate(paper.published_at)}</p>
                    )}
                    <p className="read-small mt-2 text-neutral-300">
                      <Hl text={paper.summary} />
                    </p>
                    {paper.takeaways.length > 0 && (
                      <ul className="read-small mt-2 list-disc space-y-1 pl-5 text-neutral-300 marker:text-neutral-600">
                        {paper.takeaways.map((t) => (
                          <li key={t}>
                            <Hl text={t} />
                          </li>
                        ))}
                      </ul>
                    )}
                    {paper.relation && (
                      <p className="mt-2 text-[13px] text-neutral-400">Para a sua carteira: {paper.relation}</p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/**
 * As fontes que a análise diária lê para "Outras leituras": cadastrar,
 * pausar e remover. A leitura acontece na análise das 7h51 (o app não
 * acessa esses sites).
 */
export function SourcesPanel() {
  const [sources, setSources] = useState<ReadingSource[] | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [focus, setFocus] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    getSources()
      .then(setSources)
      .catch((err: unknown) => setError(describeApiError(err)));
  useEffect(() => {
    void load();
  }, []);

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      await load();
    } catch (err: unknown) {
      setError(describeApiError(err));
    }
  }

  const field =
    "min-h-11 w-full rounded-xl bg-neutral-800/70 px-3 text-[16px] text-neutral-100 placeholder:text-neutral-500 focus:outline-none focus:ring-1 focus:ring-sky-400";
  return (
    <details className="rounded-2xl bg-neutral-900 p-4 ring-1 ring-neutral-800" data-testid="sources">
      <summary className="cursor-pointer text-[15px] font-medium text-neutral-200">
        Suas fontes de leitura{sources ? ` (${sources.length})` : ""}
      </summary>
      <p className="mt-2 text-[13px] text-neutral-500">
        A análise das 7h51 abre cada fonte ativa e traz o que saiu de novo para "Outras leituras".
      </p>
      <ul className="mt-3 divide-y divide-neutral-800">
        {(sources ?? []).map((src) => (
          <li key={src.id} className="flex flex-wrap items-center justify-between gap-2 py-2" data-testid="source">
            <div className="min-w-0">
              <p className={`text-[15px] ${src.active ? "text-neutral-100" : "text-neutral-500 line-through"}`}>
                {src.name}
              </p>
              <p className="truncate text-[12px] text-neutral-500">
                {src.focus ? `${src.focus} · ${src.url}` : src.url}
              </p>
            </div>
            <span className="flex gap-1">
              <button
                type="button"
                className="min-h-9 rounded-lg px-2.5 text-[13px] text-neutral-400 hover:bg-neutral-800"
                onClick={() =>
                  void act(() =>
                    updateSource(src.id, { name: src.name, url: src.url, focus: src.focus, active: !src.active }),
                  )
                }
              >
                {src.active ? "Pausar" : "Retomar"}
              </button>
              <button
                type="button"
                className="min-h-9 rounded-lg px-2.5 text-[13px] text-red-300 hover:bg-neutral-800"
                onClick={() => void act(() => deleteSource(src.id))}
              >
                Remover
              </button>
            </span>
          </li>
        ))}
      </ul>
      <form
        className="mt-3 grid gap-2 md:grid-cols-[1fr_1.4fr_1.4fr_auto]"
        onSubmit={(e) => {
          e.preventDefault();
          void act(async () => {
            await createSource({ name, url, focus: focus || null, active: true });
            setName("");
            setUrl("");
            setFocus("");
          });
        }}
      >
        <input
          aria-label="Nome da fonte"
          placeholder="Nome (ex.: World Reports)"
          className={field}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          aria-label="Link da fonte"
          placeholder="https://…"
          className={field}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <input
          aria-label="O que procurar"
          placeholder="O que procurar (opcional)"
          className={field}
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
        />
        <button
          type="submit"
          className="min-h-11 rounded-xl bg-neutral-100 px-4 text-[15px] font-semibold text-neutral-950 disabled:opacity-40"
          disabled={!name.trim() || !url.trim()}
        >
          Adicionar
        </button>
      </form>
      {error && (
        <p className="mt-2 text-[14px] text-red-300" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}
