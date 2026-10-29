// Análises do Claude no dashboard (Análises-2). O relatório é escrito
// pela tarefa agendada do Claude e validado pelo backend; aqui ele é
// só exibido, sempre como texto.

import { request } from "./client";

export type Signal = "POSITIVO" | "NEUTRO" | "ATENCAO";

export interface SourceLink {
  title: string;
  url: string;
}

export type MetricCode =
  | "RETURN_1M"
  | "RETURN_YTD"
  | "RETURN_1Y"
  | "RETURN_3Y_ANNUALIZED"
  | "DIVIDEND_YIELD"
  | "EXPENSE_RATIO"
  | "OCCUPANCY"
  | "EARNINGS_GROWTH"
  | "YIELD_TO_MATURITY"
  | "PE_TTM"
  | "PE_FORWARD"
  | "P_FFO"
  | "PRICE_TO_BOOK"
  | "BETA"
  | "DEBT_TO_EBITDA";

/** Indicador de mercado com número, data e fonte (relatório v2). */
export interface KeyMetric {
  code: MetricCode;
  value: number;
  as_of: string;
  source: string;
  url?: string | null;
}

export interface HoldingReading {
  ticker: string;
  signal: Signal;
  reading: string;
  metrics: { label: string; value: string; context: string | null }[];
  key_metrics?: KeyMetric[];
  sources: SourceLink[];
}

export interface ReviewPoint {
  title: string;
  detail: string;
  tickers: string[];
}

/** Avaliação da carteira pelo Claude (relatório v2). */
export interface PortfolioReview {
  overall: string;
  good: ReviewPoint[];
  attention: ReviewPoint[];
  risks: ReviewPoint[];
  improve: ReviewPoint[];
}

export interface NewsItem {
  ticker: string | null;
  topic: string;
  title: string;
  source: string;
  url: string;
  published_at: string | null;
  summary: string;
}

export interface ResearchItem {
  house: string;
  title: string;
  url: string;
  published_at: string | null;
  summary: string;
  relevance: string | null;
}

export interface WatchItem {
  topic: string;
  why: string;
  date: string | null;
}

/** Número do mercado para a faixa do topo do jornal (relatório v3). */
export interface MarketPulse {
  label: string;
  value: string;
  change: string | null;
  direction: "UP" | "DOWN" | "FLAT" | null;
  as_of: string;
  source: string;
}

/** Ideia para estudar (relatório v3) — nunca ordem de compra. */
export interface Opportunity {
  title: string;
  thesis: string;
  tickers: string[];
  relation: string | null;
  why_now: string;
  risks: string[];
  how_to_follow: string;
  sources: SourceLink[];
}

export interface EtfComposition {
  etf: string;
  as_of: string;
  source: string;
  url: string | null;
  top: { name: string; ticker: string | null; weight: number }[];
}

/** Leitura de uma fonte cadastrada pelo usuário (relatório v4). */
export interface PaperItem {
  source: string;
  title: string;
  url: string;
  published_at: string | null;
  summary: string;
  takeaways: string[];
  relation: string | null;
}

export interface InsightReport {
  schema_version: 1 | 2 | 3 | 4;
  generated_at: string;
  headline: string;
  summary: string[];
  holdings: HoldingReading[];
  news: NewsItem[];
  research: ResearchItem[];
  watch: WatchItem[];
  portfolio_review?: PortfolioReview | null;
  market?: MarketPulse[];
  opportunities?: Opportunity[];
  etf_holdings?: EtfComposition[];
  papers?: PaperItem[];
  disclaimer: string;
}

export interface InsightReportRead {
  report_date: string;
  report: InsightReport;
}

export interface InsightIndex {
  latest: InsightReportRead | null;
  history: { report_date: string; headline: string }[];
  invalid_files: { file_name: string; error: string }[];
  snapshot_written_at: string | null;
}

export function getInsights(): Promise<InsightIndex> {
  return request<InsightIndex>("/insights");
}

export function getInsight(reportDate: string): Promise<InsightReportRead> {
  return request<InsightReportRead>(`/insights/${reportDate}`);
}

/** Atualiza o retrato da carteira que a análise diária do Claude lê. */
export function writeSnapshot(): Promise<{ written_at: string; positions: number }> {
  return request<{ written_at: string; positions: number }>("/insights/snapshot", { method: "POST" });
}

// --- Alertas de hora em hora ---------------------------------------------------

export type AlertSeverity = "ALTA" | "CRITICA";

export interface Alert {
  id: string;
  detected_at: string;
  severity: AlertSeverity;
  tickers: string[];
  title: string;
  summary: string;
  why_it_matters: string;
  sources: SourceLink[];
}

export interface AlertRead {
  day: string;
  read: boolean;
  alert: Alert;
}

export interface AlertIndex {
  alerts: AlertRead[];
  unread_count: number;
  invalid_files: { file_name: string; error: string }[];
}

export function getAlerts(days = 7): Promise<AlertIndex> {
  return request<AlertIndex>(`/insights/alerts?days=${days}`);
}

export function markAlertRead(alertId: string): Promise<AlertIndex> {
  return request<AlertIndex>(`/insights/alerts/${encodeURIComponent(alertId)}/read`, { method: "POST" });
}

export function markAllAlertsRead(): Promise<AlertIndex> {
  return request<AlertIndex>("/insights/alerts/read-all", { method: "POST" });
}

// --- Conversa com o Claude (pela assinatura) -------------------------------------

/** Resumo da carteira em texto, para levar junto com a pergunta. */
export function getChatContext(): Promise<{ text: string }> {
  return request<{ text: string }>("/insights/chat-context");
}

// --- Empresas por trás dos ETFs ---------------------------------------------------

export interface CompanyExposure {
  name: string;
  ticker: string | null;
  weight: string;
  via: { ticker: string; weight: string }[];
}

/** Pesos em 0..1 sobre os investimentos da moeda; `explained` é um piso. */
export interface CurrencyLookThrough {
  currency_code: string;
  companies: CompanyExposure[];
  funds: { ticker: string; weight: string; coverage: string; as_of: string; source: string }[];
  missing: string[];
  explained: string;
}

export interface LookThrough {
  report_date: string | null;
  currencies: CurrencyLookThrough[];
}

export function getLookThrough(): Promise<LookThrough> {
  return request<LookThrough>("/insights/lookthrough");
}
