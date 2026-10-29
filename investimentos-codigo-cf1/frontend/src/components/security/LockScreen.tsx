import { useState } from "react";

import type { AuthStatus } from "../../api/auth";
import { registerThisDevice, unlock } from "../../api/auth";
import { describeAuthError } from "../../lib/authErrors";

function FaceIdGlyph() {
  // Cantos de moldura + rosto simples: o desenho que o iOS usa para Face ID.
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 8V5.5A2.5 2.5 0 0 1 5.5 3H8M16 3h2.5A2.5 2.5 0 0 1 21 5.5V8M21 16v2.5a2.5 2.5 0 0 1-2.5 2.5H16M8 21H5.5A2.5 2.5 0 0 1 3 18.5V16M9 9v1.5M15 9v1.5M12 9v4.5h-1M9.5 16.5c1.5 1 3.5 1 5 0"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const PRIMARY =
  "flex h-[50px] w-full items-center justify-center gap-2 rounded-2xl bg-sky-400 text-[17px] font-semibold text-neutral-950 transition-opacity active:opacity-70 disabled:opacity-50";

/**
 * Trava do celular, no jeito do iOS: ícone, nome, um botão grande de
 * Face ID. Sem aparelho cadastrado, vira o cadastro com o código que o
 * computador gera.
 */
export function LockScreen({ status, onUnlocked }: { status: AuthStatus; onUnlocked: (s: AuthStatus) => void }) {
  const [mode, setMode] = useState<"unlock" | "register">(status.has_passkeys ? "unlock" : "register");
  const [code, setCode] = useState("");
  const [name, setName] = useState("iPhone");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<AuthStatus>) {
    setBusy(true);
    setError(null);
    try {
      onUnlocked(await action());
    } catch (err: unknown) {
      setError(describeAuthError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main
      className="flex min-h-[100dvh] flex-col items-center justify-between bg-neutral-950 px-6 pb-[max(2rem,env(safe-area-inset-bottom))] pt-[18vh] text-neutral-100"
      data-testid="lock-screen"
    >
      <div className="flex flex-col items-center text-center">
        <img src="/apple-touch-icon.png" alt="" width={76} height={76} className="rounded-[22%]" />
        <h1 className="mt-5 text-[22px] font-semibold tracking-tight">Dashboard Financeiro</h1>
        <p className="mt-1 text-[15px] text-neutral-400">
          {mode === "unlock" ? "Bloqueado" : "Cadastrar este aparelho"}
        </p>
      </div>

      <div className="w-full max-w-sm">
        {mode === "unlock" ? (
          <button type="button" className={PRIMARY} disabled={busy} onClick={() => void run(unlock)}>
            <FaceIdGlyph />
            {busy ? "Aguardando o Face ID…" : "Desbloquear com Face ID"}
          </button>
        ) : (
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              void run(() => registerThisDevice(code, name));
            }}
          >
            <p className="text-[15px] leading-relaxed text-neutral-400">
              No computador, abra <span className="text-neutral-200">Segurança</span> e toque em “Gerar código”. Digite
              o código aqui e confirme com Face ID.
            </p>
            <label className="block">
              <span className="sr-only">Código do computador</span>
              <input
                className="h-[50px] w-full rounded-2xl bg-neutral-900 px-4 text-center text-[22px] font-medium uppercase tracking-[0.2em] text-neutral-50 ring-1 ring-neutral-800 placeholder:text-neutral-600 focus:ring-sky-400"
                placeholder="XXXX-XXXX"
                autoComplete="one-time-code"
                autoCapitalize="characters"
                autoCorrect="off"
                spellCheck={false}
                maxLength={9}
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                aria-label="Código do computador"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[13px] text-neutral-400">Nome deste aparelho</span>
              <input
                className="h-11 w-full rounded-xl bg-neutral-900 px-4 text-[17px] text-neutral-100 ring-1 ring-neutral-800 focus:ring-sky-400"
                value={name}
                maxLength={60}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <button type="submit" className={PRIMARY} disabled={busy || code.replace(/[^A-Za-z0-9]/g, "").length < 8}>
              <FaceIdGlyph />
              {busy ? "Aguardando o Face ID…" : "Cadastrar com Face ID"}
            </button>
          </form>
        )}

        {error && (
          <p className="mt-3 text-center text-[15px] text-red-300" role="alert">
            {error}
          </p>
        )}

        {status.has_passkeys && (
          <button
            type="button"
            className="mt-4 h-11 w-full text-[15px] text-sky-300"
            onClick={() => {
              setMode(mode === "unlock" ? "register" : "unlock");
              setError(null);
            }}
          >
            {mode === "unlock" ? "Cadastrar outro aparelho" : "Já tenho cadastro: desbloquear"}
          </button>
        )}
        <p className="mt-4 text-center text-[13px] leading-snug text-neutral-500">
          Acesso só pela sua rede Tailscale. Depois de {status.idle_minutes} min parado, pede o Face ID de novo.
        </p>
      </div>
    </main>
  );
}
