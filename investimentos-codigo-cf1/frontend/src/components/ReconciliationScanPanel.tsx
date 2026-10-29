import { useState } from "react";

import { scanReconciliation } from "../api/client";
import type { AccountRead, PortfolioRead, ReconciliationScanRequest, ReconciliationScanResult } from "../api/types";
import { describeScanError } from "../lib/reconciliationErrors";

interface ReconciliationScanPanelProps {
  accounts: AccountRead[];
  portfolios: PortfolioRead[];
  /** Chamado depois de um scan bem-sucedido, para a lista ser recarregada. */
  onScanned: (result: ReconciliationScanResult) => void;
}

type ScopeKind = "all" | "account" | "portfolio";

function describeResult(result: ReconciliationScanResult): string {
  if (result.created_count === 0) return "Nenhum par novo encontrado.";
  if (result.created_count === 1) return "1 par novo encontrado e adicionado às pendências.";
  return `${result.created_count} pares novos encontrados e adicionados às pendências.`;
}

export function ReconciliationScanPanel({ accounts, portfolios, onScanned }: ReconciliationScanPanelProps) {
  const [scopeKind, setScopeKind] = useState<ScopeKind>("all");
  const [targetId, setTargetId] = useState("");
  const [scanning, setScanning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const needsTarget = scopeKind !== "all";
  const options = scopeKind === "account" ? accounts : scopeKind === "portfolio" ? portfolios : [];
  const selectClass = "rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm text-neutral-100";

  async function runScan() {
    const scope: ReconciliationScanRequest =
      scopeKind === "account" ? { account_id: targetId } : scopeKind === "portfolio" ? { portfolio_id: targetId } : {};
    setScanning(true);
    setMessage(null);
    setError(null);
    try {
      const result = await scanReconciliation(scope);
      setMessage(describeResult(result));
      onScanned(result);
    } catch (err) {
      setError(describeScanError(err));
    } finally {
      setScanning(false);
    }
  }

  return (
    <div className="space-y-2" data-testid="reconciliation-scan-panel">
      <div className="flex flex-wrap items-center gap-2">
        <select
          className={selectClass}
          aria-label="Escopo da busca"
          value={scopeKind}
          disabled={scanning}
          onChange={(event) => {
            setScopeKind(event.target.value as ScopeKind);
            setTargetId("");
          }}
        >
          <option value="all">Todas as contas</option>
          <option value="account">Uma conta</option>
          <option value="portfolio">Uma carteira</option>
        </select>

        {needsTarget && (
          <select
            className={selectClass}
            aria-label={scopeKind === "account" ? "Conta" : "Carteira"}
            value={targetId}
            disabled={scanning}
            onChange={(event) => setTargetId(event.target.value)}
          >
            <option value="">Selecione…</option>
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
        )}

        <button
          type="button"
          className="rounded-md border border-neutral-700 px-3 py-2 text-sm text-neutral-100 hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40"
          disabled={scanning || (needsTarget && targetId === "")}
          onClick={runScan}
        >
          {scanning ? "Procurando…" : "Procurar divergências"}
        </button>
      </div>

      {message && (
        <p className="text-sm text-neutral-300" role="status" data-testid="scan-result">
          {message}
        </p>
      )}
      {error && (
        <p className="text-sm text-red-400" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
