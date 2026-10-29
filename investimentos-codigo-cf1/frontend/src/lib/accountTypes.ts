import type { AccountRead, AccountType } from "../api/types";

/** Ordem de exibição no cadastro: investimentos primeiro (era o único tipo). */
export const ACCOUNT_TYPES: AccountType[] = ["BROKERAGE", "CHECKING", "SAVINGS", "CREDIT_CARD", "CASH"];

export const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  BROKERAGE: "Investimentos",
  CHECKING: "Conta corrente",
  SAVINGS: "Reserva",
  CREDIT_CARD: "Cartão de crédito",
  CASH: "Dinheiro",
};

/**
 * As telas de investimentos (lançamentos, importação, reconciliação)
 * só oferecem contas BROKERAGE: o backend recusa lançamento de
 * investimento em conta do livro de caixa.
 */
export function investmentAccounts(accounts: AccountRead[]): AccountRead[] {
  return accounts.filter((account) => account.account_type === "BROKERAGE");
}
