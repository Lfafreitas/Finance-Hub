// Espelha app/schemas/*.py do backend. Campos Decimal chegam como
// STRING no JSON (Pydantic v2 serializa Decimal como string por
// padrão) — o frontend nunca deve fazer aritmética financeira sobre
// eles, só exibir. Conversão pra number é só para posicionamento em
// gráfico (recharts), nunca para recalcular um valor exibido em card.

/** BROKERAGE = livro de investimentos; os demais = livro de caixa. */
export type AccountType = "CHECKING" | "SAVINGS" | "CASH" | "CREDIT_CARD" | "BROKERAGE";

export interface AccountRead {
  id: string;
  name: string;
  institution_id: string;
  institution_name: string;
  currency_code: string;
  portfolio_id: string | null;
  account_type: AccountType;
}

export interface PortfolioRead {
  id: string;
  name: string;
}

// Uma posição (conta, ativo). `currency_code` é a moeda das transações
// ativas do par. Quando o par tem transações em mais de uma moeda a
// posição é INCONSISTENTE: `currency_code` vem null, o motivo vem em
// `currency_inconsistency_reason` e todo campo monetário vem null — só
// `quantity` e `is_closed` continuam válidos. Uma posição assim não
// pertence a nenhum bloco de `totals_by_currency`.
export interface PositionSummary {
  account_id: string;
  asset_id: string;
  asset_ticker: string;
  asset_name: string;
  currency_code: string | null;
  currency_inconsistency_reason: string | null;
  quantity: string;
  average_cost: string | null;
  total_cost_basis: string | null;
  realized_gain: string | null;
  dividends_received: string | null;
  realized_cost_basis: string | null;
  realized_return_pct: string | null;
  is_closed: boolean;
  xirr: string | null;
  cagr: string | null;
  profitability_unavailable_reason: string | null;
  // Valoração a mercado: preenchida quando há cotação do ativo na
  // moeda da posição; senão null, com o motivo em `unavailable_reason`.
  // `market_price_date` é a data da cotação usada.
  market_price: string | null;
  market_price_date: string | null;
  market_value: string | null;
  unrealized_pnl: string | null;
  unrealized_return_pct: string | null;
  unavailable_reason: string | null;
}

export interface AllocationSlice {
  asset_id: string;
  asset_ticker: string;
  asset_name: string;
  cost_basis: string;
  // Sempre relativo ao custo total da MESMA moeda (o bloco da fatia).
  percentage: string;
}

export interface ContributionPoint {
  date: string;
  cumulative_net_contribution: string;
}

// Tudo o que é dinheiro no dashboard, para UMA moeda. O backend nunca
// soma nem converte moedas diferentes — e o frontend também não: cada
// bloco é exibido isoladamente, formatado na própria moeda.
export interface DashboardCurrencyTotals {
  currency_code: string;
  total_cost_basis: string;
  total_realized_gain: string;
  total_dividends_received: string;
  net_contributions: string;
  total_realized_cost_basis: string;
  realized_return_pct: string | null;
  is_closed: boolean;
  xirr: string | null;
  cagr: string | null;
  profitability_unavailable_reason: string | null;
  // Só preenchidos quando TODA posição aberta da moeda tem cotação.
  // `current_return` é fração (0.10 = 10%). `market_data_as_of` é a
  // cotação mais antiga usada no total.
  market_value: string | null;
  unrealized_pnl: string | null;
  current_return: string | null;
  market_data_as_of: string | null;
  market_data_unavailable_reason: string | null;
  allocation: AllocationSlice[];
  contribution_evolution: ContributionPoint[];
}

// `totals_by_currency` é a única fonte de totais (um bloco por moeda,
// na ordem definida pelo backend). Não existe total no nível de cima.
export interface DashboardSummary {
  portfolio_id: string | null;
  positions: PositionSummary[];
  totals_by_currency: DashboardCurrencyTotals[];
}

// --- Transaction isolada (GET /transactions/{id}) -------------------------

export type TransactionSource =
  | "MANUAL"
  | "IMPORT_CSV"
  | "IMPORT_XLSX"
  | "IMPORT_OFX"
  | "IMPORT_PDF"
  | "API_PLUGGY";

export type TransactionStatus = "ACTIVE" | "REVERSED";

