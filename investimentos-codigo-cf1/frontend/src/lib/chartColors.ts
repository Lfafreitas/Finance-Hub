// Paleta dos gráficos: os 6 primeiros slots categóricos da paleta de
// referência, versão para fundo escuro, validados contra o fundo dos
// painéis (#141b1f) — faixa de luminosidade, croma, separação para
// daltonismo entre vizinhos e contraste ≥ 3:1 passaram.
//
// A cor segue a ENTIDADE, nunca a posição: "Renda fixa" é sempre a
// mesma cor, apareça em que ordem aparecer.

export const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"] as const;

/** Cor de cada fatia do patrimônio (chaves do backend, na ordem dos slots). */
export const PART_COLORS: Record<string, string> = {
  VARIABLE: SERIES[0],
  FIXED: SERIES[1],
  RESERVE: SERIES[2],
  LIQUID: SERIES[3],
  FUND: SERIES[4],
  OTHER: SERIES[5],
};

export const INCOME_COLOR = SERIES[0];
export const EXPENSE_COLOR = SERIES[1];

/** Cor única para barras de magnitude (um só tipo de dado). */
export const MAGNITUDE_COLOR = SERIES[0];

export const GRID_COLOR = "#24313a";
export const AXIS_TEXT_COLOR = "#9eadb6";

/**
 * Cor de cada classe de ativo nos indicadores (a cor segue a classe). São
 * 16 classes e 6 cores validadas: cada FAMÍLIA tem a sua (fundos de
 * índice, renda fixa, ações, imobiliário, fundos, cripto), nunca uma cor
 * gerada. Antes só as classes do exterior tinham cor e, numa carteira em
 * reais, "ETF (Brasil)" e "Tesouro Direto" saíam com a mesma.
 */
export const CLASS_COLORS: Record<string, string> = {
  ETF_US: SERIES[0],
  ETF_BR: SERIES[0],
  BOND: SERIES[1],
  TESOURO_DIRETO: SERIES[1],
  CDB: SERIES[1],
  LCI: SERIES[1],
  LCA: SERIES[1],
  DEBENTURE: SERIES[1],
  SAVINGS: SERIES[1],
  STOCK_US: SERIES[2],
  STOCK_BR: SERIES[2],
  BDR: SERIES[2],
  REIT: SERIES[3],
  FII: SERIES[3],
  FUND: SERIES[4],
  CRYPTO: SERIES[5],
};

export function classColor(assetClass: string): string {
  return CLASS_COLORS[assetClass] ?? SERIES[5];
}
