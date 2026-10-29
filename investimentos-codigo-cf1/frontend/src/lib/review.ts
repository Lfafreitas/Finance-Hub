import type { CashflowNature, RuleDirection, RuleWrite } from "../api/cashflowTypes";
import type { PendingGroup } from "../api/review";

/** Só saídas → regra só para saídas; só entradas → só entradas; misto → as duas. */
export function ruleDirection(group: PendingGroup): RuleDirection {
  if (group.inflows === 0) return "OUT";
  if (group.outflows === 0) return "IN";
  return "ANY";
}

/** Nome legível da regra: a descrição de exemplo, sem documento e banco. */
export function ruleName(group: PendingGroup): string {
  const parts = group.sample_description.split(" - ");
  const name = parts.length > 1 ? `${parts[0]} - ${parts[1]}` : parts[0];
  return name.trim().slice(0, 120) || group.match_text.slice(0, 120);
}

/** A regra que classifica este texto sozinho nas próximas importações. */
export function ruleFromGroup(group: PendingGroup, nature: CashflowNature, categoryId: string | null): RuleWrite {
  return {
    name: ruleName(group),
    priority: 100,
    is_active: true,
    match_type: "CONTAINS",
    pattern: group.match_text.slice(0, 200),
    direction: ruleDirection(group),
    account_id: null,
    set_nature: nature,
    set_category_id: categoryId,
    tag_ids: [],
  };
}

/** "jan/2025 – set/2026", ou um mês só. */
export function periodLabel(first: string, last: string): string {
  const names = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const month = (iso: string) => `${names[Number(iso.slice(5, 7)) - 1]}/${iso.slice(0, 4)}`;
  return first.slice(0, 7) === last.slice(0, 7) ? month(first) : `${month(first)} – ${month(last)}`;
}

/** Pagamento de fatura é transferência conta → cartão, não gasto. */
export function isInvoicePayment(group: PendingGroup): boolean {
  return group.match_text.startsWith("pagamento de fatura");
}
