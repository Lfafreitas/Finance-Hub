// Regras de FORMULÁRIO por tipo de transação: quais campos mostrar e
// quais exigir. Espelham a validação do backend
// (`_validate_transaction_data`), que continua sendo quem decide — isto
// aqui só evita o usuário preencher um campo que seria recusado.

import type { ManualTransactionType } from "../api/types";

type FieldRule = "required" | "optional" | "hidden";

export interface TransactionTypeRule {
  label: string;
  asset: FieldRule;
  quantity: FieldRule;
  unitPrice: FieldRule;
  /** Texto de ajuda da quantidade, quando o sinal ou o sentido não é óbvio. */
  quantityHint?: string;
}

export const TRANSACTION_TYPE_RULES: Record<ManualTransactionType, TransactionTypeRule> = {
  BUY: { label: "Compra", asset: "required", quantity: "required", unitPrice: "required" },
  SELL: { label: "Venda", asset: "required", quantity: "required", unitPrice: "required" },
  DIVIDEND: { label: "Dividendo", asset: "required", quantity: "hidden", unitPrice: "hidden" },
  JCP: { label: "JCP", asset: "required", quantity: "hidden", unitPrice: "hidden" },
  INCOME: { label: "Rendimento", asset: "optional", quantity: "hidden", unitPrice: "hidden" },
  FEE: { label: "Taxa avulsa", asset: "optional", quantity: "hidden", unitPrice: "hidden" },
  DEPOSIT: { label: "Depósito", asset: "hidden", quantity: "hidden", unitPrice: "hidden" },
  WITHDRAWAL: { label: "Retirada", asset: "hidden", quantity: "hidden", unitPrice: "hidden" },
  BONUS_SHARES: {
    label: "Bonificação",
    asset: "required",
    quantity: "required",
    unitPrice: "hidden",
    quantityHint: "Quantidade recebida (positiva).",
  },
  STOCK_SPLIT: {
    label: "Desdobramento",
    asset: "required",
    quantity: "required",
    unitPrice: "hidden",
    quantityHint: "Quantidade ACRESCENTADA à posição (positiva).",
  },
  REVERSE_SPLIT: {
    label: "Grupamento",
    asset: "required",
    quantity: "required",
    unitPrice: "hidden",
    quantityHint: "Variação de quantidade, NEGATIVA (ex.: -50).",
  },
};

export const MANUAL_TRANSACTION_TYPES = Object.keys(TRANSACTION_TYPE_RULES) as ManualTransactionType[];

const ALL_TYPE_LABELS: Record<string, string> = {
  ...Object.fromEntries(Object.entries(TRANSACTION_TYPE_RULES).map(([type, rule]) => [type, rule.label])),
  TRANSFER_OUT: "Transferência (saída)",
  TRANSFER_IN: "Transferência (entrada)",
  FX_CONVERSION: "Conversão de câmbio",
};

export function transactionTypeLabel(type: string): string {
  return ALL_TYPE_LABELS[type] ?? type;
}

/** Eventos societários não movimentam dinheiro: o valor bruto é sempre zero. */
export function hasNoCashAmount(type: ManualTransactionType): boolean {
  return type === "BONUS_SHARES" || type === "STOCK_SPLIT" || type === "REVERSE_SPLIT";
}
