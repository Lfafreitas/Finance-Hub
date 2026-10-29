import { describeApiError } from "./apiErrors";

/** Mensagem do erro do Face ID/passkey para a tela. */
export function describeAuthError(err: unknown): string {
  if (err instanceof Error && err.name === "NotAllowedError") {
    return "Face ID cancelado ou o tempo acabou. Toque para tentar de novo.";
  }
  if (err instanceof Error && err.name === "InvalidStateError") {
    return "Este iPhone já está cadastrado. Use “Desbloquear com Face ID”.";
  }
  return describeApiError(err);
}
