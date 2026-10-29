import { MASK, isPrivate } from "./privacy";

/** Símbolo da moeda ("R$", "US$") para o valor escondido no modo privacidade. */
function currencySymbol(currencyCode: string): string {
  try {
    const part = (0)
      .toLocaleString("pt-BR", { style: "currency", currency: currencyCode })
      .replace(/[\d.,\s\u00a0-]/g, "");
    return part || currencyCode;
  } catch {
    return currencyCode;
  }
}

/** Valor escondido: "US$ •••••". */
export function maskedCurrency(currencyCode: string): string {
  return `${currencySymbol(currencyCode)} ${MASK}`;
}

/**
 * Formata, SÓ para apresentação, um valor que já veio calculado do
 * backend, na moeda informada. Não converte nada: `currencyCode` é a
 * moeda em que o valor já está.
 */
export function formatCurrency(value: string, currencyCode: string, maximumFractionDigits = 2): string {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return value;
  if (isPrivate()) return maskedCurrency(currencyCode);
  try {
    return numeric.toLocaleString("pt-BR", {
      style: "currency",
      currency: currencyCode,
      maximumFractionDigits,
    });
  } catch {
    // Código que o Intl não aceita: mostra o código cru + o valor do
    // backend, sem inventar símbolo nem cair em outra moeda.
    return `${currencyCode} ${value}`;
  }
}

/**
 * Formata como percentual uma FRAÇÃO que já veio calculada do backend
 * (0.10 → "10,00%"). Só apresentação.
 */
export function formatPercent(value: string): string {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return value;
  return numeric.toLocaleString("pt-BR", {
    style: "percent",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Data ISO (AAAA-MM-DD) → DD/MM/AAAA, sem passar por fuso horário. */
export function formatIsoDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value;
}

/**
 * Quantidade para leitura: até 8 casas, sem zeros à direita
 * ("150.00000000" → "150"). O valor exato do backend fica no `title`
 * de quem exibe.
 */
export function formatQuantity(value: string): string {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return value;
  // Quantidade × preço revela o valor: some junto.
  if (isPrivate()) return MASK;
  return numeric.toLocaleString("pt-BR", { maximumFractionDigits: 8 });
}

/**
 * Valor com sinal explícito para "quanto rendeu": "+US$ 10,70",
 * "-R$ 5,00", "R$ 0,00". Só apresentação.
 */
export function formatSignedCurrency(value: string, currencyCode: string): string {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return value;
  if (isPrivate()) return maskedCurrency(currencyCode);
  const formatted = formatCurrency(String(Math.abs(numeric)), currencyCode);
  if (numeric > 0) return `+${formatted}`;
  if (numeric < 0) return `-${formatted}`;
  return formatted;
}

/** Eixo de gráfico: "R$ 1,2 mil", "US$ 300". Só apresentação. */
export function formatCompactCurrency(value: number, currencyCode: string): string {
  if (isPrivate()) return maskedCurrency(currencyCode);
  try {
    return value.toLocaleString("pt-BR", {
      style: "currency",
      currency: currencyCode,
      notation: "compact",
      minimumFractionDigits: 0,
      maximumFractionDigits: 1,
    });
  } catch {
    return `${currencyCode} ${value}`;
  }
}

/** Fração com sinal: 0.0357 → "+3,57%". */
export function formatSignedPercent(value: string): string {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return value;
  const text = formatPercent(String(Math.abs(numeric)));
  if (numeric > 0) return `+${text}`;
  if (numeric < 0) return `-${text}`;
  return text;
}
