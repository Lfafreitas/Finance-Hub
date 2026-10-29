import type { InboxFileResult } from "../api/cashflowTypes";

export function plural(count: number, one: string, many: string): string {
  return count === 1 ? `1 ${one}` : `${count} ${many}`;
}

/** Uma linha curta sobre o que aconteceu com um arquivo da pasta Entrada. */
export function describeInboxFile(file: InboxFileResult): string {
  if (file.status === "IMPORTED") {
    const parts = [plural(file.imported_count, "lançamento novo", "lançamentos novos")];
    if (file.duplicate_count > 0) parts.push(`${file.duplicate_count} já existiam`);
    if (file.error_rows > 0) parts.push(plural(file.error_rows, "linha com erro", "linhas com erro"));
    if (file.matched_transfers > 0)
      parts.push(plural(file.matched_transfers, "pagamento de fatura ligado", "pagamentos de fatura ligados"));
    return `${file.account_name} · ${parts.join(" · ")}`;
  }
  if (file.status === "NOTHING_NEW") return `${file.account_name} · tudo já estava no app`;
  return file.message ?? "";
}
