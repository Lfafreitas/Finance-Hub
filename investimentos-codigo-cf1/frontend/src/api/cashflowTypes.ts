// Tipos do controle financeiro (livro de caixa). Espelham os schemas
// do backend: valores monetários chegam como string decimal e nunca
// são recalculados aqui.

import type { AccountType } from "./types";

export type CashflowNature = "INCOME" | "EXPENSE" | "THIRD_PARTY" | "TRANSFER" | "ADJUSTMENT" | "UNCLASSIFIED";
export type CashflowEntryStatus = "ACTIVE" | "REVERSED";
export type RuleMatchType = "CONTAINS" | "EQUALS" | "STARTS_WITH";
export type RuleDirection = "ANY" | "IN" | "OUT";
export type CashflowImportProfile =
  | "NUBANK_ACCOUNT_CSV"
  | "NUBANK_ACCOUNT_OFX"
  | "NUBANK_CARD_CSV"
  | "NUBANK_CARD_OFX"
  | "NUBANK_CARD_PDF";

/** Conferência do arquivo contra o total que ele mesmo declara (fatura em PDF). */
export interface CashflowImportCheck {
  label: string;
  expected: string;
  found: string;
  ok: boolean;
}

export interface CashflowEntryRead {
  id: string;
  account_id: string;
  entry_date: string;
  /** Assinado: positivo entra, negativo sai. */
  amount: string;
  currency_code: string;
  description: string;
  source: string;
  nature: CashflowNature;
  counterparty_account_id: string | null;
  transfer_group_id: string | null;
  notes: string | null;
  status: CashflowEntryStatus;
  category_id: string | null;
  /** Preenchido = aquela regra classificou; nulo = decisão manual. */
  classified_by_rule_id: string | null;
  tag_ids: string[];
  /** Texto normalizado que as regras comparam. */
  match_text: string;
  /** Edição: o lançamento que este substituiu. */
  corrects_entry_id?: string | null;
}

/** Novos valores do fato numa edição; `notes` nulo mantém as notas. */
export interface CashflowEntryCorrect {
  entry_date: string;
  amount: string;
  description: string;
  notes: string | null;
}

export interface CashflowEntryCreate {
  account_id: string;
  entry_date: string;
  amount: string;
  description: string;
  nature: CashflowNature;
  notes: string | null;
}

export interface CashflowTransferCreate {
  from_account_id: string;
  to_account_id: string;
  entry_date: string;
  amount: string;
  description: string;
  notes: string | null;
}

export interface CashflowTransferRead {
  transfer_group_id: string;
  entries: CashflowEntryRead[];
}

/** Filtros da listagem; a contagem usa exatamente os mesmos. */
export interface CashflowEntryFilters {
  account_id?: string;
  start?: string;
  end?: string;
  include_reversed?: boolean;
  nature?: CashflowNature;
  category_id?: string;
  uncategorized?: boolean;
  search?: string;
}

export interface CashflowCurrencySummary {
  currency_code: string;
  entry_count: number;
  income: string;
  third_party_net: string;
  adjustments_net: string;
  unclassified_net: string;
  internal_transfers_net: string;
  expenses: string;
  net_invested: string;
  liquid_variation: string;
  reserve_variation: string;
  card_balance_variation: string;
}

export interface CashflowSummary {
  start: string;
  end: string;
  totals_by_currency: CashflowCurrencySummary[];
}

export interface CashflowAccountBalance {
  account_id: string;
  account_name: string;
  account_type: AccountType;
  currency_code: string;
  balance: string;
}

export interface CashflowCurrencyBalance {
  currency_code: string;
  liquid: string;
  reserve: string;
  card: string;
}

export interface CashflowBalances {
  as_of: string;
  accounts: CashflowAccountBalance[];
  totals_by_currency: CashflowCurrencyBalance[];
}

export interface CategoryRead {
  id: string;
  name: string;
  parent_id: string | null;
}

export interface CategoryWrite {
  name: string;
  parent_id: string | null;
}

export interface TagRead {
  id: string;
  name: string;
  tag_group: string;
}

export interface TagWrite {
  name: string;
  tag_group: string;
}

export interface EntryClassificationWrite {
  nature: CashflowNature;
  category_id: string | null;
  tag_ids: string[];
}

