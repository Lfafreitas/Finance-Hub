// Revisão do que falta classificar (Painel-1).

import type { CashflowNature } from "./cashflowTypes";
import { request } from "./client";

export interface PendingEntry {
  id: string;
  account_id: string;
  entry_date: string;
  amount: string;
  description: string;
}

export interface Suggestion {
  nature: CashflowNature;
  category_id: string | null;
  /** Quantas vezes você já classificou este texto assim. */
  evidence: number;
  /** Fatia do seu histórico com este texto (0..1). */
  share: string;
}

export interface PendingGroup {
  match_text: string;
  currency_code: string;
  sample_description: string;
  count: number;
  total: string;
  inflows: number;
  outflows: number;
  first_date: string;
  last_date: string;
  entry_ids: string[];
  preview: PendingEntry[];
  suggestion: Suggestion | null;
}

export interface PendingGroups {
  pending_entries: number;
  pending_groups: number;
  groups: PendingGroup[];
}

export interface BatchClassificationWrite {
  entry_ids: string[];
  nature: CashflowNature;
  category_id: string | null;
  tag_ids: string[];
}

export function getPendingGroups(limit = 50): Promise<PendingGroups> {
  return request<PendingGroups>(`/cashflow/pending/groups?limit=${limit}`);
}

export function classifyBatch(payload: BatchClassificationWrite): Promise<{ classified: number }> {
  return request<{ classified: number }>("/cashflow/entries/classify-batch", { method: "POST", body: payload });
}