export interface TransactionRead {
  id: string;
  account_id: string;
  asset_id: string | null;
  transaction_type: string;
  quantity: string | null;
  unit_price: string | null;
  fees: string;
  gross_amount: string;
  currency_code: string;
  transaction_date: string;
  fx_rate_to_brl: string | null;
  source: TransactionSource;
  status: TransactionStatus;
  reverses_transaction_id: string | null;
  linked_transaction_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

// --- Reconciliação (Fase 11) ----------------------------------------------

export type ReconciliationStatus = "PENDING" | "IGNORED" | "KEPT_BOTH" | "MERGED" | "STALE";

export type ReconciliationDecision = "IGNORE" | "KEEP_BOTH" | "MERGE";

export type MatchClassification = "EQUIVALENT" | "DIVERGENT";

export interface ReconciliationLogRead {
  id: string;
  user_id: string;
  transaction_a_id: string;
  transaction_b_id: string;
  match_reason: string;
  status: ReconciliationStatus;
  surviving_transaction_id: string | null;
  reversed_transaction_id: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

// Todos os valores já chegam como string de exibição pronta (o backend
// converte Decimal/date). A comparação é calculada pelo matcher no
// backend — o frontend NUNCA recalcula igualdade nem diferença.
export interface FieldComparisonRead {
  field: string;
  equal: boolean;
  value_a: string | null;
  value_b: string | null;
  absolute_difference: string | null;
  relative_difference: string | null;
}

export interface ReconciliationComparisonRead {
  reconciliation_id: string;
  classification: MatchClassification;
  match_reason: string;
  fields: FieldComparisonRead[];
}

export interface ReconciliationResolveRequest {
  decision: ReconciliationDecision;
  /** Obrigatório em MERGE, proibido nas demais decisões. */
  surviving_transaction_id?: string;
}

/** Escopo do scan: uma conta, uma carteira, ou vazio (todas as contas). */
export interface ReconciliationScanRequest {
  account_id?: string;
  portfolio_id?: string;
}

export interface ReconciliationScanResult {
  created_count: number;
  created: ReconciliationLogRead[];
}

// --- Cadastros --------------------------------------------------------------

export interface CurrencyRead {
  code: string;
  name: string;
}

export interface AssetClassRead {
  code: string;
  label: string;
}

export interface AssetRead {
  id: string;
  ticker: string;
  name: string;
  asset_class_code: string;
  country: string;
  currency_code: string;
  /** Renda fixa: vencimento (AAAA-MM-DD) e taxa anual como fração ("0.0385"). */
  maturity_date?: string | null;
  annual_rate?: string | null;
}

export interface AssetCreate {
  ticker: string;
  name: string;
  asset_class_code: string;
  country: string;
  currency_code: string;
  maturity_date?: string | null;
  annual_rate?: string | null;
}

export type InstitutionType = "BANK" | "BROKER" | "OTHER";

export interface InstitutionRead {
  id: string;
  name: string;
  institution_type: InstitutionType;
  country: string;
}

export interface InstitutionCreate {
  name: string;
  institution_type: InstitutionType;
  country: string;
}

export interface AccountCreate {
  name: string;
  institution_id: string;
  currency_code: string;
  account_type: AccountType;
  portfolio_id?: string;
}

export interface PortfolioCreate {
  name: string;
}

// --- Lançamento manual ------------------------------------------------------

// Tipos aceitos por POST /transactions. TRANSFER_OUT/IN têm fluxo
// próprio (POST /transfers); FX_CONVERSION não tem fluxo na UI.
export type ManualTransactionType =
  | "BUY"
  | "SELL"
  | "DIVIDEND"
  | "JCP"
  | "INCOME"
  | "FEE"
  | "DEPOSIT"
  | "WITHDRAWAL"
  | "BONUS_SHARES"
  | "STOCK_SPLIT"
  | "REVERSE_SPLIT";

// Valores numéricos vão como STRING, exatamente como o usuário digitou
// — o backend converte para Decimal. O frontend não calcula nada.
export interface TransactionCreate {
  account_id: string;
  asset_id?: string;
  transaction_type: ManualTransactionType;
  quantity?: string;
  unit_price?: string;
  fees?: string;
  gross_amount: string;
  currency_code: string;
  transaction_date: string;
  notes?: string;
}

export interface TransferCreate {
  from_account_id: string;
  to_account_id: string;
  gross_amount: string;
  transaction_date: string;
  fees?: string;
  notes?: string;
}

export interface TransferRead {
  transfer_out: TransactionRead;
  transfer_in: TransactionRead;
}

// --- Importação -------------------------------------------------------------

export type ImportSourceFormat = "CSV" | "XLSX" | "OFX";

export interface ImportRow {
  row_index: number;
  transaction_type: string;
  asset_ticker: string | null;
  asset_id: string | null;
  quantity: string | null;
  unit_price: string | null;
  fees: string;
  gross_amount: string;
  currency_code: string;
  transaction_date: string;
  external_reference: string;
  is_exact_duplicate: boolean;
  possible_duplicate: boolean;
  duplicate_reason: string | null;
  error: string | null;
}

export interface ImportPreviewResponse {
  account_id: string;
  source_format: string;
  rows: ImportRow[];
  signature: string;
}

export interface ImportCommitResult {
  imported_count: number;
  excluded_count: number;
  transaction_ids: string[];
}

// --- Cotações (Fase 12) -----------------------------------------------------

export interface AssetLatestPrice {
  asset_id: string;
  asset_ticker: string;
  asset_name: string;
  currency_code: string;
  price: string | null;
  price_date: string | null;
}

export interface AssetPriceRead {
  id: string;
  asset_id: string;
  price_date: string;
  price: string;
  currency_code: string;
  source: string;
}

export interface AssetPriceWrite {
  price_date: string;
  price: string;
}
