/** Configuration d'affichage des statuts, sévérités, catégories et actions. */

import type {
  AnomalyCategory,
  AnomalySeverity,
  AuditAction,
  InvoiceStatus,
  UserRole,
} from "@/types";

export const STATUS_ORDER: InvoiceStatus[] = [
  "Déposée",
  "En cours d'analyse",
  "À vérifier",
  "Validée",
  "Vendor Bill créée",
  "Rejetée",
  "Erreur système",
];

export const STATUS_STYLES: Record<InvoiceStatus, string> = {
  "Déposée": "bg-slate-100 text-slate-700 ring-slate-300",
  "En cours d'analyse": "bg-blue-50 text-blue-700 ring-blue-300",
  "À vérifier": "bg-amber-50 text-amber-700 ring-amber-300",
  "Validée": "bg-emerald-50 text-emerald-700 ring-emerald-300",
  "Vendor Bill créée": "bg-teal-50 text-teal-700 ring-teal-300",
  "Rejetée": "bg-rose-50 text-rose-700 ring-rose-300",
  "Erreur système": "bg-red-50 text-red-700 ring-red-300",
};

export const SEVERITY_STYLES: Record<AnomalySeverity, string> = {
  info: "bg-sky-50 text-sky-700 ring-sky-300",
  warning: "bg-amber-50 text-amber-700 ring-amber-300",
  critical: "bg-red-50 text-red-700 ring-red-300",
};

export const CATEGORY_LABELS: Record<AnomalyCategory, string> = {
  montant: "Montant",
  tva: "TVA",
  quantite: "Quantité",
  produit_absent: "Produit absent",
  doublon: "Doublon",
  fournisseur: "Fournisseur",
  bon_commande: "Bon de commande",
  autre: "Autre",
};

export const ACTION_LABELS: Record<AuditAction, string> = {
  validation: "Validation",
  correction: "Correction",
  rejet: "Rejet",
  vendor_bill_créée: "Vendor Bill",
};

export const ROLE_LABELS: Record<UserRole, string> = {
  Administrateur: "Administrateur",
  Comptable: "Comptable",
  Acheteur: "Acheteur",
};

export const SORT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "created_at_desc", label: "Dépôt : plus récent" },
  { value: "created_at_asc", label: "Dépôt : plus ancien" },
  { value: "issue_date_desc", label: "Date d'émission : récente" },
  { value: "issue_date_asc", label: "Date d'émission : ancienne" },
];
