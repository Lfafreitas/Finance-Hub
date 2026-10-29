import type { ScenariosRead } from "../../api/analytics";
import { formatCurrency, formatIsoDate, formatPercent } from "../../lib/formatCurrency";
import { PANEL_CLASS } from "../../lib/ui";

interface ScenariosPanelProps {
  currency: string;
  scenarios: ScenariosRead | null;
  unavailableReason: string | null;
  /** O que ainda entraria de aporte até dezembro no ritmo médio (já calculado). */
  remainingAtAverage: string | null;
}

function tone(value: string): string {
  return Number(value) < 0 ? "text-red-400" : "text-emerald-400";
}

/**
 * Pessimista, realista e otimista até a data final, com as premissas
 * que geraram os números. É uma régua de incerteza, não uma previsão.
 */
export function ScenariosPanel({ currency, scenarios, unavailableReason, remainingAtAverage }: ScenariosPanelProps) {
  if (scenarios === null) {
    return (
      <div className={PANEL_CLASS} data-testid={`scenarios-${currency}`}>
        <h3 className="mb-2 text-sm font-medium text-neutral-300">Cenários</h3>
        <p className="text-sm text-neutral-500">{unavailableReason ?? "Sem cenários para esta moeda."}</p>
      </div>
    );
  }
  const rows = [
    { label: "Pessimista", hint: "só 10% dos casos terminam abaixo", ret: scenarios.pessimistic_return, value: scenarios.pessimistic_value },
    { label: "Realista", hint: "o meio da distribuição", ret: scenarios.realistic_return, value: scenarios.realistic_value },
    { label: "Otimista", hint: "só 10% dos casos terminam acima", ret: scenarios.optimistic_return, value: scenarios.optimistic_value },
  ];
  return (
    <div className={PANEL_CLASS} data-testid={`scenarios-${currency}`}>
      <h3 className="mb-1 text-sm font-medium text-neutral-300">
        Cenários até {formatIsoDate(scenarios.until)} · {scenarios.horizon_days} dias
      </h3>
      <p className="mb-3 text-xs text-neutral-500">
        Sobre {formatCurrency(scenarios.value_today, currency)} de hoje, só o que tem risco de mercado.
      </p>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-neutral-800 text-neutral-400">
            <th className="py-2 pr-3">Cenário</th>
            <th className="py-2 pr-3 text-right">Variação</th>
            <th className="py-2 text-right">Valor na data</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-b border-neutral-900" data-testid={`scenario-${row.label}`}>
              <td className="py-2 pr-3">
                {row.label}
                <span className="block text-xs text-neutral-500">{row.hint}</span>
              </td>
              <td className={`py-2 pr-3 text-right tabular-nums ${tone(row.ret)}`}>{formatPercent(row.ret)}</td>
              <td className="py-2 text-right tabular-nums">{formatCurrency(row.value, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-sm" data-testid={`probability-${currency}`}>
        Chance de terminar abaixo do valor de hoje: <strong>{formatPercent(scenarios.probability_below_today)}</strong>
      </p>
      {remainingAtAverage !== null && Number(remainingAtAverage) > 0 && (
        <p className="mt-1 text-sm text-neutral-400" data-testid={`scenarios-contributions-${currency}`}>
          Mantendo o seu ritmo médio de aporte, entram mais {formatCurrency(remainingAtAverage, currency)} até
          dezembro — em prazo curto, é isso que mais muda o resultado.
        </p>
      )}

      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-neutral-400">Premissas usadas</summary>
        <p className="mt-2 text-xs text-neutral-500">
          Volatilidade da carteira {formatPercent(scenarios.volatility)} ao ano; retorno esperado{" "}
          {formatPercent(scenarios.expected_return)} ao ano (premissa de longo prazo, não previsão). A volatilidade de
          cada ativo vem do histórico de preços quando há pelo menos 60 dias de cotação; senão, de um valor padrão da
          classe.
        </p>
        <table className="mt-2 w-full text-left text-xs" data-testid={`assumptions-${currency}`}>
          <thead>
            <tr className="text-neutral-500">
              <th className="py-1 pr-3">Ativo</th>
              <th className="py-1 pr-3 text-right">Peso</th>
              <th className="py-1 pr-3 text-right">Volatilidade</th>
              <th className="py-1 pr-3">Origem</th>
              <th className="py-1 text-right">Retorno esperado</th>
            </tr>
          </thead>
          <tbody>
            {scenarios.assumptions.map((item) => (
              <tr key={item.key}>
                <td className="py-1 pr-3">{item.key}</td>
                <td className="py-1 pr-3 text-right tabular-nums">{formatPercent(item.weight)}</td>
                <td className="py-1 pr-3 text-right tabular-nums">{formatPercent(item.volatility)}</td>
                <td className="py-1 pr-3">
                  {item.volatility_from_history ? `histórico (${item.history_returns} dias)` : "padrão da classe"}
                </td>
                <td className="py-1 text-right tabular-nums">{formatPercent(item.expected_return)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {scenarios.excluded.length > 0 && (
          <ul className="mt-2 space-y-1 text-xs text-neutral-500" data-testid={`excluded-${currency}`}>
            {scenarios.excluded.map((item) => (
              <li key={item.key}>
                {item.key}: {item.reason}
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  );
}
