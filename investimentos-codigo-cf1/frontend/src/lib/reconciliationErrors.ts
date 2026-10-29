// Tradução de erros da API de reconciliação para mensagens legíveis.

import { ApiError } from "../api/client";

/** Mensagem compreensível por status HTTP; o detalhe do backend, quando existe, vai junto. */
export function describeResolveError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Não foi possível falar com o servidor. Nada foi alterado — tente novamente.";
  }
  const detail = error.detail ? ` (${error.detail})` : "";
  switch (error.status) {
    case 400:
      return `O servidor recusou esta decisão: ela deixaria os dados inconsistentes${detail}. Nada foi alterado.`;
    case 404:
      return `Esta pendência não existe mais${detail}. Atualize a lista.`;
    case 409:
      return `Esta pendência já foi resolvida ou uma das transações já foi revertida${detail}. Atualize a lista.`;
    case 422:
      return `A requisição foi rejeitada como inválida${detail}. Nada foi alterado.`;
    default:
      return `Erro inesperado do servidor (${error.status})${detail}. Nada foi alterado.`;
  }
}

export function describeScanError(error: unknown): string {
  if (!(error instanceof ApiError)) return "Não foi possível falar com o servidor. Tente novamente.";
  const detail = error.detail ? ` (${error.detail})` : "";
  if (error.status === 404) return `A conta ou carteira escolhida não foi encontrada${detail}.`;
  if (error.status === 400 || error.status === 422) return `Escopo de busca inválido${detail}.`;
  return `Erro inesperado do servidor (${error.status})${detail}.`;
}
