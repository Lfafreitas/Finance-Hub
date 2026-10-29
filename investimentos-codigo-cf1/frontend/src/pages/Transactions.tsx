import { useCallback, useEffect, useState } from "react";

import { getAccounts, getAccountTransactions, getAssets, getCurrencies } from "../api/client";
import type { AccountRead, AssetRead, CurrencyRead, TransactionRead } from "../api/types";
import { TransactionForm } from "../components/TransactionForm";
import { TransactionHistory } from "../components/TransactionHistory";
import { TransferForm } from "../components/TransferForm";
import { investmentAccounts } from "../lib/accountTypes";
import { COMPACT_INPUT_CLASS, INPUT_CLASS, PANEL_CLASS } from "../lib/ui";

type HistoryState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; transactions: TransactionRead[] };

type Setup =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; accounts: AccountRead[]; assets: AssetRead[]; currencies: CurrencyRead[] };

export function Transactions({ initialAccountId = "" }: { initialAccountId?: string } = {}) {
  const [setup, setSetup] = useState<Setup>({ status: "loading" });
  const [accountId, setAccountId] = useState("");
  // Filtros do histórico: só leitura, não mudam nada no backend.
  const [assetFilter, setAssetFilter] = useState("");
  const [showExcluded, setShowExcluded] = useState(false);
  const [history, setHistory] = useState<HistoryState>({ status: "idle" });
  // Lançamento aberto no formulário de correção (um por vez).
  const [correcting, setCorrecting] = useState<TransactionRead | null>(null);

  // O histórico é sempre o que o backend devolve — depois de lançar,
  // busca de novo em vez de inserir a linha localmente.
  const loadHistory = useCallback((id: string) => {
    return getAccountTransactions(id)
      .then((transactions) => setHistory({ status: "ready", transactions }))
      .catch((err: Error) => setHistory({ status: "error", message: err.message }));
  }, []);

  useEffect(() => {
    Promise.all([getAccounts(), getAssets(), getCurrencies()])
      .then(([accounts, assets, currencies]) => {
        const investment = investmentAccounts(accounts);
        setSetup({ status: "ready", accounts: investment, assets, currencies });
        // Abre direto numa conta: a que veio de outra tela, ou a única que existe.
        const preferred = investment.some((a) => a.id === initialAccountId)
          ? initialAccountId
          : investment.length === 1
            ? investment[0].id
            : "";
        if (preferred !== "") {
          setAccountId(preferred);
          setHistory({ status: "loading" });
          void loadHistory(preferred);
        }
      })
      .catch((err: Error) => setSetup({ status: "error", message: err.message }));
  }, [initialAccountId, loadHistory]);

  function selectAccount(id: string) {
    setAccountId(id);
    setAssetFilter("");
    setCorrecting(null);
    if (id === "") {
      setHistory({ status: "idle" });
      return;
    }
    setHistory({ status: "loading" });
    void loadHistory(id);
  }

  if (setup.status === "loading") {
    return (
      <p className="text-neutral-400" role="status">
        Carregando…
      </p>
    );
  }
  if (setup.status === "error") {
    return (
      <p className="text-red-400" role="alert">
        Não foi possível carregar contas e ativos: {setup.message}
      </p>
    );
  }
  if (setup.accounts.length === 0) {
    return (
      <p className="text-neutral-400" data-testid="no-accounts">
        Nenhuma conta cadastrada. Crie uma conta em Cadastros antes de lançar operações.
      </p>
    );
  }

  const account = setup.accounts.find((item) => item.id === accountId);

  return (
    <div className="space-y-6">
      <div className={PANEL_CLASS}>
        <label className="mb-1 block text-xs text-neutral-400" htmlFor="tx-account">
          Conta
        </label>
        <select
          id="tx-account"
          className={`${INPUT_CLASS} max-w-md`}
          value={accountId}
          onChange={(event) => selectAccount(event.target.value)}
        >
          <option value="">Selecione uma conta…</option>
          {setup.accounts.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} — {item.institution_name} ({item.currency_code})
            </option>
          ))}
        </select>
      </div>

      {account && (
        <>
          <div className={PANEL_CLASS}>
            <h2 className="mb-3 text-[15px] font-semibold tracking-tight text-neutral-100">
              {correcting ? "Editar lançamento" : "Novo lançamento"}
            </h2>
            {/* `key` por conta e por lançamento em correção: trocar qualquer um zera o formulário. */}
            <TransactionForm
              key={`${account.id}:${correcting?.id ?? "novo"}`}
              account={account}
              assets={setup.assets}
              currencies={setup.currencies}
              correcting={correcting ?? undefined}
              onCancelCorrection={() => setCorrecting(null)}
              onCreated={() => {
                setCorrecting(null);
                void loadHistory(account.id);
              }}
            />
          </div>

          <div className={PANEL_CLASS}>
            <h2 className="mb-3 text-[15px] font-semibold tracking-tight text-neutral-100">Histórico da conta</h2>
            {history.status === "loading" && (
              <p className="text-neutral-400" role="status">
                Carregando histórico…
              </p>
            )}
            {history.status === "error" && (
              <p className="text-red-400" role="alert">
                Não foi possível carregar o histórico: {history.message}
              </p>
            )}
            {history.status === "ready" && history.transactions.length > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
                <label className="flex items-center gap-2 text-neutral-400" htmlFor="tx-asset-filter">
                  Filtrar por ativo
                  <select
                    id="tx-asset-filter"
                    className={COMPACT_INPUT_CLASS}
                    value={assetFilter}
                    onChange={(event) => setAssetFilter(event.target.value)}
                  >
                    <option value="">Todos</option>
                    {setup.assets
                      .filter((asset) => history.transactions.some((t) => t.asset_id === asset.id))
                      .map((asset) => (
                        <option key={asset.id} value={asset.id}>
                          {asset.ticker}
                        </option>
                      ))}
                  </select>
                </label>
                <label className="flex items-center gap-2 text-neutral-400">
                  <input type="checkbox" checked={showExcluded} onChange={(event) => setShowExcluded(event.target.checked)} />
                  Mostrar excluídos
                </label>
              </div>
            )}
            {history.status === "ready" && (
              <TransactionHistory
                transactions={history.transactions.filter(
                  (t) => (assetFilter === "" || t.asset_id === assetFilter) && (showExcluded || t.status !== "REVERSED"),
                )}
                assets={setup.assets}
                onCorrect={setCorrecting}
                onReversed={() => {
                  setCorrecting(null);
                  void loadHistory(account.id);
                }}
              />
            )}
          </div>
        </>
      )}

      <div className={PANEL_CLASS}>
        <h2 className="mb-1 text-[15px] font-semibold tracking-tight text-neutral-100">Transferência entre contas</h2>
        <p className="mb-3 text-xs text-neutral-500">
          Move dinheiro entre duas contas suas da mesma moeda. Não é aporte nem retirada no consolidado.
        </p>
        <TransferForm
          accounts={setup.accounts}
          onCreated={() => {
            if (accountId !== "") void loadHistory(accountId);
          }}
        />
      </div>
    </div>
  );
}
