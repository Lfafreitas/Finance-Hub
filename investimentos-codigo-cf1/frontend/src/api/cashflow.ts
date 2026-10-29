// Chamadas do controle financeiro (rotas /cashflow). Separado de
// `client.ts` para os dois livros não se misturarem também aqui.

import { request } from "./client";
import type {
  CashflowBalances,
  CashflowEntryCorrect,
  CashflowEntryCreate,
  CashflowEntryFilters,
  CashflowEntryRead,
  CashflowImportBatchRead,
  CashflowImportCommitResult,
  CashflowImportPreview,
  CashflowImportProfile,
  CashflowSummary,
  CashflowTransferCreate,
  CashflowTransferLinkResult,
  CashflowTransferMatchResult,
  CashflowTransferRead,
  CategoryBreakdown,
  CategoryRead,
  CategoryWrite,
  EntryClassificationWrite,
  InboxListing,
  InboxRunResult,
  RuleApplyRequest,
  RuleApplyResult,
  RuleRead,
  RuleWrite,
  TagRead,
  TagWrite,
} from "./cashflowTypes";

function filterQuery(filters: CashflowEntryFilters, extra: Record<string, number> = {}): string {
  const params = new URLSearchParams();
  if (filters.account_id) params.set("account_id", filters.account_id);
  if (filters.start) params.set("start", filters.start);
  if (filters.end) params.set("end", filters.end);
  if (filters.include_reversed) params.set("include_reversed", "true");
  if (filters.nature) params.set("nature", filters.nature);
  if (filters.category_id) params.set("category_id", filters.category_id);
  if (filters.uncategorized) params.set("uncategorized", "true");
  if (filters.search) params.set("search", filters.search);
  for (const [key, value] of Object.entries(extra)) params.set(key, String(value));
  const query = params.toString();
  return query ? `?${query}` : "";
}

// --- Lançamentos -----------------------------------------------------------

export function getCashEntries(
  filters: CashflowEntryFilters = {},
  limit = 100,
  offset = 0,
): Promise<CashflowEntryRead[]> {
  return request<CashflowEntryRead[]>(`/cashflow/entries${filterQuery(filters, { limit, offset })}`);
}

/** Total da listagem com os mesmos filtros, sem paginação. */
export function countCashEntries(filters: CashflowEntryFilters = {}): Promise<{ total: number }> {
  return request<{ total: number }>(`/cashflow/entries/count${filterQuery(filters)}`);
}

export function createCashEntry(payload: CashflowEntryCreate): Promise<CashflowEntryRead> {
  return request<CashflowEntryRead>("/cashflow/entries", { method: "POST", body: payload });
}

export function createCashTransfer(payload: CashflowTransferCreate): Promise<CashflowTransferRead> {
  return request<CashflowTransferRead>("/cashflow/transfers", { method: "POST", body: payload });
}

/** Classificação manual completa: natureza, categoria e tags de uma vez. */
export function classifyCashEntry(entryId: string, payload: EntryClassificationWrite): Promise<CashflowEntryRead> {
  return request<CashflowEntryRead>(`/cashflow/entries/${entryId}/classification`, {
    method: "PUT",
    body: payload,
  });
}

/** Devolve todos os estornados: um lançamento, ou as pernas da transferência. */
export function reverseCashEntry(entryId: string): Promise<CashflowEntryRead[]> {
  return request<CashflowEntryRead[]>(`/cashflow/entries/${entryId}/reverse`, { method: "POST" });
}

/** Desfaz a exclusão: o lançamento (ou as pontas da transferência) volta a valer. */
export function restoreCashEntry(entryId: string): Promise<CashflowEntryRead[]> {
  return request<CashflowEntryRead[]>(`/cashflow/entries/${entryId}/restore`, { method: "POST" });
}

/** Edita um lançamento manual: o original fica excluído e o novo é devolvido. */
export function correctCashEntry(entryId: string, payload: CashflowEntryCorrect): Promise<CashflowEntryRead> {
  return request<CashflowEntryRead>(`/cashflow/entries/${entryId}/correct`, {
    method: "POST",
    body: payload,
  });
}

/** Liga dois lançamentos existentes como as duas pontas de uma transferência. */
export function linkCashTransfer(entryId: string, counterpartyEntryId: string): Promise<CashflowTransferLinkResult> {
  return request<CashflowTransferLinkResult>(`/cashflow/entries/${entryId}/transfer`, {
    method: "POST",
    body: { counterparty_entry_id: counterpartyEntryId },
  });
}

/** Marca o lançamento como aporte (saída) ou resgate (entrada) na conta de investimentos. */
export function markInvestmentTransfer(
  entryId: string,
  investmentAccountId: string,
): Promise<CashflowTransferLinkResult> {
  return request<CashflowTransferLinkResult>(`/cashflow/entries/${entryId}/transfer`, {
    method: "POST",
    body: { investment_account_id: investmentAccountId },
  });
}

export function unlinkCashTransfer(entryId: string): Promise<CashflowTransferLinkResult> {
  return request<CashflowTransferLinkResult>(`/cashflow/entries/${entryId}/transfer`, { method: "DELETE" });
}

/** `dryRun` verdadeiro só mostra o que seria casado. */
export function matchInvoicePayments(dryRun: boolean): Promise<CashflowTransferMatchResult> {
  return request<CashflowTransferMatchResult>(`/cashflow/transfers/match?dry_run=${dryRun}`, { method: "POST" });
}

