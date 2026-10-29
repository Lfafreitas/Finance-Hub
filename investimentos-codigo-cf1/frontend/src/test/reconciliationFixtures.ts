import type {
  AccountRead,
  ReconciliationComparisonRead,
  ReconciliationLogRead,
  TransactionRead,
} from "../api/types";

export const TX_A_ID = "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const TX_B_ID = "22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
export const LOG_ID = "99999999-cccc-4ccc-8ccc-cccccccccccc";
export const ACCOUNT_ID = "33333333-dddd-4ddd-8ddd-dddddddddddd";

export function makeLog(overrides: Partial<ReconciliationLogRead> = {}): ReconciliationLogRead {
  return {
    id: LOG_ID,
    user_id: "user-1",
    transaction_a_id: TX_A_ID,
    transaction_b_id: TX_B_ID,
    match_reason: "DIVERGENT: gross_amount: 3000.0000 != 3300.0000 (abs=300.0000, rel=0.0909)",
    status: "PENDING",
    surviving_transaction_id: null,
    reversed_transaction_id: null,
    resolved_at: null,
    created_at: "2026-08-15T12:00:00Z",
    updated_at: "2026-08-15T12:00:00Z",
    ...overrides,
  };
}

export function makeTransaction(overrides: Partial<TransactionRead> = {}): TransactionRead {
  return {
    id: TX_A_ID,
    account_id: ACCOUNT_ID,
    asset_id: "44444444-eeee-4eee-8eee-eeeeeeeeeeee",
    transaction_type: "BUY",
    quantity: "100.00000000",
    unit_price: "30.00000000",
    fees: "0.0000",
    gross_amount: "3000.0000",
    currency_code: "BRL",
    transaction_date: "2026-08-15",
    fx_rate_to_brl: null,
    source: "MANUAL",
    status: "ACTIVE",
    reverses_transaction_id: null,
    linked_transaction_id: null,
    notes: null,
    created_at: "2026-08-15T12:00:00Z",
    updated_at: "2026-08-15T12:00:00Z",
    ...overrides,
  };
}

export const transactionA = makeTransaction();
export const transactionB = makeTransaction({ id: TX_B_ID, source: "IMPORT_CSV", gross_amount: "3300.0000" });

export const divergentComparison: ReconciliationComparisonRead = {
  reconciliation_id: LOG_ID,
  classification: "DIVERGENT",
  match_reason: "DIVERGENT: gross_amount: 3000.0000 != 3300.0000 (abs=300.0000, rel=0.0909)",
  fields: [
    {
      field: "transaction_date",
      equal: false,
      value_a: "2026-08-15",
      value_b: "2026-08-16",
      absolute_difference: "1",
      relative_difference: null,
    },
    {
      field: "quantity",
      equal: true,
      value_a: "100.00000000",
      value_b: "100.00000000",
      absolute_difference: "0.00000000",
      relative_difference: "0",
    },
    {
      field: "gross_amount",
      equal: false,
      value_a: "3000.0000",
      value_b: "3300.0000",
      absolute_difference: "300.0000",
      relative_difference: "0.09090909090909090909090909091",
    },
    {
      field: "currency_code",
      equal: true,
      value_a: "BRL",
      value_b: "BRL",
      absolute_difference: null,
      relative_difference: null,
    },
  ],
};

export const equivalentComparison: ReconciliationComparisonRead = {
  reconciliation_id: LOG_ID,
  classification: "EQUIVALENT",
  match_reason: "EQUIVALENT: todos os campos comparados são iguais",
  fields: divergentComparison.fields
    .filter((field) => field.equal)
    .map((field) => ({ ...field })),
};

export const accounts: AccountRead[] = [
  {
    id: ACCOUNT_ID,
    name: "Conta Ações",
    institution_id: "inst-1",
    institution_name: "Corretora X",
    currency_code: "BRL",
    portfolio_id: null,
    account_type: "BROKERAGE",
  },
];
