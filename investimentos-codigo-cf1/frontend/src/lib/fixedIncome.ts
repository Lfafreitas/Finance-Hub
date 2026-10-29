// Renda fixa no cadastro: classes que vencem e a taxa digitada em % ao ano.

export const FIXED_INCOME_CLASSES: ReadonlySet<string> = new Set([
  "TESOURO_DIRETO",
  "CDB",
  "LCI",
  "LCA",
  "DEBENTURE",
  "BOND",
]);

export function isFixedIncome(assetClass: string): boolean {
  return FIXED_INCOME_CLASSES.has(assetClass);
}

/**
 * "3,85" (ou "3.85") % ao ano → fração "0.0385" para o backend.
 * Vazio → null. Texto que não é taxa entre 0 e 100 → "invalid".
 */
export function parseRatePercent(text: string, maxDecimals = 4): string | null | "invalid" {
  const clean = text.replace("%", "").trim().replace(",", ".");
  if (clean === "") return null;
  if (!new RegExp(`^\\d{1,3}(\\.\\d{1,${maxDecimals}})?$`).test(clean)) return "invalid";
  const [whole, frac = ""] = clean.split(".");
  // Em milionésimos (6 casas da fração = 4 casas do percentual), sem
  // ponto flutuante: "3.85" → 38500 → "0.0385".
  const micro = Number(whole) * 10000 + Number(frac.padEnd(4, "0"));
  if (micro > 1_000_000) return "invalid";
  const text6 = String(micro).padStart(7, "0");
  const fraction = `${text6.slice(0, -6)}.${text6.slice(-6)}`.replace(/0+$/, "").replace(/\.$/, "");
  return fraction;
}

/** Fração do backend ("0.038500") → texto do campo em % ("3,85"). */
export function rateToPercentText(fraction: string | null | undefined): string {
  if (fraction == null) return "";
  const n = Number(fraction) * 100;
  return n.toLocaleString("pt-BR", { maximumFractionDigits: 4, useGrouping: false });
}
