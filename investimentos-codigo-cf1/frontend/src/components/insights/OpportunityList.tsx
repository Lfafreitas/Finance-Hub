import type { ReactNode } from "react";

import type { Opportunity } from "../../api/insights";
import { SafeLink } from "./SafeLink";

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-xs font-medium text-neutral-400">{title}</p>
      <div className="mt-0.5 text-sm leading-relaxed text-neutral-300">{children}</div>
    </div>
  );
}

function OpportunityCard({ item }: { item: Opportunity }) {
  return (
    <article className="flex flex-col gap-3 border-t border-neutral-700 pt-4" data-testid="opportunity">
      <header>
        <h4 className="font-serif text-lg font-medium leading-snug text-neutral-50">{item.title}</h4>
        {item.tickers.length > 0 && (
          <p className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Ativos citados">
            {item.tickers.map((ticker) => (
              <span
                key={ticker}
                className="rounded bg-neutral-800 px-1.5 py-px text-[11px] font-medium text-neutral-300"
              >
                {ticker}
              </span>
            ))}
          </p>
        )}
      </header>
      <p className="text-sm leading-relaxed text-neutral-200">{item.thesis}</p>
      <Block title="Por que agora">{item.why_now}</Block>
      {item.relation && <Block title="E a sua carteira">{item.relation}</Block>}
      <Block title="Riscos">
        <ul className="list-disc space-y-0.5 pl-4 marker:text-neutral-600">
          {item.risks.map((risk) => (
            <li key={risk}>{risk}</li>
          ))}
        </ul>
      </Block>
      <Block title="Como acompanhar">{item.how_to_follow}</Block>
      <p className="mt-auto flex flex-wrap gap-x-3 text-xs">
        {item.sources.map((source) => (
          <SafeLink key={source.url} url={source.url}>
            {source.title}
          </SafeLink>
        ))}
      </p>
    </article>
  );
}

/**
 * Ideias que o Claude levantou para ESTUDAR no momento — cada uma com o
 * porquê agora, riscos e o que observar. Nunca é recomendação de compra:
 * o aviso fica junto da lista, não só no rodapé.
 */
export function OpportunityList({ items }: { items: Opportunity[] }) {
  if (items.length === 0) return null;
  return (
    <section aria-labelledby="opportunities-title" data-testid="opportunities">
      <h3 id="opportunities-title" className="font-serif text-xl font-medium text-neutral-50">
        Para estudar
      </h3>
      <p className="mt-1 max-w-3xl text-sm text-neutral-400" data-testid="opportunities-caveat">
        Ideias que o Claude levantou no mercado de agora, com os riscos e o que observar. São pontos de partida para
        você pesquisar — não são recomendação de compra.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-x-8 gap-y-6 md:grid-cols-2">
        {items.map((item) => (
          <OpportunityCard key={item.title} item={item} />
        ))}
      </div>
    </section>
  );
}
