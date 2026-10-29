import type { ReconciliationLogRead } from "../api/types";
import { formatDateTime, shortId } from "../lib/reconciliationLabels";

interface ReconciliationListProps {
  logs: ReconciliationLogRead[];
  selectedId: string | null;
  onSelect: (log: ReconciliationLogRead) => void;
}

export function ReconciliationList({ logs, selectedId, onSelect }: ReconciliationListProps) {
  if (logs.length === 0) {
    return <p className="text-neutral-500">Nenhuma pendência de reconciliação.</p>;
  }

  return (
    <table className="w-full text-left text-sm" data-testid="reconciliation-list">
      <thead>
        <tr className="border-b border-neutral-800 text-neutral-400">
          <th className="py-2 pr-3">Detectada em</th>
          <th className="py-2 pr-3">Transação A</th>
          <th className="py-2 pr-3">Transação B</th>
          <th className="py-2 pr-3">Motivo registrado</th>
          <th className="py-2" />
        </tr>
      </thead>
      <tbody>
        {logs.map((log) => {
          const selected = log.id === selectedId;
          return (
            <tr
              key={log.id}
              className={`border-b border-neutral-900 align-top ${selected ? "bg-neutral-800/60" : ""}`}
              aria-selected={selected}
            >
              <td className="py-2 pr-3 whitespace-nowrap">{formatDateTime(log.created_at)}</td>
              <td className="py-2 pr-3 font-mono text-xs" title={log.transaction_a_id}>
                {shortId(log.transaction_a_id)}
              </td>
              <td className="py-2 pr-3 font-mono text-xs" title={log.transaction_b_id}>
                {shortId(log.transaction_b_id)}
              </td>
              <td className="py-2 pr-3 text-neutral-300">{log.match_reason}</td>
              <td className="py-2 text-right">
                <button
                  type="button"
                  className="rounded-md border border-neutral-700 px-3 py-1 text-xs text-neutral-100 hover:bg-neutral-800"
                  onClick={() => onSelect(log)}
                  aria-label={`Ver detalhes do par ${shortId(log.transaction_a_id)} e ${shortId(log.transaction_b_id)}`}
                >
                  Ver detalhes
                </button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
