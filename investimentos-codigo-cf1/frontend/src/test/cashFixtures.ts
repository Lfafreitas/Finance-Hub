// Fixtures do controle financeiro. Nomes fictícios; valores com 4
// casas, como o backend devolve.

import type {
  CashflowBalances,
  CashflowEntryRead,
  CashflowImportCommitResult,
  CashflowImportPreview,
  CashflowImportRow,
  CashflowSummary,
  CategoryBreakdown,
  CategoryRead,
  RuleRead,
  TagRead,
} from "../api/cashflowTypes";
import type { AccountRead } from "../api/types";

export const checking: AccountRead = {
  id: "acc-checking",
  name: "Conta Corrente",
  institution_id: "inst-1",
  institution_name: "Banco Exemplo",
  currency_code: "BRL",
  portfolio_id: null,
  account_type: "CHECKING",
};

export const card: AccountRead = { ...checking, id: "acc-card", name: "Cartão", account_type: "CREDIT_CARD" };
export const savings: AccountRead = { ...checking, id: "acc-savings", name: "Reserva", account_type: "SAVINGS" };
export const brokerage: AccountRead = { ...checking, id: "acc-broker", name: "Corretora", account_type: "BROKERAGE" };
export const usdBrokerage: AccountRead = {
  ...checking,
  id: "acc-broker-usd",
  name: "Broker Exterior",
  currency_code: "USD",
  account_type: "BROKERAGE",
};
export const allAccounts: AccountRead[] = [checking, card, savings, brokerage, usdBrokerage];

export const food: CategoryRead = { id: "cat-food", name: "Alimentação", parent_id: null };
export const market: CategoryRead = { id: "cat-market", name: "Mercado", parent_id: "cat-food" };
export const home: CategoryRead = { id: "cat-home", name: "Moradia", parent_id: null };
export const categories: CategoryRead[] = [home, market, food];

export const tripTag: TagRead = { id: "tag-trip", name: "praia", tag_group: "viagem" };
export const workTag: TagRead = { id: "tag-work", name: "reembolsável", tag_group: "" };
export const tags: TagRead[] = [tripTag, workTag];

export function makeRule(overrides: Partial<RuleRead> = {}): RuleRead {
  return {
    id: "rule-1",
    name: "Mercado do bairro",
    priority: 100,
    is_active: true,
    match_type: "CONTAINS",
    pattern: "mercado exemplo",
    direction: "OUT",
    account_id: null,
    set_nature: "EXPENSE",
    set_category_id: "cat-market",
    tag_ids: [],
    ...overrides,
  };
}

export function makeEntry(overrides: Partial<CashflowEntryRead> = {}): CashflowEntryRead {
  return {
    id: "e-1",
    account_id: "acc-checking",
    entry_date: "2026-08-10",
    amount: "-100.0000",
    currency_code: "BRL",
    description: "Mercado Exemplo",
    source: "IMPORT_OFX",
    nature: "UNCLASSIFIED",
    counterparty_account_id: null,
    transfer_group_id: null,
    notes: null,
    status: "ACTIVE",
    category_id: null,
    classified_by_rule_id: null,
    tag_ids: [],
    match_text: "mercado exemplo",
    ...overrides,
  };
}

export const balancesFixture: CashflowBalances = {
  as_of: "2026-08-31",
  accounts: [
    { account_id: "acc-card", account_name: "Cartão", account_type: "CREDIT_CARD", currency_code: "BRL", balance: "-313.6000" },
    { account_id: "acc-checking", account_name: "Conta Corrente", account_type: "CHECKING", currency_code: "BRL", balance: "1789.2000" },
    { account_id: "acc-usd", account_name: "Conta Dólar", account_type: "CHECKING", currency_code: "USD", balance: "55.5000" },
  ],
  totals_by_currency: [
    { currency_code: "BRL", liquid: "1789.2000", reserve: "2222.0000", card: "-313.6000" },
    { currency_code: "USD", liquid: "55.5000", reserve: "0.0000", card: "0.0000" },
  ],
};

