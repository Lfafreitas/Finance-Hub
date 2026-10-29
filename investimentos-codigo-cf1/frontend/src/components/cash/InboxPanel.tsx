import { useCallback, useEffect, useState } from "react";

import { getInbox, processInbox } from "../../api/cashflow";
import type { InboxFileResult, InboxListing, InboxStatus } from "../../api/cashflowTypes";
import { describeApiError } from "../../lib/apiErrors";
import { describeInboxFile, plural } from "../../lib/inbox";
import { BUTTON_CLASS, PANEL_CLASS } from "../../lib/ui";
import { ErrorText } from "./shared";

const STATUS: Record<InboxStatus, { text: string; tone: string; mark: string }> = {
  IMPORTED: { text: "importado", tone: "text-emerald-300", mark: "✓" },
  NOTHING_NEW: { text: "nada novo", tone: "text-neutral-400", mark: "=" },
  REFUSED: { text: "recusado — ficou na pasta", tone: "text-red-400", mark: "✗" },
  NO_ACCOUNT: { text: "sem conta — ficou na pasta", tone: "text-amber-300", mark: "!" },
};

/**
 * Pasta Entrada: salve o extrato ou a fatura nessa pasta e clique em
 * "Carregar". Cada arquivo passa pelas mesmas conferências da prévia
 * abaixo; os aceitos vão para "importados", os recusados ficam.
 */
export function InboxPanel({ onLoaded }: { onLoaded: () => void }) {
  const [listing, setListing] = useState<InboxListing | null>(null);
  const [results, setResults] = useState<InboxFileResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    return getInbox()
      .then(setListing)
      .catch((err: unknown) => setError(describeApiError(err)));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleProcess() {
    setBusy(true);
    setError(null);
    try {
      const run = await processInbox();
      setResults(run.files);
      onLoaded();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
      void refresh();
    }
  }

  const waiting = listing?.files.length ?? 0;
  return (
    <div className={`${PANEL_CLASS} space-y-2`} data-testid="inbox-panel">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-[15px] font-semibold tracking-tight text-neutral-100">Pasta Entrada</h2>
        <span className="text-xs text-neutral-500" data-testid="inbox-count">
          {listing === null
            ? "…"
            : !listing.exists
              ? "a pasta ainda não existe"
              : waiting === 0
                ? "nenhum arquivo esperando"
                : plural(waiting, "arquivo esperando", "arquivos esperando")}
        </span>
        <button
          type="button"
          className={`${BUTTON_CLASS} ml-auto`}
          disabled={busy || waiting === 0}
          onClick={() => void handleProcess()}
        >
          {busy ? "Carregando…" : "Carregar a pasta Entrada"}
        </button>
      </div>
      <p className="text-xs text-neutral-500">
        Salve o extrato da conta (OFX ou CSV) ou a fatura do cartão (PDF, OFX ou CSV) do Nubank em{" "}
        <code className="break-all text-neutral-400">{listing?.inbox_dir ?? "…"}</code> e clique em carregar. Cada
        arquivo passa pelas mesmas conferências da prévia; o que já existe não entra de novo. Os aceitos vão para a
        subpasta “importados”.
      </p>
      {listing && waiting > 0 && results === null && (
        <ul className="text-xs text-neutral-400" data-testid="inbox-files">
          {listing.files.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      {results && (
        <ul className="space-y-1 text-sm" role="status" data-testid="inbox-results">
          {results.length === 0 && <li className="text-neutral-400">Nenhum arquivo na pasta.</li>}
          {results.map((file) => {
            const status = STATUS[file.status];
            return (
              <li key={file.file_name} data-testid={`inbox-result-${file.file_name}`}>
                <span className={status.tone}>
                  {status.mark} {file.file_name} — {status.text}
                </span>
                <span className="block text-xs text-neutral-500">{describeInboxFile(file)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
