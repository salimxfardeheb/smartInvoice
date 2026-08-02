"use client";

import type { InvoiceFilters, InvoiceStatus, SortMode, SupplierBrief } from "@/types";
import { SORT_OPTIONS, STATUS_ORDER } from "@/lib/status";
import { Select } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

export interface InvoiceFiltersProps {
  filters: InvoiceFilters;
  suppliers: SupplierBrief[];
  onChange: (filters: InvoiceFilters) => void;
}

const STATUS_OPTIONS = [
  { value: "", label: "Tous les statuts" },
  ...STATUS_ORDER.map((status) => ({ value: status, label: status })),
];

const SUPPLIER_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Tous les fournisseurs" },
];

/** Barre de filtres de la liste des factures (statut, fournisseur, date, tri). */
export function InvoiceFilters({ filters, suppliers, onChange }: InvoiceFiltersProps) {
  const supplierOptions = [
    ...SUPPLIER_OPTIONS,
    ...suppliers.map((supplier) => ({ value: String(supplier.id), label: supplier.name })),
  ];

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Select
          label="Statut"
          aria-label="Filtrer par statut"
          value={filters.status ?? ""}
          options={STATUS_OPTIONS}
          onChange={(event) =>
            onChange({ ...filters, status: (event.target.value || undefined) as InvoiceStatus | undefined })
          }
        />
        <Select
          label="Fournisseur"
          aria-label="Filtrer par fournisseur"
          value={filters.supplier_id !== undefined ? String(filters.supplier_id) : ""}
          options={supplierOptions}
          onChange={(event) =>
            onChange({
              ...filters,
              supplier_id: event.target.value ? Number(event.target.value) : undefined,
            })
          }
        />
        <Select
          label="Tri"
          aria-label="Trier les factures"
          value={filters.sort ?? "created_at_desc"}
          options={SORT_OPTIONS}
          onChange={(event) =>
            onChange({ ...filters, sort: event.target.value as SortMode })
          }
        />
        <div className="space-y-2">
          <div>
            <label htmlFor="issue-date-from" className="mb-1 block text-xs font-medium text-slate-700">
              Émise à partir de
            </label>
            <input
              id="issue-date-from"
              type="date"
              value={filters.issue_date_from ?? ""}
              onChange={(event) =>
                onChange({ ...filters, issue_date_from: event.target.value || undefined })
              }
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
            />
          </div>
          <div>
            <label htmlFor="issue-date-to" className="mb-1 block text-xs font-medium text-slate-700">
              Émise jusqu'à
            </label>
            <input
              id="issue-date-to"
              type="date"
              value={filters.issue_date_to ?? ""}
              onChange={(event) =>
                onChange({ ...filters, issue_date_to: event.target.value || undefined })
              }
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
            />
          </div>
        </div>
        <div className="flex items-end">
          <Button
            variant="secondary"
            onClick={() => onChange({})}
            className="w-full"
            aria-label="Réinitialiser les filtres"
          >
            Réinitialiser
          </Button>
        </div>
      </div>
    </div>
  );
}
