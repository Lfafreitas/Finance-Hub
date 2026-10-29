import type {
  CashflowEntryFilters,
  CashflowEntryRead,
  CashflowImportProfile,
  CashflowImportRow,
  CashflowNature,
  CategoryRead,
  RuleDirection,
  RuleMatchType,
} from "../api/cashflowTypes";
import type { AccountRead } from "../api/types";

export const NATURE_LABELS: Record<CashflowNature, string> = {
  INCOME: "Renda",
  EXPENSE: "Gasto",
  THIRD_PARTY: "Terceiros",
  TRANSFER: "Transferência",
  ADJUSTMENT: "Ajuste",
  UNCLASSIFIED: "Não classificado",
};

/**
 * Naturezas que a classificação manual aceita. Transferência fica de
 * fora: ela tem contraparte e é criada pela ação "Transferência".
 */
export const MANUAL_NATURES: CashflowNature[] = ["EXPENSE", "INCOME", "THIRD_PARTY", "ADJUSTMENT", "UNCLASSIFIED"];

/** Uma regra sempre decide uma natureza de verdade. */
export const RULE_NATURES: CashflowNature[] = ["EXPENSE", "INCOME", "THIRD_PARTY", "ADJUSTMENT"];

export const MATCH_TYPE_LABELS: Record<RuleMatchType, string> = {
  CONTAINS: "contém",
  EQUALS: "é igual a",
  STARTS_WITH: "começa com",
};

export const DIRECTION_LABELS: Record<RuleDirection, string> = {
  ANY: "Entradas e saídas",
  IN: "Só entradas",
  OUT: "Só saídas",
};

export const IMPORT_PROFILE_LABELS: Record<CashflowImportProfile, string> = {
  NUBANK_ACCOUNT_CSV: "Nubank — extrato da conta (CSV)",
  NUBANK_ACCOUNT_OFX: "Nubank — extrato da conta (OFX)",
  NUBANK_CARD_CSV: "Nubank — fatura do cartão (CSV)",
  NUBANK_CARD_OFX: "Nubank — fatura do cartão (OFX)",
  NUBANK_CARD_PDF: "Nubank — fatura do cartão (PDF)",
};

/** Contas do livro de caixa: todas, menos as de investimentos. */
export function cashAccounts(accounts: AccountRead[]): AccountRead[] {
  return accounts.filter((account) => account.account_type !== "BROKERAGE");
}

export function isOutflow(amount: string): boolean {
  return amount.trim().startsWith("-");
}

export interface CategoryOption {
  id: string;
  /** "Mãe › Filha" para subcategoria; só o nome para categoria-mãe. */
  label: string;
  isChild: boolean;
}

/** Árvore achatada em ordem alfabética: cada mãe seguida das filhas. */
export function categoryOptions(categories: CategoryRead[]): CategoryOption[] {
  const byName = (a: CategoryRead, b: CategoryRead) => a.name.localeCompare(b.name, "pt-BR");
  const roots = categories.filter((category) => category.parent_id === null).sort(byName);
  const options: CategoryOption[] = [];
  for (const root of roots) {
    options.push({ id: root.id, label: root.name, isChild: false });
    for (const child of categories.filter((category) => category.parent_id === root.id).sort(byName)) {
      options.push({ id: child.id, label: `${root.name} › ${child.name}`, isChild: true });
    }
  }
  return options;
}