export interface RuleWrite {
  name: string;
  priority: number;
  is_active: boolean;
  match_type: RuleMatchType;
  pattern: string;
  direction: RuleDirection;
  account_id: string | null;
  set_nature: CashflowNature;
  set_category_id: string | null;
  tag_ids: string[];
}

export interface RuleRead extends RuleWrite {
  id: string;
}

export interface RuleApplyRequest {
  reevaluate: boolean;
}

export interface RuleApplyChange {
  entry_id: string;
  description: string;
  match_text: string;
  amount: string;
  currency_code: string;
  entry_date: string;
  rule_id: string | null;
  rule_name: string | null;
  nature: CashflowNature;
  category_id: string | null;
  tag_ids: string[];
}

export interface RuleApplyResult {
  applied: boolean;
  examined: number;
  changes: RuleApplyChange[];
}

export interface CategoryTotalsRead {
  /** Nulo = linha "sem categoria". */
  category_id: string | null;
  category_name: string | null;
  parent_id: string | null;
  own_expenses: string;
  own_income: string;
  total_expenses: string;
  total_income: string;
}

export interface CurrencyCategoryBreakdown {
  currency_code: string;
  expenses: string;
  income: string;
  categories: CategoryTotalsRead[];
}

export interface CategoryBreakdown {
  start: string;
  end: string;
  totals_by_currency: CurrencyCategoryBreakdown[];
}

export interface CashflowImportRow {
  row_index: number;
  entry_date: string | null;
  amount: string | null;
  description: string;
  external_id: string | null;
  import_fingerprint: string | null;
  is_duplicate: boolean;
  error: string | null;
  match_text: string;
  suggested_rule_id: string | null;
  suggested_rule_name: string | null;
  suggested_nature: CashflowNature | null;
  suggested_category_id: string | null;
}

export interface CashflowImportPreview {
  account_id: string;
  profile: CashflowImportProfile;
  file_name: string;
  file_sha256: string;
  period_start: string | null;
  period_end: string | null;
  statement_balance: string | null;
  statement_balance_date: string | null;
  file_already_imported: boolean;
  rows: CashflowImportRow[];
  signature: string;
  // Informativos (fatura em PDF); ficam fora da assinatura.
  checks?: CashflowImportCheck[];
  statement_due_date?: string | null;
  statement_previous?: string | null;
  statement_total?: string | null;
}

export interface CashflowTransferMatch {
  transfer_group_id: string | null;
  sent_entry_id: string;
  received_entry_id: string;
  amount: string;
  sent_date: string;
  received_date: string;
}

export interface CashflowImportCommitResult {
  batch_id: string;
  imported_count: number;
  not_included_count: number;
  opening_adjustment: string | null;
  matched_transfers: CashflowTransferMatch[];
  rules_applied_count: number;
  statement_balance: string | null;
  statement_balance_date: string | null;
  system_balance: string | null;
  /** Saldo do sistema − saldo do arquivo. Zero = bate com o banco. */
  balance_difference: string | null;
}

export interface CashflowImportBatchRead {
  id: string;
  account_id: string;
  profile: CashflowImportProfile;
  file_name: string;
  file_sha256: string;
  period_start: string | null;
  period_end: string | null;
  rows_total: number;
  rows_imported: number;
  statement_balance: string | null;
  statement_balance_date: string | null;
  created_at: string;
}

export interface CashflowTransferLinkResult {
  entries: CashflowEntryRead[];
}

export interface CashflowTransferMatchResult {
  applied: boolean;
  matches: CashflowTransferMatch[];
}

export type InboxStatus = "IMPORTED" | "NOTHING_NEW" | "REFUSED" | "NO_ACCOUNT";

/** Resultado de um arquivo da pasta Entrada. */
export interface InboxFileResult {
  file_name: string;
  status: InboxStatus;
  profile: CashflowImportProfile | null;
  account_id: string | null;
  account_name: string | null;
  imported_count: number;
  duplicate_count: number;
  error_rows: number;
  matched_transfers: number;
  balance_difference: string | null;
  message: string | null;
  moved_to: string | null;
}

export interface InboxListing {
  inbox_dir: string;
  exists: boolean;
  files: string[];
}

export interface InboxRunResult {
  inbox_dir: string;
  files: InboxFileResult[];
}
