import { useEffect, useState } from "react";

import type { LookThrough } from "../../api/insights";
import { getLookThrough } from "../../api/insights";
import { formatIsoDate, formatPercent } from "../../lib/formatCurrency";
import { PANEL_CLASS } from "../../lib/ui";

const CURRENCY_TITLES: Record<string, string> = { BRL: "em reais", USD: "em dólar" };

/** 0,0512 → "5,1%" */
function pct1(value: string): string {
  return (Number(value) * 100).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
}

/**
 * Empresas por trás dos ETFs: quanto da carteira está em cada empresa,
 * somando o que vem por cada fundo (composição publicada pela gestora,
 * trazida pela análise do dia). É um piso: só as maiores posições de cada
 * fundo entram.
 */
export function LookThroughPanel({ reloadKey = 0 }: { reloadKey?: number }) {
  const [data, setData] = useState<LookThrough | null>(null);

  useEffect(() => {
    getLookThrough()
      .then(setData)
      .catch(() => setData(null));
  }, [reloadKey]);

  if (data === null || data.currencies.length === 0) return null;
  return (
    <section aria-labelledby="lookthrough-title" className={PANEL_CLASS} data-testid="lookthrough">
      <h3 id="lookthrough-title" className="text-sm font-medium text-neutral-200">
        Empresas por trás dos seus ETFs
      </h3>
      {data.currencies.map((block) => {
        const max = Math.max(...block.companies.map((c) => Number(c.weight)), 0);
        return (
          <div key={block.currency_code} className="mt-3" data-testid={`lookthrough-${block.currency_code}`}>
            {block.companies.length === 0 ? (
              <p className="text-sm text-neutral-400">
                A composição dos fundos chega com a análise diária (a partir da próxima edição).
              </p>
            ) : (
              <>
                <p className="text-xs text-neutral-500">
                  Peso na carteira {CURRENCY_TITLES[block.currency_code] ?? `em ${block.currency_code}`}, somando todos
                  os fundos.
                </p>
                <ul className="mt-3 space-y-2.5">
                  {block.companies.map((company) => (
                    <li key={company.ticker ?? company.name} data-testid="lookthrough-company">
                      <div className="flex items-baseline justify-between gap-3 text-sm">
                        <span className="min-w-0 truncate text-neutral-100">
                          {company.name}
                          {company.ticker && company.ticker !== company.name && (
                            <span className="ml-1.5 text-xs text-neutral-500">{company.ticker}</span>
                          )}
                        </span>
                        <span className="tabular-nums text-neutral-200">{pct1(company.weight)}</span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-neutral-800">
                        <div
                          className="h-full rounded-full bg-sky-400"
                          style={{ width: `${max > 0 ? (Number(company.weight) / max) * 100 : 0}%` }}
                        />
                      </div>
                      {company.via.length > 1 && (
                        <p className="mt-0.5 text-[11px] text-neutral-500">
                          {company.via.map((v) => `${v.ticker} ${pct1(v.weight)}`).join(" + ")}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
                <p
                  className="mt-3 text-xs text-neutral-500"
                  data-testid={`lookthrough-explained-${block.currency_code}`}
                >
                  Estas {block.companies.length} empresas somam {pct1(block.explained)} da carteira — no mínimo: só
                  entram as maiores posições de cada fundo.
                </p>
              </>
            )}
            {(block.funds.length > 0 || block.missing.length > 0) && (
              <p className="mt-2 text-xs text-neutral-500">
                {block.funds
                  .map(
                    (f) =>
                      `${f.ticker}: ${formatPercent(f.coverage)} do fundo (${f.source}, ${formatIsoDate(f.as_of)})`,
                  )
                  .join("; ")}
                {block.missing.length > 0 &&
                  `${block.funds.length > 0 ? ". " : ""}Sem composição: ${block.missing.join(", ")}.`}
              </p>
            )}
          </div>
        );
      })}
    </section>
  );
}
