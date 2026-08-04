/**
 * Types TypeScript alignés sur les schémas Pydantic de l'API SmartInvoice.
 * Les montants décimaux sont exposés par l'API sous forme de chaînes.
 */

export type InvoiceStatus =
  | "Déposée"
  | "En cours d'analyse"
  | "À vérifier"
  | "Validée"
  | "Vendor Bill créée"
  | "Rejetée"
  | "Erreur système";

export type UserRole = "Comptable" | "Acheteur" | "Administrateur";

export type AnomalyCategory =
  | "montant"
  | "tva"
  | "quantite"
  | "produit_absent"
  | "doublon"
  | "fournisseur"
  | "bon_commande"
  | "autre";

export type AnomalySeverity = "info" | "warning" | "critical";

export type AuditAction = "validation" | "correction" | "rejet" | "vendor_bill_créée";

export type SortMode =
  | "created_at_desc"
  | "created_at_asc"
  | "issue_date_desc"
  | "issue_date_asc";

export interface SupplierBrief {
  id: number;
  name: string;
}

export interface InvoiceFileInfo {
  original_filename: string;
  content_type: string;
  size: number;
}

export interface Invoice {
  id: number;
  invoice_number: string;
  supplier: SupplierBrief;
  status: InvoiceStatus;
  issue_date: string | null;
  due_date: string | null;
  currency: string;
  total_excl_tax: string | null;
  tax_amount: string | null;
  total_incl_tax: string | null;
  discount: string | null;
  shipping_fees: string | null;
  ocr_confidence_score: number | null;
  matching_score: number | null;
  vendor_bill_id: number | null;
  file_info: InvoiceFileInfo | null;
  extracted_data: OcrExtractedData | null;
  rejection_reason: string | null;
  error_message: string | null;
  is_duplicate: boolean;
  created_at: string;
  updated_at: string;
}

export interface InvoiceListResponse {
  items: Invoice[];
  total: number;
}

export interface InvoiceLine {
  line_number: number;
  description: string;
  product_ref: string | null;
  quantity: string | null;
  unit: string | null;
  unit_price: string | null;
  tax_rate: string | null;
  discount: string | null;
  amount: string | null;
}

export interface OcrExtractedData {
  general?: {
    supplier_name?: string | null;
    supplier_address?: string | null;
    invoice_number?: string | null;
    issue_date?: string | null;
    due_date?: string | null;
    currency?: string | null;
    purchase_order_reference?: string | null;
    supplier_reference?: string | null;
  } | null;
  financial?: {
    total_excl_tax?: string | null;
    tax_amount?: string | null;
    total_incl_tax?: string | null;
    discount?: string | null;
    shipping_fees?: string | null;
  } | null;
  lines?: InvoiceLine[];
}

export interface OcrResult {
  invoice_id: number;
  status: InvoiceStatus;
  ocr_confidence_score: number | null;
  error_message: string | null;
  extracted_data: OcrExtractedData | null;
}

export interface MatchingLine {
  line_number: number;
  description: string;
  product_ref: string | null;
  quantity: string | null;
  unit_price: string | null;
  purchase_order_line_odoo_id: number | null;
  quantity_matched: boolean;
  unit_price_matched: boolean;
  quantity_delta: number | null;
  unit_price_delta: number | null;
}

export interface MatchingAnomaly {
  category: AnomalyCategory;
  severity: AnomalySeverity;
  message: string;
  expected_value: string | null;
  actual_value: string | null;
}

export interface MatchingResult {
  invoice_id: number;
  purchase_order_reference: string | null;
  supplier_match: boolean;
  duplicate_found: boolean;
  score: number;
  lines: MatchingLine[];
  anomalies: MatchingAnomaly[];
}

export interface AuditUserBrief {
  id: number;
  username: string;
  full_name: string | null;
}

export interface AuditLog {
  id: number;
  invoice_id: number;
  action: AuditAction;
  message: string;
  details: Record<string, unknown> | null;
  user: AuditUserBrief | null;
  created_at: string;
}

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface PendingAnomaly {
  id: number;
  invoice_id: number;
  invoice_number: string;
  supplier_name: string | null;
  category: AnomalyCategory;
  severity: AnomalySeverity;
  message: string;
  expected_value: string | null;
  actual_value: string | null;
  created_at: string;
}

export interface DashboardSummary {
  by_status: Record<InvoiceStatus, number>;
  pending_anomalies: PendingAnomaly[];
}

/** Anomalie complète renvoyée par l'API (avec état de résolution). */
export interface Anomaly {
  id: number;
  invoice_id: number;
  invoice_number: string;
  supplier_name: string | null;
  category: AnomalyCategory;
  severity: AnomalySeverity;
  message: string;
  expected_value: string | null;
  actual_value: string | null;
  resolved: boolean;
  resolved_at: string | null;
  created_at: string;
}

export interface AnomalyListResponse {
  items: Anomaly[];
  total: number;
}

/** Filtres de la liste des anomalies. */
export interface AnomalyFilters {
  resolved?: boolean;
  severity?: AnomalySeverity;
  category?: AnomalyCategory;
  invoice_id?: number;
}

/** Corps de création d'un utilisateur (POST /api/users). */
export interface UserCreatePayload {
  username: string;
  email: string;
  password: string;
  full_name?: string;
  role?: UserRole;
}

/** Corps de mise à jour d'un utilisateur (PATCH /api/users/{id}). */
export interface UserUpdatePayload {
  full_name?: string;
  email?: string;
  role?: UserRole;
  is_active?: boolean;
}

/** Fournisseur du catalogue (lecture). */
export interface SupplierRead {
  id: number;
  odoo_id: number | null;
  name: string;
  vat: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  is_active: boolean;
}

/** Bon de commande du catalogue (lecture). */
export interface PurchaseOrderRead {
  id: number;
  odoo_id: number | null;
  reference: string;
  supplier_id: number | null;
  state: string | null;
  currency: string | null;
  date_order: string | null;
  total_amount: string | null;
  supplier: SupplierRead | null;
}

/** Résultat de la synchronisation d'un fournisseur. */
export interface SupplierSyncResult {
  synced: boolean;
  supplier: SupplierRead;
}

/** Résultat de la synchronisation d'un bon de commande. */
export interface PurchaseOrderSyncResult {
  synced: boolean;
  purchase_order: PurchaseOrderRead;
}

export type TaskState = "en attente" | "en cours" | "réussi" | "échoué";

/** Tâche asynchrone (OCR / ré-analyse) renvoyée par /api/tasks. */
export interface OcrTask {
  id: number;
  kind: string;
  state: TaskState;
  invoice_id: number | null;
  error_message: string | null;
  result: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

/** Filtres de la liste des factures (sous-ensemble de l'API). */
export interface InvoiceFilters {
  status?: InvoiceStatus;
  supplier_id?: number;
  issue_date_from?: string;
  issue_date_to?: string;
  sort?: SortMode;
}

/** Corps de la correction manuelle (PUT /correct). */
export interface InvoiceCorrectionPayload {
  invoice_number?: string | null;
  issue_date?: string | null;
  due_date?: string | null;
  currency?: string | null;
  total_excl_tax?: string | null;
  tax_amount?: string | null;
  total_incl_tax?: string | null;
  discount?: string | null;
  shipping_fees?: string | null;
  lines?: InvoiceLineCorrectionPayload[];
}

export interface InvoiceLineCorrectionPayload {
  line_number: number;
  description: string;
  product_ref?: string | null;
  quantity?: string | null;
  unit?: string | null;
  unit_price?: string | null;
  tax_rate?: string | null;
  discount?: string | null;
  amount?: string | null;
}
