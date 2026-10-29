import { ApiError } from "../api/client";

/**
 * Mensagem legível para um erro de chamada à API: o detalhe que o
 * backend devolveu quando existe, senão uma frase por tipo de falha.
 */
export function describeApiError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Não foi possível falar com o servidor. Nada foi alterado.";
  }
  if (error.detail) return error.detail;
  if (error.status === 413) return "Arquivo maior que o limite aceito pelo servidor.";
  if (error.status === 422) return "Os dados enviados são inválidos.";
  return `Erro inesperado do servidor (${error.status}).`;
}
