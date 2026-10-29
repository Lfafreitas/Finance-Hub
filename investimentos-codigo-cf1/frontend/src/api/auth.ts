// Trava do acesso remoto (Face ID no celular). O backend decide quem é
// remoto; aqui só o diálogo com o WebAuthn do navegador.

import type {
  PublicKeyCredentialCreationOptionsJSON,
  PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser";
import { startAuthentication, startRegistration } from "@simplewebauthn/browser";

import { request } from "./client";

export interface AuthStatus {
  remote: boolean;
  unlocked: boolean;
  has_passkeys: boolean;
  idle_minutes: number;
}

export interface PasskeyRead {
  id: string;
  name: string;
  rp_id: string;
  created_at: string;
  last_used_at: string | null;
}

export function getAuthStatus(): Promise<AuthStatus> {
  return request<AuthStatus>("/auth/status");
}

/** Cadastra este aparelho: código gerado no computador + Face ID. */
export async function registerThisDevice(code: string, name: string): Promise<AuthStatus> {
  const { challenge_id, options } = await request<{ challenge_id: string; options: unknown }>(
    "/auth/register/options",
    { method: "POST", body: { code } },
  );
  const credential = await startRegistration({ optionsJSON: options as PublicKeyCredentialCreationOptionsJSON });
  return request<AuthStatus>("/auth/register/verify", {
    method: "POST",
    body: { challenge_id, code, name, credential },
  });
}

/** Desbloqueia com Face ID. */
export async function unlock(): Promise<AuthStatus> {
  const { challenge_id, options } = await request<{ challenge_id: string; options: unknown }>("/auth/login/options", {
    method: "POST",
  });
  const credential = await startAuthentication({ optionsJSON: options as PublicKeyCredentialRequestOptionsJSON });
  return request<AuthStatus>("/auth/login/verify", { method: "POST", body: { challenge_id, credential } });
}

export function lockNow(): Promise<void> {
  return request<void>("/auth/logout", { method: "POST" });
}

// --- Só pelo computador ------------------------------------------------------------

export function createPairingCode(): Promise<{ code: string; expires_at: string }> {
  return request<{ code: string; expires_at: string }>("/auth/pairing", { method: "POST" });
}

export function getPasskeys(): Promise<PasskeyRead[]> {
  return request<PasskeyRead[]>("/auth/passkeys");
}

export function deletePasskey(id: string): Promise<void> {
  return request<void>(`/auth/passkeys/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function revokeAllSessions(): Promise<{ revoked: number }> {
  return request<{ revoked: number }>("/auth/sessions/revoke-all", { method: "POST" });
}
