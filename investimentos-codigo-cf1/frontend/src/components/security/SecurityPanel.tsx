import { useEffect, useState } from "react";

import type { AuthStatus, PasskeyRead } from "../../api/auth";
import {
  createPairingCode,
  deletePasskey,
  getAuthStatus,
  getPasskeys,
  lockNow,
  revokeAllSessions,
} from "../../api/auth";
import { LOCKED_EVENT } from "../../api/client";
import { describeApiError } from "../../lib/apiErrors";
import { formatRefreshTime } from "../../lib/analytics";
import { BUTTON_CLASS, PANEL_CLASS, SECTION_TITLE_CLASS } from "../../lib/ui";

/** "21:55" */
function timeOf(iso: string): string {
  const when = new Date(iso);
  return `${String(when.getHours()).padStart(2, "0")}:${String(when.getMinutes()).padStart(2, "0")}`;
}

/**
 * Segurança do acesso pelo celular. No computador: gerar o código para
 * cadastrar um iPhone, ver e remover aparelhos e bloquear todos. No
 * celular: só "Bloquear agora" (aparelhos e códigos ficam no computador).
 */
export function SecurityPanel() {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [keys, setKeys] = useState<PasskeyRead[]>([]);
  const [pairing, setPairing] = useState<{ code: string; expires_at: string } | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    getAuthStatus()
      .then((s) => {
        setStatus(s);
        if (!s.remote) return getPasskeys().then(setKeys);
      })
      .catch((err: unknown) => setError(describeApiError(err)));
  }

  useEffect(load, []);

  async function act(action: () => Promise<unknown>, done?: string) {
    setError(null);
    setMessage(null);
    try {
      await action();
      if (done) setMessage(done);
      load();
    } catch (err: unknown) {
      setError(describeApiError(err));
    }
  }

  if (status === null) return null;

  if (status.remote) {
    return (
      <section className={`${PANEL_CLASS} space-y-3`} data-testid="security-remote">
        <p className="text-sm leading-relaxed text-neutral-300">
          Você está no celular, protegido por Face ID. Depois de {status.idle_minutes} min parado, ele pede de novo.
          Cadastrar ou remover aparelhos só pelo computador.
        </p>
        <button
          type="button"
          className={BUTTON_CLASS}
          onClick={() => void lockNow().finally(() => window.dispatchEvent(new Event(LOCKED_EVENT)))}
        >
          Bloquear agora
        </button>
      </section>
    );
  }

  return (
    <div className="space-y-8" data-testid="security">
      <section aria-labelledby="pair-title">
        <h2 id="pair-title" className={`mb-3 ${SECTION_TITLE_CLASS}`}>
          Cadastrar um iPhone
        </h2>
        <div className={`${PANEL_CLASS} space-y-4`}>
          <p className="max-w-2xl text-sm leading-relaxed text-neutral-400">
            O celular entra pela sua rede Tailscale e só mostra os dados depois do Face ID. Para cadastrar um aparelho,
            gere um código aqui, abra o dashboard no iPhone e digite o código. Vale por 10 minutos, para um aparelho só,
            e bloqueia depois de 5 tentativas erradas.
          </p>
          {pairing ? (
            <div data-testid="pairing-code">
              <p className="figure-hero text-[2.5rem] tracking-[0.15em] text-neutral-50">{pairing.code}</p>
              <p className="text-xs text-neutral-500">Vale até {timeOf(pairing.expires_at)}.</p>
            </div>
          ) : null}
          <button
            type="button"
            className={BUTTON_CLASS}
            onClick={() => void act(async () => setPairing(await createPairingCode()))}
          >
            {pairing ? "Gerar outro código" : "Gerar código"}
          </button>
        </div>
      </section>

      <section aria-labelledby="devices-title">
        <h2 id="devices-title" className={`mb-3 ${SECTION_TITLE_CLASS}`}>
          Aparelhos com acesso
        </h2>
        <div className={PANEL_CLASS}>
          {keys.length === 0 ? (
            <p className="text-sm text-neutral-400" data-testid="no-devices">
              Nenhum aparelho cadastrado: pelo celular, o dashboard fica bloqueado até você cadastrar um.
            </p>
          ) : (
            <ul className="divide-y divide-neutral-800">
              {keys.map((key) => (
                <li
                  key={key.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                  data-testid="device"
                >
                  <div>
                    <p className="text-sm text-neutral-100">{key.name}</p>
                    <p className="text-xs text-neutral-500">
                      {key.rp_id} · cadastrado {formatRefreshTime(key.created_at)}
                      {key.last_used_at ? ` · último uso ${formatRefreshTime(key.last_used_at)}` : " · nunca usado"}
                    </p>
                  </div>
                  {confirming === key.id ? (
                    <span className="flex gap-2">
                      <button
                        type="button"
                        className={`${BUTTON_CLASS} border-red-400/60 text-red-300`}
                        onClick={() =>
                          void act(() => deletePasskey(key.id), `${key.name} removido.`).then(() => setConfirming(null))
                        }
                      >
                        Remover de vez
                      </button>
                      <button type="button" className={BUTTON_CLASS} onClick={() => setConfirming(null)}>
                        Cancelar
                      </button>
                    </span>
                  ) : (
                    <button type="button" className={BUTTON_CLASS} onClick={() => setConfirming(key.id)}>
                      Remover
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4 border-t border-neutral-800 pt-4">
            <button
              type="button"
              className={BUTTON_CLASS}
              onClick={() =>
                void act(async () => {
                  const { revoked } = await revokeAllSessions();
                  setMessage(
                    revoked > 0
                      ? `Bloqueado em ${revoked} sessão(ões): o celular pede Face ID de novo.`
                      : "Nenhum aparelho estava desbloqueado.",
                  );
                })
              }
            >
              Bloquear todos os aparelhos agora
            </button>
            <p className="mt-2 text-xs text-neutral-500">
              Perdeu o iPhone? Remova o aparelho aqui e, no app do Tailscale, desconecte-o da sua rede.
            </p>
          </div>
        </div>
      </section>

      {message && (
        <p className="text-sm text-emerald-300" role="status">
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
