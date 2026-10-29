// Anotações (pensamentos sobre a carteira ou qualquer assunto, trechos
// destacados na leitura) e as fontes de leitura do Jornal.

import { request } from "./client";

export interface Note {
  id: string;
  title: string | null;
  body: string;
  quote: string | null;
  source_title: string | null;
  source_url: string | null;
  tickers: string[];
  pinned: boolean;
  share_with_claude: boolean;
  created_at: string;
  updated_at: string;
}

export type NoteWrite = Omit<Note, "id" | "created_at" | "updated_at">;

export interface ReadingSource {
  id: string;
  name: string;
  url: string;
  focus: string | null;
  active: boolean;
}

export type SourceWrite = Omit<ReadingSource, "id">;

export function getNotes(search?: string): Promise<Note[]> {
  const query = search && search.trim() ? `?search=${encodeURIComponent(search.trim())}` : "";
  return request<Note[]>(`/notes${query}`);
}

export function createNote(note: Partial<NoteWrite>): Promise<Note> {
  return request<Note>("/notes", { method: "POST", body: note });
}

export function updateNote(id: string, note: NoteWrite): Promise<Note> {
  return request<Note>(`/notes/${encodeURIComponent(id)}`, { method: "PUT", body: note });
}

export function deleteNote(id: string): Promise<void> {
  return request<void>(`/notes/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function getSources(): Promise<ReadingSource[]> {
  return request<ReadingSource[]>("/reading-sources");
}

export function createSource(source: Partial<SourceWrite>): Promise<ReadingSource> {
  return request<ReadingSource>("/reading-sources", { method: "POST", body: source });
}

export function updateSource(id: string, source: SourceWrite): Promise<ReadingSource> {
  return request<ReadingSource>(`/reading-sources/${encodeURIComponent(id)}`, { method: "PUT", body: source });
}

export function deleteSource(id: string): Promise<void> {
  return request<void>(`/reading-sources/${encodeURIComponent(id)}`, { method: "DELETE" });
}
