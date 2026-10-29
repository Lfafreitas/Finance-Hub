import type {
  AccountRead,
  AssetRead,
  CurrencyRead,
  ImportPreviewResponse,
  ImportRow,
  TransactionRead,
} from "../api/types";
import { makeTransaction } from "./reconciliationFixtures";

export const brlAccount: AccountRead = {
  id: "acc-brl",
  name: "Conta Ações",
  institution_id: "inst-1",
  institution_name: "Corretora X",
  currency_code: "BRL",
  portfolio_id: null,
  account_type: "BROKERAGE",
};

export const usdAccount: AccountRead = {
  id: "acc-usd",
  name: "Conta Exterior",
  institution_id: "inst-2",
  institution_name: "Broker Y",
  currency_code: "USD",
  portfolio_id: null,
  account_type: "BROKERAGE",
};

export const checkingAccount: AccountRead = {
  id: "acc-checking",
  name: "Conta Corrente",
  institution_id: "inst-3",
  institution_name: "Banco Z",
  currency_code: "BRL",
  portfolio_id: null,
  account_type: "CHECKING",
};

export const petr4: AssetRead = {
  id: "asset-petr4",
  ticker: "PETR4",
  name: "Petrobras",
  asset_class_code: "STOCK_BR",
  country: "BR",
  currency_code: "BRL",
};

export const aapl: AssetRead = {
  id: "asset-aapl",
  ticker: "AAPL",
  name: "Apple",
  asset_class_code: "STOCK_US",
  country: "US",
  currency_code: "USD",
};

export const currencies: CurrencyRead[] = [
  { code: "BRL", name: "Real brasileiro" },
  { code: "USD", name: "Dólar americano" },
];

export function makeHistoryTransaction(overrides: Partial<TransactionRead> = {}): TransactionRead {
  return makeTransaction({ id: "tx-1", account_id: brlAccount.id, asset_id: petr4.id, ...overrides });
}

export function makeImportRow(overrides: Partial<ImportRow> = {}): ImportRow {
  return {
    row_index: 0,
    transaction_type: "BUY",
    asset_ticker: "PETR4",
    asset_id: petr4.id,
    quantity: "100",
    unit_price: "30.55",
    fees: "1.5",
    gross_amount: "3055",
    currency_code: "BRL",
    transaction_date: "2026-01-05",
    external_reference: "fp:0",
    is_exact_duplicate: false,
    possible_duplicate: false,
    duplicate_reason: null,
    error: null,
    ...overrides,
  };
}

export const previewFixture: ImportPreviewResponse = {
  account_id: brlAccount.id,
  source_format: "CSV",
  signature: "assinatura-do-servidor",
  rows: [
    makeImportRow({ row_index: 0 }),
    makeImportRow({
      row_index: 1,
      asset_ticker: "XPTO3",
      asset_id: null,
      error: "ativo 'XPTO3' não cadastrado — cadastre manualmente antes de importar",
    }),
    makeImportRow({ row_index: 2, is_exact_duplicate: true, transaction_date: "2026-01-06" }),
    makeImportRow({
      row_index: 3,
      possible_duplicate: true,
      duplicate_reason: "encontrada 1 transação ativa existente com os mesmos dados",
      transaction_date: "2026-01-07",
    }),
    makeImportRow({ row_index: 4, transaction_type: "DEPOSIT", asset_ticker: null, asset_id: null, quantity: null, unit_price: null, gross_amount: "500", transaction_date: "2026-01-08" }),
  ],
};
