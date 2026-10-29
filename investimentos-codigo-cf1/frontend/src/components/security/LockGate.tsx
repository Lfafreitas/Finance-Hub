import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";

import type { AuthStatus } from "../../api/auth";
import { getAuthStatus } from "../../api/auth";
import { LOCKED_EVENT } from "../../api/client";
import { LockScreen } from "./LockScreen";

/**
 * Porteiro do app. No computador não aparece. No celular (acesso pelo
 * Tailscale), nada é montado — nem buscado — antes do Face ID; quando a
 * sessão vence (15 min parado), a API responde 401 e a trava volta.
 * Ao ir para segundo plano, uma cortina esconde a tela (o iOS tira uma
 * foto dela para o seletor de apps).
 */
export function LockGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const [hidden, setHidden] = useState(false);

  const refresh = useCallback(() => {
    getAuthStatus()
      .then((next) => {
        setStatus(next);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener(LOCKED_EVENT, refresh);
    return () => window.removeEventListener(LOCKED_EVENT, refresh);
  }, [refresh]);

  const remote = status?.remote ?? false;
  useEffect(() => {
    if (!remote) return;
    function onVisibility() {
      const isHidden = document.visibilityState === "hidden";
      setHidden(isHidden);
      if (!isHidden) refresh(); // voltou: confere se a sessão ainda vale
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [remote, refresh]);

  // Backend fora do ar: o app mostra o aviso dele (BackendStatus).
  if (failed && status === null) return <>{children}</>;
  if (status === null) return <div className="min-h-[100dvh] bg-neutral-950" data-testid="lock-loading" />;
  if (status.remote && !status.unlocked) return <LockScreen status={status} onUnlocked={setStatus} />;
  return (
    <>
      {children}
      {hidden && (
        <div className="fixed inset-0 z-[100] bg-neutral-950" data-testid="privacy-curtain" aria-hidden="true" />
      )}
    </>
  );
}
