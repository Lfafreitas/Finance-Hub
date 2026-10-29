import { useState } from "react";

import { describeApiError } from "../../lib/apiErrors";

export const SMALL_BUTTON_CLASS =
  "rounded border border-neutral-700 px-2 py-0.5 text-xs text-neutral-200 hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40";

export function Loading() {
  return (
    <p className="text-neutral-400" role="status">
      Carregando…
    </p>
  );
}

export function ErrorText({ children }: { children: string }) {
  return (
    <p className="text-sm text-red-400" role="alert">
      {children}
    </p>
  );
}

interface ConfirmButtonProps {
  /** Rótulo do botão e do pedido de confirmação. */
  label: string;
  confirmLabel: string;
  /** Texto para leitores de tela distinguirem as linhas. */
  ariaLabel: string;
  /** Executa a ação; lança em caso de erro. */
  onConfirm: () => Promise<void>;
  disabled?: boolean;
}

/**
 * Ação que pede uma segunda confirmação no próprio lugar. A recusa do
 * backend aparece ao lado, com o motivo que ele devolveu.
 */
export function ConfirmButton({ label, confirmLabel, ariaLabel, onConfirm, disabled = false }: ConfirmButtonProps) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      setAsking(false);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  }

  if (!asking) {
    return (
      <button
        type="button"
        className={SMALL_BUTTON_CLASS}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => {
          setError(null);
          setAsking(true);
        }}
      >
        {label}
      </button>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <button type="button" className={`${SMALL_BUTTON_CLASS} border-red-800 text-red-300`} disabled={busy} onClick={run}>
        {busy ? "Aguarde…" : confirmLabel}
      </button>
      <button type="button" className={SMALL_BUTTON_CLASS} disabled={busy} onClick={() => setAsking(false)}>
        Cancelar
      </button>
      {error && (
        <span className="text-xs text-red-400" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}
