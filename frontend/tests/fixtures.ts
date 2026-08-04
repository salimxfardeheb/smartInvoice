/** Fixtures TypeScript pour les tests des composants. */

import type {
  AuditLog,
  Anomaly,
  DashboardSummary,
  Invoice,
  MatchingResult,
  OcrExtractedData,
  PendingAnomaly,
  User,
} from "@/types";

export function makeInvoice(overrides: Partial<Invoice> = {}): Invoice {
  return {
    id: 1,
    invoice_number: "FAC-2026-001",
    supplier: { id: 42, name: "ACME SAS" },
    status: "À vérifier",
    issue_date: "2026-01-15",
    due_date: "2026-02-15",
    currency: "EUR",
    total_excl_tax: "100.00",
    tax_amount: "20.00",
    total_incl_tax: "120.00",
    discount: "0.00",
    shipping_fees: "5.00",
    ocr_confidence_score: 0.92,
    matching_score: 0.75,
    vendor_bill_id: null,
    file_info: {
      original_filename: "facture.pdf",
      content_type: "application/pdf",
      size: 2048,
    },
    extracted_data: makeExtractedData(),
    rejection_reason: null,
    error_message: null,
    is_duplicate: false,
    created_at: "2026-01-10T09:00:00",
    updated_at: "2026-01-10T09:00:00",
    ...overrides,
  };
}

export function makeExtractedData(): OcrExtractedData {
  return {
    general: {
      supplier_name: "ACME SAS",
      supplier_address: "12 rue de la Paix, Paris",
      invoice_number: "FAC-2026-001",
      issue_date: "2026-01-15",
      due_date: "2026-02-15",
      currency: "EUR",
      purchase_order_reference: "BC-2026-010",
      supplier_reference: null,
    },
    financial: {
      total_excl_tax: "100.00",
      tax_amount: "20.00",
      total_incl_tax: "120.00",
      discount: "0.00",
      shipping_fees: "5.00",
    },
    lines: [
      {
        line_number: 1,
        description: "Câble HDMI 2m",
        product_ref: "CBL-001",
        quantity: "10",
        unit: "u",
        unit_price: "9.00",
        tax_rate: "20",
        discount: "0.00",
        amount: "90.00",
      },
    ],
  };
}

export function makeMatchingResult(overrides: Partial<MatchingResult> = {}): MatchingResult {
  return {
    invoice_id: 1,
    purchase_order_reference: "BC-2026-010",
    supplier_match: true,
    duplicate_found: false,
    score: 0.85,
    lines: [
      {
        line_number: 1,
        description: "Câble HDMI 2m",
        product_ref: "CBL-001",
        quantity: "10",
        unit_price: "9.00",
        purchase_order_line_odoo_id: 501,
        quantity_matched: true,
        unit_price_matched: false,
        quantity_delta: 0,
        unit_price_delta: 0.05,
      },
    ],
    anomalies: [
      {
        category: "quantite",
        severity: "warning",
        message: "Quantité différente du bon de commande.",
        expected_value: "10",
        actual_value: "8",
      },
    ],
    ...overrides,
  };
}

export function makeAuditLogs(): AuditLog[] {
  return [
    {
      id: 2,
      invoice_id: 1,
      action: "validation",
      message: "Facture validée par le comptable.",
      details: null,
      user: { id: 3, username: "comptable", full_name: "Camille Dupont" },
      created_at: "2026-01-16T10:00:00",
    },
    {
      id: 1,
      invoice_id: 1,
      action: "correction",
      message: "Données corrigées.",
      details: { currency: { from: "USD", to: "EUR" } },
      user: { id: 3, username: "comptable", full_name: null },
      created_at: "2026-01-16T09:30:00",
    },
  ];
}

export function makePendingAnomaly(overrides: Partial<PendingAnomaly> = {}): PendingAnomaly {
  return {
    id: 1,
    invoice_id: 1,
    invoice_number: "FAC-2026-001",
    supplier_name: "ACME SAS",
    category: "quantite",
    severity: "warning",
    message: "Quantité différente du bon de commande.",
    expected_value: "10",
    actual_value: "8",
    created_at: "2026-01-16T09:00:00",
    ...overrides,
  };
}

export function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 1,
    username: "salim",
    email: "salim@smartinvoice.io",
    full_name: "Salim Admin",
    role: "Administrateur",
    is_active: true,
    created_at: "2026-01-01T08:00:00",
    updated_at: "2026-01-01T08:00:00",
    ...overrides,
  };
}

export function makeAnomaly(overrides: Partial<Anomaly> = {}): Anomaly {
  return {
    id: 1,
    invoice_id: 1,
    invoice_number: "FAC-2026-001",
    supplier_name: "ACME SAS",
    category: "quantite",
    severity: "warning",
    message: "Quantité différente du bon de commande.",
    expected_value: "10",
    actual_value: "8",
    resolved: false,
    resolved_at: null,
    created_at: "2026-01-16T09:00:00",
    ...overrides,
  };
}

export function makeSummary(): DashboardSummary {
  return {
    by_status: {
      "Déposée": 3,
      "En cours d'analyse": 1,
      "À vérifier": 2,
      "Validée": 5,
      "Vendor Bill créée": 2,
      "Rejetée": 1,
      "Erreur système": 0,
    },
    pending_anomalies: [makePendingAnomaly()],
  };
}
