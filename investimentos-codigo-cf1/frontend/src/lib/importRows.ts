import type { ImportRow } from "../api/types";

/** Uma linha só pode ser importada se não tem erro e não é duplicata exata. */
export function isRowSelectable(row: ImportRow): boolean {
  return row.error === null && !row.is_exact_duplicate;
}
