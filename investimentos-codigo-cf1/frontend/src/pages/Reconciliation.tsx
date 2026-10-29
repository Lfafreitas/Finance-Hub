import { useCallback, useEffect, useState } from "react";

import { getAccounts, getPendingReconciliations, getPortfolios } from "../api/client";
import type { AccountRead, PortfolioRead, ReconciliationLogRead } from "../api/types";
import { investmentAccounts } from "../lib/accountTypes";
import { ReconciliationDetail } from "../components/ReconciliationDetail";
import { ReconciliationList } from "../components/ReconciliationList";
import { ReconciliationScanPanel } from "../components/ReconciliationScanPanel";

type ListState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; logs: ReconciliationLogRead[] };

export function Reconciliation() {
  const [list, setList] = useState<ListState>({ status: "loading" });
  const [selected, setSelected] = useState<ReconciliationLogRead | null>(null);
  const [accounts, setAccounts] = useState<AccountRead[]>([]);
  const [portfolios, setPortfolios] = useState<PortfolioRead[]>([]);
  const [notice, setNotice] = useState<string | null>(null);

  // A lista é SEMPRE a que o backend devolve — nunca atualizada de
  // forma otimista. Depois de resolver um par ou rodar um scan, busca
  // de novo.
  const loadPending = useCallback(() => {
    return getPendingReconciliations()
      .then((logs) => {
        setList({ status: "ready", logs });
        // Um par selecionado que saiu da lista (resolvido aqui ou em
        // outra aba) deixa de estar selecionado.
        setSelected((current) => (current && logs.some((log) => log.id === current.id) ? current : null));
      })
      .catch((err: Error) => setList({ status: "error", message: err.message }));
  }, []);

  useEffect(() => {
    void loadPending();
    // Contas e carteiras só alimentam o seletor de escopo do scan e o
    // nome da conta no detalhe — uma falha aqui não impede a tela.
    getAccounts()
      .then(setAccounts)
      .catch(() => {});
    getPortfolios()
      .then(setPortfolios)
      .catch(() => {});
  }, [loadPending]);

  function reload() {
    setList({ status: "loading" });
    void loadPending();
  }

  function handleResolved(resolved: ReconciliationLogRead) {
    const labels: Record<string, string> = {
      IGNORED: "Pendência ignorada.",
      KEPT_BOTH: "As duas transações foram mantidas.",
      MERGED: "Transações mescladas: uma permaneceu e a outra foi revertida.",
    };
    setNotice(labels[resolved.status] ?? "Pendência resolvida.");
    setSelected(null);
    reload();
  }

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
        <h2 className="mb-1 text-[15px] font-semibold tracking-tight text-neutral-100">Procurar divergências</h2>
        <p className="mb-3 text-xs text-neutral-500">
          Compara as transações ativas de cada conta e registra como pendência os pares que parecem ser o mesmo
          evento vindo de fontes diferentes. Nada é alterado automaticamente.
        </p>
        <ReconciliationScanPanel
          accounts={investmentAccounts(accounts)}
          portfolios={portfolios}
          onScanned={() => {
            setNotice(null);
            reload();
          }}
        />
      </div>

      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-[15px] font-semibold tracking-tight text-neutral-100">Pendências</h2>
          <button
            type="button"
            className="rounded-md border border-neutral-700 px-3 py-1 text-xs text-neutral-100 hover:bg-neutral-800"
            onClick={reload}
          >
            Atualizar
          </button>
        </div>

        {notice && (
          <p className="mb-2 text-sm text-emerald-300" role="status" data-testid="resolve-notice">
            {notice}
          </p>
        )}

        {list.status === "loading" && (
          <p className="text-neutral-400" role="status">
            Carregando pendências…
          </p>
        )}
        {list.status === "error" && (
          <p className="text-red-400" role="alert">
            Não foi possível carregar as pendências: {list.message}
          </p>
        )}
        {list.status === "ready" && (
          <ReconciliationList
            logs={list.logs}
            selectedId={selected?.id ?? null}
            onSelect={(log) => {
              setNotice(null);
              setSelected(log);
            }}
          />
        )}
      </div>

      {selected && (
        <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[15px] font-semibold tracking-tight text-neutral-100">Detalhe do par</h2>
            <button
              type="button"
              className="rounded-md border border-neutral-700 px-3 py-1 text-xs text-neutral-100 hover:bg-neutral-800"
              onClick={() => setSelected(null)}
            >
              Fechar
            </button>
          </div>
          <ReconciliationDetail key={selected.id} log={selected} accounts={accounts} onResolved={handleResolved} />
        </div>
      )}
    </div>
  );
}
