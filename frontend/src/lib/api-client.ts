/**
 * Client API typé de SmartInvoice.
 *
 * Gère l'authentification Bearer, le rafraîchissement transparent de l'access
 * token (rotation du refresh token) et la normalisation des erreurs
 * (`ApiError`). Toutes les fonctions renvoient les types définis dans
 * `src/types`.
 */

import { API_BASE_URL } from "@/lib/config";
import { ApiError, extractDetail } from "@/lib/errors";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "@/lib/tokens";
import type {
  Anomaly,
  AnomalyListResponse,
  AuditLog,
  DashboardSummary,
  Invoice,
  InvoiceCorrectionPayload,
  InvoiceFilters,
  InvoiceListResponse,
  MatchingResult,
  OcrResult,
  OcrTask,
  PurchaseOrderSyncResult,
  SupplierSyncResult,
  TokenPair,
  User,
  UserCreatePayload,
  UserUpdatePayload,
} from "@/types";

type JsonHeaders = Record<string, string>;

function buildUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

async function parseResponse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/** Tente de rafraîchir la session avec le refresh token (rotation). */
export async function tryRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  try {
    const response = await fetch(buildUrl("/api/auth/refresh"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) {
      clearTokens();
      return false;
    }
    const data = (await response.json()) as TokenPair;
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    clearTokens();
    return false;
  }
}

/**
 * POST de Formulaire avec suivi de la progression d'envoi (barre de charge).
 * Utilise XMLHttpRequest car `fetch` n'expose pas le progrès d'upload.
 */
function requestWithProgress<T>(
  path: string,
  body: FormData,
  onProgress?: (percent: number) => void,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const accessToken = getAccessToken();
    let retried = false;

    xhr.open("POST", buildUrl(path));
    if (accessToken) xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);
    xhr.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = async () => {
      if (xhr.status === 401 && !retried && (await tryRefresh())) {
        retried = true;
        const nextToken = getAccessToken();
        if (nextToken) xhr.setRequestHeader("Authorization", `Bearer ${nextToken}`);
        xhr.send(body);
        return;
      }
      const raw = typeof xhr.response === "string" ? xhr.response : "";
      let data: unknown = null;
      if (raw) {
        try {
          data = JSON.parse(raw);
        } catch {
          data = raw;
        }
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data as T);
      } else {
        reject(new ApiError(xhr.status, extractDetail(data)));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Erreur réseau pendant l'envoi du fichier."));
    xhr.onabort = () => reject(new ApiError(0, "Envoi annulé."));

    xhr.send(body);
  });
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  retried = false,
): Promise<T> {
  const { headers, body, ...rest } = init;
  const finalHeaders: JsonHeaders = {
    ...(headers as JsonHeaders),
  };
  if (!(body instanceof FormData)) {
    finalHeaders["Content-Type"] ??= "application/json";
  }
  const accessToken = getAccessToken();
  if (accessToken) {
    finalHeaders["Authorization"] = `Bearer ${accessToken}`;
  }

  const response = await fetch(buildUrl(path), {
    ...rest,
    headers: finalHeaders,
    body,
  });

  // Expiration de l'access token : on rafraîchit puis on réessaie une fois.
  if (response.status === 401 && !retried && (await tryRefresh())) {
    return request<T>(path, init, true);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  const data = await parseResponse(response);
  if (!response.ok) {
    throw new ApiError(response.status, extractDetail(data));
  }
  return data as T;
}

function serializeFilters(filters: InvoiceFilters): string {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.supplier_id !== undefined) {
    params.set("supplier_id", String(filters.supplier_id));
  }
  if (filters.issue_date_from) params.set("issue_date_from", filters.issue_date_from);
  if (filters.issue_date_to) params.set("issue_date_to", filters.issue_date_to);
  params.set("sort", filters.sort ?? "created_at_desc");
  return params.toString();
}

