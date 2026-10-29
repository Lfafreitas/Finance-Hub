import { type FormEvent, useEffect, useState } from "react";

import { commitImport, getAccounts, previewImport } from "../api/client";
import type { AccountRead, ImportCommitResult, ImportPreviewResponse, ImportSourceFormat } from "../api/types";
import { ImportPreviewTable } from "../components/ImportPreviewTable";
import { investmentAccounts } from "../lib/accountTypes";
import { describeApiError } from "../lib/apiErrors";
import { isRowSelectable } from "../lib/importRows";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS, PANEL_CLASS } from "../lib/ui";

const FORMATS: { value: ImportSourceFormat; label: string }[] = [
  { value: "CSV", label: "CSV" },
  { value: "XLSX", label: "Excel (XLSX)" },
  { value: "OFX", label: "OFX (extrato bancário)" },
];

type AccountsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; accounts: AccountRead[] };

function describeResult(result: ImportCommitResult): string {
  const imported =
    result.imported_count === 1 ? "1 transação importada" : `${result.imported_count} transações importadas`;
  const excluded =
    result.excluded_count === 0
      ? ""
      : result.excluded_count === 1
        ? "; 1 linha não incluída"
        : `; ${result.excluded_count} linhas não incluídas`;
  return `${imported}${excluded}. A checagem de reconciliação roda em seguida — confira a aba Reconciliação.`;
}

/**
 * Importação em duas etapas, como a API: (1) preview — nada é gravado;
 * (2) commit das linhas escolhidas — tudo ou nada.
 */
export function Import() {
  const [accountsState, setAccountsState] = useState<AccountsState>({ status: "loading" });
  const [accountId, setAccountId] = useState("");
  const [format, setFormat] = useState<ImportSourceFormat>("CSV");
  const [file, setFile] = useState<File | null>(null);
  // Trocar a `key` recria o campo de arquivo: depois de importar ele volta
  // vazio, e escolher o mesmo arquivo de novo dispara a leitura.
  const [fileInputKey, setFileInputKey] = useState(0);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
    getAccounts()
      .then((accounts) => setAccountsState({ status: "ready", accounts: investmentAccounts(accounts) }))
      .catch((err: Error) => setAccountsState({ status: "error", message: err.message }));
  }, []);

  /** Qualquer mudança de conta, formato ou arquivo invalida a preview anterior. */
  function resetPreview() {
    setPreview(null);
    setSelected(new Set());
    setError(null);
    setResult(null);
  }

  async function handlePreview(event: FormEvent) {
    event.preventDefault();
    if (file === null || accountId === "") return;
    setBusy(true);
    resetPreview();
    try {
      const response = await previewImport(accountId, format, file);
      setPreview(response);
      // Pré-seleção conservadora: só linhas sem erro, não duplicadas e
      // sem suspeita de duplicata. As suspeitas ficam para o usuário
      // marcar conscientemente.
      setSelected(
        new Set(
          response.rows
            .filter((row) => isRowSelectable(row) && !row.possible_duplicate)
            .map((row) => row.row_index),
        ),
      );
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

  async function handleCommit() {
    if (preview === null) return;
    setBusy(true);
    setError(null);
    try {
      const committed = await commitImport(
        preview,
        preview.rows.filter((row) => selected.has(row.row_index)).map((row) => row.row_index),
      );
      setResult(describeResult(committed));
      setPreview(null);
      setSelected(new Set());
      setFile(null);
      setFileInputKey((key) => key + 1);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  }

  if (accountsState.status === "loading") {
    return (
      <p className="text-neutral-400" role="status">
        Carregando…
      </p>
    );
  }
  if (accountsState.status === "error") {
    return (
      <p className="text-red-400" role="alert">
        Não foi possível carregar as contas: {accountsState.message}
      </p>
    );
  }
  if (accountsState.accounts.length === 0) {
    return (
      <p className="text-neutral-400" data-testid="no-accounts">
        Nenhuma conta cadastrada. Crie uma conta em Cadastros antes de importar.
      </p>
    );
  }

  const withError = preview ? preview.rows.filter((row) => row.error !== null).length : 0;
  const duplicates = preview ? preview.rows.filter((row) => row.is_exact_duplicate).length : 0;

  return (
    <div className="space-y-6">
      <form className={PANEL_CLASS} onSubmit={handlePreview} aria-label="Arquivo de importação">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <label className={LABEL_CLASS} htmlFor="import-account">
              Conta
            </label>
            <select
              id="import-account"
              className={INPUT_CLASS}
              value={accountId}
              disabled={busy}
              onChange={(event) => {
                setAccountId(event.target.value);
                resetPreview();
              }}
            >
              <option value="">Selecione…</option>
              {accountsState.accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name} — {account.institution_name} ({account.currency_code})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="import-format">
              Formato
            </label>
            <select
              id="import-format"
              className={INPUT_CLASS}
              value={format}
              disabled={busy}
              onChange={(event) => {
                setFormat(event.target.value as ImportSourceFormat);
                resetPreview();
              }}
            >
              {FORMATS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="import-file">
              Arquivo
            </label>
            <input
              key={fileInputKey}
              id="import-file"
              type="file"
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
          CSV e Excel: colunas data (AAAA-MM-DD), tipo, valor e, para operações com ativo, ativo, quantidade,
          preco_unitario, taxas e moeda. Sem a coluna moeda, a linha é lida como BRL.
        </p>

        <button type="submit" className={`${BUTTON_CLASS} mt-3`} disabled={busy || accountId === "" || file === null}>
          {busy && preview === null ? "Lendo arquivo…" : "Pré-visualizar"}
        </button>
      </form>

      {error && (
        <p className="text-sm text-red-400" role="alert">
          {error}
        </p>
      )}
      {result && (
        <p className="text-sm text-emerald-300" role="status" data-testid="import-result">
          {result}
        </p>
      )}

      {preview && (
        <div className={PANEL_CLASS}>
          <h2 className="mb-1 text-[15px] font-semibold tracking-tight text-neutral-100">Pré-visualização — nada foi gravado ainda</h2>
          <p className="mb-3 text-xs text-neutral-500" data-testid="import-summary">
            {preview.rows.length} linhas no arquivo · {selected.size} selecionadas · {withError} com erro ·{" "}
            {duplicates} já importadas
          </p>
          <ImportPreviewTable rows={preview.rows} selected={selected} onToggle={toggle} disabled={busy} />
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
    </div>
  );
}