// Cada número aparece uma única vez, para o teste saber de onde veio.
export const summaryFixture: CashflowSummary = {
  start: "2026-08-01",
  end: "2026-08-31",
  totals_by_currency: [
    {
      currency_code: "BRL",
      entry_count: 30,
      income: "5001.0000",
      third_party_net: "-12.0000",
      adjustments_net: "1254.3000",
      unclassified_net: "-629.8000",
      internal_transfers_net: "7.7700",
      expenses: "1234.5600",
      net_invested: "1050.0000",
      liquid_variation: "89.2000",
      reserve_variation: "300.0000",
      card_balance_variation: "535.3000",
    },
  ],
};

export const breakdownFixture: CategoryBreakdown = {
  start: "2026-08-01",
  end: "2026-08-31",
  totals_by_currency: [
    {
      currency_code: "BRL",
      expenses: "1000.0000",
      income: "5001.0000",
      categories: [
        { category_id: "cat-food", category_name: "Alimentação", parent_id: null, own_expenses: "50.0000", own_income: "0.0000", total_expenses: "250.0000", total_income: "0.0000" },
        { category_id: "cat-market", category_name: "Mercado", parent_id: "cat-food", own_expenses: "200.0000", own_income: "0.0000", total_expenses: "200.0000", total_income: "0.0000" },
        { category_id: "cat-home", category_name: "Moradia", parent_id: null, own_expenses: "650.0000", own_income: "0.0000", total_expenses: "650.0000", total_income: "0.0000" },
        { category_id: "cat-salary", category_name: "Salário", parent_id: null, own_expenses: "0.0000", own_income: "5001.0000", total_expenses: "0.0000", total_income: "5001.0000" },
        { category_id: null, category_name: null, parent_id: null, own_expenses: "100.0000", own_income: "0.0000", total_expenses: "100.0000", total_income: "0.0000" },
      ],
    },
  ],
};

export function makeImportRow(overrides: Partial<CashflowImportRow> = {}): CashflowImportRow {
  return {
    row_index: 0,
    entry_date: "2026-08-05",
    amount: "-40.0000",
    description: "Padaria Exemplo",
    external_id: "id-0",
    import_fingerprint: null,
    is_duplicate: false,
    error: null,
    match_text: "padaria exemplo",
    suggested_rule_id: null,
    suggested_rule_name: null,
    suggested_nature: null,
    suggested_category_id: null,
    ...overrides,
  };
}

/** Linha 1 pronta com sugestão, 2 com erro, 3 duplicada, 4 pronta. */
export const cashPreviewFixture: CashflowImportPreview = {
  account_id: "acc-checking",
  profile: "NUBANK_ACCOUNT_OFX",
  file_name: "extrato.ofx",
  file_sha256: "abc123",
  period_start: "2026-08-01",
  period_end: "2026-08-31",
  statement_balance: "89.2000",
  statement_balance_date: "2026-08-31",
  file_already_imported: false,
  rows: [
    makeImportRow({
      row_index: 0,
      description: "Mercado Exemplo",
      amount: "-100.0000",
      suggested_rule_id: "rule-1",
      suggested_rule_name: "Mercado do bairro",
      suggested_nature: "EXPENSE",
      suggested_category_id: "cat-market",
    }),
    makeImportRow({ row_index: 1, entry_date: null, amount: null, description: "linha quebrada", error: "data inválida" }),
    makeImportRow({ row_index: 2, description: "Já veio antes", is_duplicate: true }),
    makeImportRow({ row_index: 3, description: "Salário", amount: "3000.0000" }),
  ],
  signature: "sig-1",
};

export const commitResultFixture: CashflowImportCommitResult = {
  batch_id: "batch-1",
  imported_count: 2,
  not_included_count: 2,
  opening_adjustment: "1254.3000",
  matched_transfers: [
    {
      transfer_group_id: "g-1",
      sent_entry_id: "e-s",
      received_entry_id: "e-r",
      amount: "1190.6000",
      sent_date: "2026-08-30",
      received_date: "2026-08-30",
    },
  ],
  rules_applied_count: 1,
  statement_balance: "89.2000",
  statement_balance_date: "2026-08-31",
  system_balance: "89.2000",
  balance_difference: "0.0000",
};
