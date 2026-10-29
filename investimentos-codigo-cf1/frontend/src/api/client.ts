import type {
  AccountCreate,
  AccountRead,
  AssetClassRead,
  AssetCreate,
  AssetLatestPrice,
  AssetPriceRead,
  AssetPriceWrite,
  AssetRead,
  CurrencyRead,
  DashboardSummary,
  ImportCommitResult,
  ImportPreviewResponse,
  ImportSourceFormat,
  InstitutionCreate,
  InstitutionRead,
  PortfolioCreate,
  PortfolioRead,
  ReconciliationComparisonRead,
  ReconciliationLogRead,
  ReconciliationResolveRequest,
  ReconciliationScanRequest,
  ReconciliationScanResult,
  TransactionCreate,
  TransactionRead,
  TransferCreate,
  TransferRead,
} from "./types";

// Mesma origem da página: o Vite repassa /api para o backend (ver
// vite.config.ts). Funciona no computador e no celular sem mudar nada.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

/** Disparado quando a API recusa por falta de Face ID (celular). */
export const LOCKED_EVENT = "dashboard-locked";

/**
 * Erro de uma resposta HTTP não-2xx. `status` permite à UI escolher a
 * mensagem certa (400/404/409/422) e `detail` carrega o texto que o
 * backend devolveu em `{"detail": ...}`. `message` mantém o formato
 * histórico `"<status> <statusText>: <corpo>"`.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;

  constructor(status: number, statusText: string, body: string) {
    super(`${status} ${statusText}: ${body}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = extractDetail(body);
  }
}

function extractDetail(body: string): string | null {
  try {
    const parsed: unknown = JSON.parse(body);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const detail = (parsed as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      // 422 do FastAPI: lista de erros de validação com `msg`.
      if (Array.isArray(detail)) {
        const messages = detail
          .map((item) =>
            item && typeof item === "object" && "msg" in item ? String((item as { msg: unknown }).msg) : null,
          )
          .filter((msg): msg is string => msg !== null);
        return messages.length > 0 ? messages.join("; ") : null;
      }
    }
  } catch {
    // corpo não é JSON — sem detalhe estruturado.
  }
  return null;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  /** Serializado como JSON. `undefined` = request sem corpo. */
  body?: unknown;
  /**
   * Corpo multipart (upload de arquivo). Sem `Content-Type` explícito:
   * o navegador precisa gerar o cabeçalho com o `boundary`.
   */
  formData?: FormData;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, formData } = options;
  const init: RequestInit = { method };
  if (formData !== undefined) {
    init.body = formData;
  } else if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, init);
  // No celular, a sessão do Face ID venceu: a trava aparece de novo.
  if (response.status === 401 && !path.startsWith("/auth/")) {
    window.dispatchEvent(new Event(LOCKED_EVENT));
  }
  if (!response.ok) {
    throw new ApiError(response.status, response.statusText, await response.text());
  }
  // 204: exclusão bem-sucedida não tem corpo.
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function getAccounts(): Promise<AccountRead[]> {
  return request<AccountRead[]>("/accounts");
}

export function getPortfolios(): Promise<PortfolioRead[]> {
  return request<PortfolioRead[]>("/portfolios");
}

export function getDashboardSummary(portfolioId: string | null): Promise<DashboardSummary> {
  const query = portfolioId ? `?portfolio_id=${encodeURIComponent(portfolioId)}` : "";
  return request<DashboardSummary>(`/dashboard/summary${query}`);
}

// --- Reconciliação (Fase 11) ---------------------------------------------

export function getPendingReconciliations(): Promise<ReconciliationLogRead[]> {
  return request<ReconciliationLogRead[]>("/reconciliation/pending");
}

export function getTransaction(transactionId: string): Promise<TransactionRead> {
  return request<TransactionRead>(`/transactions/${encodeURIComponent(transactionId)}`);
}

export function getReconciliationComparison(reconciliationId: string): Promise<ReconciliationComparisonRead> {
  return request<ReconciliationComparisonRead>(`/reconciliation/${encodeURIComponent(reconciliationId)}/comparison`);
}

export function resolveReconciliation(
  reconciliationId: string,
  payload: ReconciliationResolveRequest,
): Promise<ReconciliationLogRead> {
  return request<ReconciliationLogRead>(`/reconciliation/${encodeURIComponent(reconciliationId)}/resolve`, {
    method: "POST",
    body: payload,
  });
}

export function scanReconciliation(scope: ReconciliationScanRequest = {}): Promise<ReconciliationScanResult> {
  return request<ReconciliationScanResult>("/reconciliation/scan", { method: "POST", body: scope });
}

// --- Cadastros -------------------------------------------------------------

export function getCurrencies(): Promise<CurrencyRead[]> {
  return request<CurrencyRead[]>("/currencies");
}

export function getAssetClasses(): Promise<AssetClassRead[]> {
  return request<AssetClassRead[]>("/asset-classes");
}

export function getAssets(): Promise<AssetRead[]> {
  return request<AssetRead[]>("/assets");
}

