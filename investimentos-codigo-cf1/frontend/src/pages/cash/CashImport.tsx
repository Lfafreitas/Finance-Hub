import { type FormEvent, useCallback, useEffect, useState } from "react";

import {
  commitCashImport,
  countCashEntries,
  getCashImportBatches,
  getCategories,
  previewCashImport,
} from "../../api/cashflow";
import type {
  CashflowImportBatchRead,
  CashflowImportCommitResult,
  CashflowImportPreview,
  CashflowImportProfile,
  CashflowImportRow,
  CategoryRead,
} from "../../api/cashflowTypes";
import { getAccounts } from "../../api/client";
import type { AccountRead } from "../../api/types";
import { InboxPanel } from "../../components/cash/InboxPanel";
import { ErrorText, Loading } from "../../components/cash/shared";
import { ACCOUNT_TYPE_LABELS } from "../../lib/accountTypes";
import { describeApiError } from "../../lib/apiErrors";
import {
  IMPORT_PROFILE_LABELS,
  NATURE_LABELS,
  cashAccounts,
  categoryLabel,
  isCashRowImportable,
} from "../../lib/cashflow";
import { formatCurrency, formatIsoDate } from "../../lib/formatCurrency";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS, PANEL_CLASS } from "../../lib/ui";

const PROFILES = Object.keys(IMPORT_PROFILE_LABELS) as CashflowImportProfile[];

interface Lookups {
  accounts: AccountRead[];
  categories: CategoryRead[];
  batches: CashflowImportBatchRead[];
}

type State = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: Lookups };

function situation(row: CashflowImportRow): { text: string; tone: string } {
  if (row.error !== null) return { text: row.error, tone: "text-red-400" };
  if (row.is_duplicate) return { text: "Já importada nesta conta", tone: "text-neutral-500" };
  return { text: "Pronta para importar", tone: "text-emerald-300" };
}

function plural(count: number, one: string, many: string): string {
  return count === 1 ? `1 ${one}` : `${count} ${many}`;
}

/**
 * Importação do extrato ou da fatura em duas etapas: (1) prévia — nada
 * é gravado; (2) confirmação das linhas escolhidas — tudo ou nada.
 */