export function categoryLabel(categories: CategoryRead[], categoryId: string | null): string | null {
  if (categoryId === null) return null;
  return categoryOptions(categories).find((option) => option.id === categoryId)?.label ?? null;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/** Data local de hoje em AAAA-MM-DD (sem passar por UTC). */
export function todayIso(now: Date = new Date()): string {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Mês local corrente em AAAA-MM. */
export function currentMonth(now: Date = new Date()): string {
  return todayIso(now).slice(0, 7);
}

/** Primeiro e último dia de um mês AAAA-MM; `null` se o texto não for um mês. */
export function monthRange(month: string): { start: string; end: string } | null {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) return null;
  const year = Number(match[1]);
  const monthNumber = Number(match[2]);
  if (monthNumber < 1 || monthNumber > 12) return null;
  const lastDay = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  return { start: `${month}-01`, end: `${month}-${pad(lastDay)}` };
}

/** Desloca uma data ISO em N dias (para a janela de busca da outra ponta). */
export function shiftIsoDate(value: string, days: number): string {
  const [year, month, day] = value.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  return `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())}`;
}

/**
 * Valor oposto como TEXTO ("-10.5000" ↔ "10.5000"). Só troca o sinal;
 * não faz conta com dinheiro.
 */
export function negateAmount(amount: string): string {
  const trimmed = amount.trim();
  return trimmed.startsWith("-") ? trimmed.slice(1) : `-${trimmed}`;
}

/**
 * Valor digitado → texto decimal que o backend aceita, ou `null` se
 * não for um valor positivo com até 4 casas. Aceita vírgula decimal
 * ("1.234,56" → "1234.56") e ponto decimal ("1234.56"). É só troca de
 * texto: nenhuma conta com dinheiro.
 */
export function parseAmountInput(text: string): string | null {
  let value = text.replace(/\s/g, "");
  if (value.includes(",")) value = value.replace(/\./g, "").replace(",", ".");
  if (!/^\d+(\.\d{1,4})?$/.test(value)) return null;
  if (/^0+(\.0+)?$/.test(value)) return null;
  return value;
}

/** Mesma folga que o backend aceita na ligação manual de transferência. */
export const LINK_WINDOW_DAYS = 10;

/**
 * A outra ponta de uma transferência só pode ser um lançamento de OUTRA
 * conta, na mesma moeda, com o valor exatamente oposto, ativo e ainda
 * não ligado.
 */
export function isCounterpartyCandidate(entry: CashflowEntryRead, other: CashflowEntryRead): boolean {
  return (
    other.id !== entry.id &&
    other.account_id !== entry.account_id &&
    other.currency_code === entry.currency_code &&
    other.status === "ACTIVE" &&
    other.nature !== "TRANSFER" &&
    other.amount === negateAmount(entry.amount)
  );
}

/** Só entra na importação o que o backend aceitaria: sem erro e ainda não importado. */
export function isCashRowImportable(row: CashflowImportRow): boolean {
  return row.error === null && !row.is_duplicate;
}

/** Prioridade válida de regra: inteiro de 0 a 100000, como o backend aceita. */
export function parsePriority(text: string): number | null {
  if (!/^\d{1,6}$/.test(text.trim())) return null;
  const value = Number(text.trim());
  return value <= 100000 ? value : null;
}

/** Lançamentos por página na lista do livro de caixa. */
export const PAGE_SIZE = 50;

/** Filtros como o formulário os guarda: tudo texto, "" = sem filtro. */
export interface FilterDraft {
  accountId: string;
  start: string;
  end: string;
  nature: string;
  /** "" = todas; "none" = sem categoria; senão o id. */
  category: string;
  search: string;
  includeReversed: boolean;
}

export const EMPTY_FILTER_DRAFT: FilterDraft = {
  accountId: "",
  start: "",
  end: "",
  nature: "",
  category: "",
  search: "",
  includeReversed: false,
};

export function toFilterDraft(filters: CashflowEntryFilters): FilterDraft {
  return {
    accountId: filters.account_id ?? "",
    start: filters.start ?? "",
    end: filters.end ?? "",
    nature: filters.nature ?? "",
    category: filters.uncategorized ? "none" : (filters.category_id ?? ""),
    search: filters.search ?? "",
    includeReversed: filters.include_reversed ?? false,
  };
}

/** Só vira filtro o que foi preenchido: campo vazio não vai para a API. */
export function toEntryFilters(draft: FilterDraft): CashflowEntryFilters {
  const filters: CashflowEntryFilters = {};
  if (draft.accountId) filters.account_id = draft.accountId;
  if (draft.start) filters.start = draft.start;
  if (draft.end) filters.end = draft.end;
  if (draft.nature) filters.nature = draft.nature as CashflowNature;
  if (draft.category === "none") filters.uncategorized = true;
  else if (draft.category) filters.category_id = draft.category;
  if (draft.search.trim()) filters.search = draft.search.trim();
  if (draft.includeReversed) filters.include_reversed = true;
  return filters;
}