export function createAsset(payload: AssetCreate): Promise<AssetRead> {
  return request<AssetRead>("/assets", { method: "POST", body: payload });
}

export function getInstitutions(): Promise<InstitutionRead[]> {
  return request<InstitutionRead[]>("/institutions");
}

export function createInstitution(payload: InstitutionCreate): Promise<InstitutionRead> {
  return request<InstitutionRead>("/institutions", { method: "POST", body: payload });
}

export function createAccount(payload: AccountCreate): Promise<AccountRead> {
  return request<AccountRead>("/accounts", { method: "POST", body: payload });
}

export function createPortfolio(payload: PortfolioCreate): Promise<PortfolioRead> {
  return request<PortfolioRead>("/portfolios", { method: "POST", body: payload });
}

// --- Lançamento manual -----------------------------------------------------

export function getAccountTransactions(accountId: string): Promise<TransactionRead[]> {
  return request<TransactionRead[]>(`/accounts/${encodeURIComponent(accountId)}/transactions`);
}

export function createTransaction(payload: TransactionCreate): Promise<TransactionRead> {
  return request<TransactionRead>("/transactions", { method: "POST", body: payload });
}

export function createTransfer(payload: TransferCreate): Promise<TransferRead> {
  return request<TransferRead>("/transfers", { method: "POST", body: payload });
}

// --- Importação ------------------------------------------------------------

export function previewImport(
  accountId: string,
  sourceFormat: ImportSourceFormat,
  file: File,
): Promise<ImportPreviewResponse> {
  const formData = new FormData();
  formData.append("account_id", accountId);
  formData.append("source_format", sourceFormat);
  formData.append("file", file);
  return request<ImportPreviewResponse>("/imports/preview", { method: "POST", formData });
}

/**
 * `preview` volta EXATAMENTE como veio do servidor: a assinatura cobre
 * o conteúdo das linhas, então o frontend só escolhe quais índices
 * incluir — nunca edita uma linha.
 */
export function commitImport(
  preview: ImportPreviewResponse,
  includedRowIndexes: number[],
): Promise<ImportCommitResult> {
  return request<ImportCommitResult>("/imports/commit", {
    method: "POST",
    body: {
      account_id: preview.account_id,
      source_format: preview.source_format,
      rows: preview.rows,
      signature: preview.signature,
      included_row_indexes: includedRowIndexes,
    },
  });
}

// --- Cotações (Fase 12) ------------------------------------------------------

export function getLatestPrices(): Promise<AssetLatestPrice[]> {
  return request<AssetLatestPrice[]>("/prices/latest");
}

/** PUT: informar de novo a cotação de uma data substitui a anterior. */
export function setAssetPrice(assetId: string, payload: AssetPriceWrite): Promise<AssetPriceRead> {
  return request<AssetPriceRead>(`/assets/${encodeURIComponent(assetId)}/prices`, {
    method: "PUT",
    body: payload,
  });
}

// --- Edição e exclusão de cadastros --------------------------------------
// PUT envia o cadastro inteiro (mesmo corpo da criação). DELETE só
// funciona para o que nunca foi usado; o backend responde 409 com o motivo.

export function updateInstitution(id: string, payload: InstitutionCreate): Promise<InstitutionRead> {
  return request<InstitutionRead>(`/institutions/${id}`, { method: "PUT", body: payload });
}

export function deleteInstitution(id: string): Promise<void> {
  return request<void>(`/institutions/${id}`, { method: "DELETE" });
}

export function updatePortfolio(id: string, payload: PortfolioCreate): Promise<PortfolioRead> {
  return request<PortfolioRead>(`/portfolios/${id}`, { method: "PUT", body: payload });
}

export function deletePortfolio(id: string): Promise<void> {
  return request<void>(`/portfolios/${id}`, { method: "DELETE" });
}

export function updateAccount(id: string, payload: AccountCreate): Promise<AccountRead> {
  return request<AccountRead>(`/accounts/${id}`, { method: "PUT", body: payload });
}

export function deleteAccount(id: string): Promise<void> {
  return request<void>(`/accounts/${id}`, { method: "DELETE" });
}

export function updateAsset(id: string, payload: AssetCreate): Promise<AssetRead> {
  return request<AssetRead>(`/assets/${id}`, { method: "PUT", body: payload });
}

export function deleteAsset(id: string): Promise<void> {
  return request<void>(`/assets/${id}`, { method: "DELETE" });
}

// --- Correção e estorno de lançamentos -----------------------------------

/** Estorna o lançamento original e grava um novo com os valores corrigidos. */
export function correctTransaction(transactionId: string, payload: TransactionCreate): Promise<TransactionRead> {
  return request<TransactionRead>(`/transactions/${transactionId}/correct`, { method: "POST", body: payload });
}

/** Marca o lançamento como revertido. Nada é apagado. */
export function reverseTransaction(transactionId: string): Promise<TransactionRead> {
  return request<TransactionRead>(`/transactions/${transactionId}/reverse`, { method: "POST" });
}

/** O backend está de pé? (`/health` não lê o banco de dados.) */
export function getHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/health");
}