export function CashImport() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [accountId, setAccountId] = useState("");
  const [profile, setProfile] = useState<"" | CashflowImportProfile>("");
  const [file, setFile] = useState<File | null>(null);
  // Trocar a `key` recria o campo de arquivo: depois de importar ele volta
  // vazio, e escolher o mesmo arquivo de novo dispara a leitura.
  const [fileInputKey, setFileInputKey] = useState(0);
  const [preview, setPreview] = useState<CashflowImportPreview | null>(null);
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
  /** A conta escolhida ainda não tem nenhum lançamento (nem estornado). */
  const [accountIsEmpty, setAccountIsEmpty] = useState(false);
  const [openingBalance, setOpeningBalance] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CashflowImportCommitResult | null>(null);

  const load = useCallback(
    () =>
      Promise.all([getAccounts(), getCategories(), getCashImportBatches()])
        .then(([accounts, categories, batches]) =>
          setState({ status: "ready", data: { accounts: cashAccounts(accounts), categories, batches } }),
        )
        .catch((err: unknown) => setState({ status: "error", message: describeApiError(err) })),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  /** Qualquer mudança de conta, formato ou arquivo invalida a prévia anterior. */
  function resetPreview() {
    setPreview(null);
    setSelected(new Set());
    setOpeningBalance(false);
    setError(null);
    setResult(null);
  }

  async function handlePreview(event: FormEvent) {
    event.preventDefault();
    if (file === null || accountId === "") return;
    setBusy(true);
    resetPreview();
    try {
      const [response, count] = await Promise.all([
        previewCashImport(accountId, file, profile === "" ? null : profile),
        countCashEntries({ account_id: accountId, include_reversed: true }),
      ]);
      const empty = count.total === 0;
      setPreview(response);
      setSelected(new Set(response.rows.filter(isCashRowImportable).map((row) => row.row_index)));
      setAccountIsEmpty(empty);
      // Primeira importação de um arquivo que informa o saldo: propõe o
      // saldo inicial, que é o que faz a conta bater com o banco.
      setOpeningBalance(empty && response.statement_balance !== null);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  }

  function toggle(rowIndex: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(rowIndex)) next.delete(rowIndex);
      else next.add(rowIndex);
      return next;
    });
  }

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") {
    return <ErrorText>{`Não foi possível carregar as contas: ${state.message}`}</ErrorText>;
  }
  const { accounts, categories, batches } = state.data;
  if (accounts.length === 0) {
    return (
      <p className="text-neutral-400" data-testid="no-cash-accounts">
        Nenhuma conta de caixa cadastrada. Crie em Cadastros uma conta do tipo corrente, reserva, cartão ou dinheiro.
      </p>
    );
  }

  const account = accounts.find((item) => item.id === accountId);
  const currency = account?.currency_code ?? "BRL";
  const accountName = (id: string) => accounts.find((item) => item.id === id)?.name ?? "—";

  const importable = preview ? preview.rows.filter(isCashRowImportable) : [];
  const withError = preview ? preview.rows.filter((row) => row.error !== null).length : 0;
  const duplicates = preview ? preview.rows.filter((row) => row.is_duplicate).length : 0;
  // O saldo inicial só fecha se o arquivo entrar inteiro.
  const allIncluded = importable.every((row) => selected.has(row.row_index));
  const openingOffered = preview !== null && preview.statement_balance !== null && accountIsEmpty;
  const openingActive = openingOffered && openingBalance && allIncluded;

  async function handleCommit() {
    if (preview === null) return;
    setBusy(true);
    setError(null);
    try {
      const committed = await commitCashImport(
        preview,
        preview.rows.filter((row) => selected.has(row.row_index)).map((row) => row.row_index),
        openingActive,
      );
      setResult(committed);
      setPreview(null);
      setSelected(new Set());
      setFile(null);
      setFileInputKey((key) => key + 1);
      await load();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <InboxPanel onLoaded={() => void load()} />
      <form className={PANEL_CLASS} onSubmit={handlePreview} aria-label="Arquivo do banco">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <label className={LABEL_CLASS} htmlFor="ci-account">
              Conta
            </label>
            <select
              id="ci-account"
              className={INPUT_CLASS}
              value={accountId}
              disabled={busy}
              onChange={(event) => {
                setAccountId(event.target.value);
                resetPreview();
              }}
            >
              <option value="">Selecione…</option>
              {accounts.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} — {ACCOUNT_TYPE_LABELS[item.account_type]} ({item.currency_code})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="ci-profile">
              Formato
            </label>
            <select
              id="ci-profile"
              className={INPUT_CLASS}
              value={profile}
              disabled={busy}
              onChange={(event) => {
                setProfile(event.target.value as "" | CashflowImportProfile);
                resetPreview();
              }}
            >
              <option value="">Detectar pelo arquivo</option>
              {PROFILES.map((item) => (
                <option key={item} value={item}>
                  {IMPORT_PROFILE_LABELS[item]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="ci-file">
              Arquivo
            </label>
            <input
              key={fileInputKey}
              id="ci-file"
              type="file"
              accept=".csv,.ofx,.pdf"
              className={INPUT_CLASS}
              disabled={busy}
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                resetPreview();
              }}
            />
          </div>
        </div>
        <p className="mt-3 text-xs text-neutral-500">
          Extrato da conta: use o OFX quando puder — ele informa o saldo, e o sistema confere se a conta bate com o
          banco. Fatura do cartão: o PDF da fatura fechada é conferido com o resumo dela (compras e pagamentos) antes
          de qualquer coisa ser gravada. O arquivo não é guardado; fica só o nome e a impressão digital dele.
        </p>
        <button type="submit" className={`${BUTTON_CLASS} mt-3`} disabled={busy || accountId === "" || file === null}>
          {busy && preview === null ? "Lendo arquivo…" : "Pré-visualizar"}
        </button>
      </form>

      {error && <ErrorText>{error}</ErrorText>}

      {result && (
        <div className={`${PANEL_CLASS} space-y-1 text-sm`} role="status" data-testid="cash-import-result">
          <p className="text-emerald-300">
            {plural(result.imported_count, "lançamento importado", "lançamentos importados")}
            {result.not_included_count > 0 &&
              ` · ${plural(result.not_included_count, "linha não incluída", "linhas não incluídas")}`}
            .
          </p>
          {result.opening_adjustment !== null && (
            <p data-testid="result-opening">
              Saldo inicial criado: {formatCurrency(result.opening_adjustment, currency)}.
            </p>
          )}
          <p data-testid="result-rules">
            {plural(result.rules_applied_count, "lançamento classificado por regra", "lançamentos classificados por regra")}
            {" · "}
            {plural(result.matched_transfers.length, "pagamento de fatura casado", "pagamentos de fatura casados")}.
          </p>
          {result.balance_difference !== null && result.system_balance !== null && result.statement_balance !== null && (
            <p
              data-testid="result-balance"
              className={Number(result.balance_difference) === 0 ? "text-emerald-300" : "text-amber-300"}
            >
              {Number(result.balance_difference) === 0
                ? `Saldo conferido: ${formatCurrency(result.system_balance, currency)} no sistema e no banco.`
                : `Saldo não bate: ${formatCurrency(result.system_balance, currency)} no sistema, ${formatCurrency(
                    result.statement_balance,
                    currency,
                  )} no banco (diferença de ${formatCurrency(result.balance_difference, currency)}).`}
            </p>
          )}
        </div>
      )}

      {preview && (
        <div className={PANEL_CLASS}>
          <h2 className="mb-1 text-[15px] font-semibold tracking-tight text-neutral-100">Prévia — nada foi gravado ainda</h2>
          <p className="mb-1 text-xs text-neutral-500" data-testid="cash-import-summary">
            {IMPORT_PROFILE_LABELS[preview.profile]} · {preview.rows.length} linhas · {selected.size} selecionadas ·{" "}
            {withError} com erro · {duplicates} já importadas
          </p>
          {preview.period_start && preview.period_end && (
            <p className="mb-1 text-xs text-neutral-500">
              Período: {formatIsoDate(preview.period_start)} a {formatIsoDate(preview.period_end)}
              {preview.statement_balance !== null &&
                preview.statement_balance_date !== null &&
                ` · saldo informado pelo banco em ${formatIsoDate(preview.statement_balance_date)}: ${formatCurrency(
                  preview.statement_balance,
                  currency,
                )}`}
            </p>
          )}
          {preview.statement_due_date && (
            <p className="mb-1 text-xs text-neutral-500" data-testid="cash-import-invoice">
              Fatura com vencimento em {formatIsoDate(preview.statement_due_date)}
              {preview.statement_total != null && ` · total a pagar ${formatCurrency(preview.statement_total, currency)}`}
            </p>
          )}
          {preview.checks && preview.checks.length > 0 && (
            <ul className="mb-2 space-y-0.5 text-xs" data-testid="cash-import-checks">
              {preview.checks.map((check) => (
                <li key={check.label} className={check.ok ? "text-emerald-300" : "text-red-400"}>
                  {check.ok ? "✓" : "✗"} {check.label}: {formatCurrency(check.found, currency)} lidos
                  {check.ok ? " = " : " ≠ "}
                  {formatCurrency(check.expected, currency)} no resumo da fatura
                </li>
              ))}
            </ul>
          )}
          {preview.file_already_imported && (
            <p className="mb-2 text-sm text-amber-300" data-testid="file-already-imported">
              Este mesmo arquivo já foi importado nesta conta. As linhas repetidas estão marcadas e não entram de novo.
            </p>
          )}

          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm" data-testid="cash-import-table">
              <thead>
                <tr className="border-b border-neutral-800 text-neutral-400">
                  <th className="py-2 pr-3">Incluir</th>
                  <th className="py-2 pr-3">Data</th>
                  <th className="py-2 pr-3">Descrição</th>
                  <th className="py-2 pr-3 text-right">Valor</th>
                  <th className="py-2 pr-3">Regra que classificaria</th>
                  <th className="py-2">Situação</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => {
                  const selectable = isCashRowImportable(row);
                  const status = situation(row);
                  const category = categoryLabel(categories, row.suggested_category_id);
                  return (
                    <tr
                      key={row.row_index}
                      data-testid={`cash-import-row-${row.row_index}`}
                      className={`border-b border-neutral-900 align-top ${selectable ? "" : "text-neutral-500"}`}
                    >
                      <td className="py-2 pr-3">
                        <input
                          type="checkbox"
                          aria-label={`Incluir linha ${row.row_index + 1}`}
                          checked={selected.has(row.row_index)}
                          disabled={busy || !selectable}
                          onChange={() => toggle(row.row_index)}
                        />
                      </td>
                      <td className="py-2 pr-3 whitespace-nowrap">{row.entry_date ? formatIsoDate(row.entry_date) : "—"}</td>
                      <td className="py-2 pr-3">{row.description}</td>
                      <td className="py-2 pr-3 text-right whitespace-nowrap tabular-nums">
                        {row.amount !== null ? formatCurrency(row.amount, currency) : "—"}
                      </td>
                      <td className="py-2 pr-3">
                        {row.suggested_nature !== null ? (
                          <>
                            {NATURE_LABELS[row.suggested_nature]}
                            {category && ` · ${category}`}
                            <span className="block text-xs text-neutral-500">{row.suggested_rule_name}</span>
                          </>
                        ) : (
                          <span className="text-neutral-500">nenhuma</span>
                        )}
                      </td>
                      <td className={`py-2 ${status.tone}`}>{status.text}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {openingOffered && (
            <div className="mt-3 text-sm">
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={openingActive}
                  disabled={busy || !allIncluded}
                  onChange={(event) => setOpeningBalance(event.target.checked)}
                />
                Criar o saldo inicial desta conta
              </label>
              <p className="mt-1 text-xs text-neutral-500" data-testid="opening-hint">
                {allIncluded
                  ? "É a primeira importação desta conta: o sistema calcula o saldo que ela tinha antes do arquivo, para o saldo final bater com o do banco."
                  : "Para criar o saldo inicial, todas as linhas válidas do arquivo precisam estar selecionadas."}
              </p>
            </div>
          )}

          <p className="mt-3 text-xs text-neutral-500">
            A importação é tudo ou nada: se uma linha selecionada for recusada, nenhuma é gravada.
          </p>
          <button
            type="button"
            className={`${BUTTON_CLASS} mt-3`}
            disabled={busy || selected.size === 0}
            onClick={handleCommit}
          >
            {busy ? "Importando…" : `Importar ${selected.size} selecionada${selected.size === 1 ? "" : "s"}`}
          </button>
        </div>
      )}

      <div className={PANEL_CLASS}>
        <h2 className="mb-3 text-[15px] font-semibold tracking-tight text-neutral-100">Arquivos já importados</h2>
        {batches.length === 0 ? (
          <p className="text-sm text-neutral-500">Nenhuma importação ainda.</p>
        ) : (
          <table className="w-full text-left text-sm" data-testid="cash-import-batches">
            <thead>
              <tr className="border-b border-neutral-800 text-neutral-400">
                <th className="py-2 pr-3">Importado em</th>
                <th className="py-2 pr-3">Conta</th>
                <th className="py-2 pr-3">Arquivo</th>
                <th className="py-2 pr-3">Período</th>
                <th className="py-2">Linhas</th>
              </tr>
            </thead>
            <tbody>
              {batches.map((batch) => (
                <tr key={batch.id} className="border-b border-neutral-900">
                  <td className="py-2 pr-3 whitespace-nowrap">{formatIsoDate(batch.created_at.slice(0, 10))}</td>
                  <td className="py-2 pr-3">{accountName(batch.account_id)}</td>
                  <td className="py-2 pr-3">{batch.file_name}</td>
                  <td className="py-2 pr-3 whitespace-nowrap">
                    {batch.period_start && batch.period_end
                      ? `${formatIsoDate(batch.period_start)} a ${formatIsoDate(batch.period_end)}`
                      : "—"}
                  </td>
                  <td className="py-2">
                    {batch.rows_imported} de {batch.rows_total}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
