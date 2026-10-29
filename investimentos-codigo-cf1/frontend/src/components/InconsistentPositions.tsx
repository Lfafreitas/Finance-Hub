import type { AccountRead, PositionSummary } from "../api/types";

interface InconsistentPositionsProps {
  /** Só posições com `currency_code === null`. */
  positions: PositionSummary[];
  /** Só para mostrar o NOME da conta; sem ele, mostra o id. */
  accounts: AccountRead[];
}

/**
 * Posições cujas transações ativas estão em mais de uma moeda. Não
 * pertencem a nenhuma moeda, então ficam fora de todos os blocos e
 * aparecem aqui, sempre visíveis. Nenhum valor monetário é exibido: o
 * backend não os calcula para essas posições.
 */
export function InconsistentPositions({ positions, accounts }: InconsistentPositionsProps) {
  if (positions.length === 0) return null;

  return (
    <div
      className="rounded-lg border border-amber-800 bg-amber-950/40 p-4"
      role="alert"
      data-testid="inconsistent-positions"
    >
      <h2 className="text-sm font-medium text-amber-200">
        Posições com moedas misturadas ({positions.length}) — fora de todos os totais
      </h2>
      <p className="mt-1 text-xs text-amber-200/70">
        Corrija ou reverta o lançamento na moeda errada para a posição voltar aos totais.
      </p>
      <table className="mt-3 w-full text-left text-sm">
        <thead>
          <tr className="border-b border-amber-900 text-amber-200/70">
            <th className="py-2 pr-3">Ativo</th>
            <th className="py-2 pr-3">Conta</th>
            <th className="py-2 pr-3">Quantidade</th>
            <th className="py-2 pr-3">Situação</th>
            <th className="py-2">Motivo</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => {
            const account = accounts.find((item) => item.id === position.account_id);
            return (
              <tr key={`${position.account_id}-${position.asset_id}`} className="border-b border-amber-950 align-top">
                <td className="py-2 pr-3 text-neutral-100">{position.asset_ticker}</td>
                <td className="py-2 pr-3" title={position.account_id}>
                  {account ? `${account.name} — ${account.institution_name}` : position.account_id}
                </td>
                <td className="py-2 pr-3">{position.quantity}</td>
                <td className="py-2 pr-3">{position.is_closed ? "Zerada" : "Aberta"}</td>
                <td className="py-2 text-amber-100">{position.currency_inconsistency_reason}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
