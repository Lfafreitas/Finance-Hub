// Rótulos e formatação SÓ de apresentação da tela de reconciliação.
// Nada aqui decide igualdade/diferença — isso vem pronto do backend.

import type { TransactionSource } from "../api/types";

export const FIELD_LABELS: Record<string, string> = {
  transaction_date: "Data",
  quantity: "Quantidade",
  unit_price: "Preço unitário",
  gross_amount: "Valor bruto",
  fees: "Taxas",
  currency_code: "Moeda",
  fx_rate_to_brl: "Câmbio para BRL",
};

export const SOURCE_LABELS: Record<TransactionSource, string> = {
  MANUAL: "Lançamento manual",
  IMPORT_CSV: "Importação CSV",
  IMPORT_XLSX: "Importação XLSX",
  IMPORT_OFX: "Importação OFX",
  IMPORT_PDF: "Importação PDF",
  API_PLUGGY: "API Pluggy",
};

export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

export function sourceLabel(source: TransactionSource): string {
  return SOURCE_LABELS[source] ?? source;
}

/** UUID abreviado para caber em tabela; o valor completo vai no `title`. */
export function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

export function formatDateTime(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/**
 * Diferença absoluta de um campo, com unidade quando o campo é data
 * (o backend devolve a diferença de `transaction_date` em DIAS).
 */
export function formatAbsoluteDifference(field: string, value: string | null): string {
  if (value === null) return "—";
  if (field === "transaction_date") return value === "1" ? "1 dia" : `${value} dias`;
  return value;
}

/**
 * A diferença relativa chega como fração exata (ex.:
 * "0.09090909090909090909090909091"). Aqui ela só é ARREDONDADA para
 * leitura ("9,09%") — o valor exato continua disponível no `title` da
 * célula. Não é recálculo: o número é o do backend.
 */
export function formatRelativeDifference(value: string | null): string {
  if (value === null) return "—";
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return value;
  return numeric.toLocaleString("pt-BR", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