// --- Resumo ------------------------------------------------------------------

export function getCashSummary(start: string, end: string): Promise<CashflowSummary> {
  return request<CashflowSummary>(`/cashflow/summary?start=${start}&end=${end}`);
}

export function getCashBalances(): Promise<CashflowBalances> {
  return request<CashflowBalances>("/cashflow/balances");
}

export function getCategoryBreakdown(start: string, end: string): Promise<CategoryBreakdown> {
  return request<CategoryBreakdown>(`/cashflow/summary/categories?start=${start}&end=${end}`);
}

// --- Categorias e tags -----------------------------------------------------

export function getCategories(): Promise<CategoryRead[]> {
  return request<CategoryRead[]>("/cashflow/categories");
}

export function createCategory(payload: CategoryWrite): Promise<CategoryRead> {
  return request<CategoryRead>("/cashflow/categories", { method: "POST", body: payload });
}

/** Cria o que faltar da árvore inicial e devolve todas as categorias. */
export function createDefaultCategories(): Promise<CategoryRead[]> {
  return request<CategoryRead[]>("/cashflow/categories/defaults", { method: "POST" });
}

export function updateCategory(id: string, payload: CategoryWrite): Promise<CategoryRead> {
  return request<CategoryRead>(`/cashflow/categories/${id}`, { method: "PUT", body: payload });
}

export function deleteCategory(id: string): Promise<void> {
  return request<void>(`/cashflow/categories/${id}`, { method: "DELETE" });
}

export function getTags(): Promise<TagRead[]> {
  return request<TagRead[]>("/cashflow/tags");
}

export function createTag(payload: TagWrite): Promise<TagRead> {
  return request<TagRead>("/cashflow/tags", { method: "POST", body: payload });
}

export function updateTag(id: string, payload: TagWrite): Promise<TagRead> {
  return request<TagRead>(`/cashflow/tags/${id}`, { method: "PUT", body: payload });
}

export function deleteTag(id: string): Promise<void> {
  return request<void>(`/cashflow/tags/${id}`, { method: "DELETE" });
}

// --- Regras ------------------------------------------------------------------

export function getRules(): Promise<RuleRead[]> {
  return request<RuleRead[]>("/cashflow/rules");
}

export function createRule(payload: RuleWrite): Promise<RuleRead> {
  return request<RuleRead>("/cashflow/rules", { method: "POST", body: payload });
}

export function updateRule(id: string, payload: RuleWrite): Promise<RuleRead> {
  return request<RuleRead>(`/cashflow/rules/${id}`, { method: "PUT", body: payload });
}

export function deleteRule(id: string): Promise<void> {
  return request<void>(`/cashflow/rules/${id}`, { method: "DELETE" });
}

/** Mostra o que a aplicação das regras mudaria. Não grava nada. */
export function previewRules(payload: RuleApplyRequest): Promise<RuleApplyResult> {
  return request<RuleApplyResult>("/cashflow/rules/preview", { method: "POST", body: payload });
}

export function applyRules(payload: RuleApplyRequest): Promise<RuleApplyResult> {
  return request<RuleApplyResult>("/cashflow/rules/apply", { method: "POST", body: payload });
}

// --- Importação --------------------------------------------------------------

/** Sem `profile`, o backend detecta o formato pelo conteúdo. */
export function previewCashImport(
  accountId: string,
  file: File,
  profile: CashflowImportProfile | null,
): Promise<CashflowImportPreview> {
  const formData = new FormData();
  formData.append("account_id", accountId);
  formData.append("file", file);
  if (profile !== null) formData.append("profile", profile);
  return request<CashflowImportPreview>("/cashflow/imports/preview", { method: "POST", formData });
}

/**
 * A prévia volta EXATAMENTE como veio (a assinatura cobre as linhas);
 * o frontend só escolhe os índices e se cria o saldo inicial.
 */
export function commitCashImport(
  preview: CashflowImportPreview,
  includedRowIndexes: number[],
  createOpeningAdjustment: boolean,
): Promise<CashflowImportCommitResult> {
  return request<CashflowImportCommitResult>("/cashflow/imports/commit", {
    method: "POST",
    body: {
      account_id: preview.account_id,
      profile: preview.profile,
      file_name: preview.file_name,
      file_sha256: preview.file_sha256,
      period_start: preview.period_start,
      period_end: preview.period_end,
      statement_balance: preview.statement_balance,
      statement_balance_date: preview.statement_balance_date,
      rows: preview.rows,
      signature: preview.signature,
      included_row_indexes: includedRowIndexes,
      create_opening_adjustment: createOpeningAdjustment,
    },
  });
}

/** Arquivos esperando na pasta Entrada. */
export function getInbox(): Promise<InboxListing> {
  return request<InboxListing>("/cashflow/inbox");
}

/** Importa os arquivos da pasta Entrada (mesmas conferências da tela). */
export function processInbox(): Promise<InboxRunResult> {
  return request<InboxRunResult>("/cashflow/inbox/process", { method: "POST" });
}

export function getCashImportBatches(): Promise<CashflowImportBatchRead[]> {
  return request<CashflowImportBatchRead[]>("/cashflow/imports");
}
