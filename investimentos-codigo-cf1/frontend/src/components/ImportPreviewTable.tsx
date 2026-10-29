import type { ImportRow } from "../api/types";
import { isRowSelectable } from "../lib/importRows";
import { transactionTypeLabel } from "../lib/transactionTypes";

interface ImportPreviewTableProps {
  rows: ImportRow[];
  selected: ReadonlySet<number>;
  onToggle: (rowIndex: number) => void;
  disabled?: boolean;
}

function rowSituation(row: ImportRow): { text: string; tone: string } {
  if (row.error !== null) return { text: row.error, tone: "text-red-400" };
  if (row.is_exact_duplicate) {
    return { text: "Já importada antes — será ignorada", tone: "text-neutral-500" };
  }
  if (row.possible_duplicate) {
    return { text: row.duplicate_reason ?? "Possível duplicata", tone: "text-amber-300" };
  }
  return { text: "Pronta para importar", tone: "text-emerald-300" };
}

/**
 * Linhas da preview, exatamente como o servidor devolveu. A tabela só
 * permite ESCOLHER linhas — nenhum valor é editável, porque o conteúdo
 * está coberto pela assinatura da preview.
 */
export function ImportPreviewTable({ rows, selected, onToggle, disabled = false }: ImportPreviewTableProps) {
  return (
    <table className="w-full text-left text-sm" data-testid="import-preview-table">
      <thead>
        <tr className="border-b border-neutral-800 text-neutral-400">
          <th className="py-2 pr-3">Incluir</th>
          <th className="py-2 pr-3">Data</th>
          <th className="py-2 pr-3">Tipo</th>
          <th className="py-2 pr-3">Ativo</th>
          <th className="py-2 pr-3">Quantidade</th>
          <th className="py-2 pr-3">Preço</th>
          <th className="py-2 pr-3">Taxas</th>
          <th className="py-2 pr-3">Valor</th>
          <th className="py-2 pr-3">Moeda</th>
          <th className="py-2">Situação</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const selectable = isRowSelectable(row);
          const situation = rowSituation(row);
          return (
            <tr
              key={row.row_index}
              data-testid={`import-row-${row.row_index}`}
              className={`border-b border-neutral-900 align-top ${selectable ? "" : "text-neutral-500"}`}
            >
              <td className="py-2 pr-3">
                <input
                  type="checkbox"
                  aria-label={`Incluir linha ${row.row_index + 1}`}
                  checked={selected.has(row.row_index)}
                  disabled={disabled || !selectable}
                  onChange={() => onToggle(row.row_index)}
                />
              </td>
              <td className="py-2 pr-3 whitespace-nowrap">{row.transaction_date}</td>
              <td className="py-2 pr-3">{transactionTypeLabel(row.transaction_type)}</td>
              <td className="py-2 pr-3">{row.asset_ticker ?? "—"}</td>
              <td className="py-2 pr-3">{row.quantity ?? "—"}</td>
              <td className="py-2 pr-3">{row.unit_price ?? "—"}</td>
              <td className="py-2 pr-3">{row.fees}</td>
              <td className="py-2 pr-3">{row.gross_amount}</td>
              <td className="py-2 pr-3">{row.currency_code}</td>
              <td className={`py-2 ${situation.tone}`}>{situation.text}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