export const api = {
  // --- Authentification ----------------------------------------------------
  async login(username: string, password: string): Promise<TokenPair> {
    return request<TokenPair>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username, password }),
    });
  },

  async logout(refreshToken: string): Promise<void> {
    try {
      await request<void>("/api/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch {
      // Déconnexion locale de toute façon.
    }
  },

  async me(): Promise<User> {
    return request<User>("/api/auth/me");
  },

  // --- Factures --------------------------------------------------------------
  async listInvoices(
    filters: InvoiceFilters,
    limit: number,
    offset: number,
  ): Promise<InvoiceListResponse> {
    const query = serializeFilters(filters);
    return request<InvoiceListResponse>(
      `/api/invoices?${query}&limit=${limit}&offset=${offset}`,
    );
  },

  async getInvoice(id: number): Promise<Invoice> {
    return request<Invoice>(`/api/invoices/${id}`);
  },

  async depositInvoice(
    form: FormData,
    onProgress?: (percent: number) => void,
  ): Promise<Invoice> {
    return requestWithProgress<Invoice>("/api/invoices", form, onProgress);
  },

  async processInvoice(id: number): Promise<OcrResult> {
    return request<OcrResult>(`/api/invoices/${id}/process`, { method: "POST" });
  },

  async matchInvoice(id: number): Promise<MatchingResult> {
    return request<MatchingResult>(`/api/invoices/${id}/match`, { method: "POST" });
  },

  async validateInvoice(id: number): Promise<Invoice> {
    return request<Invoice>(`/api/invoices/${id}/validate`, { method: "POST" });
  },

  async rejectInvoice(id: number, reason: string): Promise<Invoice> {
    return request<Invoice>(`/api/invoices/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  },

  async correctInvoice(
    id: number,
    payload: InvoiceCorrectionPayload,
  ): Promise<Invoice> {
    return request<Invoice>(`/api/invoices/${id}/correct`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  async createVendorBill(id: number): Promise<Invoice> {
    return request<Invoice>(`/api/invoices/${id}/vendor-bill`, { method: "POST" });
  },

  async auditLogs(id: number): Promise<AuditLog[]> {
    return request<AuditLog[]>(`/api/invoices/${id}/audit-logs`);
  },

  async summary(): Promise<DashboardSummary> {
    return request<DashboardSummary>("/api/invoices/summary");
  },

  /** Télécharge le fichier source avec authentification et retourne un blob. */
  async fetchFile(id: number): Promise<{ blob: Blob; contentType: string | null }> {
    const headers: JsonHeaders = {};
    const accessToken = getAccessToken();
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
    const response = await fetch(buildUrl(`/api/invoices/${id}/file`), { headers });
    if (response.status === 401) {
      if (await tryRefresh()) {
        return api.fetchFile(id);
      }
      throw new ApiError(401, "Session expirée.");
    }
    if (!response.ok) {
      throw new ApiError(response.status, extractDetail(await parseResponse(response)));
    }
    return { blob: await response.blob(), contentType: response.headers.get("content-type") };
  },

  // --- Utilisateurs ----------------------------------------------------------
  async listUsers(
    active?: boolean,
    limit = 50,
    offset = 0,
  ): Promise<User[]> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (active !== undefined) params.set("active", String(active));
    return request<User[]>(`/api/users?${params.toString()}`);
  },

  async createUser(payload: UserCreatePayload): Promise<User> {
    return request<User>("/api/users", { method: "POST", body: JSON.stringify(payload) });
  },

  async updateUser(id: number, payload: UserUpdatePayload): Promise<User> {
    return request<User>(`/api/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async deactivateUser(id: number): Promise<User> {
    return request<User>(`/api/users/${id}/deactivate`, { method: "POST" });
  },

  // --- Anomalies --------------------------------------------------------------
  async listAnomalies(
    filters: { resolved?: boolean; severity?: string; category?: string; invoice_id?: number },
    limit: number,
    offset: number,
  ): Promise<AnomalyListResponse> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (filters.resolved !== undefined) params.set("resolved", String(filters.resolved));
    if (filters.severity) params.set("severity", filters.severity);
    if (filters.category) params.set("category", filters.category);
    if (filters.invoice_id !== undefined) params.set("invoice_id", String(filters.invoice_id));
    return request<AnomalyListResponse>(`/api/anomalies?${params.toString()}`);
  },

  async resolveAnomaly(id: number): Promise<Anomaly> {
    return request<Anomaly>(`/api/anomalies/${id}/resolve`, { method: "POST" });
  },

  async resolveInvoiceAnomaly(invoiceId: number, anomalyId: number): Promise<Anomaly> {
    return request<Anomaly>(`/api/invoices/${invoiceId}/anomalies/${anomalyId}/resolve`, {
      method: "POST",
    });
  },

  // --- Synchronisation Odoo ---------------------------------------------------
  async syncSuppliers(name: string): Promise<SupplierSyncResult> {
    return request<SupplierSyncResult>("/api/odoo/sync/suppliers", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  },

  async syncPurchaseOrders(reference: string): Promise<PurchaseOrderSyncResult> {
    return request<PurchaseOrderSyncResult>("/api/odoo/sync/purchase-orders", {
      method: "POST",
      body: JSON.stringify({ reference }),
    });
  },

  // --- Tâches / ré-analyse ------------------------------------------------------
  async retryInvoice(id: number): Promise<OcrTask> {
    return request<OcrTask>(`/api/invoices/${id}/retry`, { method: "POST" });
  },

  async getTask(id: number): Promise<OcrTask> {
    return request<OcrTask>(`/api/tasks/${id}`);
  },
};
